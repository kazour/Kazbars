"""Class generation order — a port of mtasc's class.ml.

Builds one `GenClass` per typed class (its methods in source order, its initialised variables,
its constructor) and drives generation so that a class's superclass, interfaces and the classes
referenced by its static initialisers are generated first. mtasc's outer iteration order is an
OCaml hashtable's; ours is the load order, which is deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import ast
from .ast import (
    EArray,
    EArrayDecl,
    EBinop,
    EBlock,
    ECall,
    ECast,
    EClass,
    EConst,
    EField,
    EFunction,
    EInterface,
    ELambda,
    ENew,
    EObjDecl,
    EParenthesis,
    EQuestion,
    EStatic,
    EUnop,
    EVars,
    s_type_path,
)


@dataclass(eq=False)
class GenClass:
    path: tuple
    herits: list
    expr: object  # the class body (EBlock)
    filename: str
    is_interface: bool
    classes: dict = field(repr=False)
    vars: dict = field(default_factory=dict)  # name → static flag
    interfaces: list = field(default_factory=list)
    superclass: GenClass | None = None
    constructor: object = None  # Func | None
    generated: str = 'NotYet'
    initvars: list = field(default_factory=list)  # [(name, static flag, eval)]
    methods: list = field(default_factory=list)  # [Func]

    @property
    def intrinsic(self) -> bool:
        return 'HIntrinsic' in self.herits

    def is_getset(self, v: str) -> bool:
        c = self.superclass
        if c is None:
            return False
        return any(f.fname == v and f.fgetter != 'Normal' for f in c.methods)


def _add_class(h: dict, fname: str, sign) -> None:
    h[sign.path] = GenClass(sign.path, sign.herits, sign.e, fname, isinstance(sign, EInterface), h)


def _class_vars(h: dict, gen, clctx: GenClass, e) -> None:
    if isinstance(e, EVars):
        for name, _, vinit in e.vl:
            clctx.vars[name] = e.static
            if vinit is not None:
                clctx.initvars.append((name, e.static, vinit))
                if e.static == 'IsStatic':
                    _static_refs(h, gen, clctx, vinit)
    elif isinstance(e, EFunction):
        f = e.f
        if f.fname == clctx.path[1]:
            clctx.constructor = f
        else:
            clctx.vars[f.fname] = f.fstatic
            clctx.methods.append(f)
    elif isinstance(e, EBlock):
        for x in e.el:
            _class_vars(h, gen, clctx, x)
    else:
        raise AssertionError('bad class member')


def _static_refs(h: dict, gen, clctx: GenClass, v) -> None:
    def check(p):
        c2 = h.get(p)
        if c2 is None:
            raise AssertionError(f'static reference to unknown class {s_type_path(p)}')
        if c2 is not clctx:
            generate_class(h, gen, c2)

    def loop(v):
        if isinstance(v, (EField, EParenthesis, EUnop)):
            loop(v.e)
        elif isinstance(v, (EArray, ECast, EBinop)):
            loop(v.a)
            loop(v.b)
        elif isinstance(v, EObjDecl):
            for _, x in v.fields:
                loop(x)
        elif isinstance(v, EArrayDecl):
            for x in v.items:
                loop(x)
        elif isinstance(v, ECall):
            loop(v.e)
            for x in v.args:
                loop(x)
        elif isinstance(v, EQuestion):
            loop(v.cond)
            loop(v.a)
            loop(v.b)
        elif isinstance(v, EStatic):
            check(v.path)
        elif isinstance(v, ENew):
            loop(v.e)
            for x in v.args:
                loop(x)
        elif isinstance(v, (EConst, ELambda)):
            pass
        else:
            raise TypeError(v)

    loop(v)


def generate_class(h: dict, gen, clctx: GenClass) -> None:
    if clctx.generated == 'Done':
        return
    if clctx.generated == 'Generating':
        import sys
        print('Warning : loop in generation for class ' + s_type_path(clctx.path), file=sys.stderr)
        return
    clctx.generated = 'Generating'
    for herit in clctx.herits:
        if herit in ('HIntrinsic', 'HDynamic'):
            continue
        kind, path = herit
        hctx = h[path]
        if kind == 'HExtends' and not clctx.is_interface:
            clctx.superclass = hctx
            generate_class(h, gen, hctx)
        else:
            clctx.interfaces.insert(0, hctx)
            generate_class(h, gen, hctx)
    _class_vars(h, gen, clctx, clctx.expr)
    gen(clctx)
    clctx.generated = 'Done'


def generate(gen, files: dict) -> None:
    """files: file → signatures, in load order."""
    h: dict = {}
    for fname, el in files.items():
        for s in el:
            if isinstance(s, (EClass, EInterface)):
                _add_class(h, fname, s)
    for cl in list(h.values()):
        generate_class(h, gen, cl)


__all__ = ['GenClass', 'generate', 'generate_class']
_ = ast
