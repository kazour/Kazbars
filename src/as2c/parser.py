"""Parser — a port of mtasc's parser.ml (a camlp4 stream parser) as recursive descent.

Faithfully reproduces its quirks because they change the emitted bytecode: binary operators
are re-associated by `make_binop` (comparisons, `&&`, `||` and assignments are *right*
associative; `%` binds tighter than `*`/`/`; `&`, `|`, `^` share one level), prefix operators
and `instanceof` rebind into the leftmost leaf, semicolons are optional everywhere, and only
assignments / calls / `++` / `--` / ternaries may stand as statements (`check_val`).
"""

from __future__ import annotations

import os

from . import ast
from .ast import (
    EArray,
    EArrayDecl,
    EBinop,
    EBlock,
    EBreak,
    ECall,
    EClass,
    EConst,
    EContinue,
    EField,
    EFor,
    EForIn,
    EFunction,
    EIf,
    EImport,
    EInterface,
    ELambda,
    ENew,
    EObjDecl,
    EParenthesis,
    EQuestion,
    EReturn,
    ESwitch,
    ETry,
    EUnop,
    EVal,
    EVars,
    EWhile,
    EWith,
    Func,
    Ident,
    Pos,
    String,
    punion,
)
from .lexer import Lexer, Token, s_token


class ParseError(Exception):
    def __init__(self, msg: str, pos: Pos):
        self.msg = msg
        self.pos = pos
        super().__init__(msg)


# -- operator priorities (parser.ml) -----------------------------------------------------------

def priority(op) -> int:
    if op == 'OpAssign' or isinstance(op, tuple):
        return -4
    if op == 'OpBoolOr':
        return -3
    if op == 'OpBoolAnd':
        return -2
    if op in ('OpEq', 'OpNotEq', 'OpGt', 'OpLt', 'OpGte', 'OpLte', 'OpPhysEq', 'OpPhysNotEq'):
        return -1
    if op in ('OpOr', 'OpAnd', 'OpXor'):
        return 0
    if op in ('OpShl', 'OpShr', 'OpUShr'):
        return 1
    if op in ('OpAdd', 'OpSub'):
        return 2
    if op in ('OpMult', 'OpDiv'):
        return 3
    if op == 'OpMod':
        return 4
    raise ValueError(op)


def is_not_assign(op) -> bool:
    return not (op == 'OpAssign' or isinstance(op, tuple))


def can_swap(_op, op) -> bool:
    p1, p2 = priority(_op), priority(op)
    if p1 < p2:
        return True
    return p1 == p2 and p1 >= 0  # numerical ops are left-associative


def make_binop(op, e, e2):
    if isinstance(e2, EBinop) and can_swap(e2.op, op) and (is_not_assign(e2.op) or is_not_assign(op)):
        _e = make_binop(op, e, e2.a)
        return EBinop(e2.op, _e, e2.b, punion(_e.pos, e2.b.pos))
    if isinstance(e2, EQuestion) and is_not_assign(op):
        _e = make_binop(op, e, e2.cond)
        return EQuestion(_e, e2.a, e2.b, punion(e.pos, e2.b.pos))
    return EBinop(op, e, e2, punion(e.pos, e2.pos))


def make_unop(op, e, p1):
    if isinstance(e, EBinop):
        return EBinop(e.op, make_unop(op, e.a, p1), e.b, punion(p1, e.pos))
    if isinstance(e, EQuestion):
        _e = make_unop(op, e.cond, p1)
        return EQuestion(_e, e.a, e.b, punion(p1, e.b.pos))
    return EUnop(op, 'Prefix', e, punion(p1, e.pos))


def wrap_var(e):
    if isinstance(e, EVars):
        return EBlock([e], e.pos)
    return e


class _Fail(Exception):
    """Internal: a grammar alternative did not match (mtasc's Stream.Failure)."""


