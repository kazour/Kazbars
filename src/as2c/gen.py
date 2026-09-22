"""AVM1 code generation — a port of mtasc's genSwf.ml (the `-version 8` paths).

Stack-depth accounting is reproduced exactly because it decides where `Pop`s are emitted;
push coalescing and jump targets follow mtasc's `opt_push` rules through the assembler's
label mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import asm, avm1
from .asm import Code, Label
from .ast import (
    NULL_POS,
    EArray,
    EArrayDecl,
    EBinop,
    EBlock,
    EBreak,
    ECall,
    ECast,
    EConst,
    EContinue,
    EField,
    EFor,
    EForIn,
    EFunction,
    EIf,
    ELambda,
    ENew,
    EObjDecl,
    EParenthesis,
    EQuestion,
    EReturn,
    EStatic,
    ESwitch,
    ETry,
    EUnop,
    EVal,
    EVars,
    EWhile,
    EWith,
    Float,
    Ident,
    Int,
    Pos,
    String,
    s_type_path,
)
from .avm1 import Bool, Double, Null, Reg, Undefined
from .avm1 import Int as PInt
from .classgen import GenClass
from .lexer import LexError
from .ocaml_hashtbl import Hashtbl
from .typer import TyperError

# ---------------------------------------------------------------------------------------------
# OPCODES (swflib names → codes)
# ---------------------------------------------------------------------------------------------

A = avm1.CODES
A_ADD, A_DIVIDE, A_SUBTRACT, A_MULTIPLY, A_MOD = A['Add2'], A['Divide'], A['Subtract'], A['Multiply'], A['Modulo']
A_STRINGADD, A_AND, A_OR, A_XOR = A['StringAdd'], A['BitAnd'], A['BitOr'], A['BitXor']
A_SHL, A_SHR, A_ASR = A['BitLShift'], A['BitRShift'], A['BitURShift']
A_COMPARE, A_GREATER, A_EVAL, A_NOT = A['Less2'], A['Greater'], A['GetVariable'], A['Not']
A_TOINT, A_TONUMBER, A_TOSTRING, A_SWAP = A['ToInteger'], A['ToNumber'], A['ToString'], A['StackSwap']
A_EQUAL, A_PHYSEQUAL, A_NEW, A_OBJECT = A['Equals2'], A['StrictEquals'], A['NewObject'], A['InitObject']
A_INITARRAY, A_SET, A_POP, A_DUP = A['InitArray'], A['SetVariable'], A['Pop'], A['PushDuplicate']
A_OBJGET, A_OBJSET, A_LOCALVAR, A_LOCALASSIGN = A['GetMember'], A['SetMember'], A['DefineLocal2'], A['DefineLocal']
A_RETURN, A_FSCOMMAND2, A_DELETEOBJ, A_INSTANCEOF = A['Return'], A['FSCommand2'], A['Delete'], A['InstanceOf']
A_CAST, A_EXTENDS, A_IMPLEMENTS, A_ENUM2 = A['CastOp'], A['Extends'], A['ImplementsOp'], A['Enumerate2']
A_TRACE, A_THROW, A_GETTIMER, A_INCREMENT = A['Trace'], A['Throw'], A['GetTime'], A['Increment']
A_DECREMENT, A_CHR, A_ORD, A_RANDOM = A['Decrement'], A['AsciiToChar'], A['CharToAscii'], A['RandomNumber']
A_DELETE, A_TYPEOF, A_TARGETPATH, A_OBJCALL = A['Delete2'], A['TypeOf'], A['TargetPath'], A['CallMethod']
A_CALL, A_NEWMETHOD, A_STOPSOUNDS = A['CallFunction'], A['NewMethod'], A['StopSounds']

STACK_DELTA = {
    A_ADD: -1, A_DIVIDE: -1, A_SUBTRACT: -1, A_MULTIPLY: -1, A_MOD: -1, A_STRINGADD: -1,
    A_AND: -1, A_OR: -1, A_XOR: -1, A_SHL: -1, A_SHR: -1, A_ASR: -1,
    A_COMPARE: -1, A_GREATER: -1,
    A_EVAL: 0, A_NOT: 0, A_TOINT: 0, A_TONUMBER: 0, A_TOSTRING: 0, A_SWAP: 0,
    A_EQUAL: -1, A_PHYSEQUAL: -1,
    A_NEW: -1, A_OBJECT: 0, A_INITARRAY: 0,
    A_SET: -2, A_POP: -1, A_DUP: 1,
    A_OBJGET: -1, A_OBJSET: -3, A_LOCALVAR: -1, A_LOCALASSIGN: -2, A_RETURN: -1,
    A_FSCOMMAND2: 0, A_DELETEOBJ: -1, A_INSTANCEOF: -1, A_CAST: -1,
    A_EXTENDS: -2, A_IMPLEMENTS: -2, A_ENUM2: -1, A_TRACE: -1, A_THROW: -1, A_GETTIMER: 1,
    A_INCREMENT: 0, A_DECREMENT: 0, A_CHR: 0, A_ORD: 0, A_RANDOM: 0, A_DELETE: 0, A_TYPEOF: 0,
    A_TARGETPATH: 0,
}

# swflib's action names, for mtasc's "Unknown stack delta" failure message
SWFLIB_NAMES = {0x09: 'STOPSOUNDS', 0x04: 'NEXTFRAME', 0x05: 'PREVFRAME', 0x06: 'PLAY', 0x07: 'STOP',
                0x08: 'TGLHIGHQULTY', 0x0A: 'ADDNUM', 0x0E: 'CMP', 0x0F: 'EQNUM', 0x10: 'LAND',
                0x11: 'LOR', 0x13: 'STREQ', 0x1C: 'EVAL', 0x1D: 'SET', 0x22: 'GETPROP', 0x23: 'SETPROP',
                0x24: 'DUPLICATEMC', 0x25: 'REMOVEMC', 0x27: 'STARTDRAG', 0x28: 'STOPDRAG',
                0x31: 'MBSTRLEN', 0x35: 'MBSTRSUB', 0x36: 'MBORD', 0x37: 'MBCHR', 0x3D: 'CALL',
                0x52: 'OBJCALL', 0x53: 'NEWMETHOD', 0x68: 'STRGT', 0x9E: 'CALLFRAME'}

# DefineFunction2 flags
THIS_REGISTER, ARGUMENTS_NOVAR, SUPER_REGISTER, SUPER_NOVAR = 0x01, 0x08, 0x10, 0x20

# ---------------------------------------------------------------------------------------------
# ACCESS KINDS
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class VarReg:
    reg: int


class VarStr:
    pass


class VarObj:
    pass


@dataclass(frozen=True)
class VarGetSet:
    name: str


VAR_STR = VarStr()
VAR_OBJ = VarObj()
VAR_NONE = VarReg(-1)  # true / false / null / undefined: nothing to fetch


class GenError(Exception):
    """A typer-style error raised at generation time (mtasc raises Typer.Error here)."""


def malformed(p: Pos):
    raise TyperError('Custom', 'Malformed expression', p)


@dataclass
class LocalCtx:
    reg: int
    sp: int


@dataclass
class Options:
    version: int = 8
    enable_main: bool = False
    ftrace: str | None = None


class MainCtx:
    """State shared across all classes of one compilation."""

    def __init__(self, options: Options):
        self.options = options
        self.main: tuple | None = None


class FuncFrame:
    """Per-function generator state (mtasc keeps it in the shared ctx and saves/restores)."""


class Gen:
    """Code generation for one action stream (one class). Ports mtasc's `context`."""

    def __init__(self, main: MainCtx, current: GenClass):
        self.main = main
        self.current = current
        self.code = Code()  # current emission target (a function body while inside one)
        self.locals: dict[str, LocalCtx] = {}
        self.stack = 0  # scope depth
        self.stack_size = 0  # values on the operand stack
        self.reg_count = 0
        self.cur_block = EBreak(NULL_POS)
        self.breaks: list = []  # pending break jumps (labels to place)
        self.continue_label: Label = asm.STREAM_START  # mtasc's continue_pos starts at action 0
        self.curmethod = ''
        self.forins = 0

    # -- primitive emission -------------------------------------------------------------------
    def write(self, code: int, **operands) -> None:
        if code not in STACK_DELTA:  # mtasc: failwith ("Unknown stack delta for " ^ name)
            raise Failure('Unknown stack delta for ' + SWFLIB_NAMES.get(code, f'0x{code:02X}'))
        self.code.op(code, **operands)
        self.stack_size += STACK_DELTA[code]

    def push(self, items: list) -> None:
        self.code.push(items)
        self.stack_size += len(items)

    def pop(self, n: int) -> None:
        for _ in range(n):
            self.write(A_POP)

    def cjmp(self) -> Label:
        """Emit a conditional forward jump; the returned label is placed where it should land."""
        lab = self.code.label()
        self.code.branch_if(lab)
        self.stack_size -= 1
        return lab

    def jmp(self) -> Label:
        lab = self.code.label()
        self.code.jump(lab)
        return lab

    def place(self, lab: Label) -> None:
        self.code.place(lab)

    def call(self, kind, n: int) -> None:
        if isinstance(kind, VarReg):
            self.push([Reg(kind.reg), Undefined()])
            op, n = A_OBJCALL, n + 2
        elif kind is VAR_STR:
            op, n = A_CALL, n + 1
        elif kind is VAR_OBJ:
            op, n = A_OBJCALL, n + 2
        else:
            raise AssertionError('call on a getter/setter')
        self.code.op(op)
        self.stack_size -= n

    def new_call(self, kind, n: int) -> None:
        if isinstance(kind, VarReg):
            self.push([Reg(kind.reg), Undefined()])
            op, n = A_NEWMETHOD, n + 2
        elif kind is VAR_STR:
            op, n = A_NEW, n + 1
        elif kind is VAR_OBJ:
            op, n = A_NEWMETHOD, n + 2
        else:
            raise AssertionError('new on a getter/setter')
        self.code.op(op)
        self.stack_size -= n

    def setvar(self, kind, retval: bool = False) -> None:
        if isinstance(kind, VarReg):
            if kind.reg == -1:
                raise AssertionError('assignment to a constant')
            self.code.op(avm1.STORE_REGISTER, reg=kind.reg)
            if not retval:
                self.write(A_POP)
        elif kind is VAR_STR or kind is VAR_OBJ:
            if retval:
                self.code.op(avm1.STORE_REGISTER, reg=0)
            self.write(A_SET if kind is VAR_STR else A_OBJSET)
            if retval:
                self.push([Reg(0)])
        else:
            self.push([PInt(1), Reg(2), '__set__' + kind.name])
            self.call(VAR_OBJ, 1)

    def getvar(self, kind) -> None:
        if isinstance(kind, VarReg):
            if kind.reg != -1:
                self.push([Reg(kind.reg)])
        elif kind is VAR_STR:
            self.write(A_EVAL)
        elif kind is VAR_OBJ:
            self.write(A_OBJGET)
        else:
            self.push([PInt(0), Reg(2), '__get__' + kind.name])
            self.call(VAR_OBJ, 0)

    # -- scopes -------------------------------------------------------------------------------
    def clean_stack(self, stack: int) -> None:
        for name in [n for n, l in self.locals.items() if l.sp > stack]:
            del self.locals[name]
        self.stack = stack

    def open_block(self, e):
        old_block = self.cur_block
        old_stack = self.stack
        start_size = self.stack_size
        self.stack += 1
        self.cur_block = e

        def close():
            self.clean_stack(old_stack)
            self.pop(self.stack_size - start_size)
            self.cur_block = old_block

        return close

    # -- names --------------------------------------------------------------------------------
    def generate_package(self, l, fast: bool = False):
        if fast and (not l or l[0] not in self.locals):
            if not l:
                return VAR_STR
            self.push([l[0]])
            self.write(A_EVAL)
            for p in l[1:]:
                self.push([p])
                self.write(A_OBJGET)
            return VAR_OBJ
        self.push(['_global'])
        self.write(A_EVAL)
        for p in l:
            self.push([p])
            self.write(A_OBJGET)
        return VAR_OBJ

    def generate_package_register(self, l) -> None:
        if not l:
            return
        if len(l) == 1:
            p = l[0]
            self.generate_package([p], fast=True)
            self.write(A_NOT)
            self.write(A_NOT)
            j = self.cjmp()
            self.push(['_global'])
            self.write(A_EVAL)
            self.push([p, PInt(0), 'Object'])
            self.write(A_NEW)
            self.write(A_OBJSET)
            self.place(j)
            return
        all_but_last, last = l[:-1], l[-1]
        self.generate_package_register(all_but_last)
        self.generate_package(l, fast=True)
        self.write(A_NOT)
        self.write(A_NOT)
        j = self.cjmp()
        self.push(['_global'])
        self.write(A_EVAL)
        for p in all_but_last:
            self.push([p])
            self.write(A_OBJGET)
        self.push([last, PInt(0), 'Object'])
        self.write(A_NEW)
        self.write(A_OBJSET)
        self.place(j)

    def generate_ident(self, s: str, p: Pos):
        if s == 'this':
            return VarReg(1)
        if s == 'undefined':
            self.push([Undefined()])
            return VAR_NONE
        if s == 'null':
            self.push([Null()])
            return VAR_NONE
        if s == 'true':
            self.push([Bool(True)])
            return VAR_NONE
        if s == 'false':
            self.push([Bool(False)])
            return VAR_NONE
        if s in ('_global', '_root', 'arguments'):
            self.push([s])
            return VAR_STR
        if s == 'super':
            raise AssertionError('bare super')
        l = self.locals.get(s)
        if l is not None:
            if l.reg == 0:
                self.push([s])
                return VAR_STR
            return VarReg(l.reg)
        self.push([s])
        return VAR_STR

    # -- constants ----------------------------------------------------------------------------
    def generate_constant(self, p: Pos, c) -> None:
        if isinstance(c, Int):
            v = ocaml_int32_of_string(c.s)
            if v is None:
                self.generate_constant(p, Float(c.s))
            else:
                self.push([PInt(v)])
        elif isinstance(c, Float):
            self.push([Double(ocaml_float_of_string(c.s, p))])
        elif isinstance(c, String):
            self.push([unescape_chars(c.s, p)])
        else:
            raise AssertionError('identifier constant')

    # -- access -------------------------------------------------------------------------------
    def generate_access(self, v, forcall: bool = False):
        if isinstance(v, EConst) and isinstance(v.c, Ident):
            if v.c.s == 'super':
                if forcall:
                    self.push([Reg(2)])
                    self.push([Undefined()])
                    return VAR_OBJ
                return VarReg(2)
            return self.generate_ident(v.c.s, v.pos)
        if isinstance(v, EField):
            if isinstance(v.e, EConst) and isinstance(v.e.c, Ident) and v.e.c.s == 'super' and self.current.is_getset(v.name):
                return VarGetSet(v.name)
            self.generate_val(v.e)
            self.push([v.name])
            return VAR_OBJ
        if isinstance(v, EStatic):
            pkg, s = v.path
            if pkg == ('__With',):
                self.push([s])
                return VAR_STR
            k = self.generate_package(list(pkg), fast=True)
            self.push([s])
            return k
        if isinstance(v, EArray):
            self.generate_val(v.a)
            self.generate_val(v.b)
            return VAR_OBJ
        if not forcall:
            malformed(v.pos)
        self.generate_val(v)
        self.push([Undefined()])
        return VAR_OBJ

    # -- operators ----------------------------------------------------------------------------
    def generate_binop(self, retval: bool, op, v1, v2) -> None:
        def gen(a: int):
            self.generate_val(v1)
            self.generate_val(v2)
            self.write(a)

        if op == 'OpAssign':
            k = self.generate_access(v1)
            self.generate_val(v2)
            self.setvar(k, retval)
        elif isinstance(op, tuple):
            k = self.generate_access(v1)
            self.generate_binop(True, op[1], v1, v2)
            self.setvar(k, retval)
        elif op == 'OpAdd':
            gen(A_ADD)
        elif op == 'OpMult':
            gen(A_MULTIPLY)
        elif op == 'OpDiv':
            gen(A_DIVIDE)
        elif op == 'OpSub':
            gen(A_SUBTRACT)
        elif op == 'OpEq':
            gen(A_EQUAL)
        elif op == 'OpPhysEq':
            gen(A_PHYSEQUAL)
        elif op == 'OpPhysNotEq':
            gen(A_PHYSEQUAL)
            self.write(A_NOT)
        elif op == 'OpNotEq':
            gen(A_EQUAL)
            self.write(A_NOT)
        elif op == 'OpGt':
            gen(A_GREATER)
        elif op == 'OpGte':
            gen(A_COMPARE)
            self.write(A_NOT)
        elif op == 'OpLt':
            gen(A_COMPARE)
        elif op == 'OpLte':
            gen(A_GREATER)
            self.write(A_NOT)
        elif op == 'OpAnd':
            gen(A_AND)
        elif op == 'OpOr':
            gen(A_OR)
        elif op == 'OpXor':
            gen(A_XOR)
        elif op == 'OpBoolAnd':
            self.generate_val(v1)
            self.write(A_DUP)
            self.write(A_NOT)
            jump_end = self.cjmp()
            self.write(A_POP)
            self.generate_val(v2)
            self.place(jump_end)
        elif op == 'OpBoolOr':
            self.generate_val(v1)
            self.write(A_DUP)
            jump_end = self.cjmp()
            self.write(A_POP)
            self.generate_val(v2)
            self.place(jump_end)
        elif op == 'OpShl':
            gen(A_SHL)
        elif op == 'OpShr':
            gen(A_SHR)
        elif op == 'OpUShr':
            gen(A_ASR)
        elif op == 'OpMod':
            gen(A_MOD)
        else:
            raise ValueError(op)

    def generate_geturl(self, c: str, vars_: list, p: Pos) -> None:
        if len(vars_) == 1 and c == 'getURL':
            self.generate_val(vars_[0])
            self.push(['_self'])
            k = 0
        elif len(vars_) >= 2:
            self.generate_val(vars_[0])
            self.generate_val(vars_[1])
            rest = vars_[2:]
            if not rest:
                k = 0
            elif len(rest) == 1 and isinstance(rest[0], EConst) and isinstance(rest[0].c, String) and rest[0].c.s == 'GET':
                k = 1
            elif len(rest) == 1 and isinstance(rest[0], EConst) and isinstance(rest[0].c, String) and rest[0].c.s == 'POST':
                k = 2
            else:
                malformed(rest[0].pos)
        else:
            malformed(p)
        base = {'getURL': 0, 'loadMovie': 64, 'loadVariables': 192}[c]
        self.code.op(avm1.GET_URL2, flags=k + base)
        self.stack_size -= 2

    def generate_call(self, v, vl: list, newcall: bool = False) -> None:
        name = v.c.s if isinstance(v, EConst) and isinstance(v.c, Ident) else None
        n = len(vl)
        if name == 'trace':
            ftrace = self.main.options.ftrace
            if ftrace is None:
                if n != 1:
                    malformed(v.pos)
                self.generate_val(vl[0])
                self.write(A_TRACE)
                return
            if ftrace in ('', 'no'):
                return
            parts = ftrace.split('.')
            pos = v.pos
            e = EStatic((tuple(parts[:-1]), parts[-1]), pos)
            line = self.main.line_of(pos)
            extra = [
                EConst(String(s_type_path(self.current.path) + '::' + self.curmethod), pos),
                EConst(String(pos.file.replace('\\', '\\\\')), pos),
                EConst(Int(str(line)), pos),
            ]
            self.generate_call(e, [*vl, *extra])
            return
        if name == 'instanceof' and n == 2:
            self.generate_val(vl[0])
            self.generate_val(vl[1])
            self.write(A_INSTANCEOF)
            return
        if name == 'typeof' and n == 1:
            self.generate_val(vl[0])
            self.write(A_TYPEOF)
            return
        if name == 'chr' and n == 1:
            self.generate_val(vl[0])
            self.write(A_CHR)
            return
        if name == 'ord' and n == 1:
            self.generate_val(vl[0])
            self.write(A_ORD)
            return
        if name == 'int' and n == 1:
            self.generate_val(vl[0])
            self.write(A_TOINT)
            return
        if name == 'string' and n == 1:
            self.generate_val(vl[0])
            self.write(A_TOSTRING)
            return
        if name == 'random' and n == 1:
            self.generate_val(vl[0])
            self.write(A_RANDOM)
            return
        if name == 'delete' and n == 1:
            x = vl[0]
            if isinstance(x, EParenthesis):
                x = x.e
            k = self.generate_access(x)
            if k is VAR_OBJ:
                self.write(A_DELETEOBJ)
            elif isinstance(k, VarReg) and k.reg != -1:
                pass
            else:
                self.write(A_DELETE)
            return
        if name == 'throw' and n == 1:
            self.generate_val(vl[0])
            self.write(A_THROW)
            return
        if name == 'eval' and n == 1:
            self.generate_val(vl[0])
            self.write(A_EVAL)
            return
        if name == 'getTimer' and n == 0:
            self.write(A_GETTIMER)
            return
        if name == 'targetPath' and n == 1:
            self.generate_val(vl[0])
            self.write(A_TARGETPATH)
            return
        if name == 'FSCommand2':
            for a in reversed(vl):
                self.generate_val(a)
            self.push([PInt(n)])
            self.write(A_FSCOMMAND2)
            self.stack -= n
            return
        if name == 'fscommand' and n == 1:
            self.push(['FSCommand:'])
            self.generate_val(vl[0])
            self.write(A_STRINGADD)
            self.push([''])
            self.code.op(avm1.GET_URL2, flags=0)
            self.stack_size -= 2
            return
        if name == 'fscommand' and n == 2:
            self.push(['FSCommand:'])
            self.generate_val(vl[0])
            self.write(A_STRINGADD)
            self.generate_val(vl[1])
            self.code.op(avm1.GET_URL2, flags=0)
            self.stack_size -= 2
            return
        if name == 'print' and n == 2:
            v2 = vl[1]
            if isinstance(v2, EConst) and isinstance(v2.c, String) and v2.c.s in ('bmovie', 'bframe', 'bmax'):
                s = {'bmovie': 'print:', 'bframe': 'print:#bframe', 'bmax': 'print:#bmax'}[v2.c.s]
            else:
                raise TyperError('Custom', 'print parameter should be either bmovie, bframe or bmax', v2.pos)
            self.push([s])
            self.generate_val(vl[0])
            self.code.op(avm1.GET_URL2, flags=0)
            self.stack_size -= 2
            return
        if name in ('getURL', 'loadMovie', 'loadVariables'):
            self.generate_geturl(name, vl, v.pos)
            return
        if isinstance(v, EField) and isinstance(v.e, EConst) and isinstance(v.e.c, Ident) and v.e.c.s == 'super':
            for a in reversed(vl):
                self.generate_val(a)
            self.push([PInt(n), Reg(2), v.name])
            self.call(VAR_OBJ, n)
            return
        if name == 'getVersion':
            self.push(['/:$version'])
            self.write(A_EVAL)
            return
        if name == 'stopAllSounds' and n == 0:
            self.write(A_STOPSOUNDS)
            return
        for a in reversed(vl):
            self.generate_val(a)
        self.push([PInt(n)])
        k = self.generate_access(v, forcall=True)
        if newcall:
            self.new_call(k, n)
        else:
            self.call(k, n)

    # -- values -------------------------------------------------------------------------------
    def generate_val(self, v, retval: bool = True) -> None:
        if isinstance(v, (EArray, EField, EStatic)) or (isinstance(v, EConst) and isinstance(v.c, Ident)):
            k = self.generate_access(v)
            self.getvar(k)
        elif isinstance(v, EConst):
            self.generate_constant(v.pos, v.c)
        elif isinstance(v, EParenthesis):
            self.generate_val(v.e, retval)
        elif isinstance(v, ECast):
            a = v.a
            if isinstance(a, EStatic) and a.path == ((), 'String'):
                self.generate_val(v.b)
                self.write(A_TOSTRING)
            elif isinstance(a, EStatic) and a.path == ((), 'Number'):
                self.generate_val(v.b)
                self.write(A_TONUMBER)
            elif isinstance(a, EStatic) and a.path == ((), 'Boolean'):
                self.generate_val(v.b)
                self.write(A_NOT)
                self.write(A_NOT)
            elif self.main.options.version == 6:
                self.generate_val(v.b)
            else:
                self.generate_val(v.a)
                self.generate_val(v.b)
                self.write(A_CAST)
        elif isinstance(v, EQuestion):
            self.generate_val(v.cond)
            jump_else = self.cjmp()
            self.generate_val(v.b)
            jump_end = self.jmp()
            self.place(jump_else)
            self.generate_val(v.a)
            self.place(jump_end)
            self.stack_size -= 1
        elif isinstance(v, EBinop):
            self.generate_binop(retval, v.op, v.a, v.b)
        elif isinstance(v, ELambda):
            self.generate_function(v.f)
        elif isinstance(v, ECall):
            self.generate_call(v.e, v.args)
        elif isinstance(v, EObjDecl):
            for s, x in v.fields:
                self.push([s])
                self.generate_val(x)
            self.push([PInt(len(v.fields))])
            self.write(A_OBJECT)
            self.stack_size -= len(v.fields) * 2
        elif isinstance(v, EArrayDecl):
            for x in reversed(v.items):
                self.generate_val(x)
            self.push([PInt(len(v.items))])
            self.write(A_INITARRAY)
            self.stack_size -= len(v.items)
        elif isinstance(v, ENew):
            self.generate_call(v.e, v.args, newcall=True)
        elif isinstance(v, EUnop):
            op = v.op
            if op == 'Not':
                self.generate_val(v.e)
                self.write(A_NOT)
            elif op == 'Neg' and isinstance(v.e, EConst) and isinstance(v.e.c, Int):
                n = ocaml_int32_of_string(v.e.c.s)
                if n is None:
                    self.generate_val(EUnop('Neg', v.flag, EConst(Float(v.e.c.s), v.e.pos), v.pos))
                else:
                    n = -n
                    if n >= 2**31:  # Int32.neg wraps
                        n -= 2**32
                    self.push([PInt(n)])
            elif op == 'Neg' and isinstance(v.e, EConst) and isinstance(v.e.c, Float):
                self.push([Double(0.0 - ocaml_float_of_string(v.e.c.s, v.e.pos))])
            elif op == 'Neg':
                self.push([PInt(0)])
                self.generate_val(v.e)
                self.write(A_SUBTRACT)
            elif op == 'NegBits':
                self.generate_val(v.e)
                self.push([PInt(-1)])
                self.write(A_XOR)
            else:
                if retval and v.flag == 'Postfix':
                    k = self.generate_access(v.e)
                    self.getvar(k)
                self.generate_access(v.e)
                k = self.generate_access(v.e)
                self.getvar(k)
                self.write(A_INCREMENT if op == 'Increment' else A_DECREMENT)
                self.setvar(k, retval and v.flag == 'Prefix')
        else:
            raise TypeError(v)

    # -- locals -------------------------------------------------------------------------------
    def generate_local_var(self, vname: str, vinit) -> None:
        if used_in_block(False, vname, self.cur_block) or self.reg_count >= 250:
            self.push([vname])
            self.locals[vname] = LocalCtx(0, self.stack)
            if vinit is None:
                self.write(A_LOCALVAR)
            else:
                self.generate_val(vinit)
                self.write(A_LOCALASSIGN)
        else:
            self.reg_count += 1
            r = self.reg_count
            self.locals[vname] = LocalCtx(r, self.stack)
            if vinit is not None:
                self.generate_val(vinit)
                self.setvar(VarReg(r))

    def gen_forins(self, all_: bool) -> None:
        for _ in range(self.forins if all_ else 1):
            lab = self.code.label()
            self.place(lab)
            self.push([Null()])
            self.write(A_EQUAL)
            self.write(A_NOT)
            self.code.branch_if(lab)
            self.stack_size -= 1

    def generate_breaks(self, olds: list) -> None:
        for lab in self.breaks:
            self.place(lab)
        self.breaks = olds

    def do_jmp(self, lab: Label) -> None:
        self.code.jump(lab)

    # -- statements ---------------------------------------------------------------------------
    def generate_expr(self, e) -> None:
        if isinstance(e, EFunction):
            raise AssertionError('nested function declaration')
        if isinstance(e, EVars):
            for vname, _, vinit in e.vl:
                self.generate_local_var(vname, vinit)
        elif isinstance(e, EBlock):
            close = self.open_block(e)
            for x in e.el:
                self.generate_expr(x)
            close()
        elif isinstance(e, EFor):
            close = self.open_block(e.body)
            for x in e.inits:
                self.generate_expr(x)
            test = self.jmp()
            start = self.code.label()
            self.place(start)
            old_continue = self.continue_label
            old_breaks = self.breaks
            self.breaks = []
            self.continue_label = start
            for v in e.incrs:
                self.generate_expr(EVal(v, NULL_POS))
            self.place(test)
            jumps = []
            for cond in e.conds:
                self.generate_val(cond)
                self.write(A_NOT)
                jumps.append(self.cjmp())
            self.generate_expr(e.body)
            self.do_jmp(start)
            for j in jumps:
                self.place(j)
            self.generate_breaks(old_breaks)
            self.continue_label = old_continue
            close()
        elif isinstance(e, EForIn):
            close = self.open_block(e.body)
            self.generate_val(e.v)
            self.write(A_ENUM2)
            start = self.code.label()
            self.place(start)
            old_continue = self.continue_label
            old_breaks = self.breaks
            self.breaks = []
            self.continue_label = start
            self.forins += 1
            self.code.op(avm1.STORE_REGISTER, reg=0)
            self.push([Null()])
            self.write(A_EQUAL)
            jump_end = self.cjmp()
            decl = e.decl
            if isinstance(decl, EVal) and isinstance(decl.v, EConst) and isinstance(decl.v.c, Ident):
                k = self.generate_access(decl.v)
                self.push([Reg(0)])
                self.setvar(k)
            elif isinstance(decl, EVars) and len(decl.vl) == 1 and decl.vl[0][2] is None:
                x = decl.vl[0][0]
                self.push([x])
                self.locals[x] = LocalCtx(0, self.stack)
                self.push([Reg(0)])
                self.write(A_LOCALASSIGN)
            else:
                malformed(decl.pos)
            self.generate_expr(e.body)
            self.do_jmp(start)
            has_breaks = bool(self.breaks)
            self.generate_breaks(old_breaks)
            if has_breaks:
                self.gen_forins(False)
            self.place(jump_end)
            self.forins -= 1
            self.continue_label = old_continue
            close()
        elif isinstance(e, EIf):
            self.generate_val(e.cond)
            self.write(A_NOT)
            jump_else = self.cjmp()
            self.generate_expr(e.e)
            if e.eelse is None:
                self.place(jump_else)
            else:
                jump_end = self.jmp()
                self.place(jump_else)
                self.generate_expr(e.eelse)
                self.place(jump_end)
        elif isinstance(e, EVal):
            s = self.stack_size
            self.generate_val(e.v, retval=False)
            self.pop(self.stack_size - s)
        elif isinstance(e, EWhile):
            jump_begin = self.jmp() if e.flag == 'DoWhile' else None
            start = self.code.label()
            self.place(start)
            old_continue = self.continue_label
            old_breaks = self.breaks
            self.breaks = []
            self.continue_label = start
            self.generate_val(e.cond)
            self.write(A_NOT)
            jump_end = self.cjmp()
            if jump_begin is not None:
                self.place(jump_begin)
            self.generate_expr(e.body)
            self.do_jmp(start)
            self.generate_breaks(old_breaks)
            self.continue_label = old_continue
            self.place(jump_end)
        elif isinstance(e, EWith):
            self.generate_val(e.v)
            end = self.code.with_begin()
            self.stack_size -= 1
            self.generate_expr(e.e)
            self.place(end)
        elif isinstance(e, EBreak):
            lab = self.code.label('break')
            self.code.jump(lab)
            self.breaks.insert(0, lab)
        elif isinstance(e, EContinue):
            self.do_jmp(self.continue_label)
        elif isinstance(e, EReturn):
            self.gen_forins(True)
            if e.v is None:
                self.push([Undefined()])
            else:
                self.generate_val(e.v)
            self.write(A_RETURN)
        elif isinstance(e, ESwitch):
            self.generate_val(e.v)
            self.code.op(avm1.STORE_REGISTER, reg=0)
            old_breaks = self.breaks
            first_case = True
            self.breaks = []
            def_state = {'lab': None}  # the pending jump-to-default/end
            cases = []
            for v, body in e.cases:
                if v is None:
                    def resolve_default():
                        if def_state['lab'] is not None:
                            self.place(def_state['lab'])
                            def_state['lab'] = None
                    cases.append((resolve_default, body))
                else:
                    if first_case:
                        first_case = False
                    else:
                        self.push([Reg(0)])
                    self.generate_val(v)
                    self.write(A_PHYSEQUAL)
                    lab = self.cjmp()
                    cases.append(((lambda lab=lab: self.place(lab)), body))
            def_state['lab'] = self.jmp()
            for j, body in cases:
                j()
                self.generate_expr(body)
            if def_state['lab'] is not None:
                self.place(def_state['lab'])
            self.generate_breaks(old_breaks)
        elif isinstance(e, ETry):
            tr = self.code.try_begin(catch_reg=0)
            self.generate_expr(e.e)
            jump_end = self.jmp()
            self.place(tr.catch_start)
            end_throw = True
            first_catch = True
            jumps = []
            for name, t, body in e.catches:
                saved = self.locals.get(name)
                self.locals[name] = LocalCtx(0, self.stack)
                if t is None:
                    end_throw = False
                    self.write(A_POP)
                    self.push([name, Reg(0)])
                    self.write(A_LOCALASSIGN)
                    self.generate_expr(body)
                    next_catch = None
                else:
                    if not first_catch:
                        self.write(A_POP)
                    self.getvar(self.generate_access(EStatic(t, body.pos)))
                    self.push([Reg(0)])
                    self.write(A_CAST)
                    self.write(A_DUP)
                    self.push([Null()])
                    self.write(A_EQUAL)
                    c = self.cjmp()
                    self.push([name])
                    self.write(A_SWAP)
                    self.write(A_LOCALASSIGN)
                    self.generate_expr(body)
                    next_catch = c
                first_catch = False
                j = self.jmp()
                if next_catch is not None:
                    self.place(next_catch)
                if saved is None:
                    del self.locals[name]
                else:
                    self.locals[name] = saved
                jumps.append(j)
            if end_throw and e.catches:
                self.write(A_POP)
                self.push([Reg(0)])
                self.write(A_THROW)
            tr.has_catch = bool(e.catches)
            self.place(tr.finally_start)
            for j in jumps:
                self.place(j)
            self.place(jump_end)
            if e.fo is not None:
                tr.has_finally = True
                self.generate_expr(e.fo)
            self.place(tr.end)
        else:
            raise TypeError(e)

    # -- functions ----------------------------------------------------------------------------
    def generate_function(self, f, constructor: bool = False) -> None:
        fexpr = f.fexpr
        if fexpr is None:
            return
        old_name = self.curmethod
        stack_base, old_nregs = self.stack, self.reg_count
        have_super = used_in_block(True, 'super', fexpr)
        reg_super = have_super or (constructor and self.current.superclass is not None)
        old_forin = self.forins
        self.reg_count = 2 if reg_super else 1
        if f.fname != '':
            self.curmethod = f.fname
        self.forins = 0
        self.stack += 1
        args = []
        for aname, _ in f.fargs:
            if used_in_block(False, aname, fexpr):
                r = 0
            else:
                self.reg_count += 1
                r = self.reg_count
            self.locals[aname] = LocalCtx(r, self.stack)
            args.append((r, aname))
        arguments = used_in_block(True, 'arguments', fexpr)
        flags = THIS_REGISTER | (0 if arguments else ARGUMENTS_NOVAR) | (SUPER_REGISTER if reg_super else SUPER_NOVAR)
        outer = self.code
        body = Code()
        item = outer.function('', args, 0, flags, body)
        self.stack_size += 1
        self.code = body
        if constructor and self.current.superclass is not None and not have_super:
            self.generate_expr(SUPER_CALL)
        self.generate_expr(fexpr)
        if f.fgetter == 'Setter':
            self.push([PInt(0), Reg(1), '__get__' + f.fname])
            self.call(VAR_OBJ, 0)
            self.write(A_RETURN)
        item.regs = self.reg_count + 1
        self.code = outer
        self.clean_stack(stack_base)
        self.forins = old_forin
        self.reg_count = old_nregs
        self.curmethod = old_name

    # -- class --------------------------------------------------------------------------------
    def generate_class_code(self, clctx: GenClass) -> None:
        cpath, cname = clctx.path
        self.getvar(self.generate_access(EStatic((cpath, cname), NULL_POS)))
        self.write(A_NOT)
        self.write(A_NOT)
        jump_end_def = self.cjmp()
        self.generate_package_register(list(cpath))
        k = self.generate_package(list(cpath))
        self.push([cname])
        if clctx.constructor is None:
            flags = THIS_REGISTER | ARGUMENTS_NOVAR | SUPER_REGISTER
            outer = self.code
            body = Code()
            item = outer.function('', [], 0, flags, body)
            self.stack_size += 1
            if clctx.superclass is not None:
                self.code = body
                self.generate_expr(SUPER_CALL)
                self.code = outer
            item.regs = 3
        else:
            self.generate_function(clctx.constructor, constructor=True)
        self.code.op(avm1.STORE_REGISTER, reg=0)
        self.setvar(k)
        if clctx.superclass is not None:
            csuper = clctx.superclass
            if self.main.options.version == 6:
                self.push([Reg(0), 'prototype'])
                self.getvar(VAR_OBJ)
                self.push(['__proto__'])
                self.getvar(self.generate_access(EStatic(csuper.path, NULL_POS)))
                self.push(['prototype'])
                self.getvar(VAR_OBJ)
                self.setvar(VAR_OBJ)
                self.push([Reg(0), 'prototype'])
                self.getvar(VAR_OBJ)
                self.push(['__constructor__'])
                self.getvar(self.generate_access(EStatic(csuper.path, NULL_POS)))
                self.setvar(VAR_OBJ)
            else:
                self.push([Reg(0)])
                self.getvar(self.generate_access(EStatic(csuper.path, NULL_POS)))
                self.write(A_EXTENDS)
        self.push([Reg(0), 'prototype'])
        self.getvar(VAR_OBJ)
        self.code.op(avm1.STORE_REGISTER, reg=1)
        self.write(A_POP)
        getters = Hashtbl()
        for f in clctx.methods:
            if f.fexpr is None:
                continue
            self.push([Reg(1 if f.fstatic == 'IsMember' else 0)])
            if f.fgetter == 'Normal':
                if f.fname == 'main' and f.fstatic == 'IsStatic' and self.main.options.enable_main:
                    if self.main.main is None:
                        self.main.main = clctx.path
                    else:
                        raise Failure('Duplicate main entry point : ' + s_type_path(self.main.main) + ' and ' + s_type_path(clctx.path))
                name = f.fname
            elif f.fgetter == 'Getter':
                getters.add((f.fname, 1, 0 if f.fstatic == 'IsMember' else 1))
                name = '__get__' + f.fname
            else:
                getters.add((f.fname, 2, 0 if f.fstatic == 'IsMember' else 1))
                name = '__set__' + f.fname
            self.push([name])
            self.generate_function(f)
            self.setvar(VAR_OBJ)
        dones: set = set()
        for (name, get, stat) in getters.keys():
            if (name, get, stat) in dones:
                continue
            reg = 1 if stat == 0 else 0
            getter = get == 1 or getters.mem((name, 1, stat))
            setter = get == 2 or getters.mem((name, 2, stat))
            dones.add((name, 1, stat))
            dones.add((name, 2, stat))
            if setter:
                self.push([Reg(reg), '__set__' + name])
                self.getvar(VAR_OBJ)
            else:
                self._no_getset()
            if getter:
                self.push([Reg(reg), '__get__' + name])
                self.getvar(VAR_OBJ)
            else:
                self._no_getset()
            self.push([name, PInt(3)])
            self.push([Reg(reg), 'addProperty'])
            self.call(VAR_OBJ, 3)
            self.write(A_POP)
        for cintf in clctx.interfaces:
            self.getvar(self.generate_access(EStatic(cintf.path, NULL_POS)))
        nintf = len(clctx.interfaces)
        if nintf > 0:
            self.push([PInt(nintf), Reg(0)])
            self.write(A_IMPLEMENTS)
            self.stack_size -= nintf
        self.push([PInt(1), Null(), Reg(1), PInt(3), 'ASSetPropFlags'])
        self.call(VAR_STR, 3)
        self.write(A_POP)
        for name, stat, v in clctx.initvars:
            self.push([Reg(1 if stat == 'IsMember' else 0), name])
            self.generate_val(v)
            self.setvar(VAR_OBJ)
        self.place(jump_end_def)

    def _no_getset(self) -> None:
        # AFunction { f_name = ""; f_args = []; f_codelen = 0 } — an empty DefineFunction
        self.code.op(avm1.DEFINE_FUNCTION, name='', params=[], size=0)
        self.stack_size += 1


