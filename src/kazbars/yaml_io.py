"""YAML text for the files the user touches: the profile, its exports, grids
files and the stock template.

`dumps` is a small writer with one fixed layout — block style, two-space
indent, keys in the dict's own order, a list of scalars on one line — so a
file diffs cleanly and reads the same in any YAML tool. Its quoting is
written for YAML 1.1 readers (PyYAML): every value it writes reads back as
the same value. `loads` is PyYAML's safe loader (libyaml's when the wheel has
it), shaped as JSON would be; JSON text is valid input. `read_file` reads a
data file by its extension. No Tk.
"""

import json
import math
import re
from decimal import Decimal
from pathlib import Path

import yaml

_PLAIN_FIRST_BANNED = set('-?:,[]{}#&*!|>\'"%@`<=~+.')
# `?` too: PyYAML's pure-Python reader ends a plain scalar at it in a flow
# list (libyaml does not), so `[a?b]` would not read back there.
_FLOW_BANNED = set(',[]{}?')
_ODD_SPACES = set('\u0085\u00a0\u2028\u2029\ufeff')
_SURROGATES = re.compile('[\ud800-\udfff]')
_RESERVED = {'null', 'true', 'false', 'yes', 'no', 'on', 'off', 'y', 'n'}
_ESCAPES = {'"': '\\"', '\\': '\\\\', '\n': '\\n', '\r': '\\r', '\t': '\\t', '\0': '\\0'}


class YamlError(ValueError):
    """Text that isn't readable YAML."""


# ============================================================================
# READ
# ============================================================================
def loads(text):
    """The value `text` holds (JSON text reads too), in JSON's shapes: a
    mapping key is always text and a value YAML types beyond JSON (a date,
    a set, binary) reads as text or a list, and a lone surrogate reads as
    U+FFFD as `dumps` writes it, so whatever loads, `dumps` writes back the
    same. Raises `YamlError`."""
    try:
        return _json_shaped(yaml.load(text, Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader)))
    except yaml.YAMLError as e:
        raise YamlError(str(e)) from e


def read_file(path):
    """A data file's value by extension: `.json` as JSON, anything else as
    YAML, both in `loads`' shapes. Raises `OSError`, or `ValueError` for text that doesn't read
    (`UnicodeDecodeError`, a JSON or YAML error)."""
    path = Path(path)
    text = path.read_text(encoding='utf-8')
    return _json_shaped(json.loads(text)) if path.suffix.lower() == '.json' else loads(text)


def _json_shaped(value):
    if isinstance(value, dict):
        return {_key_text(k): _json_shaped(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_shaped(v) for v in value]
    if isinstance(value, str):
        return _SURROGATES.sub('\ufffd', value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, bytes):
        return value.decode('utf-8', 'replace')
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


def _key_text(key):
    """A mapping key as JSON writes one: `1` → "1", `true` → "true"."""
    if isinstance(key, str):
        return _json_shaped(key)
    if key is None or isinstance(key, bool):
        return json.dumps(key)
    return str(_json_shaped(key))


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
    # A lone surrogate can't be written or read back in any form (libyaml
    # refuses even its escape): it becomes U+FFFD, the replacement character.
    text = _SURROGATES.sub('\ufffd', text)
    return text if _plain_ok(text) else _quoted(text)


def _is_control(ch):
    """A character a YAML reader refuses raw: C0/C1 controls and the
    non-characters U+FFFE / U+FFFF — escaped instead."""
    code = ord(ch)
    return code < 0x20 or 0x7f <= code <= 0x9f or code in (0xfffe, 0xffff)


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
        elif _is_control(ch) or ch in '\u2028\u2029\ufeff':
            out.append(f'\\u{ord(ch):04x}')
        else:
            out.append(ch)
    return '"' + ''.join(out) + '"'
