"""The compile driver — mtasc's main.ml: classpath assembly, typing, generation, injection."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import ast, avm1, classgen, gen, swf, typer
from .diagnostics import CompileError
from .inject import inject
from .lexer import LexError, LineTable
from .parser import ParseError

PACKAGE_DIR = Path(__file__).resolve().parent


@dataclass
class Options:
    version: int = 8
    keep: bool = False
    frame: int = 1
    main: bool = False
    header: str | None = None
    trace: str | None = None
    strict: bool = False
    infer: bool = False
    warn_imports: bool = False
    msvc: bool = False
    verbose: bool = False


@dataclass
class Result:
    classes: list[tuple[str, bytes]]
    warnings: list[str] = field(default_factory=list)


def normalize_path(p: str) -> str:
    if not p:
        return './'
    return p if p[-1] in '\\/' else p + '/'


def parse_class_path(base_path: str, path: str) -> list[str]:
    out: list[str] = []
    for part in path.split(';'):
        if not part:
            continue
        fp = normalize_path(part)
        if len(fp) >= 2 and (fp[0] == '/' or fp[0] == '.' or fp[1] == ':'):
            out.append(fp)
        else:
            out.append(fp)
            out.append(base_path + fp)
    return out


def class_name(file: str) -> tuple:
    """mtasc's Main.class_name: (directory segments, basename without extension)."""
    path = os.path.dirname(file)
    segs = [s for s in re.split(r'[/\\]', path) if s != '']
    if segs[:1] == ['.']:
        segs = segs[1:]
    base = os.path.basename(file)
    stem = base.rsplit('.', 1)[0] if '.' in base else base
    return tuple(segs), stem


def build_class_path(classpaths: list[str], version: int, base_path: str) -> list[str]:
    cp = [base_path, '', '/']
    for p in classpaths:
        cp = parse_class_path(base_path, p) + cp
    cp = [base_path + 'std/', *cp]
    if version >= 8:
        cp = [base_path + 'std8/', *cp]
    return cp


class Reporter:
    def __init__(self, ctx_holder: dict, msvc: bool = False):
        self.ctx_holder = ctx_holder
        self.msvc = msvc
        self.warnings: list[str] = []

    def epos(self, p: ast.Pos) -> str:
        if p.pmin == -1:
            return '(unknown)'
        ctx = self.ctx_holder.get('ctx')
        table = ctx.line_tables.get(p.file) if ctx is not None else None
        if table is None:
            table = LineTable([])
        l1, p1 = table.find(p.pmin)
        l2, p2 = table.find(p.pmax)
        head = f'{p.file}({l1}):' if self.msvc else f'{p.file}:{l1}:'
        if l1 == l2:
            s = f' {p1}' if p1 == p2 else f's {p1}-{p2}'
            return f'{head} character{s}'
        return f'{head} lines {l1}-{l2}'

    def format(self, msg: str, p: ast.Pos, etype: str) -> str:
        return f'{self.epos(p)} : {etype} {msg}'

    def warning(self, msg: str, p: ast.Pos) -> None:
        self.warnings.append(self.format(msg, p, 'Warning'))