class Failure(Exception):
    pass


SUPER_CALL = EVal(ECall(EConst(Ident('super'), NULL_POS), [], NULL_POS), NULL_POS)


# ---------------------------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------------------------

def used_in_block(curblock: bool, vname: str, e) -> bool:
    """Does `vname` occur inside a lambda within `e`? (`curblock` = count top-level uses too)."""
    in_lambda = [curblock]

    def vloop(v) -> bool:
        if isinstance(v, EConst):
            return isinstance(v.c, Ident) and in_lambda[0] and v.c.s == vname
        if isinstance(v, (ECast, EArray)):
            return vloop(v.a) or vloop(v.b)
        if isinstance(v, EBinop):
            return vloop(v.a) or vloop(v.b)
        if isinstance(v, EField):
            return vloop(v.e)
        if isinstance(v, EStatic):
            return v.path[0] == ('__With',) and v.path[1] == vname
        if isinstance(v, EParenthesis):
            return vloop(v.e)
        if isinstance(v, EObjDecl):
            return any(vloop(x) for _, x in v.fields)
        if isinstance(v, EArrayDecl):
            return any(vloop(x) for x in v.items)
        if isinstance(v, ECall):
            return vloop(v.e) or any(vloop(x) for x in v.args)
        if isinstance(v, ENew):
            return vloop(v.e) or any(vloop(x) for x in v.args)
        if isinstance(v, EUnop):
            return vloop(v.e)
        if isinstance(v, EQuestion):
            return vloop(v.cond) or vloop(v.a) or vloop(v.b)
        if isinstance(v, ELambda):
            if v.f.fexpr is None:
                return False
            old = in_lambda[0]
            in_lambda[0] = True
            r = loop(v.f.fexpr)
            in_lambda[0] = old
            return r
        raise TypeError(v)

    def loop(e) -> bool:
        if isinstance(e, EFunction):
            raise AssertionError('nested function declaration')
        if isinstance(e, EVars):
            return any(v is not None and vloop(v) for _, _, v in e.vl)
        if isinstance(e, EBlock):
            return any(loop(x) for x in e.el)
        if isinstance(e, EFor):
            return any(loop(x) for x in e.inits) or any(vloop(c) for c in e.conds) or any(vloop(i) for i in e.incrs) or loop(e.body)
        if isinstance(e, EForIn):
            return loop(e.decl) or vloop(e.v) or loop(e.body)
        if isinstance(e, EIf):
            return vloop(e.cond) or loop(e.e) or (e.eelse is not None and loop(e.eelse))
        if isinstance(e, EWhile):
            return vloop(e.cond) or loop(e.body)
        if isinstance(e, ESwitch):
            return vloop(e.v) or any((v is not None and vloop(v)) or loop(b) for v, b in e.cases)
        if isinstance(e, ETry):
            return loop(e.e) or any(vname == n or loop(b) for n, _, b in e.catches) or (e.fo is not None and loop(e.fo))
        if isinstance(e, EWith):
            return vloop(e.v) or loop(e.e)
        if isinstance(e, EReturn):
            return e.v is not None and vloop(e.v)
        if isinstance(e, EVal):
            return vloop(e.v)
        if isinstance(e, (EBreak, EContinue)):
            return False
        raise TypeError(e)

    return loop(e)


