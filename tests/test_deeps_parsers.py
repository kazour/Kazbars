"""Smoke tests for kazbars.deeps_parsers.

Ports every behavior-table row from Deeps's docs and test files as pytest
cases. If our Python parsers ever drift from the Rust source, one of these
fails with a clear name pointing at the failing input.

Coverage sources:
  - Deeps/rust/aoc-damage/src/lib.rs (parse_me_damage tests)
  - Deeps/rust/aoc-damage/src/damage_in.rs (parse_me_damage_received tests)
  - Deeps/rust/aoc-damage/src/pets.rs (parse_pet_hit tests)
  - Deeps/rust/aoc-heal/src/lib.rs (parse_incoming_heal tests)
  - Deeps/docs/aoc-damage.md and aoc-heal.md behavior tables

Run: `pytest tests/test_deeps_parsers.py` (from repo root).
"""

import pytest

from kazbars.deeps_parsers import (
    HealKind,
    IncomingHeal,
    _extract_pet_name,
    _is_heal_verb,
    actor_is_pet,
    is_pet,
    parse_incoming_damage,
    parse_incoming_heal,
    parse_outgoing_damage,
    parse_outgoing_damage_with_target,
    parse_outgoing_heal,
    parse_pet_hit,
    parse_pet_hit_with_target,
    strip_log_timestamp,
    target_is_own_pet,
)

# =========================================================================== #
# parse_outgoing_damage — accepted cases                                      #
# =========================================================================== #

@pytest.mark.parametrize(
    ("line", "expected"),
    [
        # From aoc-damage.md behavior table — Your forms
        ("Your Resonance hits Xoika for 1234 unholy damage.", 1234),
        ("Your Bone Shatter (Finesse) hits Arbanus for 5461 damage.", 5461),
        ("Your offhand slashes Arbanus for 244.", 244),
        ("Your Decays of Nature critically hits X for 99.", 99),
        ("Your Smite glancingly hits X for 30.", 30),
        ("Your Strike hits Arbanus for 105. (Glancing)", 105),
        ("Your Strike hits Arbanus for 80. (-5% combo damage)", 80),
        # From aoc-damage.md behavior table — You forms
        ("You slash Neesa for 83.", 83),
        ("You critically pierce Neesa for 412.", 412),
        ("You crush Neesa for 105. (Glancing)", 105),
        # Self-damage filter must not affect other targets that share a prefix
        ("Your Strike hits Yourbalin for 100.", 100),
        ("Your Strike hits Your Pet for 100.", 100),  # "Pet" not in registry
        # Non-pet ability whose name happens to contain a pet substring
        ("Your Slow Death Strike IV critically pierces Serpent Man for 821.", 821),
    ],
    ids=lambda v: repr(v)[:60] if isinstance(v, str) else str(v),
)
def test_outgoing_damage_accepted(line: str, expected: int) -> None:
    assert parse_outgoing_damage(line) == expected


# =========================================================================== #
# parse_outgoing_damage — rejected cases                                      #
# =========================================================================== #

@pytest.mark.parametrize(
    "line",
    [
        # Other actors
        "Xoika's Decays of Nature hits Arbanus for 132 unholy damage.",
        "Hathor-Ka's Mutilation hits Arbanus for 5000.",
        "Armageddon Falls hits Arbanus for 9999.",
        # Heal verbs
        "Your Word of Command heals Arbanus for 500.",
        "You heal Arbanus for 500.",
        "Your Word of Command critically heals Arbanus for 1200.",
        "You critically heal Arbanus for 1200.",
        # Structural rejects
        "Arbanus died.",
        "",
        "   ",
        "Your shield protects Arbanus.",
        # Self-damage — Layer 2 owns these
        "Your Life Drain hits you for 50.",
        "Your Burning Tar hits you for 120 fire damage.",
        "Your Soul Siphon critically hits you for 200.",
        # Own-pet actor — pet parser owns these
        "Your Blighted One hits Crimson Underling for 94 slashing damage.",
        "Your Corruptor hits Crimson Underling for 135 crushing damage.",
        "Your Cacodemon critically hits Boss for 800 fire damage.",
        "Your Mutilator's Mutilation (1) hits Crimson Underling for 29 slashing damage.",
        "Your Corruptor's Corrupting Touch hits Crimson Underling for 75 unholy damage.",
        # Own-pet target — drain HP-cost trade, not real damage
        "Your Siphon Unlife hits Your Necrotic Bomb for 90 damage.",
        "Your Siphon Unlife hits Your Mutilator for 108 damage.",
        "Your Some Ability hits Your Cacodemon for 50 fire damage.",
        # Self-heal half of the drain trade
        "Your Siphon Unlife heals you for 58.",
    ],
    ids=lambda v: repr(v)[:60],
)
def test_outgoing_damage_rejected(line: str) -> None:
    assert parse_outgoing_damage(line) is None