def compile_classes(classpaths: list, entries: list, options: Options | None = None,
                    base_path: str | None = None) -> Result:
    """Type and generate every reachable class. Raises CompileError with mtasc's message."""
    options = options or Options()
    base_path = normalize_path(base_path or str(PACKAGE_DIR))
    holder: dict = {}
    rep = Reporter(holder, options.msvc)
    cp = build_class_path([str(p) for p in classpaths], options.version, base_path)
    topts = typer.Options(strict_mode=options.strict, local_inference=options.infer,
                          warn_imports=options.warn_imports, verbose=options.verbose)
    try:
        try:
            ctx = typer.create(cp, topts, rep.warning)
        except typer.TyperError as e:
            if e.kind == 'Class_not_found' and e.data == ((), 'StdPresent'):
                raise CompileError("Directory 'std' containing MTASC class headers cannot be found :\n"
                                   "Please install it or set classpath using '-cp' so it can be found.") from None
            raise
        holder['ctx'] = ctx
        for file in entries:
            real = os.path.realpath(str(file))
            if any(os.path.realpath(c.file) == real for c in ctx.load_order):
                continue  # already loaded through a reference from an earlier entry
            typer.load_class(ctx, class_name(str(file)), ast.ARGV_POS)
        typer.finalize(ctx)

        def line_of(pos: ast.Pos) -> int:
            table = ctx.line_tables.get(pos.file) or LineTable([])
            return table.find(pos.pmin)[0]

        g = gen.Generator(gen.Options(version=options.version, enable_main=options.main,
                                      ftrace=options.trace), line_of)
        classgen.generate(g.gen_class, ctx.files)
        g.finish()
    except ast.InvalidExpression as e:
        raise CompileError(rep.format('Invalid Expression', e.pos, 'parse error')) from None
    except LexError as e:
        raise CompileError(rep.format(e.msg, e.pos, 'syntax error')) from None
    except ParseError as e:
        raise CompileError(rep.format(e.msg, e.pos, 'parse error')) from None
    except typer.TyperError as e:
        raise CompileError(rep.format(typer.error_msg(e.kind, e.data), e.pos, 'type error')) from None
    except typer.FileNotFound as e:
        raise CompileError(f'File not found {e.file}') from None
    except gen.Failure as e:
        raise CompileError(str(e)) from None
    except avm1.Overflow as e:
        raise CompileError(f'Fatal error: exception IO.Overflow("{e}")') from None
    classes = [(c.name, c.code) for c in g.classes]
    if g.main_code is not None:
        classes.append(('', g.main_code))
    return Result(classes, rep.warnings)


def compile_into_movie(movie: swf.Movie, classpaths: list, entries: list, options: Options | None = None,
                       **kw) -> Result:
    options = options or Options(**kw)
    result = compile_classes(classpaths, entries, options)
    main_code = None
    classes = []
    for name, code in result.classes:
        if name == '':
            main_code = code
        else:
            classes.append((name, code))
    res = inject(movie, classes, version=options.version, keep=options.keep, frame=options.frame,
                 main_code=main_code)
    result.warnings.extend(res.warnings)
    return result


def compile_swf(swf_in, classpaths: list, entries: list, swf_out=None, options: Options | None = None,
                **kw) -> Result:
    """mtasc `-swf` semantics: read `swf_in`, inject, write `swf_out` (default: in place)."""
    options = options or Options(**kw)
    if options.header is not None:
        movie = header_movie(options.header)
    else:
        swf_in = Path(swf_in)
        if not swf_in.is_file():
            raise CompileError(f'File not found {swf_in}')
        try:
            movie = swf.Movie.load(swf_in)
        except Exception:
            raise CompileError('Input swf is corrupted') from None
    result = compile_into_movie(movie, classpaths, entries, options)
    movie.save(swf_out or swf_in)
    return result


def header_movie(header: str) -> swf.Movie:
    """`-header w:h:fps[:bgcolor]` — a fresh movie like mtasc builds."""
    parts = header.split(':')
    try:
        w, h, fps = int(parts[0]), int(parts[1]), float(parts[2])
        bg = int(parts[3], 16) if len(parts) == 4 else 0xFFFFFF
        if len(parts) not in (3, 4):
            raise ValueError
    except (ValueError, IndexError):
        raise CompileError('Invalid header format') from None
    m = swf.new_movie(7, w, h, 0, bg)
    m.frame_rate = round(fps * 256) & 0xFFFF
    m.compressed = True
    nbits = 16 if max(w, h) >= 820 else 15
    bits = f'{nbits:05b}' + f'{0:0{nbits}b}' + f'{w * 20:0{nbits}b}' + f'{0:0{nbits}b}' + f'{h * 20:0{nbits}b}'
    bits += '0' * (-len(bits) % 8)
    m.frame_size = int(bits, 2).to_bytes(len(bits) // 8, 'big')
    return m