def ocaml_int32_of_string(s: str) -> int | None:
    """OCaml's Int32.of_string, or None where it raises: signed 32-bit result."""
    sign = 1
    body = s
    if body.startswith('-'):
        sign, body = -1, body[1:]
    elif body.startswith('+'):
        body = body[1:]
    try:
        if body[:2] in ('0x', '0X'):
            v = int(body[2:], 16)
            if v >= 2**32:
                return None
        elif body[:2] in ('0o', '0O'):
            v = int(body[2:], 8)
            if v >= 2**32:
                return None
        elif body[:2] in ('0b', '0B'):
            v = int(body[2:], 2)
            if v >= 2**32:
                return None
        else:
            if not body.isdigit():
                return None
            v = int(body)
            if v > 2**31:  # OCaml 3.x: exactly 2^31 is accepted and wraps to -2^31
                return None
    except ValueError:
        return None
    v = (sign * v) & 0xFFFFFFFF
    return v - 2**32 if v >= 2**31 else v


MIN_NORMAL = 2.2250738585072014e-308


def ocaml_float_of_string(s: str, p: Pos) -> float:
    """OCaml's float_of_string as built with the MSVC runtime: denormals flush to zero."""
    try:
        v = float(s.replace('_', ''))
    except ValueError:
        malformed(p)
    if v != 0.0 and abs(v) < MIN_NORMAL:
        return 0.0
    return v