# =========================================================================== #
# parse_incoming_damage — accepted cases                                      #
# =========================================================================== #

@pytest.mark.parametrize(
    ("line", "expected"),
    [
        # From damage_in.rs tests + behavior table
        ("The King of Winter hits you for 1523 crushing damage.", 1523),
        ("The King of Winter's Pulverize hits you for 989 crushing damage.", 989),
        ("Living Statue critically slashes you for 2718.", 2718),
        ("The King of Winter's Mighty Sweep critically hits you for 3500 crushing damage.", 3500),
        ("Frost Giant's Ice Lance glancingly hits you for 42.", 42),
        ("Scorpion Archer Prince's Killehr crushes you for 144. (Glancing)", 144),
        # Self-damage IS accepted in incoming (per locked decision)
        ("Your Life Drain hits you for 50.", 50),
        ("Your Burning Tar hits you for 120 fire damage.", 120),
        ("Your Soul Siphon critically hits you for 200.", 200),
    ],
    ids=lambda v: repr(v)[:60] if isinstance(v, str) else str(v),
)
def test_incoming_damage_accepted(line: str, expected: int) -> None:
    assert parse_incoming_damage(line) == expected


# =========================================================================== #
# parse_incoming_damage — rejected cases                                      #
# =========================================================================== #

@pytest.mark.parametrize(
    "line",
    [
        # Heals to ME — Layer 1 (parse_incoming_heal) territory
        "Chapagetti's Healing Lotus heals you for 64.",
        "Daisydook's Celestial Gaze critically heals you for 2126.",
        # Damage to others — not us
        "Xoika's Decays of Nature hits Arbanus for 132 unholy damage.",
        # ME outgoing — Layer 0 territory
        "Your Resonance hits Xoika for 1234 unholy damage.",
        # Bare "You verb X" — never matches (verb has no -s suffix; target not "you")
        "You slash Neesa for 83.",
        # Structural rejects
        "",
        "Arbanus died.",
    ],
    ids=lambda v: repr(v)[:60],
)
def test_incoming_damage_rejected(line: str) -> None:
    assert parse_incoming_damage(line) is None


# =========================================================================== #
# parse_incoming_heal — accepted cases                                        #
# =========================================================================== #

def test_heal_health_tap_basic() -> None:
    h = parse_incoming_heal("You are healed for 29 (health tap).")
    assert h == IncomingHeal(amount=29, kind=HealKind.HEALTH_TAP, source=None)


def test_heal_potion_self() -> None:
    h = parse_incoming_heal("Your Health Potion Effect 10 heals you for 70.")
    assert h == IncomingHeal(
        amount=70,
        kind=HealKind.POTION,
        source="Your Health Potion Effect 10",
    )


def test_heal_spell_from_other() -> None:
    h = parse_incoming_heal("Chapagetti's Healing Lotus (Rank 6) heals you for 64.")
    assert h == IncomingHeal(
        amount=64,
        kind=HealKind.SPELL,
        source="Chapagetti's Healing Lotus (Rank 6)",
    )


def test_heal_spell_crit_verb_from_other() -> None:
    # The "critically heals" verb still parses as a spell heal; we no longer
    # track a crit flag, so only amount + kind matter.
    h = parse_incoming_heal("Daisydook's Celestial Gaze critically heals you for 2126.")
    assert h is not None
    assert h.amount == 2126
    assert h.kind == HealKind.SPELL


def test_heal_spell_self_via_your() -> None:
    h = parse_incoming_heal("Your Wave of Life (Rank 6) heals you for 7.")
    assert h == IncomingHeal(
        amount=7,
        kind=HealKind.SPELL,
        source="Your Wave of Life (Rank 6)",
    )


def test_heal_spell_self_via_yourself() -> None:
    h = parse_incoming_heal("You heal yourself for 100.")
    assert h == IncomingHeal(amount=100, kind=HealKind.SPELL, source=None)


