"""Pre-commit gate: a Database.json edit must ship with its changelog entry.

Wired in .pre-commit-config.yaml with `files: ^src/kazbars/assets/kazbars/Database\\.json$`,
so it only runs when the stock catalog itself is staged (the `$` anchor keeps
`.default` out -- that file has its own byte-parity check in
tests/test_data_integrity.py).

The rule it enforces: every catalog change is logged in docs/database-changelog.md,
one dated bullet per buff, with the spell ID. Without a log entry there is no way
to answer "when did this buff change, and to what" six months later.
"""

import subprocess
import sys

CATALOG = 'src/kazbars/assets/kazbars/Database.json'
CHANGELOG = 'docs/database-changelog.md'


def staged():
    out = subprocess.run(
        ['git', 'diff', '--cached', '--name-only'],
        capture_output=True, text=True, check=False,
    )
    return {line.strip().replace('\\', '/') for line in out.stdout.splitlines() if line.strip()}


def main():
    names = staged()
    if CATALOG not in names:
        return 0
    if CHANGELOG in names:
        return 0
    print(
        f'{CATALOG} is staged but {CHANGELOG} is not.\n'
        f'Log the change first: one dated "## YYYY-MM-DD" bullet per buff, '
        f'each carrying its spell ID(s), newest first.\n'
        f'See that file\'s "How to maintain it" section for the exact format.',
        file=sys.stderr,
    )
    return 1


if __name__ == '__main__':
    sys.exit(main())
