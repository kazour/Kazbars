"""Typer — a port of mtasc's typer.ml.

Loads classes from the classpath (the bundled std headers included), checks types the way
mtasc does, and rewrites identifiers in place so the code generator knows what each name is:
`x` → `this.x` / `Cls.x` / `_global.x`, dotted paths → `EStatic` + fields, one-argument calls
on a class → `ECast`, `with` members → `EStatic(["__With"], x)`.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field

from . import ast
from .ast import (
    ARGV_POS,
    NULL_POS,
    EArray,
    EArrayDecl,
    EBinop,
    EBlock,
    EBreak,
    ECall,
    ECast,
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
    set_eval,
)
from .lexer import LexError, LineTable, read_source
from .parser import ParseError, parse

# ---------------------------------------------------------------------------------------------
# TYPES
# ---------------------------------------------------------------------------------------------


class _Singleton:
    def __init__(self, name: str):
        self.name = name

    def __repr__(self) -> str:
        return self.name


Void = _Singleton('Void')
Dyn = _Singleton('Dyn')


@dataclass(eq=False)
class Class:
    c: ClassContext

    def __eq__(self, other) -> bool:
        return isinstance(other, Class) and other.c is self.c

    __hash__ = object.__hash__


@dataclass(eq=False)
class Static:
    c: ClassContext

    def __eq__(self, other) -> bool:
        return isinstance(other, Static) and other.c is self.c

    __hash__ = object.__hash__


@dataclass(eq=False)
class Function:
    args: list
    ret: object

    def __eq__(self, other) -> bool:
        return isinstance(other, Function) and other.args == self.args and other.ret == self.ret

    __hash__ = object.__hash__


@dataclass(eq=False)
class Package:
    path: list

    def __eq__(self, other) -> bool:
        return isinstance(other, Package) and other.path == self.path

    __hash__ = object.__hash__


@dataclass
class ClassField:
    f_name: str
    f_type: object
    f_static: str
    f_public: str
    f_pos: Pos


@dataclass
class ImportPath:
    imp_path: tuple
    imp_pos: Pos
    imp_used: bool = False


@dataclass
class ImportWild:
    wimp_path: tuple
    wimp_pos: Pos
    wimp_used: bool = False


@dataclass
class Imports:
    paths: dict = field(default_factory=dict)
    wildcards: list = field(default_factory=list)


class ClassContext:
    def __init__(self, path, name, file, native, interface, dynamic, imports):
        self.path = path
        self.param: ClassContext | None = None
        self.name = name
        self.file = file
        self.native = native
        self.interface = interface
        self.dynamic = dynamic
        self.imports = imports
        self.fields: dict[str, ClassField] = {}
        self.statics: dict[str, ClassField] = {}
        self.super: ClassContext = self
        self.implements: list[ClassContext] = []
        self.constructor: ClassField | None = None
        # for the class generator
        self.sign = None  # the EClass / EInterface signature
        self.herits: list = []

    def __repr__(self) -> str:
        return f'<class {s_type_path(self.path)}>'


@dataclass
class Local:
    lt: object
    lf: int


class TyperError(Exception):
    """kind: 'Class_not_found' | 'Class_name_mistake' | 'Cannot_unify' | 'Custom'."""

    def __init__(self, kind: str, data, pos: Pos):
        self.kind = kind
        self.data = data
        self.pos = pos
        super().__init__(error_msg(kind, data))


class FileNotFound(Exception):
    def __init__(self, file: str):
        self.file = file
        super().__init__(f'File not found {file}')


def s_type_decl(t) -> str:
    if t is Void:
        return 'Void'
    if t is Dyn:
        return 'Any'
    if isinstance(t, Class):
        return s_type_path(t.c.path)
    if isinstance(t, Static):
        return '#' + s_type_path(t.c.path)
    if isinstance(t, Function):
        return 'function (' + ', '.join(s_type_decl(a) for a in t.args) + ') : ' + s_type_decl(t.ret)
    if isinstance(t, Package):
        return '.'.join(t.path)
    raise TypeError(t)


def error_msg(kind: str, data) -> str:
    if kind == 'Class_not_found':
        return 'class not found : ' + s_type_path(data)
    if kind == 'Class_name_mistake':
        return 'class name mistake : should be ' + s_type_path(data)
    if kind == 'Cannot_unify':
        ta, tb = data
        return s_type_decl(ta) + ' should be ' + s_type_decl(tb)
    return data


def error(kind: str, data, pos: Pos):
    raise TyperError(kind, data, pos)


def custom(msg: str, pos: Pos):
    raise TyperError('Custom', msg, pos)


@dataclass
class Options:
    strict_mode: bool = False
    local_inference: bool = False
    use_components: bool = False
    warn_imports: bool = False
    verbose: bool = False


# ---------------------------------------------------------------------------------------------
# CONTEXT
# ---------------------------------------------------------------------------------------------


class Context:
    def __init__(self, class_path: list[str], options: Options, warning):
        self.class_path = class_path
        self.options = options
        self.warning = warning
        self.files: dict[str, list] = {}  # file → signatures (insertion = load order)
        self.line_tables: dict[str, LineTable] = {}
        self.classes: dict[tuple, ClassContext] = {}
        self.in_static = True
        self.in_lambda: ClassContext | None = None
        self.in_constructor = False
        self.locals: dict[str, Local] = {}
        self.frame = 0
        self.inumber = None
        self.ibool = None
        self.istring = None
        self.returns = Void
        self.current: ClassContext | None = None
        self.curwith = None
        self.finalizers: list = []  # shared (a ref in OCaml)
        self.load_order: list[ClassContext] = []

    def derive(self, **overrides) -> Context:
        """`{ ctx with ... }` — a shallow copy sharing the tables and the finalizer list."""
        c = copy.copy(self)
        for k, v in overrides.items():
            setattr(c, k, v)
        return c

    def verbose(self, msg: str) -> None:
        if self.options.verbose:
            print(msg, flush=True)


def t_object(ctx: Context) -> ClassContext:
    return load_class(ctx, ((), 'Object'), NULL_POS)


def t_array(ctx: Context) -> ClassContext:
    return load_class(ctx, ((), 'Array'), NULL_POS)


def is_super(sup: ClassContext, c: ClassContext) -> bool:
    while True:
        if c is sup:
            return True
        if c.super is c:
            return False
        c = c.super


def is_number(ctx: Context, t) -> bool:
    return isinstance(t, Class) and t.c is ctx.inumber.c


def is_boolean(ctx: Context, t) -> bool:
    return isinstance(t, Class) and t.c is ctx.ibool.c


def is_string(ctx: Context, t) -> bool:
    return isinstance(t, Class) and t.c is ctx.istring.c


def resolve_path(ctx: Context, p: tuple, pos: Pos) -> ClassContext:
    pkg, n = p
    if pkg:
        return load_class(ctx, p, pos)
    for imp in ctx.current.imports.wildcards:
        try:
            cl = load_class(ctx, (imp.wimp_path, n), pos)
            imp.wimp_used = True
            return cl
        except TyperError as e:
            if e.kind == 'Class_not_found' and e.data == (imp.wimp_path, n):
                continue
            raise
    imp = ctx.current.imports.paths.get(n)
    if imp is not None:
        cl = load_class(ctx, imp.imp_path, pos)
        imp.imp_used = True
        return cl
    return load_class(ctx, p, pos)


def is_function(cl: ClassContext) -> bool:
    while True:
        if cl.path == ((), 'Function'):
            return True
        if cl.super is cl:
            return False
        cl = cl.super


def unify(ta, tb, p: Pos) -> None:
    """check that ta >= tb"""
    if ta is Dyn or tb is Dyn:
        return
    if ta is Void and tb is Void:
        return
    if isinstance(ta, Function) and isinstance(tb, Function):
        for x, y in zip(ta.args, tb.args):
            unify(x, y, p)
        unify(tb.ret, ta.ret, p)
        return
    if isinstance(ta, Class) and isinstance(tb, Class):
        cl1, cl2 = ta.c, tb.c

        def loop(c: ClassContext) -> bool:
            while True:
                if c is cl2 or any(loop(i) for i in c.implements):
                    return True
                if c.super is c:
                    return False
                c = c.super

        if not loop(cl1):
            if cl1.param is not None and cl2.param is not None and cl1.param is cl2.param:
                return
            error('Cannot_unify', (ta, tb), p)
        return
    if (isinstance(ta, Function) or isinstance(ta, Static)) and isinstance(tb, Class) and tb.c.super is tb.c:
        return  # unify with Object
    if isinstance(ta, Static) and isinstance(tb, Class) and is_function(tb.c):
        return
    if isinstance(ta, Class) and isinstance(tb, Static) and is_function(ta.c):
        return
    if isinstance(ta, Class) and isinstance(tb, Function) and is_function(ta.c):
        return
    if isinstance(ta, Function) and isinstance(tb, Class) and is_function(tb.c):
        return
    error('Cannot_unify', (ta, tb), p)


def unify_array(t1, t2, v, p: Pos) -> None:
    if isinstance(t2, Class) and t2.c.path[1] == 'Array' and len(t2.c.path[0]) == 1 and t2.c.path[0][0][0] == '#':
        if isinstance(v, ENew) and isinstance(v.e, EStatic) and v.e.path == ((), 'Array') and not v.args:
            return
        if isinstance(v, EArrayDecl):
            return
    unify(t1, t2, p)


def tcommon(ctx: Context, ta, tb, p: Pos):
    if ta is Void and tb is Void:
        return Void
    if ta is Void or tb is Void:
        error('Cannot_unify', (ta, tb), p)
    if ta is Dyn or tb is Dyn:
        return Dyn
    if isinstance(ta, (Function, Static)):
        return tcommon(ctx, Class(load_class(ctx, ((), 'Function'), NULL_POS)), tb, p)
    if isinstance(tb, (Function, Static)):
        return tcommon(ctx, ta, Class(load_class(ctx, ((), 'Function'), NULL_POS)), p)
    if isinstance(ta, Package) or isinstance(tb, Package):
        raise AssertionError('tcommon on a package')
    a, b = ta.c, tb.c

    def is_sub(cl1: ClassContext, cl2: ClassContext) -> bool:
        while True:
            if cl1 is cl2 or any(is_sub(cl1, i) for i in cl2.implements):
                return True
            if cl2.super is cl2:
                return False
            cl2 = cl2.super

    def parent(cl1: ClassContext, cl2: ClassContext):
        if is_sub(cl2, cl1):
            return cl2
        for i in cl2.implements:
            r = parent(cl1, i)
            if r is not None:
                return r
        if cl2.super is cl2:
            return None
        return parent(cl1, cl2.super)

    p1 = parent(a, b)
    p2 = parent(b, a)
    if p1 is None and p2 is None:
        return Class(t_object(ctx))
    if p1 is not None and p2 is None:
        return Class(p1)
    if p1 is None:
        return Class(p2)
    return Class(p2) if is_sub(p1, p2) else Class(p1)


def t_opt(ctx: Context, p: Pos, t):
    if t is None:
        if ctx.options.strict_mode and not ctx.current.native:
            custom('Type required in strict mode', p)
        return Dyn
    if t == ((), 'Void'):
        return Void
    return Class(resolve_path(ctx, t, p))


def has_return(any_: bool, e) -> bool:
    hr = lambda x: has_return(any_, x)  # noqa: E731
    if isinstance(e, (EVars, EFunction, EBreak, EContinue, EVal)):
        return False
    if isinstance(e, EReturn):
        return True if e.v is not None else any_
    if isinstance(e, EBlock):
        return any(hr(x) for x in e.el)
    if isinstance(e, EFor):
        return any(hr(x) for x in [e.body, *e.inits])
    if isinstance(e, EForIn):
        return hr(e.decl) or hr(e.body)
    if isinstance(e, EIf):
        return hr(e.e) or (e.eelse is not None and hr(e.eelse))
    if isinstance(e, EWhile):
        return hr(e.body)
    if isinstance(e, ESwitch):
        return any(hr(b) for _, b in e.cases)
    if isinstance(e, ETry):
        return hr(e.e) or any(hr(b) for _, _, b in e.catches) or (e.fo is not None and hr(e.fo))
    if isinstance(e, EWith):
        return hr(e.e)
    raise TypeError(e)


def ret_opt(ctx: Context, p: Pos, f):
    if f.fexpr is not None and not has_return(False, f.fexpr):
        if f.ftype is None or f.ftype == ((), 'Void'):
            return Void
        custom('Missing return of type ' + s_type_path(f.ftype), p)
    return t_opt(ctx, p, f.ftype)


def add_class_field(ctx: Context, clctx: ClassContext, fname: str, stat: str, pub: str, get: str, ft, p: Pos) -> None:
    if pub == 'IsPrivate' and clctx.interface:
        custom('Private fields are not possible in interfaces', p)
    if stat == 'IsStatic' and clctx.interface:
        custom('Static fields are not possible in interfaces', p)
    h = clctx.statics if stat == 'IsStatic' else clctx.fields
    f = h.get(fname)
    if get in ('Getter', 'Setter'):
        add_class_field(ctx, clctx, ('__get__' if get == 'Getter' else '__set__') + fname, stat, pub, 'Normal', ft, p)
        if get == 'Getter':
            assert isinstance(ft, Function)
            t = ft.ret
        else:
            assert isinstance(ft, Function)
            if len(ft.args) == 1:
                r = ft.ret
                if r is not Void and r is not Dyn:
                    custom('Setter should not return any value', p)
                t = ft.args[0]
            else:
                custom('Setter can only have one parameter', p)
        if f is None:
            nf = ClassField(fname, t, stat, pub, p)
        else:
            try:
                unify(f.f_type, t, f.f_pos)
                unify(t, f.f_type, p)
                ftype = t
            except TyperError as e:
                if e.kind == 'Cannot_unify' and ctx.options.use_components:
                    ftype = f.f_type
                else:
                    raise
            if pub != f.f_public:
                custom('Getter and setter have different public/private visibility', p)
            nf = ClassField(fname, ftype, stat, pub, p)
        h[fname] = nf
        return
    other = clctx.fields if stat == 'IsStatic' else clctx.statics
    if f is not None or fname in other:
        custom('Field redefiniton : ' + fname, p)
    h[fname] = ClassField(fname, ft, stat, pub, p)


def is_dynamic(t) -> bool:
    if t is Dyn or isinstance(t, (Function, Package)):
        return True
    if t is Void:
        return False
    return t.c.dynamic


def add_finalizer(ctx: Context, f) -> None:
    ctx.finalizers.append(f)


def no_void(t, p: Pos) -> None:
    if t is Void:
        custom('Void where Object expected', p)


def define_local(ctx: Context, name: str, t, p: Pos) -> None:
    if name in ctx.locals:
        custom('Local variable redefinition : ' + name, p)
    ctx.locals[name] = Local(t, ctx.frame)


def new_frame(ctx: Context) -> int:
    f = ctx.frame
    ctx.frame = f + 1
    return f


def clean_frame(ctx: Context, f: int) -> None:
    ctx.frame = f
    for n in [n for n, l in ctx.locals.items() if l.lf > f]:
        del ctx.locals[n]


def resolve(t, fname: str):
    if t is Void or t is Dyn or isinstance(t, Function):
        return None
    if isinstance(t, Package):
        return ClassField(fname, Package([*t.path, fname]), 'IsMember', 'IsPublic', NULL_POS)
    if isinstance(t, Static):
        c = t.c
        while True:
            f = c.statics.get(fname)
            if f is not None:
                return f
            if c.super is c:
                return None
            c = c.super
    c = t.c
    while True:
        f = c.fields.get(fname)
        if f is not None:
            return f
        if c.super is c:
            return None
        c = c.super


def type_ident(ctx: Context, name: str, e, p: Pos):
    # with lookup
    if ctx.curwith is not None:
        t = ctx.curwith
        if t is Dyn or isinstance(t, Function):
            set_eval(e, EStatic((('__With',), name), p))
            return Dyn
        if isinstance(t, Class):
            f = resolve(t, name)
            if f is not None:
                if f.f_public == 'IsPrivate' and not is_super(t.c, ctx.current):
                    custom('Cannot access private field', p)
                set_eval(e, EStatic((('__With',), name), p))
                return f.f_type
        else:
            raise AssertionError('bad with type')
    # local variable lookup
    l = ctx.locals.get(name)
    if l is not None:
        return l.lt
    # member variable lookup
    if name == ctx.current.path[1]:
        set_eval(e, EStatic(ctx.current.path, p))
        return Static(ctx.current)
    f = resolve(Class(ctx.current), name)
    if f is not None:
        if ctx.in_static:
            custom('Cannot access member variable ' + name + ' in static function', p)
        set_eval(e, EField(EConst(Ident('this'), p), name, p))
        return f.f_type
    # static variable lookup
    c = ctx.current
    while True:
        f = c.statics.get(name)
        if f is not None:
            set_eval(e, EField(EStatic(c.path, p), name, p))
            return f.f_type
        if c.super is c:
            break
        c = c.super
    f = resolve(Static(load_class(ctx, ((), 'TopLevel'), NULL_POS)), name)
    if f is not None:
        if f.f_public == 'IsPublic':
            set_eval(e, EField(EConst(Ident('_global'), p), name, p))
        return f.f_type
    if len(name) > 6 and name.startswith('_level') and name[6:].isdigit():
        return Class(load_class(ctx, ((), 'MovieClip'), NULL_POS))
    return Package([name])


def type_constant(ctx: Context, c, e, p: Pos):
    if isinstance(c, (Int, Float)):
        return ctx.inumber
    if isinstance(c, String):
        return ctx.istring
    name = c.s
    if name == '_root':
        return Class(load_class(ctx, ((), 'MovieClip'), p))
    if name in ('true', 'false'):
        return ctx.ibool
    if name in ('null', 'undefined', '_global'):
        return Dyn
    if name == 'this':
        if ctx.in_lambda is not None:
            return Dyn
        if ctx.in_static:
            custom('Cannot access this in static function', p)
        return Class(ctx.current)
    if name == 'super':
        if ctx.in_lambda is not None:
            return Dyn
        if ctx.in_static:
            custom('Cannot access super in static function', p)
        return Class(ctx.current.super)
    return type_ident(ctx, name, e, p)


class _Exit(Exception):
    pass


def resolve_package(ctx: Context, v, p: list, pos: Pos):
    cname, fields = p[0], p[1:]

    def access(path, l):
        if not l:
            return EStatic(path, pos)
        return EField(access(path, l[1:]), l[0], pos)

    def search_package(pth: list):
        rev = list(reversed(pth))
        acc: list = []
        for i, x in enumerate(rev):
            cpath = (tuple(reversed(rev[i + 1:])), x)
            try:
                cl = load_class(ctx, cpath, pos)
            except TyperError as e:
                if e.kind == 'Class_not_found' and e.data == cpath:
                    acc.insert(0, x)
                    continue
                raise
            vv = access(cl.path, list(reversed(acc)))
            set_eval(v, vv)
            t = Static(cl)
            for f in acc:
                t = type_field(ctx, t, f, pos)
            return t
        raise _Exit()

    imp = ctx.current.imports.paths.get(cname)
    if imp is not None:
        candidates = [([*imp.imp_path[0], imp.imp_path[1], *fields], lambda imp=imp: setattr(imp, 'imp_used', True))]
    else:
        candidates = [([cname, *fields], lambda: None)]
    for wimp in ctx.current.imports.wildcards:
        candidates.append(([*wimp.wimp_path, cname, *fields], lambda wimp=wimp: setattr(wimp, 'wimp_used', True)))
    for pth, use in candidates:
        try:
            r = search_package(pth)
            use()
            return r
        except _Exit:
            continue
    last = p[-1]
    if last and 'A' <= last[0] <= 'Z':
        custom('Unknown class ' + '.'.join(p), pos)
    custom('Unknown variable ' + p[0], pos)


def type_field(ctx: Context, t, f: str, p: Pos):
    r = resolve(t, f)
    if r is None:
        if not is_dynamic(t):
            shown = Class(t.c) if isinstance(t, Static) else t
            custom(s_type_decl(shown) + ' has no ' + ('static ' if isinstance(t, Static) else '') + 'field ' + f, p)
        return Dyn
    if r.f_public == 'IsPrivate' and isinstance(t, (Class, Static)):
        c = t.c
        if not is_super(c, ctx.current):
            if ctx.in_lambda is None or not is_super(c, ctx.in_lambda):
                custom('Cannot access private field ' + r.f_name, p)
    return r.f_type


def type_binop(ctx: Context, op, v1, v2, p: Pos):
    t1 = type_val(ctx, v1)
    t2 = type_val(ctx, v2)
    no_void(t1, v1.pos)
    no_void(t2, v2.pos)

    def loop(op):
        if op == 'OpAdd':
            if t1 is Dyn or t2 is Dyn:
                return Dyn
            if is_number(ctx, t1) and is_number(ctx, t2):
                return ctx.inumber
            return ctx.istring
        if op in ('OpAnd', 'OpOr', 'OpXor', 'OpShl', 'OpShr', 'OpUShr', 'OpMod', 'OpMult', 'OpDiv', 'OpSub'):
            unify(t1, ctx.inumber, p)
            unify(t2, ctx.inumber, p)
            return ctx.inumber
        if op == 'OpAssign':
            unify_array(t2, t1, v2, p)
            return t1
        if op in ('OpEq', 'OpPhysEq', 'OpPhysNotEq', 'OpNotEq', 'OpGt', 'OpGte', 'OpLt', 'OpLte'):
            return ctx.ibool
        if op in ('OpBoolAnd', 'OpBoolOr'):
            return tcommon(ctx, t1, t2, p)
        if isinstance(op, tuple):
            t = loop(op[1])
            unify(t, t1, p)
            return t1
        raise ValueError(op)

    return loop(op)


def type_val(ctx: Context, e, in_field: bool = False):
    if isinstance(e, EConst):
        t = type_constant(ctx, e.c, e, e.pos)
        if isinstance(t, Package) and not in_field:
            return resolve_package(ctx, e, t.path, e.pos)
        return t
    if isinstance(e, ECast):
        t = type_val(ctx, e.a)
        type_val(ctx, e.b)
        if isinstance(t, Static):
            return Class(t.c)
        custom('Casting to not a class', e.a.pos)
    if isinstance(e, EArray):
        t = type_val(ctx, e.a)
        type_val(ctx, e.b)
        if isinstance(t, Class) and t.c.param is not None:
            return Class(t.c.param)
        return Dyn
    if isinstance(e, EBinop):
        return type_binop(ctx, e.op, e.a, e.b, e.pos)
    if isinstance(e, EField):
        t = type_val(ctx, e.e, in_field=True)
        t = type_field(ctx, t, e.name, e.pos)
        if isinstance(t, Package) and not in_field:
            t = resolve_package(ctx, e, t.path, e.pos)
        v = e.e if isinstance(e, EField) else None
        if isinstance(v, EStatic) and e.name != 'prototype' and v.path[0] != ('__With',):
            cl = load_class(ctx, v.path, v.pos)
            while True:
                if e.name in cl.statics:
                    path = cl.path
                    break
                if cl.super is cl:
                    path = v.path
                    break
                cl = cl.super
            set_eval(v, EStatic(path, v.pos))
        return t
    if isinstance(e, EStatic):
        c = resolve_path(ctx, e.path, e.pos)
        set_eval(e, EStatic(c.path, e.pos))
        return Static(c)
    if isinstance(e, EParenthesis):
        return type_val(ctx, e.e)
    if isinstance(e, EObjDecl):
        for _, v in e.fields:
            no_void(type_val(ctx, v), v.pos)
        return Class(t_object(ctx))
    if isinstance(e, EArrayDecl):
        for v in e.items:
            no_void(type_val(ctx, v), v.pos)
        return Class(t_array(ctx))
    if isinstance(e, ECall):
        callee = e.e
        if isinstance(callee, EConst) and isinstance(callee.c, Ident) and callee.c.s == 'super':
            if not ctx.in_constructor:
                custom('Super constructor can only be called in class constructor', e.pos)
            args = [type_val(ctx, a) for a in e.args]
            ctor = ctx.current.super.constructor
            if ctor is not None:
                unify(Function(args, Void), ctor.f_type, e.pos)
            return Void
        t = type_val(ctx, callee)
        if isinstance(t, Function):
            fargs = t.args
            for i, v in enumerate(e.args):
                if i < len(fargs):
                    unify(type_val(ctx, v), fargs[i], v.pos)
                else:
                    type_val(ctx, v)
            return t.ret
        if t is Dyn:
            for v in e.args:
                no_void(type_val(ctx, v), v.pos)
            return Dyn
        if isinstance(t, Class) and is_function(t.c):
            for v in e.args:
                no_void(type_val(ctx, v), v.pos)
            return Dyn
        if isinstance(t, Static) and len(e.args) == 1:
            type_val(ctx, e.args[0])
            set_eval(e, ECast(callee, e.args[0], e.pos))
            return Class(t.c)
        custom('Cannot call non-function object ' + s_type_decl(t), callee.pos)
    if isinstance(e, EQuestion):
        no_void(type_val(ctx, e.cond), e.cond.pos)
        t1 = type_val(ctx, e.a)
        t2 = type_val(ctx, e.b)
        return tcommon(ctx, t1, t2, e.pos)
    if isinstance(e, EUnop):
        if e.op == 'Not':
            no_void(type_val(ctx, e.e), e.e.pos)
            return ctx.ibool
        unify(type_val(ctx, e.e), ctx.inumber, e.e.pos)
        return ctx.inumber
    if isinstance(e, ENew):
        args = [type_val(ctx, a) for a in e.args]
        t = type_val(ctx, e.e)
        if isinstance(t, Static):
            cl = t.c
            ctor = cl.constructor
            if ctor is not None:
                if ctor.f_public == 'IsPrivate' and not is_super(cl, ctx.current):
                    custom('Cannot call private constructor', e.pos)
                unify(Function(args, Dyn), ctor.f_type, e.pos)
            return Class(cl)
        if t is Dyn:
            return Dyn
        if isinstance(t, Class) and is_function(t.c):
            return Dyn
        custom('Invalid type : ' + s_type_decl(t) + ' for new call', e.pos)
    if isinstance(e, ELambda):
        return type_function(ctx, t_object(ctx), e.f, e.pos, lambda_=True)
    raise TypeError(e)


def type_expr(ctx: Context, e) -> None:
    if isinstance(e, EVars):
        for name, tt, v in e.vl:
            if ctx.options.local_inference and v is not None and tt is None:
                t = Dyn
            else:
                t = t_opt(ctx, e.pos, tt)
            if v is not None:
                tv = type_val(ctx, v)
                unify_array(tv, t, v, v.pos)
                if ctx.options.local_inference and tt is None:
                    t = tv
            define_local(ctx, name, t, e.pos)
        return
    if isinstance(e, EFunction):
        raise AssertionError('nested function declaration')
    if isinstance(e, EBlock):
        f = new_frame(ctx)
        for x in e.el:
            type_expr(ctx, x)
        clean_frame(ctx, f)
        return
    if isinstance(e, EFor):
        f = new_frame(ctx)
        for x in e.inits:
            type_expr(ctx, x)
        for v in e.conds:
            no_void(type_val(ctx, v), v.pos)
        for v in e.incrs:
            type_val(ctx, v)
        type_expr(ctx, e.body)
        clean_frame(ctx, f)
        return
    if isinstance(e, EForIn):
        f = new_frame(ctx)
        decl = e.decl
        if isinstance(decl, EVal) and isinstance(decl.v, EConst) and isinstance(decl.v.c, Ident):
            t = type_val(ctx, decl.v)
            unify(ctx.istring, t, decl.pos)
            unify(t, ctx.istring, decl.pos)
        elif isinstance(decl, EVars) and len(decl.vl) == 1 and decl.vl[0][2] is None:
            x, t, _ = decl.vl[0]
            unify(ctx.istring, t_opt(ctx, decl.pos, t), decl.pos)
            define_local(ctx, x, ctx.istring, decl.pos)
        else:
            custom('Invalid forin parameter', e.pos)
        no_void(type_val(ctx, e.v), e.v.pos)
        type_expr(ctx, e.body)
        clean_frame(ctx, f)
        return
    if isinstance(e, EIf):
        no_void(type_val(ctx, e.cond), e.cond.pos)
        type_expr(ctx, e.e)
        if e.eelse is not None:
            type_expr(ctx, e.eelse)
        return
    if isinstance(e, EWhile):
        no_void(type_val(ctx, e.cond), e.cond.pos)
        type_expr(ctx, e.body)
        return
    if isinstance(e, ESwitch):
        t = type_val(ctx, e.v)
        for v, body in e.cases:
            if v is not None:
                unify(type_val(ctx, v), t, v.pos)
            type_expr(ctx, body)
        return
    if isinstance(e, ETry):
        type_expr(ctx, e.e)
        no_type = False
        new_catches = []
        for name, t, body in e.catches:
            if no_type:
                custom('Misplaced catch will fail to catch any exception', body.pos)
            if t is None:
                no_type = True
                t2 = None
            else:
                t2 = resolve_path(ctx, t, e.pos).path
            f = new_frame(ctx)
            define_local(ctx, name, t_opt(ctx, e.pos, t), e.pos)
            type_expr(ctx, body)
            clean_frame(ctx, f)
            new_catches.append((name, t2, body))
        e.catches[:] = new_catches
        if e.fo is not None:
            type_expr(ctx, e.fo)
        return
    if isinstance(e, EWith):
        old_with = ctx.curwith
        t = type_val(ctx, e.v)
        if t is Void or isinstance(t, Static):
            custom("Invalid type for 'with' argument", e.pos)
        if isinstance(t, Package):
            raise AssertionError('with on a package')
        ctx.curwith = t
        type_expr(ctx, e.e)
        ctx.curwith = old_with
        return
    if isinstance(e, EReturn):
        if e.v is None:
            if ctx.returns is not Void and ctx.returns is not Dyn:
                custom('Return type cannot be Void', e.pos)
        else:
            unify(type_val(ctx, e.v), ctx.returns, e.v.pos)
        return
    if isinstance(e, (EBreak, EContinue)):
        return
    if isinstance(e, EVal):
        type_val(ctx, e.v)
        return
    raise TypeError(e)


def type_function(ctx: Context, clctx: ClassContext, f, p: Pos, lambda_: bool = False):
    assert f.fexpr is not None
    if not lambda_:
        ctx.verbose('Typing ' + s_type_path(clctx.path) + '.' + f.fname)
    if lambda_:
        cur = copy.copy(clctx)
        cur.imports = ctx.current.imports
        cur.native = False
        in_lambda = ctx.current if ctx.in_lambda is None else ctx.in_lambda
        locals_ = ctx.locals
    else:
        cur = clctx
        in_lambda = None
        locals_ = {}
    ctx = ctx.derive(current=cur, locals=locals_, in_static=(f.fstatic == 'IsStatic'),
                     in_constructor=(f.fstatic == 'IsMember' and f.fname == clctx.name),
                     in_lambda=in_lambda, curwith=None)
    fr = new_frame(ctx)
    ctx.returns = ret_opt(ctx, p, f)
    argst = []
    for a, t in f.fargs:
        at = t_opt(ctx, p, t)
        define_local(ctx, a, at, p)
        argst.append(at)
    type_expr(ctx, f.fexpr)
    clean_frame(ctx, fr)
    return Function(argst, ctx.returns)


def type_class_fields(ctx: Context, clctx: ClassContext, comp: bool, e) -> None:
    if isinstance(e, EBlock):
        for x in e.el:
            type_class_fields(ctx, clctx, comp, x)
        return
    if isinstance(e, EVars):
        if clctx.interface:
            custom('Interface cannot contain variable declaration', e.pos)
        for vname, vtype, vinit in e.vl:
            t = t_opt(ctx, e.pos, vtype)
            add_class_field(ctx, clctx, vname, e.static, e.public, 'Normal', t, e.pos)
            if vinit is not None and not comp:
                def fin(v=vinit, t=t, p=e.pos):
                    ctx.current = clctx
                    unify(type_val(ctx, v), t, p)
                add_finalizer(ctx, fin)
        return
    if isinstance(e, EFunction):
        f = e.f
        t = Function([t_opt(ctx, e.pos, at) for _, at in f.fargs], ret_opt(ctx, e.pos, f))
        if f.fname == clctx.path[1]:
            if f.ftype is not None:
                custom('Constructor return type should not be specified', e.pos)
            if clctx.interface:
                custom("Interface can't have a constructor", e.pos)
            if clctx.constructor is not None:
                custom('Duplicate constructor', e.pos)
            clctx.constructor = ClassField(f.fname, t, 'IsMember', f.fpublic, NULL_POS)
        else:
            add_class_field(ctx, clctx, f.fname, f.fstatic, f.fpublic, f.fgetter, t, e.pos)
        if f.fexpr is not None and not comp:
            add_finalizer(ctx, lambda f=f, p=e.pos: type_function(ctx, clctx, f, p))
        return
    raise AssertionError('bad class member')


def type_class(ctx: Context, cpath, herits, e, imports: Imports, file: str, interf: bool, native: bool, s) -> ClassContext:
    old = ctx.current
    clctx = ClassContext(cpath, cpath[1], file, native, interf, 'HDynamic' in herits, imports)
    clctx.sign = s
    imports.paths[clctx.name] = ImportPath(clctx.path, s.pos, True)
    if cpath in ctx.classes:
        custom('Redefinition of class ' + s_type_path(cpath) + ', please check using -v that the file is not referenced several times', s.pos)
    ctx.classes[cpath] = clctx
    ctx.load_order.append(clctx)
    ctx.current = clctx
    resolved = []
    for h in herits:
        if isinstance(h, tuple) and h[0] == 'HExtends':
            resolved.append(('HExtends', resolve_path(ctx, h[1], e.pos).path))
        elif isinstance(h, tuple) and h[0] == 'HImplements':
            resolved.append(('HImplements', resolve_path(ctx, h[1], e.pos).path))
        else:
            resolved.append(h)
    herits = resolved
    is_component = ctx.options.use_components and clctx.path[0][:1] == ('mx',)
    if is_component:
        herits = ['HIntrinsic', *herits]
    s.herits = herits
    clctx.herits = herits
    # superclass
    sup = None
    seen_extends = False
    for h in herits:
        if isinstance(h, tuple) and h[0] == 'HExtends':
            if seen_extends:
                custom('Multiple inheritance is not allowed', e.pos)
            seen_extends = True
            cl = resolve_path(ctx, h[1], e.pos)
            if clctx.interface and not cl.interface:
                custom('Interface cannot extends a class', e.pos)
            sup = cl
    clctx.super = sup if sup is not None else t_object(ctx)
    if clctx.super.interface and not clctx.interface:
        custom('Cannot extends an interface', e.pos)
    impls = []
    for h in herits:
        if isinstance(h, tuple) and h[0] == 'HImplements':
            c = resolve_path(ctx, h[1], e.pos)
            if clctx.interface:
                custom('Interface cannot implements another interface, use extends', e.pos)
            if not c.interface:
                custom('Cannot implements a class', e.pos)
            impls.append(c)
    clctx.implements = impls
    type_class_fields(ctx, clctx, is_component, e)
    ctx.current = old
    return clctx


def type_file(ctx: Context, req_path, file: str, el: list, pos: Pos) -> ClassContext | None:
    clctx = None
    imports = Imports()

    def clerror(t, p: Pos):
        if pos == ARGV_POS:
            return
        if s_type_path(req_path).lower() == s_type_path(t).lower():
            ctx.files.pop(file, None)
            error('Class_not_found', req_path, pos)
        else:
            names = os.listdir(os.path.dirname(file) or '.')
            if os.path.basename(file) in names:
                error('Class_name_mistake', req_path, p)
            error('Class_name_mistake', t, pos)

    for s in el:
        if isinstance(s, EClass):
            if s.path != req_path:
                clerror(s.path, s.e.pos)
            if clctx is not None:
                custom('Cannot declare several classes in same file', s.pos)
            clctx = type_class(ctx, s.path, s.herits, s.e, imports, file, False, 'HIntrinsic' in s.herits, s)
        elif isinstance(s, EInterface):
            if s.path != req_path:
                clerror(s.path, s.e.pos)
            if clctx is not None:
                custom('Cannot declare several classes in same file', s.pos)
            clctx = type_class(ctx, s.path, s.herits, s.e, imports, file, True, False, s)
        elif isinstance(s, EImport):
            if s.name is not None:
                if s.name in imports.paths:
                    custom('Duplicate Import', s.pos)
                imports.paths[s.name] = ImportPath((s.pkg, s.name), s.pos, False)
            else:
                imports.wildcards.insert(0, ImportWild(s.pkg, s.pos, False))
    if ctx.options.warn_imports and (not ctx.options.use_components or not (clctx is not None and clctx.path[0][:1] == ('mx',))):
        def warn():
            for imp in imports.paths.values():
                if not imp.imp_used:
                    ctx.warning('import not used', imp.imp_pos)
            for imp in imports.wildcards:
                if not imp.wimp_used:
                    ctx.warning('import not used', imp.wimp_pos)
        add_finalizer(ctx, warn)
    return clctx


def load_file(ctx: Context, file: str) -> tuple[str, list]:
    for path in ctx.class_path:
        full = path + file
        try:
            src = read_source(full)
        except OSError:
            continue
        sigs, _ = parse(src, full, ctx.warning,
                        on_lexer=lambda lx, full=full: ctx.line_tables.__setitem__(full, LineTable(lx.lines)))
        for s in sigs:
            ast.check_sign(s)
        ctx.files[full] = sigs
        ctx.verbose('Parsed ' + full)
        return full, sigs
    raise FileNotFound(file)


def load_class(ctx: Context, path, p: Pos) -> ClassContext:
    pkg, name = path
    if name == 'Array' and len(pkg) == 1 and pkg[0][:1] == '#':
        cl = load_class(ctx, ((), 'ArrayPoly'), p)
        parts = pkg[0][1:].split('.')
        path2 = (tuple(parts[:-1]), parts[-1])
        cl2 = resolve_path(ctx, path2, p)
        arr = copy.copy(cl)
        arr.path = path
        arr.param = cl2
        arr.fields = {}
        arr.statics = {}
        arr.implements = []
        arr.constructor = None

        def map_type(t):
            if isinstance(t, Class) and t.c.path == ((), 'ArrayParam'):
                return Class(cl2)
            if isinstance(t, Class) and t.c.path == (('#ArrayParam',), 'Array'):
                return Class(arr)
            if isinstance(t, Function):
                return Function([map_type(a) for a in t.args], map_type(t.ret))
            return t

        for s, f in cl.fields.items():
            arr.fields[s] = ClassField(f.f_name, map_type(f.f_type), f.f_static, f.f_public, f.f_pos)
        return arr
    found = ctx.classes.get(path)
    if found is not None:
        return found
    if name.lower() == 'con':
        custom("CON is a special file under Windows and shouldn't be used as class name", p)
    file_name = name + '.as' if not pkg else '/'.join(pkg) + '/' + name + '.as'
    try:
        f, e = load_file(ctx, file_name)
    except FileNotFound:
        error('Class_not_found', path, p)
    c = type_file(ctx, path, f, e, p)
    if c is None:
        custom('Missing class definition', Pos(file_name, 0, 0))
    return c


def check_interfaces(ctx: Context) -> None:
    for clctx in list(ctx.classes.values()):
        cli = Class(clctx)

        def loopeq(variance: bool, t1, t2) -> bool:
            if t1 is Void and t2 is Void:
                return True
            if t1 is Dyn:
                return True
            if isinstance(t1, Class) and isinstance(t2, Class):
                cl1, cl2 = t1.c, t2.c
                if cl1.path == cl2.path:
                    return True
                try:
                    t = tcommon(ctx, Class(cl1), Class(cl2), NULL_POS)
                except Exception:
                    t = Dyn
                if isinstance(t, Class) and t.c.path == cl1.path:
                    return variance
                if isinstance(t, Class) and t.c.path == cl2.path:
                    return not variance
                return False
            if isinstance(t1, Function) and isinstance(t2, Function) and len(t1.args) == len(t2.args):
                return all(loopeq(True, a, b) for a, b in zip(t1.args, t2.args)) and loopeq(False, t1.ret, t2.ret)
            return False

        def loop_fields(i: ClassContext, cli=cli, clctx=clctx):
            if i.super.interface:
                loop_fields(i.super)
            for f in i.fields.values():
                if f.f_static != 'IsMember':
                    continue
                f2 = resolve(cli, f.f_name)
                if f2 is None:
                    custom('Missing field ' + f.f_name + ' required by ' + s_type_path(i.path), Pos(clctx.file, 0, 0))
                if f2.f_public == 'IsPrivate':
                    custom('Field ' + f.f_name + ' is declared in an interface and should be public', f2.f_pos)
                unify(f2.f_type, f.f_type, f2.f_pos)
                if not loopeq(True, f.f_type, f2.f_type):
                    custom('Field ' + f.f_name + ' type is different from the one defined in ' + s_type_path(i.path), f2.f_pos)

        for i in clctx.implements:
            loop_fields(i)


def create(class_path: list[str], options: Options | None = None, warning=None) -> Context:
    ctx = Context(class_path, options or Options(), warning or (lambda msg, pos: None))
    load_class(ctx, ((), 'StdPresent'), NULL_POS)
    ctx.inumber = Class(load_class(ctx, ((), 'Number'), NULL_POS))
    ctx.ibool = Class(load_class(ctx, ((), 'Boolean'), NULL_POS))
    ctx.istring = Class(load_class(ctx, ((), 'String'), NULL_POS))
    return ctx


def finalize(ctx: Context) -> None:
    while ctx.finalizers:
        fl = ctx.finalizers[:]
        ctx.finalizers.clear()
        for f in fl:
            f()
    check_interfaces(ctx)


__all__ = [
    'Context',
    'FileNotFound',
    'LexError',
    'Options',
    'ParseError',
    'TyperError',
    'create',
    'finalize',
    'load_class',
]