def test_heal_spell_self_via_yourself_crit_verb() -> None:
    # "critically heal yourself" still parses (amount extracted past the verb).
    h = parse_incoming_heal("You critically heal yourself for 200.")
    assert h == IncomingHeal(amount=200, kind=HealKind.SPELL, source=None)


# =========================================================================== #
# parse_incoming_heal — rejected cases                                        #
# =========================================================================== #

@pytest.mark.parametrize(
    "line",
    [
        # Unknown modifier on "You are healed for N (...)"
        "You are healed for 50 (mystery thing).",
        # Damage to ME — not a heal
        "The King of Winter hits you for 1500 crushing damage.",
        # Heal to another target
        "Your Word of Command heals Bob for 500.",
        # Structural rejects
        "",
        "Arbanus died.",
    ],
    ids=lambda v: repr(v)[:60],
)
def test_incoming_heal_rejected(line: str) -> None:
    assert parse_incoming_heal(line) is None


# =========================================================================== #
# parse_pet_hit — accepted cases                                              #
# =========================================================================== #

@pytest.mark.parametrize(
    ("line", "expected"),
    [
        # Own pet shapes — AoC prefixes the logger's pet with "Your".
        ("Your Cacodemon's Hellfire hits Boss for 1500.", 1500),
        ("Your Mutilator slashes Boss for 500.", 500),
        ("Your Cacodemon's Hellfire critically hits Boss for 2000 fire damage.", 2000),
        ("Your Idol of Set's Aspect of Set hits Boss for 750.", 750),
        ("Your Blighted One hits Crimson Underling for 94 slashing damage.", 94),
        ("Your Mutilator's Mutilation (1) hits Crimson Underling for 29 slashing damage.", 29),
    ],
    ids=lambda v: repr(v)[:60] if isinstance(v, str) else str(v),
)
def test_pet_hit_accepted(line: str, expected: int) -> None:
    assert parse_pet_hit(line) == expected


# =========================================================================== #
# parse_pet_hit — rejected cases                                              #
# =========================================================================== #

@pytest.mark.parametrize(
    "line",
    [
        # Team-mates' pets of the same kind appear WITHOUT "Your" — excluded
        # (own-pet-only: KazBars credits only the logger's pet).
        "Cacodemon's Hellfire hits Boss for 1500.",
        "Mutilator slashes Boss for 500.",
        "Idol of Set's Charge Stone hits Kozak Pillager for 296 electrical damage.",
        # Non-pet actor with the same possessive shape
        "Hathor-Ka's Mutilation hits Arbanus for 5000.",
        # Bare non-pet actor
        "Xoika hits Arbanus for 1000.",
        # Pet hitting the logger — Layer 2 owns this
        "Cacodemon's Hellfire hits you for 1500.",
        "Mutilator slashes you for 500.",
        "Your Mutilator hits you for 50.",
        # Pet heals (rare but possible)
        "Blood Pit heals Arbanus for 100.",
        "Blood Pit critically heals Arbanus for 200.",
        # Player abilities (not pets)
        "Your Resonance hits Xoika for 1234.",
        "Your Strike hits Arbanus for 100.",
        # Structural rejects
        "",
        "Arbanus died.",
    ],
    ids=lambda v: repr(v)[:60],
)
def test_pet_hit_rejected(line: str) -> None:
    assert parse_pet_hit(line) is None


# =========================================================================== #
# Pet name helpers                                                            #
# =========================================================================== #

def test_pet_registry_loads() -> None:
    """Registry loads without panicking; spot-check three classes' pets."""
    assert is_pet("Cacodemon")  # Demonologist
    assert is_pet("Mutilator")  # Necromancer melee
    assert is_pet("Idol of Set")  # Tempest of Set


def test_pet_registry_rejects_unknown() -> None:
    assert not is_pet("Bob")
    assert not is_pet("Hathor-Ka")
    assert not is_pet("")


@pytest.mark.parametrize(
    ("actor", "expected"),
    [
        ("Cacodemon", "Cacodemon"),
        ("Cacodemon's Hellfire", "Cacodemon"),
        ("Your Cacodemon", "Cacodemon"),
        ("Your Mutilator's Mutilation (1)", "Mutilator"),
        ("Your Strike", "Your Strike"),  # not a pet path; helper returns as-is post strip
    ],
)
def test_extract_pet_name(actor: str, expected: str) -> None:
    # _extract_pet_name strips "Your " first, then splits on "'s "
    # For "Your Strike": strip "Your " → "Strike" — no "'s " → return "Strike".
    # We only assert the helper round-trips; is_pet() determines the final yes/no.
    got = _extract_pet_name(actor)
    if actor == "Your Strike":
        assert got == "Strike"
    else:
        assert got == expected


