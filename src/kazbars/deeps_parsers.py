"""KazBars — Deeps parsers (pure data layer).

Ports the Rust parsers from `Deeps/rust/aoc-damage/src/` and
`Deeps/rust/aoc-heal/src/lib.rs`. Every regex is byte-identical to its
Rust counterpart so the numerical output matches. No Tk, no threading,
no shared state — pure functions on log lines.

Five parser entry points:

- `parse_outgoing_damage(line)` — damage authored by the logger
- `parse_incoming_damage(line)` — damage targeting the logger
- `parse_incoming_heal(line)`   — heals targeting the logger (classified)
- `parse_pet_hit(line)`         — damage authored by a known pet
- `parse_outgoing_heal(line)`   — heals authored by the logger to other players

`parse_outgoing_damage` and `parse_pet_hit` have `_with_target` siblings
that return the target name alongside the amount, so the meter can
populate a known-mobs set used to filter bubble-boss heal-conversion
lines out of HPS-out.

Plus `strip_log_timestamp(line)` for callers that haven't already
stripped the `[YYYY-MM-DD HH:MM:SS] ` prefix.
"""

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum

from .paths import ASSETS

logger = logging.getLogger(__name__)


# =========================================================================== #
# Heal classification                                                         #
# =========================================================================== #

class HealKind(Enum):
    """Category of a heal received by the logger."""

    SPELL = "spell"
    POTION = "potion"
    HEALTH_TAP = "health_tap"


@dataclass(frozen=True)
class IncomingHeal:
    """A heal received by the logger."""

    amount: int
    kind: HealKind
    source: str | None


# =========================================================================== #
# Compiled regexes — byte-identical to Deeps's Rust patterns                  #
# =========================================================================== #

# Lifted verbatim from Deeps/rust/aoc-damage/src/lib.rs::re_dmg
# (originally from CLP's lib/aoclib/log_parse.py:52-55).
# Group 1: actor, group 2: verb, group 3: target, group 4: damage.
_RE_DMG = re.compile(
    r"^(.+?)\s+(critically [a-z]+s|glancingly hits|[a-z]+s)\s+(.+?)\s+for\s+(\d+)"
    r"(?:\s+(?:\w+\s+)?damage)?\.(?:\s*\((?P<modifier>[^)]*)\))?\s*$"
)

# Lifted verbatim from Deeps/rust/aoc-damage/src/lib.rs::re_you_bare.
# Group 1: verb, group 2: target, group 3: damage.
_RE_YOU_BARE = re.compile(
    r"^You\s+(critically\s+\w+|\w+)\s+(.+?)\s+for\s+(\d+)\."
    r"(?:\s*\((?P<modifier>[^)]*)\))?\s*$"
)

# Lifted verbatim from Deeps/rust/aoc-damage/src/damage_in.rs::re_dmg_you.
# Group 1: actor, group 2: verb, group 3: damage. Target is pinned to literal "you".
_RE_DMG_YOU = re.compile(
    r"^(.+?)\s+(critically [a-z]+s|glancingly hits|[a-z]+s)\s+you\s+for\s+(\d+)"
    r"(?:\s+(?:\w+\s+)?damage)?\.(?:\s*\((?P<modifier>[^)]*)\))?\s*$"
)

# Lifted verbatim from Deeps/rust/aoc-heal/src/lib.rs.
_RE_YOU_ARE_HEALED = re.compile(
    r"^You are healed for\s+(\d+)\s*\((?P<modifier>[^)]+)\)\.\s*$"
)
_RE_HEALS_YOU = re.compile(
    r"^(.+?)\s+(critically heals|heals)\s+you\s+for\s+(\d+)\.(?:\s*\([^)]*\))?\s*$"
)
_RE_YOU_HEAL_YOURSELF = re.compile(
    r"^You\s+(critically\s+heal|heal)\s+yourself\s+for\s+(\d+)\.(?:\s*\([^)]*\))?\s*$"
)

# Outgoing heal from the logger to a third party. AoC verb-tense quirk:
# non-crit uses present "heals", crit to third parties uses past
# "critically healed" — confirmed across PoM / BS / ToS / Conq corpora.
# Self-heal crits use "critically heals" and are owned by _RE_HEALS_YOU.
_RE_OUT_HEAL = re.compile(
    r"^(.+?)\s+(critically healed|heals)\s+(.+?)\s+for\s+(\d+)\.(?:\s*\([^)]*\))?\s*$"
)


# =========================================================================== #
# Pet name registry — loaded once from assets/deeps/pets.json                 #
# =========================================================================== #

_PET_NAMES: frozenset[str] | None = None


def _pet_names() -> frozenset[str]:
    """Lazily load and cache the pet name registry."""
    global _PET_NAMES
    if _PET_NAMES is None:
        path = ASSETS / "deeps" / "pets.json"
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            _PET_NAMES = frozenset(p["name"] for p in data.get("pets", []))
        except (OSError, json.JSONDecodeError, KeyError) as e:
            logger.error("Failed to load pets.json: %s", e)
            _PET_NAMES = frozenset()
    return _PET_NAMES


