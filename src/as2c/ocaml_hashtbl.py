"""Just enough of OCaml 3.x's `Hashtbl` to reproduce mtasc's iteration order.

mtasc registers a class's getters/setters by iterating a `Hashtbl` keyed on
`(name, getter_flag, static_flag)`; the emitted `addProperty` calls therefore come out in the
table's bucket order, which depends on OCaml's polymorphic hash and its resize policy. This is
the 3.10-era implementation (mtasc 1.14, 2008): `Hashtbl.hash` = `hash_univ_param 10 100`,
buckets grow 1 → 3 → 7 → 15 (2n+1) when size > 2 × buckets, bucket index = hash mod buckets,
chains are newest-first and keep their order across resizes.
"""

from __future__ import annotations

ALPHA = 65599
BETA = 19
MASK32 = 0xFFFFFFFF


class _Hasher:
    def __init__(self, count: int = 10, limit: int = 100):
        self.accu = 0
        self.count = count
        self.limit = limit

    def combine(self, n: int) -> None:
        self.accu = (self.accu * ALPHA + n) & MASK32

    def combine_small(self, n: int) -> None:
        self.accu = (self.accu * BETA + n) & MASK32

    def aux(self, v) -> None:
        self.limit -= 1
        if self.count < 0 or self.limit < 0:
            return
        if isinstance(v, bool):
            v = int(v)
        if isinstance(v, int):  # immediate
            self.count -= 1
            self.combine(v & MASK32)
            return
        if isinstance(v, str):  # String_tag: bytes of the (latin-1 / utf-8) string
            self.count -= 1
            for b in v.encode('latin-1', 'replace') if all(ord(ch) < 256 for ch in v) else v.encode('utf-8'):
                self.combine_small(b)
            return
        if isinstance(v, tuple):  # structured block, tag 0, fields hashed last to first
            self.count -= 1
            self.combine_small(0)
            for field in reversed(v):
                self.aux(field)
            return
        raise TypeError(f'cannot hash {v!r}')


def ocaml_hash(v) -> int:
    h = _Hasher()
    h.aux(v)
    return h.accu & 0x3FFFFFFF


class Hashtbl:
    """Insertion-compatible subset: add / mem / iter (in OCaml order)."""

    def __init__(self, initial_size: int = 0):
        self.buckets: list[list] = [[] for _ in range(max(1, initial_size))]  # each list newest-first
        self.size = 0

    def _index(self, key, nbuckets: int) -> int:
        return ocaml_hash(key) % nbuckets

    def add(self, key, value=None) -> None:
        i = self._index(key, len(self.buckets))
        self.buckets[i].insert(0, (key, value))
        self.size += 1
        if self.size > len(self.buckets) * 2:
            self._resize()

    def _resize(self) -> None:
        nsize = 2 * len(self.buckets) + 1
        ndata: list[list] = [[] for _ in range(nsize)]
        for bucket in self.buckets:
            # oldest first so that the new chains keep the original relative order
            for key, value in reversed(bucket):
                ndata[self._index(key, nsize)].insert(0, (key, value))
        self.buckets = ndata

    def mem(self, key) -> bool:
        return any(k == key for bucket in self.buckets for k, _ in bucket)

    def items(self):
        for bucket in self.buckets:
            yield from bucket

    def keys(self):
        for k, _ in self.items():
            yield k
