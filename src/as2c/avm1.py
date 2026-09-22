"""AVM1 action bytecode — encoder, decoder, and a readable disassembler.

The `Action` model is deliberately flat: an action is an opcode plus its decoded operands, and
branch operands are byte offsets exactly as stored (relative to the end of the action). The
assembler in `emit.py` works in terms of labels and resolves them to these offsets; the decoder
here turns bytes back into the same model so an oracle diff compares like with like.

Format reference: Adobe "SWF File Format Specification" v19, chapter 5 (Actions).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------------------------
# OPCODES
# ---------------------------------------------------------------------------------------------

# Opcodes without operands (code < 0x80 has no length field at all).
SIMPLE = {
    0x04: 'NextFrame', 0x05: 'PrevFrame', 0x06: 'Play', 0x07: 'Stop', 0x08: 'ToggleQuality',
    0x09: 'StopSounds', 0x0A: 'Add', 0x0B: 'Subtract', 0x0C: 'Multiply', 0x0D: 'Divide',
    0x0E: 'Equals', 0x0F: 'Less', 0x10: 'And', 0x11: 'Or', 0x12: 'Not', 0x13: 'StringEquals',
    0x14: 'StringLength', 0x15: 'StringExtract', 0x17: 'Pop', 0x18: 'ToInteger',
    0x1C: 'GetVariable', 0x1D: 'SetVariable', 0x20: 'SetTarget2', 0x21: 'StringAdd',
    0x22: 'GetProperty', 0x23: 'SetProperty', 0x24: 'CloneSprite', 0x25: 'RemoveSprite',
    0x26: 'Trace', 0x27: 'StartDrag', 0x28: 'EndDrag', 0x29: 'StringLess', 0x2A: 'Throw',
    0x2B: 'CastOp', 0x2C: 'ImplementsOp', 0x2D: 'FSCommand2', 0x30: 'RandomNumber',
    0x31: 'MBStringLength', 0x32: 'CharToAscii', 0x33: 'AsciiToChar', 0x34: 'GetTime',
    0x35: 'MBStringExtract', 0x36: 'MBCharToAscii', 0x37: 'MBAsciiToChar', 0x3A: 'Delete',
    0x3B: 'Delete2', 0x3C: 'DefineLocal', 0x3D: 'CallFunction', 0x3E: 'Return', 0x3F: 'Modulo',
    0x40: 'NewObject', 0x41: 'DefineLocal2', 0x42: 'InitArray', 0x43: 'InitObject',
    0x44: 'TypeOf', 0x45: 'TargetPath', 0x46: 'Enumerate', 0x47: 'Add2', 0x48: 'Less2',
    0x49: 'Equals2', 0x4A: 'ToNumber', 0x4B: 'ToString', 0x4C: 'PushDuplicate',
    0x4D: 'StackSwap', 0x4E: 'GetMember', 0x4F: 'SetMember', 0x50: 'Increment',
    0x51: 'Decrement', 0x52: 'CallMethod', 0x53: 'NewMethod', 0x54: 'InstanceOf',
    0x55: 'Enumerate2', 0x60: 'BitAnd', 0x61: 'BitOr', 0x62: 'BitXor', 0x63: 'BitLShift',
    0x64: 'BitRShift', 0x65: 'BitURShift', 0x66: 'StrictEquals', 0x67: 'Greater',
    0x68: 'StringGreater', 0x69: 'Extends',
}

# Opcodes with operands (code >= 0x80 always carries a u16 length).
GOTO_FRAME = 0x81
GET_URL = 0x83
STORE_REGISTER = 0x87
CONSTANT_POOL = 0x88
WAIT_FOR_FRAME = 0x8A
SET_TARGET = 0x8B
GOTO_LABEL = 0x8C
WAIT_FOR_FRAME2 = 0x8D
DEFINE_FUNCTION2 = 0x8E
TRY = 0x8F
WITH = 0x94
PUSH = 0x96
JUMP = 0x99
GET_URL2 = 0x9A
DEFINE_FUNCTION = 0x9B
IF = 0x9D
CALL = 0x9E
GOTO_FRAME2 = 0x9F

LONG_NAMES = {
    GOTO_FRAME: 'GotoFrame', GET_URL: 'GetURL', STORE_REGISTER: 'StoreRegister',
    CONSTANT_POOL: 'ConstantPool', WAIT_FOR_FRAME: 'WaitForFrame', SET_TARGET: 'SetTarget',
    GOTO_LABEL: 'GotoLabel', WAIT_FOR_FRAME2: 'WaitForFrame2', DEFINE_FUNCTION2: 'DefineFunction2',
    TRY: 'Try', WITH: 'With', PUSH: 'Push', JUMP: 'Jump', GET_URL2: 'GetURL2',
    DEFINE_FUNCTION: 'DefineFunction', IF: 'If', CALL: 'Call', GOTO_FRAME2: 'GotoFrame2',
}

NAMES = {**SIMPLE, **LONG_NAMES, 0x00: 'End'}
CODES = {v: k for k, v in NAMES.items()}

# DefineFunction2 flags (SWF spec 5.10).
F2_PRELOAD_PARENT = 0x80
F2_PRELOAD_ROOT = 0x04
F2_SUPPRESS_SUPER = 0x20
F2_PRELOAD_SUPER = 0x10
F2_SUPPRESS_ARGUMENTS = 0x08
F2_PRELOAD_ARGUMENTS = 0x04
F2_SUPPRESS_THIS = 0x02
F2_PRELOAD_THIS = 0x01
F2_PRELOAD_GLOBAL = 0x100
# (bit layout as stored in the u16: PreloadParent 0x80, PreloadRoot 0x40, SuppressSuper 0x20,
#  PreloadSuper 0x10, SuppressArguments 0x08, PreloadArguments 0x04, SuppressThis 0x02,
#  PreloadThis 0x01, PreloadGlobal 0x100)
F2_PRELOAD_ROOT = 0x40

FLAG_NAMES = [
    (0x01, 'preload_this'), (0x02, 'suppress_this'), (0x04, 'preload_arguments'),
    (0x08, 'suppress_arguments'), (0x10, 'preload_super'), (0x20, 'suppress_super'),
    (0x40, 'preload_root'), (0x80, 'preload_parent'), (0x100, 'preload_global'),
]


# ---------------------------------------------------------------------------------------------
# PUSH VALUES
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Str:
    value: str


@dataclass(frozen=True)
class Float:
    value: float


@dataclass(frozen=True)
class Null:
    pass


@dataclass(frozen=True)
class Undefined:
    pass


@dataclass(frozen=True)
class Reg:
    index: int


@dataclass(frozen=True)
class Bool:
    value: bool


@dataclass(frozen=True)
class Double:
    value: float


@dataclass(frozen=True)
class Int:
    value: int


@dataclass(frozen=True)
class Const8:
    index: int


@dataclass(frozen=True)
class Const16:
    index: int


PushValue = Str | Float | Null | Undefined | Reg | Bool | Double | Int | Const8 | Const16
NULL = Null()
UNDEFINED = Undefined()


# ---------------------------------------------------------------------------------------------
# ACTION MODEL
# ---------------------------------------------------------------------------------------------

@dataclass
class Action:
    code: int
    # Operand payload, by opcode:
    #   Push            -> values: list[PushValue]
    #   ConstantPool    -> strings: list[str]
    #   StoreRegister   -> reg
    #   Jump / If       -> offset (i16, from end of this action)
    #   With            -> size (u16 body length)
    #   DefineFunction  -> name, params (list[str]), size
    #   DefineFunction2 -> name, params (list[(reg, name)]), regs, flags, size
    #   Try             -> flags, try_size, catch_size, finally_size, catch_name | catch_reg
    #   GotoFrame       -> frame;  GotoLabel/SetTarget -> name;  GetURL -> url, target
    #   WaitForFrame    -> frame, skip;  WaitForFrame2 -> skip;  GetURL2 -> flags
    #   GotoFrame2      -> flags, scene_bias
    values: list = field(default_factory=list)
    strings: list[str] = field(default_factory=list)
    reg: int = 0
    offset: int = 0
    size: int = 0
    name: str = ''
    params: list = field(default_factory=list)
    regs: int = 0
    flags: int = 0
    try_size: int = 0
    catch_size: int = 0
    finally_size: int = 0
    catch_name: str | None = None
    catch_reg: int | None = None
    frame: int = 0
    skip: int = 0
    url: str = ''
    target: str = ''
    scene_bias: int = 0
    raw: bytes = b''  # unknown opcodes: payload kept verbatim

    @property
    def opname(self) -> str:
        return NAMES.get(self.code, f'Unknown{self.code:02X}')

    def __repr__(self) -> str:  # compact, for test failures
        return f'Action({format_action(self)})'


class Overflow(Exception):
    """A u16 field overflowed — swflib dies with IO.Overflow("write_ui16")."""


def encode_string(s) -> bytes:
    return (s if isinstance(s, bytes) else s.encode('utf-8')) + b'\0'


def encode_double(f: float) -> bytes:
    """PUSH doubles store the two 32-bit halves swapped (high word first)."""
    d = struct.pack('<d', f)
    return d[4:] + d[:4]


def decode_double(b: bytes) -> float:
    return struct.unpack('<d', b[4:] + b[:4])[0]


def encode_push_value(v: PushValue) -> bytes:
    match v:
        case Str(s):
            return b'\x00' + encode_string(s)
        case Float(f):
            return b'\x01' + struct.pack('<f', f)
        case Null():
            return b'\x02'
        case Undefined():
            return b'\x03'
        case Reg(i):
            return b'\x04' + bytes([i])
        case Bool(b):
            return b'\x05' + bytes([1 if b else 0])
        case Double(f):
            return b'\x06' + encode_double(f)
        case Int(i):
            return b'\x07' + struct.pack('<i', i) if i < 0 else b'\x07' + struct.pack('<I', i & 0xFFFFFFFF)
        case Const8(i):
            return b'\x08' + bytes([i])
        case Const16(i):
            return b'\x09' + struct.pack('<H', i)
    raise ValueError(f'not a push value: {v!r}')


def encode_action(a: Action) -> bytes:
    code = a.code
    if code < 0x80:
        return bytes([code])
    body = encode_payload(a)
    if len(body) > 0xFFFF:
        raise Overflow('write_ui16')
    return bytes([code]) + struct.pack('<H', len(body)) + body


def encode_payload(a: Action) -> bytes:
    code = a.code
    if code == PUSH:
        return b''.join(encode_push_value(v) for v in a.values)
    if code == CONSTANT_POOL:
        return struct.pack('<H', len(a.strings)) + b''.join(encode_string(s) for s in a.strings)
    if code == STORE_REGISTER:
        return bytes([a.reg])
    if code in (JUMP, IF):
        if not -0x8000 <= a.offset <= 0x7FFF:
            raise Overflow('write_i16')
        return struct.pack('<h', a.offset)
    if code == WITH:
        return struct.pack('<H', a.size)
    if code == DEFINE_FUNCTION:
        return (encode_string(a.name) + struct.pack('<H', len(a.params))
                + b''.join(encode_string(p) for p in a.params) + struct.pack('<H', a.size))
    if code == DEFINE_FUNCTION2:
        out = encode_string(a.name) + struct.pack('<HBH', len(a.params), a.regs, a.flags)
        for reg, pname in a.params:
            out += bytes([reg]) + encode_string(pname)
        return out + struct.pack('<H', a.size)
    if code == TRY:
        flags = a.flags
        out = bytes([flags]) + struct.pack('<HHH', a.try_size, a.catch_size, a.finally_size)
        if flags & 0x04:
            out += bytes([a.catch_reg or 0])
        else:
            out += encode_string(a.catch_name or '')
        return out
    if code == GOTO_FRAME:
        return struct.pack('<H', a.frame)
    if code == GET_URL:
        return encode_string(a.url) + encode_string(a.target)
    if code == WAIT_FOR_FRAME:
        return struct.pack('<HB', a.frame, a.skip)
    if code in (SET_TARGET, GOTO_LABEL):
        return encode_string(a.name)
    if code == WAIT_FOR_FRAME2:
        return bytes([a.skip])
    if code == GET_URL2:
        return bytes([a.flags])
    if code == GOTO_FRAME2:
        return bytes([a.flags]) + (struct.pack('<H', a.scene_bias) if a.flags & 2 else b'')
    if code == CALL:
        return b''
    return a.raw


def encode_actions(actions: list[Action], terminate: bool = True) -> bytes:
    out = b''.join(encode_action(a) for a in actions)
    return out + b'\x00' if terminate else out


def action_length(a: Action) -> int:
    return len(encode_action(a))


# ---------------------------------------------------------------------------------------------
# DECODER
# ---------------------------------------------------------------------------------------------

class _Reader:
    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def u8(self) -> int:
        v = self.data[self.pos]
        self.pos += 1
        return v

    def u16(self) -> int:
        (v,) = struct.unpack_from('<H', self.data, self.pos)
        self.pos += 2
        return v

    def i16(self) -> int:
        (v,) = struct.unpack_from('<h', self.data, self.pos)
        self.pos += 2
        return v

    def i32(self) -> int:
        (v,) = struct.unpack_from('<i', self.data, self.pos)
        self.pos += 4
        return v

    def f32(self) -> float:
        (v,) = struct.unpack_from('<f', self.data, self.pos)
        self.pos += 4
        return v

    def string(self) -> str:
        end = self.data.index(b'\0', self.pos)
        s = self.data[self.pos:end].decode('utf-8', 'replace')
        self.pos = end + 1
        return s

    def take(self, n: int) -> bytes:
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b


def decode_push_values(payload: bytes) -> list[PushValue]:
    r = _Reader(payload)
    out: list[PushValue] = []
    while r.pos < len(payload):
        t = r.u8()
        if t == 0:
            out.append(Str(r.string()))
        elif t == 1:
            out.append(Float(r.f32()))
        elif t == 2:
            out.append(NULL)
        elif t == 3:
            out.append(UNDEFINED)
        elif t == 4:
            out.append(Reg(r.u8()))
        elif t == 5:
            out.append(Bool(r.u8() != 0))
        elif t == 6:
            out.append(Double(decode_double(r.take(8))))
        elif t == 7:
            out.append(Int(r.i32()))
        elif t == 8:
            out.append(Const8(r.u8()))
        elif t == 9:
            out.append(Const16(r.u16()))
        else:
            raise ValueError(f'unknown push type {t}')
    return out


def decode_action(code: int, payload: bytes) -> Action:
    a = Action(code)
    r = _Reader(payload)
    if code == PUSH:
        a.values = decode_push_values(payload)
    elif code == CONSTANT_POOL:
        n = r.u16()
        a.strings = [r.string() for _ in range(n)]
    elif code == STORE_REGISTER:
        a.reg = r.u8()
    elif code in (JUMP, IF):
        a.offset = r.i16()
    elif code == WITH:
        a.size = r.u16()
    elif code == DEFINE_FUNCTION:
        a.name = r.string()
        n = r.u16()
        a.params = [r.string() for _ in range(n)]
        a.size = r.u16()
    elif code == DEFINE_FUNCTION2:
        a.name = r.string()
        n = r.u16()
        a.regs = r.u8()
        a.flags = r.u16()
        a.params = [(r.u8(), r.string()) for _ in range(n)]
        a.size = r.u16()
    elif code == TRY:
        a.flags = r.u8()
        a.try_size, a.catch_size, a.finally_size = r.u16(), r.u16(), r.u16()
        if a.flags & 0x04:
            a.catch_reg = r.u8()
        else:
            a.catch_name = r.string()
    elif code == GOTO_FRAME:
        a.frame = r.u16()
    elif code == GET_URL:
        a.url, a.target = r.string(), r.string()
    elif code == WAIT_FOR_FRAME:
        a.frame, a.skip = r.u16(), r.u8()
    elif code in (SET_TARGET, GOTO_LABEL):
        a.name = r.string()
    elif code == WAIT_FOR_FRAME2:
        a.skip = r.u8()
    elif code == GET_URL2:
        a.flags = r.u8()
    elif code == GOTO_FRAME2:
        a.flags = r.u8()
        if a.flags & 2:
            a.scene_bias = r.u16()
    elif code == CALL:
        pass
    else:
        a.raw = payload
    return a


def decode_actions(data: bytes, start: int = 0, end: int | None = None) -> list[tuple[int, Action]]:
    """Decode a flat action stream into (byte offset, Action) pairs.

    Stops at the terminating End (0x00) or at `end`. Function / with / try bodies are NOT
    recursed into here — they are part of the flat stream, exactly as stored; see `Program`.
    """
    if end is None:
        end = len(data)
    pos = start
    out: list[tuple[int, Action]] = []
    while pos < end:
        code = data[pos]
        off = pos
        pos += 1
        if code == 0:
            break
        if code >= 0x80:
            (length,) = struct.unpack_from('<H', data, pos)
            pos += 2
            payload = data[pos:pos + length]
            pos += length
        else:
            payload = b''
        out.append((off, decode_action(code, payload)))
    return out


# ---------------------------------------------------------------------------------------------
# DISASSEMBLER
# ---------------------------------------------------------------------------------------------

def format_push_value(v: PushValue, pool: list[str] | None = None) -> str:
    match v:
        case Str(s):
            return repr(s)
        case Float(f):
            return f'float({f!r})'
        case Null():
            return 'null'
        case Undefined():
            return 'undefined'
        case Reg(i):
            return f'r{i}'
        case Bool(b):
            return 'true' if b else 'false'
        case Double(f):
            return f'double({f!r})'
        case Int(i):
            return str(i)
        case Const8(i) | Const16(i):
            if pool is not None and i < len(pool):
                return f'c{i}={pool[i]!r}'
            return f'c{i}'
    return repr(v)


def format_flags(flags: int) -> str:
    names = [n for bit, n in FLAG_NAMES if flags & bit]
    return f'0x{flags:03x}' + (f'({",".join(names)})' if names else '')


def format_action(a: Action, pool: list[str] | None = None, pos: int | None = None) -> str:
    code = a.code
    if code == PUSH:
        return 'Push ' + ', '.join(format_push_value(v, pool) for v in a.values)
    if code == CONSTANT_POOL:
        return 'ConstantPool ' + ', '.join(f'{i}:{s!r}' for i, s in enumerate(a.strings))
    if code == STORE_REGISTER:
        return f'StoreRegister r{a.reg}'
    if code in (JUMP, IF):
        tgt = f' -> @{pos + action_length(a) + a.offset:04x}' if pos is not None else ''
        return f'{a.opname} {a.offset:+d}{tgt}'
    if code == WITH:
        return f'With size={a.size}'
    if code == DEFINE_FUNCTION:
        return f'DefineFunction {a.name!r}({", ".join(a.params)}) size={a.size}'
    if code == DEFINE_FUNCTION2:
        ps = ', '.join(f'r{r}:{n}' if r else n for r, n in a.params)
        return f'DefineFunction2 {a.name!r}({ps}) regs={a.regs} flags={format_flags(a.flags)} size={a.size}'
    if code == TRY:
        catch = f'r{a.catch_reg}' if a.flags & 4 else repr(a.catch_name)
        return f'Try flags=0x{a.flags:02x} try={a.try_size} catch={a.catch_size} finally={a.finally_size} var={catch}'
    if code == GOTO_FRAME:
        return f'GotoFrame {a.frame}'
    if code == GET_URL:
        return f'GetURL {a.url!r} {a.target!r}'
    if code == WAIT_FOR_FRAME:
        return f'WaitForFrame {a.frame} skip={a.skip}'
    if code in (SET_TARGET, GOTO_LABEL):
        return f'{a.opname} {a.name!r}'
    if code == WAIT_FOR_FRAME2:
        return f'WaitForFrame2 skip={a.skip}'
    if code == GET_URL2:
        return f'GetURL2 0x{a.flags:02x}'
    if code == GOTO_FRAME2:
        return f'GotoFrame2 0x{a.flags:02x} bias={a.scene_bias}'
    if code in NAMES:
        return a.opname
    return f'Unknown 0x{code:02X} {a.raw.hex()}'


def disassemble(data: bytes, indent: str = '', pool: list[str] | None = None, base: int = 0) -> str:
    """Human-readable listing; function/with/try bodies are indented under their opener."""
    lines: list[str] = []
    _disasm_range(data, 0, len(data), indent, pool, lines, base)
    return '\n'.join(lines)


def _disasm_range(data: bytes, start: int, end: int, indent: str, pool: list[str] | None,
                  lines: list[str], base: int) -> None:
    pos = start
    while pos < end:
        code = data[pos]
        off = pos
        pos += 1
        if code == 0:
            lines.append(f'{indent}@{base + off:04x}  End')
            continue
        if code >= 0x80:
            (length,) = struct.unpack_from('<H', data, pos)
            pos += 2
            payload = data[pos:pos + length]
            pos += length
        else:
            payload = b''
        a = decode_action(code, payload)
        if code == CONSTANT_POOL:
            pool = a.strings
        lines.append(f'{indent}@{base + off:04x}  {format_action(a, pool, base + off)}')
        if code in (DEFINE_FUNCTION, DEFINE_FUNCTION2, WITH):
            body_end = pos + a.size
            _disasm_range(data, pos, body_end, indent + '    ', pool, lines, base)
            pos = body_end
        elif code == TRY:
            body_end = pos + a.try_size
            lines.append(f'{indent}  try:')
            _disasm_range(data, pos, body_end, indent + '    ', pool, lines, base)
            pos = body_end
            if a.flags & 1:
                lines.append(f'{indent}  catch:')
                _disasm_range(data, pos, pos + a.catch_size, indent + '    ', pool, lines, base)
                pos += a.catch_size
            if a.flags & 2:
                lines.append(f'{indent}  finally:')
                _disasm_range(data, pos, pos + a.finally_size, indent + '    ', pool, lines, base)
                pos += a.finally_size
