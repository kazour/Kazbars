"""Command line — mtasc-compatible flags.

    as2c [options] <files...>
      -cp <path>       add classpath (repeatable)
      -swf <file>      swf file to update
      -out <file>      swf output file
      -version <n>     SWF version (default 8)
      -frame <n>       export into target frame
      -keep            do not remove AS2 classes from the input SWF
      -main            enable main entry point
      -header w:h:fps  create a new movie instead of updating one
      -trace <fn>      custom trace function
      -strict -infer -wimp -msvc -v
"""

from __future__ import annotations

import sys

from .compile import Options, compile_swf
from .diagnostics import CompileError

USAGE = """as2c - ActionScript 2 compiler (mtasc-compatible)
 Usage : as2c [options] <files...>
 Options :
  -cp <paths> : add classpath
  -v : turn on verbose mode
  -strict : turn on strict mode
  -infer : turn on local variables inference
  -wimp : turn on warnings for unused imports
  -msvc : use MSVC style errors
  -swf <file> : swf file to update
  -out <file> : swf output file
  -keep : does not remove AS2 classes from input SWF
  -frame <frame> : export into target frame (must exist in the swf)
  -main : enable main entry point
  -header <header> : specify header format 'width:height:fps'
  -version : change SWF version (6,7,8,...)
  -trace <function> : specify a TRACE function
  -help  Display this list of options"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    opts = Options()
    classpaths: list[str] = []
    files: list[str] = []
    swf_in = out = None
    i = 0

    def need(flag: str) -> str:
        nonlocal i
        i += 1
        if i >= len(args):
            print(f'{flag} needs an argument', file=sys.stderr)
            sys.exit(2)
        return args[i]

    while i < len(args):
        a = args[i]
        if a == '-cp':
            classpaths.append(need(a))
        elif a == '-swf':
            swf_in = need(a)
        elif a == '-out':
            out = need(a)
        elif a == '-version':
            opts.version = int(need(a))
        elif a == '-frame':
            opts.frame = int(need(a))
            if opts.frame <= 0:
                print('Invalid frame', file=sys.stderr)
                return 2
        elif a == '-keep':
            opts.keep = True
        elif a == '-main':
            opts.main = True
        elif a == '-header':
            opts.header = need(a)
        elif a == '-trace':
            opts.trace = need(a)
        elif a == '-strict':
            opts.strict = True
        elif a == '-infer':
            opts.infer = True
        elif a == '-wimp':
            opts.warn_imports = True
        elif a == '-msvc':
            opts.msvc = True
        elif a == '-v':
            opts.verbose = True
        elif a in ('-help', '--help', '-h'):
            print(USAGE)
            return 0
        elif a.startswith('-'):
            print(f'unknown option {a}', file=sys.stderr)
            print(USAGE, file=sys.stderr)
            return 2
        else:
            files.append(a)
        i += 1
    if not files:
        print(USAGE)
        return 0
    if opts.keep and opts.header is not None:
        print('-keep cannot be used together with -header', file=sys.stderr)
        return 1
    if swf_in is None and opts.header is None:
        # mtasc type-checks without producing output when no -swf is given
        from .compile import compile_classes
        try:
            result = compile_classes(classpaths, files, opts)
        except CompileError as e:
            print(e, file=sys.stderr)
            return 1
        for w in result.warnings:
            print(w, file=sys.stderr)
        return 0
    try:
        result = compile_swf(swf_in, classpaths, files, swf_out=out, options=opts)
    except CompileError as e:
        print(e, file=sys.stderr)
        return 1
    for w in result.warnings:
        print(w, file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
