"""One-shot harness: dump per-category totals from a CombatLog file.

Reads a `CombatLog-*.txt`, runs every Deeps parser over each line, and
prints the cumulative totals. Used to compare against Deeps's Rust binary
output for parity verification.

Run from repo root:
    python tools/deeps_parity_dump.py "<path to CombatLog-*.txt>"
"""

import sys
import time
from collections import Counter
from pathlib import Path

# Add src/ to path so we can import kazbars.* without installing the package.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from kazbars.deeps_parsers import (
    HealKind,
    parse_incoming_damage,
    parse_incoming_heal,
    parse_outgoing_damage,
    parse_pet_hit,
    strip_log_timestamp,
)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: deeps_parity_dump.py <combatlog.txt>", file=sys.stderr)
        return 2

    log_path = Path(sys.argv[1])
    if not log_path.exists():
        print(f"file not found: {log_path}", file=sys.stderr)
        return 1

    lines_total = 0
    lines_blank = 0

    out_count = 0
    out_total = 0

    in_dmg_count = 0
    in_dmg_total = 0

    heal_total_count = 0
    heal_total_amount = 0
    heal_by_kind: Counter[str] = Counter()
    heal_amount_by_kind: Counter[str] = Counter()

    pet_count = 0
    pet_total = 0

    start = time.monotonic()
    with open(log_path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            lines_total += 1
            line = raw.rstrip("\r\n")
            line = strip_log_timestamp(line)
            if not line:
                lines_blank += 1
                continue

            dmg_out = parse_outgoing_damage(line)
            if dmg_out is not None:
                out_count += 1
                out_total += dmg_out

            dmg_in = parse_incoming_damage(line)
            if dmg_in is not None:
                in_dmg_count += 1
                in_dmg_total += dmg_in

            heal = parse_incoming_heal(line)
            if heal is not None:
                heal_total_count += 1
                heal_total_amount += heal.amount
                heal_by_kind[heal.kind.value] += 1
                heal_amount_by_kind[heal.kind.value] += heal.amount

            pet_hit = parse_pet_hit(line)
            if pet_hit is not None:
                pet_count += 1
                pet_total += pet_hit

    elapsed = time.monotonic() - start
    rate = lines_total / elapsed if elapsed > 0 else 0

    print(f"file: {log_path}")
    print(f"size: {log_path.stat().st_size:,} bytes")
    print(f"lines: {lines_total:,} ({lines_blank:,} blank/empty after timestamp strip)")
    print(f"parse time: {elapsed:.2f}s ({rate:,.0f} lines/sec)")
    print()
    print("=== Outgoing damage (parse_outgoing_damage) ===")
    print(f"  matches: {out_count:,}")
    print(f"  total:   {out_total:,}")
    print()
    print("=== Incoming damage (parse_incoming_damage) ===")
    print(f"  matches: {in_dmg_count:,}")
    print(f"  total:   {in_dmg_total:,}")
    print()
    print("=== Incoming heals (parse_incoming_heal) ===")
    print(f"  matches: {heal_total_count:,}")
    print(f"  total:   {heal_total_amount:,}")
    for kind in HealKind:
        c = heal_by_kind[kind.value]
        a = heal_amount_by_kind[kind.value]
        print(f"    {kind.value:12s}: {c:>8,} matches, {a:>12,} total")
    print()
    print("=== Pet damage (parse_pet_hit) — would credit player if toggle ON ===")
    print(f"  matches: {pet_count:,}")
    print(f"  total:   {pet_total:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
