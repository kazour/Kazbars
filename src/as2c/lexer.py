"""Lexer — a port of mtasc's lexer.mll.

Works on the file's *bytes* (decoded as latin-1, one char per byte) so positions are byte
offsets like OCaml's and string literals pass through untouched; the code generator decides
what the bytes mean. Comments are returned as tokens (the parser needs the last one to spot
typed-array annotations) and filtered by the token stream.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ast import Float, Ident, Int, Pos, String

# `add` is removed from this set at startup by mtasc's main (Hashtbl.remove Lexer.keywords "add").
KEYWORDS = frozenset({
    'function', 'class', 'static', 'var', 'if', 'else', 'while', 'do', 'for', 'break', 'return',
    'continue', 'interface', 'extends', 'implements', 'import', 'switch', 'case', 'default',
    'intrinsic', 'dynamic', 'public', 'private', 'try', 'catch', 'finally', 'with', 'in',
    'instanceof', 'new', 'this', 'throw', 'typeof', 'delete', 'void',
    'and', 'or', 'eq', 'ne', 'not', 'le', 'lt', 'ge', 'gt', 'ifFrameLoaded', 'on',
    'onClipEvent', 'tellTarget',
})

# token kinds: 'Eof' 'Const' 'Kwd' 'Comment' 'CommentLine' 'Binop' 'Unop' 'Next' 'Sep'
# 'BrOpen' 'BrClose' 'BkOpen' 'BkClose' 'POpen' 'PClose' 'Dot' 'DblDot' 'Question' 'Sharp'

OPERATORS: list[tuple[str, str, object]] = [
    ('>>>=', 'Binop', ('OpAssignOp', 'OpUShr')),
    ('<<=', 'Binop', ('OpAssignOp', 'OpShl')),
    ('>>=', 'Binop', ('OpAssignOp', 'OpShr')),
    ('>>>', 'Binop', 'OpUShr'),
    ('===', 'Binop', 'OpPhysEq'),
    ('!==', 'Binop', 'OpPhysNotEq'),
    ('++', 'Unop', 'Increment'),
    ('--', 'Unop', 'Decrement'),
    ('%=', 'Binop', ('OpAssignOp', 'OpMod')),
    ('&=', 'Binop', ('OpAssignOp', 'OpAnd')),
    ('|=', 'Binop', ('OpAssignOp', 'OpOr')),
    ('^=', 'Binop', ('OpAssignOp', 'OpXor')),
    ('+=', 'Binop', ('OpAssignOp', 'OpAdd')),
    ('-=', 'Binop', ('OpAssignOp', 'OpSub')),
    ('*=', 'Binop', ('OpAssignOp', 'OpMult')),
    ('/=', 'Binop', ('OpAssignOp', 'OpDiv')),
    ('==', 'Binop', 'OpEq'),
    ('!=', 'Binop', 'OpNotEq'),
    ('<=', 'Binop', 'OpLte'),
    ('>=', 'Binop', 'OpGte'),
    ('&&', 'Binop', 'OpBoolAnd'),
    ('||', 'Binop', 'OpBoolOr'),
    ('<<', 'Binop', 'OpShl'),
    ('>>', 'Binop', 'OpShr'),
    ('~', 'Unop', 'NegBits'),
    ('!', 'Unop', 'Not'),
    ('<', 'Binop', 'OpLt'),
    ('>', 'Binop', 'OpGt'),
    (';', 'Next', None),
    (':', 'DblDot', None),
    (',', 'Sep', None),
    ('.', 'Dot', None),
    ('%', 'Binop', 'OpMod'),
    ('&', 'Binop', 'OpAnd'),
    ('|', 'Binop', 'OpOr'),
    ('^', 'Binop', 'OpXor'),
    ('+', 'Binop', 'OpAdd'),
    ('*', 'Binop', 'OpMult'),
    ('/', 'Binop', 'OpDiv'),
    ('-', 'Binop', 'OpSub'),
    ('=', 'Binop', 'OpAssign'),
    ('[', 'BkOpen', None),
    (']', 'BkClose', None),
    ('{', 'BrOpen', None),
    ('}', 'BrClose', None),
    ('(', 'POpen', None),
    (')', 'PClose', None),
    ('?', 'Question', None),
    ('#', 'Sharp', None),
]


class LexError(Exception):
    def __init__(self, msg: str, pos: Pos):
        self.msg = msg
        self.pos = pos
        super().__init__(msg)


@dataclass
class Token:
    kind: str
    value: object
    pos: Pos

    def is_kwd(self, *kws: str) -> bool:
        return self.kind == 'Kwd' and self.value in kws

    def is_ident(self, *names: str) -> bool:
        return self.kind == 'Const' and isinstance(self.value, Ident) and (not names or self.value.s in names)


def s_token(t: Token) -> str:
    """mtasc's rendering of a token in "Unexpected ..." messages."""
    k = t.kind
    if k == 'Eof':
        return '<end of file>'
    if k == 'Const':
        c = t.value
        if isinstance(c, String):
            return '"' + c.s.replace('\n', '\\n').replace('\t', '\\t').replace('\r', '\\r') + '"'
        return c.s
    if k == 'Kwd':
        return t.value
    if k == 'Comment':
        return '/*' + t.value + '*/'
    if k == 'CommentLine':
        return '//' + t.value
    if k == 'Binop':
        from .ast import s_binop
        return s_binop(t.value)
    if k == 'Unop':
        from .ast import UNOP_SYMBOLS
        return UNOP_SYMBOLS[t.value]
    return {'Next': ';', 'Sep': ',', 'BkOpen': '[', 'BkClose': ']', 'BrOpen': '{', 'BrClose': '}',
            'POpen': '(', 'PClose': ')', 'Dot': '.', 'DblDot': ':', 'Question': '?', 'Sharp': '#'}[k]


