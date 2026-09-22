"""Syntax tree — a port of mtasc's expr.ml.

Value expressions (`Eval`) and statements (`Expr`) are separate families, as in the original.
The typer rewrites value nodes in place (`set_eval`), exactly like mtasc's `Obj.set_field`
trick, so the code generator sees `this.x`, `Cls.x`, `_global.x`, casts and resolved static
paths without a second tree.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pos:
    file: str
    pmin: int
    pmax: int


NULL_POS = Pos('<null>', -1, -1)
ARGV_POS = Pos('<argv>', -1, -1)


def punion(p: Pos, p2: Pos) -> Pos:
    return Pos(p.file, min(p.pmin, p2.pmin), max(p.pmax, p2.pmax))


# ---------------------------------------------------------------------------------------------
# CONSTANTS, OPERATORS, FLAGS
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Int:
    s: str


@dataclass(frozen=True)
class Float:
    s: str


@dataclass(frozen=True)
class String:
    s: str  # raw source text between the quotes; escapes are processed at codegen


@dataclass(frozen=True)
class Ident:
    s: str


Constant = Int | Float | String | Ident

# binop names follow mtasc: 'OpAdd' 'OpMult' 'OpDiv' 'OpSub' 'OpAssign' 'OpEq' 'OpPhysEq'
# 'OpNotEq' 'OpPhysNotEq' 'OpGt' 'OpGte' 'OpLt' 'OpLte' 'OpAnd' 'OpOr' 'OpXor' 'OpBoolAnd'
# 'OpBoolOr' 'OpShl' 'OpShr' 'OpUShr' 'OpMod' and ('OpAssignOp', op).
Binop = str | tuple

BINOP_SYMBOLS = {
    'OpAdd': '+', 'OpMult': '*', 'OpDiv': '/', 'OpSub': '-', 'OpAssign': '=', 'OpEq': '==',
    'OpPhysEq': '===', 'OpNotEq': '!=', 'OpPhysNotEq': '!==', 'OpGte': '>=', 'OpLte': '<=',
    'OpGt': '>', 'OpLt': '<', 'OpAnd': '&', 'OpOr': '|', 'OpXor': '^', 'OpBoolAnd': '&&',
    'OpBoolOr': '||', 'OpShr': '>>', 'OpUShr': '>>>', 'OpShl': '<<', 'OpMod': '%',
}


def s_binop(op: Binop) -> str:
    if isinstance(op, tuple):
        return s_binop(op[1]) + '='
    return BINOP_SYMBOLS[op]


# unops: 'Increment' 'Decrement' 'Not' 'Neg' 'NegBits'; flags: 'Prefix' 'Postfix'
UNOP_SYMBOLS = {'Increment': '++', 'Decrement': '--', 'Not': '!', 'Neg': '-', 'NegBits': '~'}

# static_flag: 'IsMember' | 'IsStatic'; public_flag: 'IsPublic' | 'IsPrivate'
# getter_flag: 'Normal' | 'Getter' | 'Setter'; while_flag: 'NormalWhile' | 'DoWhile'

TypePath = tuple  # (tuple[str, ...] package, str name)


def s_type_path(p: TypePath) -> str:
    pkg, name = p
    return name if not pkg else '.'.join(pkg) + '.' + name


# ---------------------------------------------------------------------------------------------
# FUNCTIONS AND CLASS HERITAGE
# ---------------------------------------------------------------------------------------------

@dataclass(eq=False)
class Func:
    fname: str
    fargs: list  # [(name, TypePath | None)]
    ftype: TypePath | None
    fstatic: str
    fpublic: str
    fgetter: str
    fexpr: object  # Expr | None


# herit: ('HExtends', path) | ('HImplements', path) | 'HIntrinsic' | 'HDynamic'


# ---------------------------------------------------------------------------------------------
# VALUE EXPRESSIONS (eval)
# ---------------------------------------------------------------------------------------------

@dataclass(eq=False)
class EConst:
    c: Constant
    pos: Pos


@dataclass(eq=False)
class EArray:
    a: Eval
    b: Eval
    pos: Pos


@dataclass(eq=False)
class EBinop:
    op: Binop
    a: Eval
    b: Eval
    pos: Pos


@dataclass(eq=False)
class EField:
    e: Eval
    name: str
    pos: Pos


@dataclass(eq=False)
class EParenthesis:
    e: Eval
    pos: Pos


@dataclass(eq=False)
class EObjDecl:
    fields: list  # [(name, Eval)]
    pos: Pos


@dataclass(eq=False)
class EArrayDecl:
    items: list  # [Eval]
    pos: Pos


@dataclass(eq=False)
class ECall:
    e: Eval
    args: list
    pos: Pos


@dataclass(eq=False)
class ENew:
    e: Eval
    args: list
    pos: Pos


@dataclass(eq=False)
class EUnop:
    op: str
    flag: str
    e: Eval
    pos: Pos


@dataclass(eq=False)
class EQuestion:
    cond: Eval
    a: Eval
    b: Eval
    pos: Pos


@dataclass(eq=False)
class ELambda:
    f: Func
    pos: Pos


@dataclass(eq=False)
class EStatic:
    path: TypePath
    pos: Pos


@dataclass(eq=False)
class ECast:
    a: Eval
    b: Eval
    pos: Pos


Eval = (EConst | EArray | EBinop | EField | EParenthesis | EObjDecl | EArrayDecl | ECall | ENew
        | EUnop | EQuestion | ELambda | EStatic | ECast)


def set_eval(e, v) -> None:
    """Rewrite `e` in place to be `v` (keeping e's identity, as mtasc's set_eval does)."""
    e.__class__ = v.__class__
    e.__dict__ = dict(v.__dict__)


# ---------------------------------------------------------------------------------------------
# STATEMENTS (expr)
# ---------------------------------------------------------------------------------------------

@dataclass(eq=False)
class EVars:
    static: str
    public: str
    vl: list  # [(name, TypePath | None, Eval | None)]
    pos: Pos


@dataclass(eq=False)
class EFunction:
    f: Func
    pos: Pos


@dataclass(eq=False)
class EBlock:
    el: list
    pos: Pos


@dataclass(eq=False)
class EFor:
    inits: list  # [Expr]
    conds: list  # [Eval]
    incrs: list  # [Eval]
    body: Expr
    pos: Pos


@dataclass(eq=False)
class EForIn:
    decl: Expr  # EVal(ident) or EVars with one declarator
    v: Eval
    body: Expr
    pos: Pos


@dataclass(eq=False)
class EIf:
    cond: Eval
    e: Expr
    eelse: Expr | None
    pos: Pos


@dataclass(eq=False)
class EWhile:
    cond: Eval
    body: Expr
    flag: str
    pos: Pos


@dataclass(eq=False)
class ESwitch:
    v: Eval
    cases: list  # [(Eval | None, Expr)]
    pos: Pos


@dataclass(eq=False)
class ETry:
    e: Expr
    catches: list  # [(name, TypePath | None, Expr)] — the typer rewrites the type to the resolved path
    fo: Expr | None
    pos: Pos


@dataclass(eq=False)
class EWith:
    v: Eval
    e: Expr
    pos: Pos


@dataclass(eq=False)
class EReturn:
    v: Eval | None
    pos: Pos


@dataclass(eq=False)
class EBreak:
    pos: Pos


@dataclass(eq=False)
class EContinue:
    pos: Pos


@dataclass(eq=False)
class EVal:
    v: Eval
    pos: Pos


Expr = (EVars | EFunction | EBlock | EFor | EForIn | EIf | EWhile | ESwitch | ETry | EWith | EReturn
        | EBreak | EContinue | EVal)


# ---------------------------------------------------------------------------------------------
# FILE-LEVEL SIGNATURES
# ---------------------------------------------------------------------------------------------

@dataclass(eq=False)
class EClass:
    path: TypePath
    herits: list
    e: Expr  # EBlock of EVars / EFunction
    pos: Pos


@dataclass(eq=False)
class EInterface:
    path: TypePath
    herits: list
    e: Expr
    pos: Pos


@dataclass(eq=False)
class EImport:
    pkg: tuple  # package segments
    name: str | None  # None = wildcard
    pos: Pos


Signature = EClass | EInterface | EImport


# ---------------------------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------------------------

def is_postfix(e: Eval, op: str) -> bool:
    if op in ('Increment', 'Decrement'):
        return isinstance(e, (EConst, EField, EStatic, EArray))
    return False


def is_prefix(op: str) -> bool:
    return True


class InvalidExpression(Exception):
    def __init__(self, pos: Pos):
        self.pos = pos
        super().__init__('Invalid Expression')


def check_val(v: Eval) -> None:
    """Only assignments, calls, ++/-- and ternaries may stand as statements."""
    if isinstance(v, EBinop) and (v.op == 'OpAssign' or isinstance(v.op, tuple)):
        return
    if isinstance(v, ECall) or isinstance(v, EQuestion):
        return
    if isinstance(v, EUnop) and v.op in ('Increment', 'Decrement'):
        return
    if isinstance(v, EParenthesis):
        check_val(v.e)
        return
    raise InvalidExpression(v.pos)


def check_expr(e: Expr) -> None:
    if isinstance(e, EVars):
        return
    if isinstance(e, EFunction):
        if e.f.fexpr is not None:
            check_expr(e.f.fexpr)
    elif isinstance(e, EBlock):
        for x in e.el:
            check_expr(x)
    elif isinstance(e, EFor):
        for x in e.inits:
            check_expr(x)
        check_expr(e.body)
    elif isinstance(e, EForIn):
        check_expr(e.body)
    elif isinstance(e, EIf):
        check_expr(e.e)
        if e.eelse is not None:
            check_expr(e.eelse)
    elif isinstance(e, EWhile):
        check_expr(e.body)
    elif isinstance(e, ESwitch):
        for _, body in e.cases:
            check_expr(body)
    elif isinstance(e, ETry):
        check_expr(e.e)
        for _, _, body in e.catches:
            check_expr(body)
        if e.fo is not None:
            check_expr(e.fo)
    elif isinstance(e, EWith):
        check_expr(e.e)
    elif isinstance(e, EVal):
        check_val(e.v)


def check_sign(s: Signature) -> None:
    if isinstance(s, (EClass, EInterface)):
        check_expr(s.e)
