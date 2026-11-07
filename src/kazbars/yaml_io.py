"""YAML text for the files the user touches: the profile, its exports, grids
files and the stock template.

`dumps` is a small writer with one fixed layout — block style, two-space
indent, keys in the dict's own order, a list of scalars on one line — so a
file diffs cleanly and reads the same in any YAML tool. Its quoting is
written for YAML 1.1 readers (PyYAML): every value it writes reads back as
the same value. `loads` is PyYAML's safe loader (libyaml's when the wheel has
it); JSON text is valid input. Pure: no Tk, no files.
"""

import math
from decimal import Decimal

import yaml

_PLAIN_FIRST_BANNED = set('-?:,[]{}#&*!|>\'"%@`<=~+.')
# `?` too: PyYAML's pure-Python reader ends a plain scalar at it in a flow
# list (libyaml does not), so `[a?b]` would not read back there.
_FLOW_BANNED = set(',[]{}?')
_ODD_SPACES = set('\u0085   ﻿')
_RESERVED = {'null', 'true', 'false', 'yes', 'no', 'on', 'off', 'y', 'n'}
_ESCAPES = {'"': '\\"', '\\': '\\\\', '\n': '\\n', '\r': '\\r', '\t': '\\t', '\0': '\\0'}


class YamlError(ValueError):
    """Text that isn't readable YAML."""


# ============================================================================
# READ
# ============================================================================
def loads(text):
    """The value `text` holds (JSON text reads too). Raises `YamlError`."""
    try:
        return yaml.load(text, Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader))
    except yaml.YAMLError as e:
        raise YamlError(str(e)) from e


# ============================================================================
# WRITE
# ============================================================================
def dumps(value):
    """`value` as YAML text in the fixed layout, one trailing newline."""
    if _is_block(value):
        return '\n'.join(_block(value, 0)) + '\n'
    return _inline(value) + '\n'


def _is_block(value):
    """A non-empty dict, or a list holding any dict or list."""
    if isinstance(value, dict):
        return bool(value)
    return isinstance(value, list) and any(isinstance(v, (dict, list)) for v in value)


def _block(value, indent):
    """The lines of a block value, each starting at `indent`."""
    pad = ' ' * indent
    lines = []
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f'YAML keys must be text, not {type(key).__name__}')
            if _is_block(item):
                lines.append(f'{pad}{_str(key)}:')
                lines.extend(_block(item, indent + 2))
            else:
                lines.append(f'{pad}{_str(key)}: {_inline(item)}')
        return lines
    for item in value:
        if _is_block(item):
            inner = _block(item, indent + 2)
            lines.append(f'{pad}- {inner[0][indent + 2:]}')
            lines.extend(inner[1:])
        else:
            lines.append(f'{pad}- {_inline(item)}')
    return lines


def _inline(value):
    """A scalar, an empty dict, or a list of scalars on one line."""
    if isinstance(value, dict):
        return '{}'
    if isinstance(value, list):
        return '[' + ', '.join(_inline(v) for v in value) + ']'
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _float(value)
    if isinstance(value, str):
        return _str(value)
    raise TypeError(f'no YAML form for {type(value).__name__}')


def _float(value):
    """Never an exponent, always a '.': `1.0`, `0.0000001`."""
    if math.isnan(value):
        return '.nan'
    if math.isinf(value):
        return '.inf' if value > 0 else '-.inf'
    text = repr(value)
    if 'e' in text or 'E' in text:
        text = format(Decimal(text), 'f')
    if not any(c in text for c in '.eE'):
        text += '.0'
    return text


def _str(text):
    return text if _plain_ok(text) else _quoted(text)


def _is_control(ch):
    code = ord(ch)
    return code < 0x20 or 0x7f <= code <= 0x9f


def _plain_ok(text):
    """Whether `text` reads back as itself unquoted, as a value, a key or a
    flow-list item."""
    if not text:
        return False
    first, last = text[0], text[-1]
    if first in _PLAIN_FIRST_BANNED or first.isdigit() or first.isspace():
        return False
    if last.isspace() or last == ':':
        return False
    if ': ' in text or ' #' in text:
        return False
    if any(ch in _FLOW_BANNED or ch in _ODD_SPACES or _is_control(ch) for ch in text):
        return False
    return text.lower() not in _RESERVED


def _quoted(text):
    out = []
    for ch in text:
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif _is_control(ch) or ch in '  ﻿':
            out.append(f'\\u{ord(ch):04x}')
        else:
            out.append(ch)
    return '"' + ''.join(out) + '"'
