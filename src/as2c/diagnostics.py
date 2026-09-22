"""Compiler diagnostics."""

from __future__ import annotations


class CompileError(Exception):
    """A user-facing compile error, positioned when we know where."""

    def __init__(self, message: str, pos=None):
        self.message = message
        self.pos = pos
        super().__init__(str(self))

    def __str__(self) -> str:
        if self.pos is None:
            return self.message
        return f'{self.pos.file}:{self.pos.line}: characters {self.pos.col}: {self.message}'