def is_pet(name: str) -> bool:
    """True iff `name` is a known pet (case-sensitive)."""
    return name in _pet_names()


def _extract_pet_name(actor: str) -> str:
    """Strip the leading `Your ` then split on the first `'s ` to get the pet name.

    Handles four shapes from the live corpus:
      - `Cacodemon's Hellfire` → `Cacodemon`
      - `Cacodemon`             → `Cacodemon`
      - `Your Cacodemon's Hellfire` → `Cacodemon`
      - `Your Cacodemon`             → `Cacodemon`
    """
    if actor.startswith("Your "):
        actor = actor[5:]
    idx = actor.find("'s ")
    if idx != -1:
        return actor[:idx]
    return actor


def actor_is_pet(actor: str) -> bool:
    """True iff the actor field resolves to a known pet."""
    return is_pet(_extract_pet_name(actor))


def target_is_own_pet(target: str) -> bool:
    """True iff the target is the logger's own pet (`Your <KnownPet>`).

    Used to reject drain-shape lines where the player's ability damages their
    own pet as part of a self-heal trade — the displayed value is a resource
    cost, not real outgoing damage.
    """
    if target.startswith("Your "):
        return is_pet(target[5:])
    return False


# =========================================================================== #
# Heal-verb filter                                                            #
# =========================================================================== #

def _is_heal_verb(verb: str) -> bool:
    """True iff the captured verb is a heal verb.

    Matches: `heals`, `critically heals` (from `RE_DMG` / `RE_DMG_YOU`),
             `heal`,  `critically heal`  (from `RE_YOU_BARE`).
    Mirrors Deeps's lib.rs::is_heal_verb.
    """
    if verb.startswith("critically "):
        verb = verb[11:]
    return verb in ("heal", "heals")


# =========================================================================== #
# Timestamp stripping                                                         #
# =========================================================================== #

def strip_log_timestamp(line: str) -> str:
    """Strip the leading `[YYYY-MM-DD HH:MM:SS] ` prefix if present.

    Mirrors Deeps's meter.rs::strip_log_timestamp. Returns the input
    unchanged if no bracketed prefix is found.
    """
    if line.startswith("["):
        idx = line.find("] ")
        if idx != -1:
            return line[idx + 2:]
    return line


# =========================================================================== #
# Parser 1 — outgoing damage (logger as author)                               #
# =========================================================================== #

def parse_outgoing_damage_with_target(line: str) -> tuple[int, str] | None:
    """Return `(amount, target)` iff `line` is a hit authored by the logger.

    Same filtering as `parse_outgoing_damage`; the target is surfaced for the
    meter's known-mobs registry (used to filter bubble-boss heal-conversion
    lines out of HPS-out).
    """
    if line.startswith("Your "):
        m = _RE_DMG.match(line)
        if m is None:
            return None
        verb = m.group(2)
        if _is_heal_verb(verb):
            return None
        target = m.group(3)
        # Self-damage: Layer 2 (parse_incoming_damage) owns this.
        if target.lower() == "you":
            return None
        # Drain-to-own-pet: resource cost, not real outgoing damage.
        if target_is_own_pet(target):
            return None
        # Own-pet actor: route to parse_pet_hit instead.
        actor = m.group(1)
        if actor_is_pet(actor):
            return None
        return int(m.group(4)), target

    if line.startswith("You "):
        m = _RE_YOU_BARE.match(line)
        if m is None:
            return None
        verb = m.group(1)
        if _is_heal_verb(verb):
            return None
        return int(m.group(3)), m.group(2)

    return None


def parse_outgoing_damage(line: str) -> int | None:
    """Return the damage amount iff `line` is a hit authored by the logger.

    Mirrors Deeps's parse_me_damage. Rejection rules (in order):
      - heal verbs (`Your Word of Command heals X for N`)
      - self-damage (`Your X hits you for N` — Layer 2 owns it)
      - own-pet target (`Your X hits Your Cacodemon for N` — drain cost)
      - own-pet actor  (`Your Mutilator hits Y for N` — pet parser owns it)

    Drain-ability classification (PR 1 §6.2 in Deeps) is a no-op because
    Deeps's `abilities.json` ships empty; we skip it entirely.
    """
    result = parse_outgoing_damage_with_target(line)
    return result[0] if result is not None else None


# =========================================================================== #
# Parser 2 — incoming damage (logger as target)                               #
# =========================================================================== #

def parse_incoming_damage(line: str) -> int | None:
    """Return the damage amount iff `line` is a hit targeting the logger.

    Mirrors Deeps's parse_me_damage_received. The rule is `target == "you"`
    regardless of who authored it — so self-damage (`Your X hits you for N`)
    IS counted here (per the locked decision in our design discussion).
    """
    if " you for " not in line:
        return None
    m = _RE_DMG_YOU.match(line)
    if m is None:
        return None
    if _is_heal_verb(m.group(2)):
        return None
    return int(m.group(3))


