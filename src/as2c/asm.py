"""Label-based AVM1 assembler.

Code generation appends *items* to a `Code` block: pushes (which coalesce into one Push action
while nothing but other pushes intervene — a placed label breaks the run), plain actions,
labels, branches to labels, DefineFunction2 items with a nested body, and `With` / `Try`
headers whose regions are delimited by labels in the same flat stream (as in mtasc's single
action array). `assemble_stream()` resolves everything to bytes and prepends the constant pool,
built from the symbolic string pushes in first-emission order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import avm1
from .avm1 import Action

# ---------------------------------------------------------------------------------------------
# ITEMS
# ---------------------------------------------------------------------------------------------


@dataclass(eq=False)
class Label:
    name: str = ''
    offset: int = -1  # filled in by the assembler (stream-global byte offset)


STREAM_START = Label('stream_start', 0)  # the ConstantPool action at offset 0 (mtasc's action index 0)


@dataclass(frozen=True)
class SymStr:
    """A string pushed through the constant pool."""

    value: str


@dataclass
class PushItem:
    values: list


@dataclass
class OpItem:
    action: Action


@dataclass
class BranchItem:
    code: int  # avm1.JUMP or avm1.IF
    target: Label


@dataclass
class FuncItem:
    name: str
    params: list  # [(reg, name)]
    regs: int
    flags: int
    body: Code


@dataclass
class WithItem:
    end: Label  # body runs from just after this header to `end`


@dataclass
class TryItem:
    catch_reg: int | None
    catch_name: str | None
    catch_start: Label  # end of the try body
    finally_start: Label  # end of the catch body (== catch_start when there is no catch)
    end: Label  # end of the finally body (== finally_start when there is none)
    has_catch: bool = False
    has_finally: bool = False


Item = PushItem | OpItem | BranchItem | FuncItem | WithItem | TryItem | Label


# ---------------------------------------------------------------------------------------------
# CODE BLOCK
# ---------------------------------------------------------------------------------------------


@dataclass
class Code:
    items: list = field(default_factory=list)

    @property
    def last_is_push(self) -> bool:
        return bool(self.items) and isinstance(self.items[-1], PushItem)

    def push(self, values: list) -> None:
        """Append push values; merges into the previous Push when it is the last item."""
        vals = [SymStr(v) if isinstance(v, str) else v for v in values]
        if self.last_is_push:
            self.items[-1].values.extend(vals)
        else:
            self.items.append(PushItem(vals))

    def push_separate(self, values: list) -> None:
        """A Push that must start its own action even after another Push."""
        self.items.append(PushItem([SymStr(v) if isinstance(v, str) else v for v in values]))

    def op(self, code: int, **operands) -> None:
        self.items.append(OpItem(Action(code, **operands)))

    def label(self, name: str = '') -> Label:
        return Label(name)

    def place(self, label: Label) -> None:
        self.items.append(label)

    def jump(self, target: Label) -> None:
        self.items.append(BranchItem(avm1.JUMP, target))

    def branch_if(self, target: Label) -> None:
        self.items.append(BranchItem(avm1.IF, target))

    def function(self, name: str, params: list, regs: int, flags: int, body: Code) -> FuncItem:
        it = FuncItem(name, params, regs, flags, body)
        self.items.append(it)
        return it

    def with_begin(self) -> Label:
        end = Label('with_end')
        self.items.append(WithItem(end))
        return end

    def try_begin(self, catch_reg: int | None = None, catch_name: str | None = None) -> TryItem:
        it = TryItem(catch_reg, catch_name, Label('catch'), Label('finally'), Label('try_end'))
        self.items.append(it)
        return it

    # -- constant pool ------------------------------------------------------------------------
    def collect_strings(self, pool: list[str], seen: dict[str, int]) -> None:
        for it in self.items:
            if isinstance(it, PushItem):
                for v in it.values:
                    if isinstance(v, SymStr) and v.value not in seen:
                        seen[v.value] = len(pool)
                        pool.append(v.value)
            elif isinstance(it, FuncItem):
                it.body.collect_strings(pool, seen)


# ---------------------------------------------------------------------------------------------
# ASSEMBLY
# ---------------------------------------------------------------------------------------------


def to_utf8(s: str) -> bytes:
    """mtasc's `to_utf8`: a byte string that is structurally valid UTF-8 is kept (extlib's
    validator accepts encoded surrogates), anything else is re-encoded byte by byte as if it
    were latin-1. Strings here carry one char per source byte."""
    raw = s.encode('latin-1', 'strict') if all(ord(c) < 256 for c in s) else s.encode('utf-8')
    try:
        raw.decode('utf-8', 'surrogatepass')
        return raw
    except UnicodeDecodeError:
        return raw.decode('latin-1').encode('utf-8')


def assemble_stream(code: Code, with_pool: bool = True, size_check=None) -> bytes:
    """Assemble a top-level stream → [ConstantPool] + body + End.

    `size_check(n)` is called with the code length excluding the pool's strings (what mtasc
    measures against its 32K per-class limit) before any operand is encoded, so a too-big
    class is reported as such rather than as an overflowing jump."""
    pool: list[str] = []
    seen: dict[str, int] = {}
    code.collect_strings(pool, seen)
    strings = [to_utf8(s) for s in pool]
    head_len = 5 + sum(len(s) + 1 for s in strings) if with_pool else 0
    body = _assemble(code, seen, head_len, size_check)
    head = avm1.encode_action(Action(avm1.CONSTANT_POOL, strings=strings)) if with_pool else b''
    return head + body + b'\x00'


def _resolve_push(values: list, pool: dict[str, int]) -> list:
    out = []
    for v in values:
        if isinstance(v, SymStr):
            idx = pool[v.value]
            out.append(avm1.Const8(idx) if idx <= 0xFF else avm1.Const16(idx))
        else:
            out.append(v)
    return out


TRY_BASE = 3 + 1 + 6  # header + flags + three u16 sizes
WITH_SIZE = 3 + 2


def _assemble(code: Code, pool: dict[str, int], base: int = 0, size_check=None) -> bytes:
    """`base` is this block's stream-global start offset: labels are global so a jump may
    target any point of the stream (mtasc computes deltas over one flat action array)."""
    # Pass 1: sizes and encodings of fixed-size items; labels get offsets.
    encoded: list[bytes | None] = []
    sizes: list[int] = []
    pos = base
    for it in code.items:
        if isinstance(it, Label):
            it.offset = pos
            encoded.append(b'')
            sizes.append(0)
            continue
        if isinstance(it, PushItem):
            b = avm1.encode_action(Action(avm1.PUSH, values=_resolve_push(it.values, pool)))
        elif isinstance(it, OpItem):
            b = avm1.encode_action(it.action)
        elif isinstance(it, BranchItem):
            b = None
            size = 5
        elif isinstance(it, FuncItem):
            hdr_size = avm1.action_length(Action(avm1.DEFINE_FUNCTION2, name=it.name, params=it.params,
                                                 regs=it.regs, flags=it.flags, size=0))
            body = _assemble(it.body, pool, pos + hdr_size)
            hdr = avm1.encode_action(Action(avm1.DEFINE_FUNCTION2, name=it.name, params=it.params,
                                            regs=it.regs, flags=it.flags, size=len(body)))
            b = hdr + body
        elif isinstance(it, WithItem):
            b = None
            size = WITH_SIZE
        elif isinstance(it, TryItem):
            b = None
            size = TRY_BASE + (1 if it.catch_reg is not None else len((it.catch_name or '').encode('utf-8')) + 1)
        else:
            raise TypeError(it)
        if b is not None:
            size = len(b)
        encoded.append(b)
        sizes.append(size)
        pos += size
    if size_check is not None:
        size_check(pos - base + 1 + 5)  # + End + the empty pool placeholder mtasc counts
    # Pass 2: emit, resolving label-dependent operands.
    out = bytearray()
    pos = base
    for it, size, enc in zip(code.items, sizes, encoded):
        if isinstance(it, BranchItem):
            if it.target.offset < 0 and it.target.name == 'break':
                delta = 0  # a `break` outside any loop: mtasc never patches the jump
            else:
                _check(it.target)
                delta = it.target.offset - (pos + size)
            out += avm1.encode_action(Action(it.code, offset=delta))
        elif isinstance(it, WithItem):
            _check(it.end)
            out += avm1.encode_action(Action(avm1.WITH, size=it.end.offset - (pos + size)))
        elif isinstance(it, TryItem):
            for lab in (it.catch_start, it.finally_start, it.end):
                _check(lab)
            body_start = pos + size
            flags = (1 if it.has_catch else 0) | (2 if it.has_finally else 0) | (4 if it.catch_reg is not None else 0)
            out += avm1.encode_action(Action(
                avm1.TRY, flags=flags, try_size=it.catch_start.offset - body_start,
                catch_size=it.finally_start.offset - it.catch_start.offset,
                finally_size=it.end.offset - it.finally_start.offset,
                catch_name=it.catch_name, catch_reg=it.catch_reg))
        else:
            out += enc
        pos += size
    return bytes(out)


def _check(label: Label) -> None:
    if label.offset < 0:
        raise ValueError(f'unplaced label {label.name!r}')