def _is_ident_start(c: str) -> bool:
    return c == '_' or c == '$' or 'a' <= c <= 'z' or 'A' <= c <= 'Z'


def _is_ident_part(c: str) -> bool:
    return _is_ident_start(c) or '0' <= c <= '9'


def _is_digit(c: str) -> bool:
    return '0' <= c <= '9'


def _is_hex(c: str) -> bool:
    return _is_digit(c) or 'a' <= c <= 'f' or 'A' <= c <= 'F'


class Lexer:
    """Tokenizes one file; also remembers line starts for error positions."""

    def __init__(self, src: str, file: str):
        self.src = src
        self.file = file
        self.i = 0
        self.n = len(src)
        # offsets of the first character of every line after the first (mtasc's `lines`)
        self.lines: list[int] = []

    def error(self, msg: str, at: int) -> LexError:
        return LexError(msg, Pos(self.file, at, at))

    def invalid_char(self, c: str, at: int) -> LexError:
        o = ord(c)
        if 32 < o < 128:
            return self.error(f"Invalid character '{c}'", at)
        return self.error(f'Invalid character 0x{o:02X}', at)

    def token(self) -> Token:
        src, n = self.src, self.n
        while True:
            i = self.i
            if i >= n:
                return Token('Eof', None, Pos(self.file, i, i))
            c = src[i]
            if i == 0 and src.startswith('\xef\xbb\xbf'):
                self.i = 3
                continue
            if c == ' ' or c == '\t':
                self.i += 1
                continue
            if c == '\r' and i + 1 < n and src[i + 1] == '\n':
                self.i += 2
                self.lines.append(self.i)
                continue
            if c == '\n' or c == '\r':
                self.i += 1
                self.lines.append(self.i)
                continue
            break
        start = self.i
        c = src[start]
        if c == '0' and start + 1 < n and src[start + 1] == 'x' and start + 2 < n and _is_hex(src[start + 2]):
            i = start + 2
            while i < n and _is_hex(src[i]):
                i += 1
            self.i = i
            return Token('Const', Int(src[start:i]), Pos(self.file, start, i))
        if _is_digit(c) or (c == '.' and start + 1 < n and _is_digit(src[start + 1])):
            return self._number(start)
        if c == '/' and start + 1 < n and src[start + 1] == '/':
            i = start + 2
            while i < n and src[i] not in '\n\r':
                i += 1
            self.i = i
            return Token('CommentLine', src[start + 2:i], Pos(self.file, start, i))
        if c == '/' and start + 1 < n and src[start + 1] == '*':
            return self._comment(start)
        if c == '"' or c == "'":
            return self._string(start, c)
        if _is_ident_start(c):
            i = start + 1
            while i < n and _is_ident_part(src[i]):
                i += 1
            self.i = i
            word = src[start:i]
            if word in KEYWORDS:
                return Token('Kwd', word, Pos(self.file, start, i))
            return Token('Const', Ident(word), Pos(self.file, start, i))
        for text, kind, value in OPERATORS:
            if src.startswith(text, start):
                self.i = start + len(text)
                return Token(kind, value, Pos(self.file, start, self.i))
        raise self.invalid_char(c, start)

    def _number(self, start: int) -> Token:
        src, n = self.src, self.n
        i = start
        while i < n and _is_digit(src[i]):
            i += 1
        is_float = False
        if i < n and src[i] == '.':
            # ocamllex longest match: "digits '.' digits*" beats a plain int when a '.' follows
            is_float = True
            i += 1
            while i < n and _is_digit(src[i]):
                i += 1
        # ocamllex: only literals that start with a digit may carry an exponent
        if i < n and src[i] in 'eE' and _is_digit(src[start]):
            j = i + 1
            if j < n and src[j] in '+-':
                j += 1
            if j < n and _is_digit(src[j]):
                is_float = True
                i = j
                while i < n and _is_digit(src[i]):
                    i += 1
        self.i = i
        text = src[start:i]
        if is_float:
            return Token('Const', Float(text), Pos(self.file, start, i))
        return Token('Const', Int(text), Pos(self.file, start, i))

    def _comment(self, start: int) -> Token:
        src, n = self.src, self.n
        i = start + 2
        while True:
            if i >= n:
                raise self.error('Unclosed comment', start)
            if src.startswith('*/', i):
                self.i = i + 2
                return Token('Comment', src[start + 2:i], Pos(self.file, start, self.i))
            if src[i] == '\r' and i + 1 < n and src[i + 1] == '\n':
                i += 2
                self.lines.append(i)
                continue
            if src[i] in '\n\r':
                i += 1
                self.lines.append(i)
                continue
            i += 1

    def _string(self, start: int, quote: str) -> Token:
        src, n = self.src, self.n
        i = start + 1
        while True:
            if i >= n:
                raise self.error('Unterminated string', start)
            c = src[i]
            if c == '\\':
                # mtasc stores escapes raw; a backslash swallows the next char unless it is a
                # line break (which the newline rule must still count)
                i += 1
                if i < n and src[i] not in '\r\n':
                    i += 1
                continue
            if c == quote:
                self.i = i + 1
                return Token('Const', String(src[start + 1:i]), Pos(self.file, start, self.i))
            if c == '\r' and i + 1 < n and src[i + 1] == '\n':
                i += 2
                self.lines.append(i)
                continue
            if c in '\n\r':
                i += 1
                self.lines.append(i)
                continue
            i += 1


def read_source(path) -> str:
    """One char per byte; CRLF becomes LF (mtasc opens sources in text mode), so a raw line
    break inside a string literal is a single \n whatever the checkout's line endings."""
    with open(path, 'rb') as f:
        return f.read().replace(b'\r\n', b'\n').decode('latin-1')


class LineTable:
    """Maps byte offsets to (line, column) the way mtasc's Lexer.find_line does.

    Keeps a live reference to the lexer's line list, so a table registered before parsing
    still knows every line break seen up to a lexing/parsing error."""

    def __init__(self, lines: list[int]):
        self.lines = lines

    def find(self, p: int) -> tuple[int, int]:
        n, delta = 1, 0
        for lp in sorted(self.lines):
            if lp > p:
                break
            n += 1
            delta = lp
        return n, p - delta