@pytest.mark.parametrize(
    ("actor", "expected"),
    [
        ("Cacodemon", True),
        ("Cacodemon's Hellfire", True),
        ("Your Cacodemon", True),
        ("Your Mutilator's Mutilation (1)", True),
        ("Xoika", False),
        ("Hathor-Ka's Mutilation", False),
        ("Your Resonance", False),
        ("Your Strike", False),
    ],
)
def test_actor_is_pet(actor: str, expected: bool) -> None:
    assert actor_is_pet(actor) is expected


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("Your Necrotic Bomb", True),
        ("Your Mutilator", True),
        ("Your Cacodemon", True),
        ("Your Pet", False),  # "Pet" not in registry
        ("Your Strike", False),
        ("you", False),
        ("You", False),
        ("Crimson Underling", False),
    ],
)
def test_target_is_own_pet(target: str, expected: bool) -> None:
    assert target_is_own_pet(target) is expected


# =========================================================================== #
# Heal-verb filter                                                            #
# =========================================================================== #

@pytest.mark.parametrize(
    ("verb", "expected"),
    [
        ("heals", True),
        ("heal", True),
        ("critically heals", True),
        ("critically heal", True),
        ("hits", False),
        ("crits", False),
        ("slashes", False),
        ("critically hits", False),
        ("glancingly hits", False),
        ("", False),
    ],
)
def test_is_heal_verb(verb: str, expected: bool) -> None:
    assert _is_heal_verb(verb) is expected


# =========================================================================== #
# Timestamp stripping                                                         #
# =========================================================================== #

def test_strip_log_timestamp_basic() -> None:
    assert (
        strip_log_timestamp("[2026-05-17 20:57:31] Your Strike hits X for 100.")
        == "Your Strike hits X for 100."
    )


def test_strip_log_timestamp_no_prefix() -> None:
    """Unbracketed lines pass through unchanged."""
    assert strip_log_timestamp("Your Strike hits X for 100.") == "Your Strike hits X for 100."


def test_strip_log_timestamp_only_open_bracket() -> None:
    """Unmatched `[` without a `] ` close passes through unchanged."""
    assert strip_log_timestamp("[broken line without close") == "[broken line without close"


def test_strip_log_timestamp_empty() -> None:
    assert strip_log_timestamp("") == ""


# =========================================================================== #
# parse_outgoing_heal — accepted cases (PoM / BS / ToS / Conq real corpus)    #
# =========================================================================== #

@pytest.mark.parametrize(
    ("line", "amount", "target"),
    [
        # PoM — Wave of Life ticks to multiple players
        ("Your Wave of Life (Rank 6) heals Zarse for 384.", 384, "Zarse"),
        ("Your Wave of Life (Rank 6) heals Barbiedancer for 192.", 192, "Barbiedancer"),
        # PoM — Divine Lance group proc, both tense forms
        ("Your Divine Lance heals Raphaello for 356.", 356, "Raphaello"),
        ("Your Divine Lance critically healed Xaerax for 645.", 645, "Xaerax"),
        # PoM — Shimmering Invocation
        ("Your Shimmering Invocation heals Shmeyker for 719.", 719, "Shmeyker"),
        # ToS — Vitalizing Jolt, Vital Shock, Lightning Arc (crit verb form)
        ("Your Vitalizing Jolt (Rank 5) heals Sweetsinx for 192.", 192, "Sweetsinx"),
        ("Your Vital Shock critically healed Satcha for 738.", 738, "Satcha"),
        # BS — Blood Flow ticks
        ("Your Blood Flow (Rank 6) heals Sadyra for 192.", 192, "Sadyra"),
        ("Your Renewal heals Edwardgein for 64.", 64, "Edwardgein"),
        ("Your Fierce Recovery (Rank 5) critically healed Hogam for 2109.", 2109, "Hogam"),
        # Conq — Defiance + compound-actor banner heal
        ("Your Defiance heals Holyagony for 940.", 940, "Holyagony"),
        ("Your Defiance critically healed Holyagony for 1198.", 1198, "Holyagony"),
        (
            "Your The Restoring Standard's The Restoring Standard heals Irisviell for 300.",
            300,
            "Irisviell",
        ),
        # Multi-word player name (crit verb form)
        ("Your Lightning Arc critically healed Lady Zelandra for 129.", 129, "Lady Zelandra"),
    ],
    ids=lambda v: repr(v)[:60] if isinstance(v, str) else str(v),
)
def test_outgoing_heal_accepted(line: str, amount: int, target: str) -> None:
    assert parse_outgoing_heal(line) == (amount, target)