class Parser:
    def __init__(self, src: str, file: str, warning=None):
        self.lexer = Lexer(src, file)
        self.file = file
        self.toks: list[Token] = []
        self.comments: list[tuple[str, Pos]] = []
        self.prev_comment: list[str | None] = []  # comment right before each token
        self.i = 0
        self.warning = warning or (lambda msg, pos: None)
        self._tokenize()

    def _tokenize(self) -> None:
        last_comment = None
        while True:
            t = self.lexer.token()
            if t.kind in ('Comment', 'CommentLine'):
                last_comment = t.value
                self.comments.append((t.value, t.pos))
                continue
            self.toks.append(t)
            self.prev_comment.append(last_comment)
            last_comment = None
            if t.kind == 'Eof':
                break

    # -- token access -------------------------------------------------------------------------
    @property
    def tok(self) -> Token:
        return self.toks[self.i]

    def peek(self, k: int = 1) -> Token:
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def advance(self) -> Token:
        t = self.toks[self.i]
        if t.kind != 'Eof':
            self.i += 1
        return t

    def unexpected(self) -> ParseError:
        t = self.tok
        return ParseError('Unexpected ' + s_token(t), t.pos)

    def accept(self, kind: str, value=None) -> Token | None:
        t = self.tok
        if t.kind == kind and (value is None or t.value == value):
            return self.advance()
        return None

    def expect(self, kind: str, value=None) -> Token:
        t = self.accept(kind, value)
        if t is None:
            raise self.unexpected()
        return t

    def accept_kwd(self, kw: str) -> Token | None:
        return self.accept('Kwd', kw)

    def expect_kwd(self, kw: str) -> Token:
        return self.expect('Kwd', kw)

    def accept_ident(self) -> Token | None:
        t = self.tok
        if t.kind == 'Const' and isinstance(t.value, Ident):
            return self.advance()
        return None

    def expect_ident(self) -> Token:
        t = self.accept_ident()
        if t is None:
            raise self.unexpected()
        return t

    # -- file level ---------------------------------------------------------------------------
    def parse_code(self) -> list:
        out = []
        while True:
            t = self.tok
            if t.kind == 'Eof':
                return out
            if t.kind == 'Next':
                self.advance()
                continue
            out.append(self.parse_signature())

    def parse_signature(self):
        t = self.tok
        if t.kind == 'BkOpen':
            self.advance()
            self.parse_metadata()
            return self.parse_signature()
        if t.kind == 'Kwd' and t.value == 'import':
            self.advance()
            pkg, name = self.parse_import()
            return EImport(pkg, name, t.pos)
        if t.kind == 'Kwd' and t.value == 'interface':
            self.advance()
            path = self.parse_class_path()
            herits = self.parse_herits()
            p = self.expect('BrOpen').pos
            el, p2 = self.parse_class(True)
            return EInterface(path, herits, EBlock(el, punion(p, p2)), punion(t.pos, p2))
        if t.kind == 'Sharp':
            self.parse_include()
            return self.parse_signature()
        flags = self.parse_class_flags()
        if not self.tok.is_kwd('class'):
            raise self.unexpected()
        p = self.advance().pos
        path = self.parse_class_path()
        herits = self.parse_herits()
        op = self.expect('BrOpen').pos
        el, p2 = self.parse_class('HIntrinsic' in flags)
        return EClass(path, flags + herits, EBlock(el, punion(op, p2)), punion(p, p2))

    def parse_herits(self) -> list:
        if self.accept_kwd('extends'):
            p = self.parse_class_path()
            return [('HExtends', p), *self.parse_herits()]
        if self.accept_kwd('implements'):
            p = self.parse_class_path()
            return [('HImplements', p), *self.parse_other_implements()]
        return []

    def parse_other_implements(self) -> list:
        if self.accept('Sep'):
            p = self.parse_class_path()
            return [('HImplements', p), *self.parse_other_implements()]
        return self.parse_herits()

    def parse_class_flags(self) -> list:
        if self.accept_kwd('intrinsic'):
            return ['HIntrinsic', *self.parse_class_flags()]
        if self.accept_kwd('dynamic'):
            return ['HDynamic', *self.parse_class_flags()]
        return []

    def parse_class(self, interf: bool) -> tuple[list, Pos]:
        out = []
        while True:
            t = self.tok
            if t.kind == 'BrClose':
                self.advance()
                return out, t.pos
            if t.kind == 'Next':
                self.advance()
                continue
            if t.kind == 'BkOpen':
                self.advance()
                self.parse_metadata()
                continue
            if t.kind == 'Sharp':
                self.parse_include()
                continue
            flags = self.parse_field_flags()
            out.append(self.parse_class_field(flags, interf))

    def parse_field_flags(self) -> tuple[str, str]:
        stat, pub = 'IsMember', None
        while True:
            t = self.tok
            if t.is_kwd('static') and stat == 'IsMember':
                self.advance()
                stat = 'IsStatic'
            elif t.is_kwd('public') and pub is None:
                self.advance()
                pub = 'IsPublic'
            elif t.is_kwd('private') and pub is None:
                self.advance()
                pub = 'IsPrivate'
            else:
                return stat, pub or 'IsPublic'

    def parse_class_field(self, flags: tuple[str, str], interf: bool):
        stat, pub = flags
        t = self.tok
        if t.is_kwd('var'):
            self.advance()
            vl, p2 = self.parse_vars(t.pos)
            return EVars(stat, pub, vl, punion(t.pos, p2))
        if t.is_kwd('function'):
            self.advance()
            name, g = self.parse_fun_name()
            self.expect('POpen')
            args, p2 = self.parse_args()
            typ = self.parse_type_option()
            fexpr = None if interf else self.parse_expr()
            f = Func(name, args, typ, stat, pub, g, fexpr)
            return EFunction(f, punion(t.pos, p2))
        raise self.unexpected()

    def parse_fun_name(self) -> tuple[str, str]:
        t = self.tok
        if t.kind == 'Kwd' and os.path.basename(t.pos.file) == 'TopLevel.as':
            self.advance()
            return t.value, 'Normal'
        name = self.expect_ident().value.s
        if name in ('get', 'set'):
            t2 = self.accept_ident()
            if t2 is not None:
                return t2.value.s, 'Getter' if name == 'get' else 'Setter'
        return name, 'Normal'

    # -- statements ---------------------------------------------------------------------------
    def parse_expr(self):
        t = self.tok
        k = t.kind
        if k == 'BrOpen':
            self.advance()
            el, p2 = self.parse_block(t.pos)
            return EBlock(el, punion(t.pos, p2))
        if k == 'Kwd':
            kw = t.value
            if kw == 'for':
                self.advance()
                self.expect('POpen')
                c = self.parse_expr_opt()
                return self.parse_for(t.pos, c)
            if kw == 'if':
                self.advance()
                cond = self.parse_eval()
                e = self.parse_expr_opt()
                e2, p2 = self.parse_else(e.pos)
                return EIf(cond, wrap_var(e), e2, punion(t.pos, p2))
            if kw == 'return':
                self.advance()
                v, p2 = self.parse_eval_option(t.pos)
                return EReturn(v, punion(t.pos, p2))
            if kw == 'break':
                self.advance()
                return EBreak(t.pos)
            if kw == 'continue':
                self.advance()
                return EContinue(t.pos)
            if kw == 'while':
                self.advance()
                v = self.parse_eval()
                e = self.parse_expr_opt()
                return EWhile(v, wrap_var(e), 'NormalWhile', punion(t.pos, e.pos))
            if kw == 'do':
                self.advance()
                e = self.parse_expr()
                self.expect_kwd('while')
                v = self.parse_eval()
                return EWhile(v, wrap_var(e), 'DoWhile', punion(t.pos, v.pos))
            if kw == 'switch':
                self.advance()
                v = self.parse_eval()
                self.expect('BrOpen')
                el, p2 = self.parse_switch(False)
                return ESwitch(v, el, punion(t.pos, p2))
            if kw == 'var':
                self.advance()
                vl, p2 = self.parse_vars(t.pos)
                return EVars('IsMember', 'IsPublic', vl, punion(t.pos, p2))
            if kw == 'try':
                self.advance()
                e = self.parse_expr()
                c = self.parse_catches()
                f = self.parse_finally()
                return ETry(wrap_var(e), c, f, punion(t.pos, e.pos))
            if kw == 'with':
                self.advance()
                v = self.parse_eval()
                e = self.parse_expr()
                return EWith(v, wrap_var(e), punion(t.pos, e.pos))
        if k == 'Sharp':
            self.parse_include()
            return self.parse_expr()
        e = self.parse_eval()
        return EVal(e, e.pos)

    def parse_expr_opt(self):
        try:
            return self.parse_expr()
        except _Fail:
            t = self.expect('Next')
            return EBlock([], t.pos)

    def parse_else(self, p: Pos):
        while True:
            if self.accept('Next'):
                continue
            if self.accept_kwd('else'):
                e = self.parse_expr()
                return wrap_var(e), e.pos
            return None, p

    def parse_for(self, p: Pos, c):
        if self.accept_kwd('in'):
            v = self.parse_eval()
            p2 = self.expect('PClose').pos
            e = self.parse_expr_opt()
            return EForIn(c, v, wrap_var(e), punion(p, p2))
        cl = self.parse_for_conds()
        l1 = self.parse_eval_list()
        l2 = self.parse_eval_list()
        p2 = self.expect('PClose').pos
        e = self.parse_expr_opt()
        return EFor([c, *cl], l1, l2, wrap_var(e), punion(p, p2))

    def parse_for_conds(self) -> list:
        if self.accept('Sep'):
            e = self.parse_expr()
            return [e, *self.parse_for_conds()]
        self.accept('Next')
        return []

    def parse_switch(self, has_default: bool) -> tuple[list, Pos]:
        cases = []
        while True:
            t = self.tok
            if t.kind == 'BrClose':
                self.advance()
                return cases, t.pos
            if t.is_kwd('case'):
                self.advance()
                v = self.parse_eval()
                self.expect('DblDot')
                c = self.parse_switch_clause()
                cases.append((v, EBlock(c, t.pos)))
                continue
            if t.is_kwd('default'):
                self.advance()
                self.expect('DblDot')
                c = self.parse_switch_clause()
                if has_default:
                    raise ParseError('Duplicate default', t.pos)
                has_default = True
                cases.append((None, EBlock(c, t.pos)))
                continue
            raise self.unexpected()

    def parse_switch_clause(self) -> list:
        out = []
        while True:
            if self.accept('Next'):
                continue
            try:
                out.append(self.parse_expr())
            except _Fail:
                return out

    def parse_block(self, sp: Pos) -> tuple[list, Pos]:
        out = []
        while True:
            t = self.tok
            if t.kind == 'Next':
                self.advance()
                continue
            if t.kind == 'BrClose':
                self.advance()
                return out, t.pos
            if t.kind == 'Eof':
                raise ParseError('Unclosed parenthesis', sp)
            try:
                out.append(self.parse_expr())
            except _Fail:
                raise self.unexpected() from None

    def parse_catches(self) -> list:
        out = []
        while self.tok.is_kwd('catch'):
            self.advance()
            self.expect('POpen')
            name = self.expect_ident().value.s
            typ = self.parse_type_option()
            self.expect('PClose')
            e = self.parse_expr()
            out.append((name, typ, e))
        return out

    def parse_finally(self):
        if self.accept_kwd('finally'):
            return self.parse_expr()
        return None

    def parse_vars(self, p: Pos) -> tuple[list, Pos]:
        out = []
        while True:
            t = self.accept_ident()
            if t is None:
                return out, p
            typ = self.parse_type_option()
            init = self.parse_var_init()
            out.append((t.value.s, typ, init))
            p = t.pos
            if not self.accept('Sep'):
                return out, p

    def parse_var_init(self):
        if self.tok.kind == 'Binop' and self.tok.value == 'OpAssign':
            self.advance()
            return self.parse_eval()
        return None

    def parse_args(self) -> tuple[list, Pos]:
        out = []
        t = self.tok
        if t.kind == 'PClose':
            self.advance()
            return out, t.pos
        while True:
            name = self.expect_ident().value.s
            typ = self.parse_type_option()
            out.append((name, typ))
            if self.accept('Sep'):
                continue
            p = self.expect('PClose').pos
            return out, p

    def parse_type_option(self):
        if self.accept('DblDot'):
            return self.parse_class_path()
        return None

    def parse_class_path(self) -> tuple:
        t = self.tok
        if t.kind == 'Const' and isinstance(t.value, Ident):
            if t.value.s == 'Array' and self.prev_comment[self.i] is not None:
                self.advance()
                return (('#' + self.prev_comment[self.i - 1],), 'Array')
            self.advance()
            return self.parse_class_path2(t.value.s)
        raise self.unexpected()

    def parse_class_path2(self, name: str) -> tuple:
        if self.accept('Dot'):
            p, n = self.parse_class_path()
            return ((name, *p), n)
        return ((), name)

    def parse_import(self) -> tuple[tuple, str | None]:
        t = self.tok
        if t.kind == 'Const' and isinstance(t.value, Ident):
            self.advance()
            return self.parse_import2(t.value.s)
        if t.kind == 'Binop' and t.value == 'OpMult':
            self.advance()
            return (), None
        raise self.unexpected()

    def parse_import2(self, name: str) -> tuple[tuple, str | None]:
        if self.accept('Dot'):
            p, n = self.parse_import()
            return (name, *p), n
        return (), name

    def parse_metadata(self) -> None:
        while True:
            t = self.advance()
            if t.kind == 'BkClose':
                return
            if t.kind == 'Eof':
                raise self.unexpected()

    def parse_include(self) -> None:
        p1 = self.expect('Sharp').pos
        t = self.tok
        if not (t.is_ident('include')):
            raise self.unexpected()
        self.advance()
        s = self.tok
        if not (s.kind == 'Const' and isinstance(s.value, String)):
            raise self.unexpected()
        self.advance()
        if not s.value.s.endswith('ComponentVersion.as'):
            self.warning('unsupported #include', punion(p1, s.pos))

    # -- value expressions --------------------------------------------------------------------
    def parse_eval_option(self, p: Pos):
        try:
            v = self.parse_eval()
            return v, v.pos
        except _Fail:
            return None, p

    def parse_eval_list(self) -> list:
        try:
            v = self.parse_eval()
        except _Fail:
            self.accept('Next')
            return []
        out = [v]
        while True:
            if self.accept('Sep'):
                out.append(self.parse_eval())
                continue
            self.accept('Next')
            return out

    def parse_eval(self):
        t = self.tok
        k = t.kind
        if k == 'Kwd':
            kw = t.value
            if kw == 'function':
                self.advance()
                self.expect('POpen')
                args, _ = self.parse_args()
                typ = self.parse_type_option()
                e = self.parse_expr()
                f = Func('', args, typ, 'IsStatic', 'IsPublic', 'Normal', e)
                return self.parse_eval_next(ELambda(f, punion(t.pos, e.pos)))
            if kw in ('throw', 'delete', 'typeof'):
                self.advance()
                return self.parse_delete(EConst(Ident(kw), t.pos))
            if kw == 'new':
                self.advance()
                v = self.parse_eval()
                if isinstance(v, ECall):
                    return self.parse_eval_next(ENew(v.e, v.args, punion(t.pos, v.pos)))
                return self.parse_eval_next(ENew(v, [], punion(t.pos, v.pos)))
            if kw == 'this':
                self.advance()
                return self.parse_eval_next(EConst(Ident('this'), t.pos))
            raise _Fail()
        if k == 'Const':
            self.advance()
            return self.parse_eval_next(EConst(t.value, t.pos))
        if k == 'POpen':
            self.advance()
            e = self.parse_eval()
            p2 = self.expect('PClose').pos
            return self.parse_eval_next(EParenthesis(e, punion(t.pos, p2)))
        if k == 'BrOpen':
            self.advance()
            el, p2 = self.parse_field_list()
            return self.parse_eval_next(EObjDecl(el, punion(t.pos, p2)))
        if k == 'BkOpen':
            self.advance()
            el, p2 = self.parse_array()
            return self.parse_eval_next(EArrayDecl(el, punion(t.pos, p2)))
        if k == 'Unop':
            self.advance()
            e = self.parse_eval()
            return make_unop(t.value, e, t.pos)
        if k == 'Binop' and t.value == 'OpSub':
            self.advance()
            e = self.parse_eval()
            return make_unop('Neg', e, t.pos)
        if k == 'Sharp':
            self.parse_include()
            return self.parse_eval_next(EObjDecl([], ast.NULL_POS))
        raise _Fail()

    def parse_eval_next(self, e):
        t = self.tok
        k = t.kind
        if k == 'BkOpen':
            self.advance()
            e2 = self.parse_eval()
            p2 = self.expect('BkClose').pos
            return self.parse_eval_next(EArray(e, e2, punion(e.pos, p2)))
        if k == 'Binop':
            self.advance()
            e2 = self.parse_eval()
            return make_binop(t.value, e, e2)
        if k == 'Kwd' and t.value == 'and':
            self.advance()
            e2 = self.parse_eval()
            return make_binop('OpBoolAnd', e, e2)
        if k == 'Dot':
            self.advance()
            f = self.expect_ident()
            return self.parse_eval_next(EField(e, f.value.s, punion(e.pos, f.pos)))
        if k == 'POpen':
            self.advance()
            args = self.parse_eval_list()
            p2 = self.expect('PClose').pos
            return self.parse_eval_next(ECall(e, args, punion(e.pos, p2)))
        if k == 'Unop' and ast.is_postfix(e, t.value):
            self.advance()
            return self.parse_eval_next(EUnop(t.value, 'Postfix', e, punion(e.pos, t.pos)))
        if k == 'Question':
            self.advance()
            v1 = self.parse_eval()
            self.expect('DblDot')
            v2 = self.parse_eval()
            return self.parse_eval_next(EQuestion(e, v1, v2, punion(e.pos, v2.pos)))
        if k == 'Kwd' and t.value == 'instanceof':
            self.advance()
            v = self.parse_eval()

            def iof(v2):
                return ECall(EConst(Ident('instanceof'), t.pos), [e, v2], punion(e.pos, v2.pos))

            def loop(v2):
                if isinstance(v2, EBinop):
                    return EBinop(v2.op, loop(v2.a), v2.b, punion(t.pos, v2.pos))
                if isinstance(v2, EQuestion):
                    return EQuestion(loop(v2.cond), v2.a, v2.b, punion(t.pos, v2.pos))
                return iof(v2)

            return self.parse_eval_next(loop(v))
        return e

    def parse_delete(self, v):
        try:
            e = self.parse_eval()
        except _Fail:
            return self.parse_eval_next(v)

        def loop(x):
            if isinstance(x, EBinop):
                return EBinop(x.op, loop(x.a), x.b, punion(e.pos, v.pos))
            return ECall(v, [x], punion(x.pos, v.pos))

        return self.parse_eval_next(loop(e))

    def parse_field_list(self) -> tuple[list, Pos]:
        out = []
        t = self.tok
        if t.kind == 'BrClose':
            self.advance()
            return out, t.pos
        while True:
            name = self.expect_ident().value.s
            self.expect('DblDot')
            out.append((name, self.parse_eval()))
            if self.accept('Sep'):
                continue
            p = self.expect('BrClose').pos
            return out, p

    def parse_array(self) -> tuple[list, Pos]:
        out = []
        t = self.tok
        if t.kind == 'BkClose':
            self.advance()
            return out, t.pos
        while True:
            out.append(self.parse_eval())
            if self.accept('Sep'):
                continue
            p = self.expect('BkClose').pos
            return out, p


def parse(src: str, file: str, warning=None, on_lexer=None) -> tuple[list, Lexer]:
    """Parse a whole file → (signatures, lexer). `on_lexer(lexer)` is called before any token
    is read, so error reporting can map offsets to lines even when parsing fails."""
    lexer = Lexer(src, file)
    if on_lexer is not None:
        on_lexer(lexer)
    p = Parser.__new__(Parser)
    p.lexer = lexer
    p.file = file
    p.toks = []
    p.comments = []
    p.prev_comment = []
    p.i = 0
    p.warning = warning or (lambda msg, pos: None)
    p._tokenize()
    try:
        sigs = p.parse_code()
    except _Fail:
        raise p.unexpected() from None
    return sigs, p.lexer