def utf8_bytes(cp: int) -> bytes:
    if cp < 0x80:
        return bytes([cp])
    if cp < 0x800:
        return bytes([0xC0 | (cp >> 6), 0x80 | (cp & 0x3F)])
    if cp < 0x10000:
        return bytes([0xE0 | (cp >> 12), 0x80 | ((cp >> 6) & 0x3F), 0x80 | (cp & 0x3F)])
    return bytes([0xF0 | (cp >> 18), 0x80 | ((cp >> 12) & 0x3F), 0x80 | ((cp >> 6) & 0x3F), 0x80 | (cp & 0x3F)])


def unescape_chars(s: str, p: Pos) -> str:
    out: list[str] = []
    i = 0
    n = len(s)

    def bad(c: str):
        o = ord(c)
        msg = f"Invalid character '{c}'" if 32 < o < 128 else f'Invalid character 0x{o:02X}'
        raise LexError(msg, p)

    while i < n:
        c = s[i]
        if c != '\\':
            out.append(c)
            i += 1
            continue
        i += 1
        if i >= n:
            break
        c = s[i]
        if c == 'b':
            out.append('\b')
        elif c == 'f':
            out.append('\x0c')
        elif c == 'n':
            out.append('\n')
        elif c == 'r':
            out.append('\r')
        elif c == 't':
            out.append('\t')
        elif c in ('"', "'", '\\'):
            out.append(c)
        elif c in '0123':
            seg = s[i:i + 3]
            if len(seg) != 3 or any(d not in '01234567' for d in seg):
                bad(c)
            out.append(chr(int(seg, 8)))
            i += 2
        elif c == 'x':
            seg = s[i + 1:i + 3]
            if len(seg) != 2 or any(d not in '0123456789abcdefABCDEF' for d in seg):
                bad(c)
            out.append(chr(int(seg, 16)))
            i += 2
        elif c == 'u':
            seg = s[i + 1:i + 5]
            if len(seg) != 4 or any(d not in '0123456789abcdefABCDEF' for d in seg):
                bad(c)
            # UTF-8 bytes (extlib encodes any code point, surrogates included), one char per byte
            out.append(utf8_bytes(int(seg, 16)).decode('latin-1'))
            i += 4
        else:
            bad(c)
        i += 1
    return ''.join(out)