# =========================================================================== #
# parse_outgoing_heal — rejected cases                                        #
# =========================================================================== #

@pytest.mark.parametrize(
    "line",
    [
        # Self-heal — HPS-in owns these
        "Your Wave of Life (Rank 6) heals you for 115.",
        "Your Holy Strike heals you for 14.",
        # Own pet / totem / banner / spirit
        "Your Life of Set (Rank 6) heals Your Idol of Set for 192.",
        "Your Bloodthirst critically healed Your Protective Spirit for 261.",
        (
            "Your The Restoring Standard's The Restoring Standard "
            "heals Your The Restoring Standard for 300."
        ),
        # Other player's pet / totem / standard / object
        "Your Wave of Life (Rank 6) heals Zarse's Life-stealer for 384.",
        "Your Healing Lotus (Rank 6) heals Satcha's Idol of Set for 64.",
        "Your Bloodthirst critically healed Hogam's Protective Spirit for 201.",
        "Your Renewal heals Damoclan's The Burning Standard for 64.",
        "Your Vital Shock critically healed Tetp's The Burning Standard for 150.",
        # Authored by someone else — fails the `Your ` gate
        "Nopetsforhc's Health Potion Effect 10 heals Nopetsforhc for 415.",
        "Brittle Back heals Lady Zelandra for 50.",
        # Damage line (heal verbs only — won't match the outgoing-heal regex)
        "Your Lance of Mitra hits Igneous for 1541 holy damage.",
        # Application line — no `for N` amount
        "You affect Jamora with Recently healed by Shimmering Invocation",
        # Self crit to logger — different verb tense, owned by parse_incoming_heal
        "Your Divine Lance critically heals you for 574.",
        # Structural rejects
        "",
        "Arbanus died.",
    ],
    ids=lambda v: repr(v)[:60],
)
def test_outgoing_heal_rejected(line: str) -> None:
    assert parse_outgoing_heal(line) is None


# =========================================================================== #
# _with_target variants — return (amount, target)                             #
# =========================================================================== #

@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Your Resonance hits Xoika for 1234 unholy damage.", (1234, "Xoika")),
        ("Your Decays of Nature critically hits Xoika for 99.", (99, "Xoika")),
        ("Your Smite glancingly hits Xoika for 30.", (30, "Xoika")),
        # AoC's "crits" verb (ToS Storm Field, Idol of Set Charge Stone).
        ("Your Storm Field crits Kozak Destroyer for 2551 electrical damage.", (2551, "Kozak Destroyer")),
        # You-bare form.
        ("You slash Neesa for 83.", (83, "Neesa")),
        ("You critically pierce Neesa for 412.", (412, "Neesa")),
    ],
    ids=lambda v: repr(v)[:60] if isinstance(v, str) else str(v),
)
def test_outgoing_damage_with_target(line: str, expected: tuple[int, str]) -> None:
    assert parse_outgoing_damage_with_target(line) == expected


def test_outgoing_damage_with_target_rejects_same_as_wrapper() -> None:
    assert parse_outgoing_damage_with_target("Your Soul Siphon hits you for 200.") is None


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Your Cacodemon's Hellfire hits Boss for 1500.", (1500, "Boss")),
        ("Your Cacodemon's Hellfire critically hits Boss for 2000 fire damage.", (2000, "Boss")),
    ],
    ids=lambda v: repr(v)[:60] if isinstance(v, str) else str(v),
)
def test_pet_hit_with_target(line: str, expected: tuple[int, str]) -> None:
    assert parse_pet_hit_with_target(line) == expected


def test_pet_hit_with_target_rejects_team_mate_pet() -> None:
    # Bare (no "Your") same-kind pet is a team-mate's — excluded.
    assert parse_pet_hit_with_target("Cacodemon's Hellfire hits Boss for 1500.") is None


def test_pet_hit_with_target_rejects_pet_hitting_logger() -> None:
    assert parse_pet_hit_with_target("Your Cacodemon's Hellfire hits you for 1500.") is None