# =========================================================================== #
# Parser 3 — incoming heal (logger as target, classified)                     #
# =========================================================================== #

def parse_incoming_heal(line: str) -> IncomingHeal | None:
    """Return an `IncomingHeal` iff `line` is a heal targeting the logger.

    Mirrors Deeps's aoc_heal::parse_incoming_heal. Three forms recognised:
      - `You are healed for N (health tap).` → HEALTH_TAP
      - `<source> [critically] heals you for N.` → POTION (if `source` contains
         `"Potion Effect"`) else SPELL
      - `You [critically] heal yourself for N.` → SPELL

    Unknown modifiers on the `You are healed for N (...)` shape return None
    rather than guessing.
    """
    # Hot-path gate: every recognised form contains "heal".
    if "heal" not in line:
        return None

    # Form 1: "You are healed for N (modifier)."
    if "are healed for" in line:
        m = _RE_YOU_ARE_HEALED.match(line)
        if m is None:
            return None
        amount = int(m.group(1))
        modifier = m.group("modifier")
        if modifier == "health tap":
            return IncomingHeal(amount=amount, kind=HealKind.HEALTH_TAP, source=None)
        return None

    # Form 2: "<source> [critically] heals you for N."
    if "heals you for" in line:
        m = _RE_HEALS_YOU.match(line)
        if m is None:
            return None
        source = m.group(1)
        amount = int(m.group(3))
        kind = HealKind.POTION if "Potion Effect" in source else HealKind.SPELL
        return IncomingHeal(amount=amount, kind=kind, source=source)

    # Form 3: "You [critically] heal yourself for N."
    if line.startswith("You ") and "yourself for" in line:
        m = _RE_YOU_HEAL_YOURSELF.match(line)
        if m is None:
            return None
        amount = int(m.group(2))
        return IncomingHeal(amount=amount, kind=HealKind.SPELL, source=None)

    return None


# =========================================================================== #
# Parser 4 — pet damage (any owner)                                           #
# =========================================================================== #

def parse_pet_hit_with_target(line: str) -> tuple[int, str] | None:
    """Return `(amount, target)` iff `line` is a hit authored by your OWN pet.

    Only the logger's own pet counts. AoC prefixes the logger's pet lines with
    `Your ` (`Your Cacodemon's Hellfire hits X for N`); group-mates' pets of
    the same kind appear without it, so the `Your ` gate isolates your pet and
    excludes team-mates'. The target is surfaced for the meter's known-mobs
    registry.
    """
    if not line.startswith("Your "):
        return None
    if " for " not in line:
        return None
    m = _RE_DMG.match(line)
    if m is None:
        return None
    verb = m.group(2)
    if _is_heal_verb(verb):
        return None
    target = m.group(3)
    if target.lower() == "you":
        return None
    actor = m.group(1)
    if not is_pet(_extract_pet_name(actor)):
        return None
    return int(m.group(4)), target


def parse_pet_hit(line: str) -> int | None:
    """Return the damage amount iff `line` is a hit authored by your own pet.

    Used by the meter when the `include_pet_damage` toggle is enabled. Rejects:
      - lines not prefixed `Your ` (team-mates' pets of the same kind)
      - heal verbs
      - target == `you` (Layer 2 owns those)
      - actors whose pet-name doesn't resolve to a known pet

    Accepts the possessive (`Your Cacodemon's Hellfire`) and bare
    (`Your Mutilator`) own-pet shapes.
    """
    result = parse_pet_hit_with_target(line)
    return result[0] if result is not None else None


# =========================================================================== #
# Parser 5 — outgoing heal (logger as author, third-party target)             #
# =========================================================================== #

def parse_outgoing_heal(line: str) -> tuple[int, str] | None:
    """Return `(amount, target)` iff `line` is a heal you cast on another player.

    Filtering (all-classes corpus: PoM, BS, ToS, Conq):
      - line must start with `Your ` (logger-authored — gate)
      - verb is `heals` (non-crit) or `critically healed` (crit to others;
        self crits use `critically heals` and are owned by parse_incoming_heal)
      - reject `target == "you"`            — self-heal (HPS-in owns it)
      - reject `target` starts with `Your ` — own pet/totem/banner/spirit
      - reject `target` contains `"'s "`    — another player's pet/totem/etc

    Caller (the meter) additionally rejects targets in its known-mobs set
    to filter bubble-converted boss heals — that filter requires state
    across lines and can't live in this pure-function parser.
    """
    if not line.startswith("Your "):
        return None
    m = _RE_OUT_HEAL.match(line)
    if m is None:
        return None
    target = m.group(3)
    if target.lower() == "you":
        return None
    if target.startswith("Your "):
        return None
    if "'s " in target:
        return None
    return int(m.group(4)), target