# ---------------------------------------------------------------------------------------------
# DRIVER
# ---------------------------------------------------------------------------------------------

@dataclass
class GeneratedClass:
    name: str  # dotted path
    code: bytes  # DoInitAction actions incl. pool + End


class Generator:
    def __init__(self, options: Options, line_of=None):
        self.options = options
        self.main = MainCtx(options)
        self.main.line_of = line_of or (lambda pos: 0)
        self.classes: list[GeneratedClass] = []
        self.main_code: bytes | None = None

    def gen_class(self, clctx: GenClass) -> None:
        if clctx.intrinsic:
            return
        g = Gen(self.main, clctx)
        g.generate_class_code(clctx)

        def check(size: int) -> None:
            if size >= 1 << 15:
                raise Failure('Class ' + s_type_path(clctx.path) + ' excess 32K bytecode limit, please split it')

        code = asm.assemble_stream(g.code, size_check=check)
        self.classes.append(GeneratedClass(s_type_path(clctx.path), code))

    def finish(self) -> None:
        if self.main.main is None:
            if self.options.enable_main:
                raise Failure('Main entry point not found')
            return
        p, clname = self.main.main
        g = Gen(self.main, GenClass(((), ''), [], EBlock([], NULL_POS), '', False, {}))
        g.push(['MTASC_MAIN'])
        g.code.op(avm1.STORE_REGISTER, reg=0)
        g.write(A_POP)
        g.push(['this'])
        g.write(A_EVAL)
        g.push([PInt(1)])
        k = g.generate_package(list(p), fast=True)
        g.push([clname])
        g.getvar(k)
        g.push(['main'])
        g.call(VAR_OBJ, 1)
        g.write(A_POP)
        self.main_code = asm.assemble_stream(g.code)
