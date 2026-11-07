#!/usr/bin/env python3
"""Convert JSON profile files to YAML profile files.

Repo tooling — NOT shipped. Takes 3.1 profile files (a library
``profiles/*.json`` document or a ``.kazbars.json`` export) and writes each as
the YAML profile file the app now reads and writes, beside it or under
``--out``: ``X.kazbars.json`` → ``X.kazbars.yml``, any other ``X.json`` →
``X.yml``. An export's embedded custom buffs ride along; a bare document has
none. The document is not validated here — the app's gate does that on load,
exactly as it would for the JSON.

    python scripts/convert_profiles.py PATH... [--out DIR] [--check]

A PATH may be a file or a folder (its ``*.json``). ``--check`` reads every
written file back and fails (exit 1) unless it holds the same value that was
written. One line per file; any unreadable input also exits 1.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from kazbars import profile_share, yaml_io
from kazbars.settings_manager import safe_write_text


def target_for(src, out_dir=None):
    """Where `src`'s YAML lands."""
    name = src.name
    stem = name[:-len('.kazbars.json')] + '.kazbars' if name.endswith('.kazbars.json') else src.stem
    return (Path(out_dir) if out_dir else src.parent) / f'{stem}.yml'


def convert(src, out_dir=None, check=False):
    """Convert one file; returns (ok, message)."""
    try:
        raw = json.loads(src.read_text(encoding='utf-8'))
        profile, buffs = profile_share.parse_profile_file(raw)
    except (OSError, UnicodeDecodeError, ValueError) as e:  # JSONDecodeError is a ValueError
        return False, f'{src}: not converted ({e})'
    value = profile_share.build_profile_file(profile, buffs)
    text = yaml_io.dumps(value)
    dest = target_for(src, out_dir)
    safe_write_text(dest, text)
    if check:
        try:
            same = yaml_io.loads(dest.read_text(encoding='utf-8')) == value
        except (OSError, yaml_io.YamlError) as e:
            return False, f'{src} -> {dest}: unreadable ({e})'
        if not same:
            return False, f'{src} -> {dest}: round trip differs'
        return True, f'{src} -> {dest}: round trip equal'
    return True, f'{src} -> {dest}'


def main(argv=None):
    parser = argparse.ArgumentParser(description='Convert JSON profile files to YAML.')
    parser.add_argument('paths', nargs='+', help='profile files, or folders of *.json')
    parser.add_argument('--out', help='write the YAML here instead of beside each file')
    parser.add_argument('--check', action='store_true', help='read each file back and compare')
    args = parser.parse_args(argv)
    sources = []
    for p in map(Path, args.paths):
        sources.extend(sorted(p.glob('*.json')) if p.is_dir() else [p])
    ok = True
    for src in sources:
        good, message = convert(src, args.out, args.check)
        print(message)
        ok = ok and good
    return 0 if ok and sources else 1


if __name__ == '__main__':
    sys.exit(main())
