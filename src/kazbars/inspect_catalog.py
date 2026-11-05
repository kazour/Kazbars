"""KazBars — the Inspect Panel stat catalog (pure data, no Tk).

Every stat row the in-game inspect panel can show: which server ids a row
reads, how those ids decode into a value, and the AS2 object-literal fields
the generator bakes verbatim for it (`KazBarsInspectRows` reads them). The
profile's `inspect.rows` picks rows by key; absent, the panel shows the
Summary group (`default_keys`). The PvP tab is a fixed view (`PVP_VIEW`),
whatever rows the user picked. Every id and formula here was measured in game
— see docs/inspect-panel.md before changing a number.
"""

import math
from dataclasses import dataclass
from enum import Enum

# ============================================================================
# GROUPS AND FRESHNESS
# ============================================================================


class Group(Enum):
    """The panel's sections, in render and emission order."""
    SUMMARY = 'Summary'
    VITALS = 'Vitals'
    ATTRIBUTES = 'Attributes'
    OFFENSIVE = 'Offensive'
    DEFENSIVE = 'Defensive'
    PVP_STATS = 'PvP Stats'
    PVP_COMBAT = 'PvP Combat'

    @property
    def label(self) -> str:
        return self.value

    @property
    def player_gated(self) -> bool:
        """The two PvP groups show on player targets only."""
        return self in (Group.PVP_STATS, Group.PVP_COMBAT)

    @property
    def index(self) -> int:
        return list(Group).index(self)


class Fresh(Enum):
    """How current a viewer's copy is: `S` server-sent (always live), `R`
    rebuilt from the target's gear and visible buffs (exact once built fresh
    in view), `D` moves live with debuffs/buffs on any target."""
    S = 'Always live on any target.'
    R = ('Exact after the target zones or is re-targeted from out of sight; '
         'a live re-equip can lag by gem lines.')
    D = 'Moves live with buffs and debuffs on any target, bosses included.'

    @property
    def sentence(self) -> str:
        return self.value


# ============================================================================
# ROW KINDS — how a row's value is read off the polled ids
# ============================================================================


@dataclass(frozen=True)
class Kind:
    """One formatter: the AS2 fields `KazBarsInspectRows` dispatches on (`f`
    names the formatter), the server ids it reads, and a short note on the
    encoding ('' for the composed kinds)."""
    as2_fields: str
    needed_ids: tuple[int, ...]
    encoding_note: str = ''


def _opt(**fields: int) -> str:
    """`, k: v` for each non-zero field (0 means unused, never a real id)."""
    return ''.join(f', {k}: {v}' for k, v in fields.items() if v)


def health() -> Kind:
    return Kind('f: "health"', (1, 27), 'current / max')


def pool(cur: int, pct: int) -> Kind:
    return Kind(f'f: "pool", s: {cur}, t: {pct}', (cur, pct), 'current value (percent)')


def armor(pvp: bool) -> Kind:
    """The sheet's armor total with its mitigation; PvP adds 454."""
    return Kind(f'f: "armor", p: {int(pvp)}', (448, 450, 804, 902, 911) + ((454,) if pvp else ()))


def prot(school: int, attr: int, invul: int, pvp: bool) -> Kind:
    """The sheet's protection total for a school; PvP adds 458."""
    return Kind(f'f: "prot", s: {school}, t: {attr}, i: {invul}, p: {int(pvp)}',
                (school, 451, 334, attr, invul, 911) + ((458,) if pvp else ()))


def rating(sid: int) -> Kind:
    return Kind(f'f: "rate", s: {sid}', (sid,), 'rating; percent = rating / 36.6')


def tap(a: int, b: int, scale: int, rate: int, pvp_rating: int) -> Kind:
    """percent = a/scale + b + (rating + pvp_rating)/36.6; b and pvp_rating 0 when unused."""
    return Kind(f'f: "tap", s: {a}, d: {scale}, t: {rate}' + _opt(u=b, v=pvp_rating),
                tuple(i for i in (a, b, rate, pvp_rating) if i), 'rating (direct % + rating / 36.6)')


def chance(pct: int, scale: int, rate: int, attr: int, pvp_rating: int) -> Kind:
    """Rating column = rating + half the attribute + pvp_rating; percent = that
    / 36.6 + pct/scale (scale 100 for the x100 percent ids, 1 for whole ones)."""
    return Kind(f'f: "chance", s: {pct}, d: {scale}, t: {rate}' + _opt(a=attr, v=pvp_rating),
                tuple(i for i in (pct, rate, attr, pvp_rating) if i), 'rating (percent id + rating / 36.6)')


def hate() -> Kind:
    """Hate Modification: rating 491 - 488, percent that / 36.6 + the signed percent in 170."""
    return Kind('f: "hate"', (170, 488, 491), 'increase - decrease (rating / 36.6 + modifier)')


def prot_max() -> Kind:
    """The highest of the five PvE protections with its mitigation."""
    return Kind('f: "protmax"', (928, 929, 157, 927, 926, 810, 808, 907, 908, 167, 906, 905, 451, 334, 911),
                "highest school's protection (mitigation %)")


def crit_pct() -> Kind:
    return Kind('f: "critp"', (312, 67, 711, 710), 'chance % / bonus damage %')


def hate_pct() -> Kind:
    return Kind('f: "hatep"', (170, 488, 491), '(increase - decrease) / 36.6 + modifier')


def rate_pct(sid: int) -> Kind:
    return Kind(f'f: "ratep", s: {sid}', (sid,), 'percent = rating / 36.6')


def rate_pct_pair(a: int, b: int) -> Kind:
    return Kind(f'f: "ratepp", s: {a}, t: {b}', (a, b), 'percents = rating / 36.6')


def regen(sid: int, k: int, a: int, b: int, c: int) -> Kind:
    """floor(sid + (k/100) x (attr(a) + attr(b) + attr(c))); k in hundredths, a/b/c 0 when unused."""
    return Kind(f'f: "regen", s: {sid}' + _opt(k=k, a=a, b=b, c=c),
                tuple(i for i in (sid, a, b, c) if i), 'base + attribute share, rounded down')


def heal() -> Kind:
    """713 and the heal range it buys."""
    return Kind('f: "heal"', (713,))


def spell(pvp: bool, school: int) -> Kind:
    """Bonus spell damage: one school's id, 0 the highest; PvP adds 226."""
    pvp_id = (226,) if pvp else ()
    if school == 0:
        return Kind(f'f: "spell", p: {int(pvp)}', (507, 158, 876, 877, 878, 879, 861, 808, 810) + pvp_id)
    return Kind(f'f: "spell", p: {int(pvp)}, s: {school}', (507, school, 861, 808, 810) + pvp_id)


def cdi(pvp: bool) -> Kind:
    """The combat rating synthesis; PvP adds 225."""
    return Kind(f'f: "cdi", p: {int(pvp)}',
                (67, 148, 875, 866, 867, 868, 869, 870, 871, 872, 873, 162, 1007, 1008, 1009, 1010)
                + ((225,) if pvp else ()))


def weapon_dmg() -> Kind:
    return Kind('f: "wd"', (1095, 1096))


def crit_chance() -> Kind:
    return Kind('f: "critc"', (312, 67))


def crit_dmg() -> Kind:
    return Kind('f: "critd"', (711, 710))


def pen(sid: int) -> Kind:
    return Kind(f'f: "pen", s: {sid}', (sid,))


def ferocity() -> Kind:
    return Kind('f: "fer"', (1403,))


def pair(a: int, b: int) -> Kind:
    """"a / b", zero is real data."""
    return Kind(f'f: "pair", s: {a}, t: {b}', (a, b))


# Minigame wins then losses, overall: Annihilation, Capture the Skull, Conquest
# (`KazBarsInspectRows.wlLine` sums them in this order).
_MINIGAME_IDS = (666, 668, 1000026, 667, 669, 1000027)


def minigame_wl() -> Kind:
    return Kind('f: "wl"', _MINIGAME_IDS, 'wins / losses, each summed over three games')


def raw(sid: int) -> Kind:
    return Kind(f'f: "raw", s: {sid}', (sid,), 'raw value')


def x100(sid: int) -> Kind:
    return Kind(f'f: "x100", s: {sid}', (sid,), 'percent = value / 100')


def x10p10(sid: int) -> Kind:
    """An attribute stored as value x 10 + 10, shown rounded as the sheet does."""
    return Kind(f'f: "attr", s: {sid}', (sid,), 'attribute: (value - 10) / 10')


def raw_pct(sid: int) -> Kind:
    return Kind(f'f: "pct", s: {sid}', (sid,), 'percent as read')


def pct_base(sid: int, base: int) -> Kind:
    note = ('percent; idle reads 100, shown as the difference' if base == 100
            else 'percent, shown as the difference from its idle value')
    return Kind(f'f: "pctb", s: {sid}, d: {base}', (sid,), note)


# ============================================================================
# ROWS
# ============================================================================


@dataclass(frozen=True)
class Row:
    key: str
    label: str
    group: Group
    kind: Kind
    fresh: Fresh
    player_only: bool
    note: str = ''

    def as2_fields(self) -> str:
        """The row's AS2 fields. Summary (Default) lines add `z: 1`: a would-be
        dash renders as a zero, like the character sheet."""
        f = self.kind.as2_fields
        return f'{f}, z: 1' if self.group is Group.SUMMARY else f


# Declared group by group as the panel renders them; within a group the
# retributive ratings and per-tick modifiers sit last.
_DECLARED = (
    # -- Summary: the twelve lines a profile with no row list shows (Default). --
    Row('sum_health', 'Health', Group.SUMMARY, health(), Fresh.R, False,
        'Current / maximum health.'),
    Row('sum_armor', 'Armor', Group.SUMMARY, armor(False), Fresh.R, False),
    Row('sum_prot', 'Protection', Group.SUMMARY, prot_max(), Fresh.R, False,
        'The highest of the five protections, with its mitigation.'),
    Row('sum_crit', 'Crit Chance / Damage', Group.SUMMARY, crit_pct(), Fresh.R, False,
        'Critical chance and critical bonus damage, as percentages.'),
    Row('sum_hate', 'Hate', Group.SUMMARY, hate_pct(), Fresh.R, False,
        'Hate Modification, as a percentage.'),
    Row('sum_critigation', 'Critig Chance / Amount', Group.SUMMARY, rate_pct_pair(1000016, 1000018), Fresh.R, False,
        'Critigation chance and amount, as percentages.'),
    Row('sum_tenacity', 'Tenacity', Group.SUMMARY, rate_pct(1000017), Fresh.R, False),
    Row('sum_pen', 'Armor / Spell Pen', Group.SUMMARY, pair(449, 452), Fresh.R, False,
        'Armor and spell penetration ratings.'),
    Row('sum_heal', 'Heal Rating', Group.SUMMARY, heal(), Fresh.R, True),
    Row('sum_cdi', 'Combat Rating', Group.SUMMARY, cdi(False), Fresh.R, False),
    Row('sum_spell', 'Bonus Spell Damage', Group.SUMMARY, spell(False, 0), Fresh.R, True),
    Row('sum_fer', 'Ferocity', Group.SUMMARY, ferocity(), Fresh.R, True),

    # -- Vitals: the three character-sheet cards (Health/Stamina/Mana), each
    # led by its maximum, then the pool line, its natural and non-combat
    # regen, and its two tap lines. Name, class, level and PvP level are
    # not rows: the panel's own title line already carries all four. --
    Row('s1', 'Max HP', Group.VITALS, raw(1), Fresh.R, False),
    Row('health', 'Health', Group.VITALS, pool(27, 525), Fresh.S, False),
    Row('regen_health', 'Health Regen', Group.VITALS, regen(899, 0, 0, 0, 0), Fresh.D, False,
        'The sheet calls this Natural Health Regen. No attribute term.'),
    Row('regen_health_nc', 'Health Regen OOC', Group.VITALS, regen(278, 15, 804, 806, 0), Fresh.R, False,
        "The sheet's Non Combat Health Regen: the id plus 15% of Strength + Constitution."),
    Row('tap_phys', 'Health Tap Phys', Group.VITALS, tap(894, 227, 1, 477, 0), Fresh.R, False,
        'Buff percents land in either of two ids; gear lands in the rating. Whole percents only, so a fractional buff percent reads low.'),
    Row('tap_magic', 'Health Tap Magic', Group.VITALS, tap(533, 0, 100, 476, 0), Fresh.R, False),
    Row('s505', 'Max Stamina', Group.VITALS, raw(505), Fresh.R, False),
    Row('stamina', 'Stamina', Group.VITALS, pool(504, 1356), Fresh.R, False),
    Row('regen_stamina', 'Stamina Regen', Group.VITALS, regen(901, 5, 804, 806, 814), Fresh.D, False,
        "The sheet's Natural Stamina Regen: the id plus 5% of Strength + Constitution + Dexterity."),
    Row('regen_stamina_nc', 'Stamina Regen OOC', Group.VITALS, regen(279, 15, 804, 806, 814), Fresh.R, False,
        "The sheet's Non Combat Stamina Regen."),
    Row('tap_phys_stam', 'Stam Tap Phys', Group.VITALS, tap(896, 277, 1, 493, 0), Fresh.R, False),
    Row('tap_magic_stam', 'Stam Tap Magic', Group.VITALS, tap(545, 0, 100, 492, 0), Fresh.R, False),
    Row('s507', 'Max Mana', Group.VITALS, raw(507), Fresh.R, False),
    Row('mana', 'Mana', Group.VITALS, pool(506, 1357), Fresh.R, False,
        'Current mana and the percent of maximum.'),
    Row('regen_mana', 'Mana Regen', Group.VITALS, regen(498, 7, 808, 810, 0), Fresh.D, False,
        "The sheet's Natural Mana Regen: the id plus 7% of Intelligence + Wisdom."),
    Row('regen_mana_nc', 'Mana Regen OOC', Group.VITALS, regen(280, 38, 808, 810, 0), Fresh.R, False,
        "The sheet's Non Combat Mana Regen."),
    Row('tap_phys_mana', 'Mana Tap Phys', Group.VITALS, tap(895, 276, 1, 481, 0), Fresh.R, False),
    Row('tap_magic_mana', 'Mana Tap Magic', Group.VITALS, tap(544, 0, 100, 480, 0), Fresh.R, False),

    # -- Attributes: the General tab's Attributes card, in its order. The
    # ids store the attribute as value x10 + 10; the sheet rounds the
    # tenths away, so the rows show the rounded value the sheet shows. --
    Row('s804', 'Strength', Group.ATTRIBUTES, x10p10(804), Fresh.R, False),
    Row('s808', 'Intelligence', Group.ATTRIBUTES, x10p10(808), Fresh.R, False),
    Row('s806', 'Constitution', Group.ATTRIBUTES, x10p10(806), Fresh.R, False),
    Row('s814', 'Dexterity', Group.ATTRIBUTES, x10p10(814), Fresh.R, False),
    Row('s810', 'Wisdom', Group.ATTRIBUTES, x10p10(810), Fresh.R, False),
    Row('ferocity', 'Ferocity', Group.ATTRIBUTES, ferocity(), Fresh.R, True),

    # -- Defensive: the sheet's mitigation lines, score + the mitigation %
    # they buy (measured in game: armor over 219.6, protection over 73.7,
    # then invulnerability applied to what gets through). --
    Row('armor', 'Armor', Group.DEFENSIVE, armor(False), Fresh.R, False),
    Row('evade', 'Evade Chance', Group.DEFENSIVE, chance(254, 100, 308, 814, 0), Fresh.R, False,
        'The rating column is the rating id plus half your Dexterity, measured in game on three characters.'),
    Row('prot_holy', 'Holy Prot', Group.DEFENSIVE, prot(928, 810, 907, False), Fresh.R, False),
    Row('prot_unholy', 'Unholy Prot', Group.DEFENSIVE, prot(929, 810, 908, False), Fresh.R, False),
    Row('prot_cold', 'Cold Prot', Group.DEFENSIVE, prot(157, 808, 167, False), Fresh.R, False),
    Row('prot_elec', 'Elec Prot', Group.DEFENSIVE, prot(927, 808, 906, False), Fresh.R, False),
    Row('prot_fire', 'Fire Prot', Group.DEFENSIVE, prot(926, 808, 905, False), Fresh.R, False),
    Row('immunity', 'Immunity Chance', Group.DEFENSIVE, chance(326, 100, 490, 0, 0), Fresh.R, False,
        'Max Immunity caps this; it is a separate row.'),
    Row('critigation_chance', 'Critigation Chance', Group.DEFENSIVE, rating(1000016), Fresh.R, False),
    Row('critigation_amount', 'Critigation Amount', Group.DEFENSIVE, rating(1000018), Fresh.R, False),
    Row('heal_rating', 'Heal Rating', Group.DEFENSIVE, heal(), Fresh.R, True),
    Row('s979', 'Retributive Magic', Group.DEFENSIVE, raw(979), Fresh.R, True),
    Row('s977', 'Retributive Melee', Group.DEFENSIVE, raw(977), Fresh.R, True),
    Row('s978', 'Retributive Ranged', Group.DEFENSIVE, raw(978), Fresh.R, True,
        'Measured from one gear source.'),
    Row('s329', 'Max Immunity %', Group.DEFENSIVE, x100(329), Fresh.D, False),
    Row('s535', 'Healing Efficiency', Group.DEFENSIVE, x100(535), Fresh.D, False,
        '100 % is neutral.'),
    Row('s330', 'Received Healing', Group.DEFENSIVE, raw_pct(330), Fresh.D, False),
    Row('s974', 'Damage Deflection', Group.DEFENSIVE, raw(974), Fresh.D, False),
    Row('s240', 'Movement Speed', Group.DEFENSIVE, raw_pct(240), Fresh.D, False),
    Row('s241', 'OOC Move Speed', Group.DEFENSIVE, raw_pct(241), Fresh.D, False),

    # -- Offensive: the sheet lines that raise your own output. Common
    # first, then the melee-only lines, then the magic ones. --
    Row('crit_chance', 'Critical Chance', Group.OFFENSIVE, crit_chance(), Fresh.R, False),
    Row('crit_dmg', 'Critical Bonus Damage', Group.OFFENSIVE, crit_dmg(), Fresh.R, False,
        'The +% base is read from one stat and was measured on one character.'),
    Row('tenacity', 'Tenacity', Group.OFFENSIVE, rating(1000017), Fresh.R, False),
    Row('fatality', 'Fatality Chance', Group.OFFENSIVE, chance(375, 1, 475, 0, 0), Fresh.R, False,
        'Rating over 36.6 on top of the 20 percent base every character has.'),
    Row('hate', 'Hate Modification', Group.OFFENSIVE, hate(), Fresh.R, False,
        'Hate Increase minus Hate Decrease over 36.6, plus the signed percent a stance or gear sets.'),
    Row('hit', 'Hit Bonus Chance', Group.OFFENSIVE, chance(0, 1, 310, 0, 0), Fresh.R, False,
        'Rating over 36.6; the PvP card adds its own rating on top.'),
    Row('s152', 'Penetration Rating', Group.OFFENSIVE, raw(152), Fresh.R, True,
        'Named by the engine; no rating-to-effect conversion has been measured, so it shows raw.'),
    # melee
    Row('combat_rating', 'Combat Rating', Group.OFFENSIVE, cdi(False), Fresh.R, False),
    Row('weapon_dmg', 'Weapon Damage Increase', Group.OFFENSIVE, weapon_dmg(), Fresh.R, False),
    Row('s840', 'Damage Multiplier', Group.OFFENSIVE, raw_pct(840), Fresh.D, False,
        'Outgoing damage; stances land here.'),
    Row('offhand', 'Offhand Attack Chance', Group.OFFENSIVE, chance(1071, 1, 1099, 0, 0), Fresh.R, False),
    Row('armor_pen', 'Armor Penetration', Group.OFFENSIVE, pen(449), Fresh.R, False),
    # magic
    Row('spell_dmg', 'Bonus Spell Damage', Group.OFFENSIVE, spell(False, 0), Fresh.R, True),
    Row('s1041', 'Base Spell Damage', Group.OFFENSIVE, raw(1041), Fresh.D, False),
    Row('s380', 'Spell Fatality Chance', Group.OFFENSIVE, raw_pct(380), Fresh.R, True),
    Row('s536', 'Magic Damage Modifier', Group.OFFENSIVE, pct_base(536, 100), Fresh.D, False,
        '100 is neutral.'),
    Row('spell_pen', 'Spell Penetration', Group.OFFENSIVE, pen(452), Fresh.R, False),
    Row('s252', 'Miss Chance %', Group.OFFENSIVE, raw_pct(252), Fresh.D, False),

    # -- PvP Stats: the game's PvP Stats tab, one row per line, valued "season / overall" like its two columns. Experience and Pit Master's Arena Kills are left out: the game sends them for your own character only. --
    Row('pvp_kills', 'Kills', Group.PVP_STATS, pair(1382, 656), Fresh.S, False,
        'This season / overall.'),
    Row('pvp_deaths', 'Deaths', Group.PVP_STATS, pair(1383, 658), Fresh.S, False,
        'This season / overall.'),
    Row('pvp_fatalities', 'Fatalities', Group.PVP_STATS, pair(1385, 1380), Fresh.S, False,
        'This season / overall.'),
    Row('s1097', 'Murder Points', Group.PVP_STATS, raw(1097), Fresh.S, False,
        'Overall only: the sheet keeps no season count.'),
    Row('pvp_annih_wins', 'Annihilation Wins', Group.PVP_STATS, pair(1386, 666), Fresh.S, False,
        'This season / overall.'),
    Row('pvp_annih_losses', 'Annihilation Losses', Group.PVP_STATS, pair(1392, 667), Fresh.S, False,
        'This season / overall.'),
    Row('pvp_cts_wins', 'CTS Wins', Group.PVP_STATS, pair(1387, 668), Fresh.S, False,
        'Capture the Skull. This season / overall.'),
    Row('pvp_cts_losses', 'CTS Losses', Group.PVP_STATS, pair(1393, 669), Fresh.S, False,
        'Capture the Skull. This season / overall.'),
    Row('pvp_conquest_wins', 'Conquest Wins', Group.PVP_STATS, pair(1388, 1000026), Fresh.S, False,
        'This season / overall.'),
    Row('pvp_conquest_losses', 'Conquest Losses', Group.PVP_STATS, pair(1394, 1000027), Fresh.S, False,
        'This season / overall.'),
    Row('pvp_tournament_wins', 'Tournament Wins', Group.PVP_STATS, pair(1389, 1000025), Fresh.S, False,
        "This season / overall. The season id follows the sheet's layout; no season win has been measured yet."),
    Row('pvp_siege_wins', 'Siege Wins', Group.PVP_STATS, pair(1390, 670), Fresh.S, False,
        'This season / overall.'),
    Row('pvp_siege_losses', 'Siege Losses', Group.PVP_STATS, pair(1395, 671), Fresh.S, False,
        'This season / overall.'),
    Row('pvp_abandoned', 'Minigames Abandoned', Group.PVP_STATS, pair(1397, 1376), Fresh.S, False,
        'This season / overall.'),
    Row('s690', 'PvP XP Modifier', Group.PVP_STATS, raw_pct(690), Fresh.R, False),
    # The PvP view's two record lines.
    Row('pvp_kd', 'Overall K/D', Group.PVP_STATS, pair(656, 658), Fresh.S, False,
        'Overall kills / overall deaths.'),
    Row('pvp_minigames', 'Minigame W/L', Group.PVP_STATS, minigame_wl(), Fresh.S, False,
        'Overall wins / losses, summed over Annihilation, Capture the Skull and Conquest.'),

    # -- PvP Combat: the game's PvP Combat tab, in its order: the Combat Stats card, then Protection, then Bonus Spell Damage per school, then PvP Taps. --
    Row('pvp_evade', 'Evade Chance', Group.PVP_COMBAT, chance(254, 100, 308, 814, 309), Fresh.R, False),
    Row('pvp_hit', 'Hit Bonus Chance', Group.PVP_COMBAT, chance(0, 1, 310, 0, 311), Fresh.R, False),
    Row('pvp_immunity', 'Immunity Chance', Group.PVP_COMBAT, chance(326, 100, 490, 0, 1100), Fresh.R, False),
    Row('pvp_armor', 'Armor', Group.PVP_COMBAT, armor(True), Fresh.R, False),
    Row('pvp_combat_rating', 'Combat Damage Increase', Group.PVP_COMBAT, cdi(True), Fresh.R, False,
        'The Combat Rating with the PvP rating on top; its effect is the damage per second it adds.'),
    Row('pvp_prot_holy', 'Holy Prot', Group.PVP_COMBAT, prot(928, 810, 907, True), Fresh.R, False),
    Row('pvp_prot_unholy', 'Unholy Prot', Group.PVP_COMBAT, prot(929, 810, 908, True), Fresh.R, False),
    Row('pvp_prot_cold', 'Cold Prot', Group.PVP_COMBAT, prot(157, 808, 167, True), Fresh.R, False),
    Row('pvp_prot_elec', 'Elec Prot', Group.PVP_COMBAT, prot(927, 808, 906, True), Fresh.R, False),
    Row('pvp_prot_fire', 'Fire Prot', Group.PVP_COMBAT, prot(926, 808, 905, True), Fresh.R, False),
    # One line per school (holy 878, unholy 879, cold 158, electrical 877, fire 876), each the school's whole
    # spell total plus the PvP magic damage 226 (measured in game: the sheet's per-school block).
    Row('pvp_spell_holy', 'Holy Spell Damage', Group.PVP_COMBAT, spell(True, 878), Fresh.R, True),
    Row('pvp_spell_unholy', 'Unholy Spell Damage', Group.PVP_COMBAT, spell(True, 879), Fresh.R, True),
    Row('pvp_spell_cold', 'Cold Spell Damage', Group.PVP_COMBAT, spell(True, 158), Fresh.R, True),
    Row('pvp_spell_elec', 'Elec Spell Damage', Group.PVP_COMBAT, spell(True, 877), Fresh.R, True),
    Row('pvp_spell_fire', 'Fire Spell Damage', Group.PVP_COMBAT, spell(True, 876), Fresh.R, True),
    Row('pvp_tap_phys', 'Health Tap Phys', Group.PVP_COMBAT, tap(894, 227, 1, 477, 478), Fresh.R, False,
        'PvP gear ratings convert like the PvE ones. Buff percents carry over from the PvE line.'),
    Row('pvp_tap_phys_mana', 'Mana Tap Phys', Group.PVP_COMBAT, tap(895, 276, 1, 481, 482), Fresh.R, False,
        'PvP gear ratings convert like the PvE ones. Buff percents carry over from the PvE line.'),
    Row('pvp_tap_phys_stam', 'Stam Tap Phys', Group.PVP_COMBAT, tap(896, 277, 1, 493, 494), Fresh.R, False,
        'PvP gear ratings convert like the PvE ones. Buff percents carry over from the PvE line.'),
    Row('pvp_tap_magic', 'Health Tap Magic', Group.PVP_COMBAT, tap(533, 0, 100, 476, 479), Fresh.R, False,
        'PvP gear ratings convert like the PvE ones. Buff percents carry over from the PvE line.'),
    Row('pvp_tap_magic_mana', 'Mana Tap Magic', Group.PVP_COMBAT, tap(544, 0, 100, 480, 483), Fresh.R, False,
        'PvP gear ratings convert like the PvE ones. Buff percents carry over from the PvE line.'),
    Row('pvp_tap_magic_stam', 'Stam Tap Magic', Group.PVP_COMBAT, tap(545, 0, 100, 492, 495), Fresh.R, False,
        'PvP gear ratings convert like the PvE ones. Buff percents carry over from the PvE line.'),
)

# The full catalog in Group order, each group's rows in declaration order.
ROWS: tuple[Row, ...] = tuple(r for g in Group for r in _DECLARED if r.group is g)
_BY_KEY = {r.key: r for r in ROWS}

# Row keys retired after a release shipped them, with the live keys that
# replace them: a saved selection naming one gets its successors in place.
# Append-only — a key stays here for as long as profiles that name it can be
# opened. A key retired with no successor is deliberately absent: validation
# drops it.
ALIASES: dict[str, tuple[str, ...]] = {
    # The two Kills / Deaths lines (overall, this season) are now the season /
    # overall pairs of the Kills and Deaths rows.
    'pvp_kills_deaths': ('pvp_kills', 'pvp_deaths'),
    'season_kd': ('pvp_kills', 'pvp_deaths'),
    # Overall-only Tournament / Conquest lines, now season / overall pairs.
    's1000025': ('pvp_tournament_wins',),
    's1000026': ('pvp_conquest_wins',),
    's1000027': ('pvp_conquest_losses',),
    # The PvP Hit / Immunity ratings, now folded into the two PvP Combat chance
    # rows that add them to the PvE rating.
    's311': ('pvp_hit',),
    's1100': ('pvp_immunity',),
    # The PvP Bonus Spell Damage line (the highest school), now one line per
    # school, as the game's PvP Combat tab has them.
    'pvp_spell_dmg': ('pvp_spell_holy', 'pvp_spell_unholy', 'pvp_spell_cold',
                      'pvp_spell_elec', 'pvp_spell_fire'),
}

# Teardown gate + title + player gate, always polled.
ALWAYS_IDS = (1, 54, 67, 70, 804, 808, 810, 814)

# The panel's PvP tab: the game's PvP Combat tab in its order and with its
# columns, less the PvP taps, then two record lines — (title, column titles,
# (label, catalog key) lines). Fixed whatever rows the user picked; a line's
# value splits into the columns at the rating.
PVP_VIEW: tuple[tuple[str, tuple[str, ...], tuple[tuple[str, str], ...]], ...] = (
    ('PvP Combat Stats', ('Rating', 'Effect'), (
        ('Evade Chance', 'pvp_evade'),
        ('Hit Bonus Chance', 'pvp_hit'),
        ('Immunity Chance', 'pvp_immunity'),
        ('Armor', 'pvp_armor'),
        ('Combat Damage Increase', 'pvp_combat_rating'),
    )),
    ('Protection', ('Score', 'Mitigation'), (
        ('Holy', 'pvp_prot_holy'),
        ('Unholy', 'pvp_prot_unholy'),
        ('Cold', 'pvp_prot_cold'),
        ('Electrical', 'pvp_prot_elec'),
        ('Fire', 'pvp_prot_fire'),
    )),
    ('Bonus Spell Damage', ('Damage',), (
        ('Holy', 'pvp_spell_holy'),
        ('Unholy', 'pvp_spell_unholy'),
        ('Cold', 'pvp_spell_cold'),
        ('Electrical', 'pvp_spell_elec'),
        ('Fire', 'pvp_spell_fire'),
    )),
    ('Record', (), (('Overall K/D', 'pvp_kd'), ('Minigame W/L', 'pvp_minigames'))),
)


# ============================================================================
# QUERIES
# ============================================================================


def find(key: str) -> Row | None:
    return _BY_KEY.get(key)


def resolve(key: str) -> tuple[str, ...]:
    """The live keys a stored row key stands for: itself when the catalog has
    it, its successors when it was retired with some, nothing otherwise."""
    if key in _BY_KEY:
        return (key,)
    return ALIASES.get(key, ())


def select(keys: list[str]) -> list[Row]:
    """The rows `keys` name in the panel's order: section by section in Group
    order, each section in the order `keys` gives it. Unknown keys skipped,
    duplicates collapsed (first kept)."""
    picked: list[Row] = []
    for key in keys:
        row = _BY_KEY.get(key)
        if row is not None and row not in picked:
            picked.append(row)
    return sorted(picked, key=lambda r: r.group.index)


def default_keys() -> list[str]:
    """What a profile with no `inspect.rows` shows: the Summary group."""
    return [r.key for r in ROWS if r.group is Group.SUMMARY]


def shown(selection: list[str] | None) -> list[Row]:
    """The rows a panel with this `inspect.rows` shows (what the build bakes)."""
    return select(default_keys() if selection is None else selection)


def watch_ids(selected: list[Row]) -> list[int]:
    """Ascending, deduped union of the rows' ids and ALWAYS_IDS."""
    ids = set(ALWAYS_IDS)
    for r in selected:
        ids.update(r.kind.needed_ids)
    return sorted(ids)


def pvp_rows() -> list[Row]:
    """Every catalog row the PvP view reads, in its order."""
    return [_BY_KEY[key] for _, _, lines in PVP_VIEW for _, key in lines]


# ============================================================================
# EDITING A ROW LIST (the inspect dialog's picker)
# ============================================================================


def matches(row: Row, query: str) -> bool:
    """Search over a row's label, key, group and every stat id it reads
    (`1382` finds Kills)."""
    q = query.strip().lower()
    if not q:
        return True
    hay = (row.label.lower(), row.key.lower(), row.group.label.lower())
    return any(q in h for h in hay) or any(q == str(i) for i in row.kind.needed_ids)


def add_keys(active: list[str], keys: list[str]) -> list[str]:
    """`active` with `keys` added, each last in its section."""
    return [r.key for r in select(active + keys)]


def move_keys(active: list[str], keys: list[str], delta: int) -> list[str]:
    """`active` with the rows `keys` moved one place up (-1) or down (+1)
    within their section, as a block; a row at its section's edge stays."""
    rows = select(active)
    out: list[str] = []
    for g in Group:
        section = [r.key for r in rows if r.group is g]
        order = range(len(section)) if delta < 0 else range(len(section) - 1, -1, -1)
        for i in order:
            j = i + delta
            if section[i] in keys and 0 <= j < len(section) and section[j] not in keys:
                section[i], section[j] = section[j], section[i]
        out.extend(section)
    return out


# The panel's height, estimated as KazBarsInspect lays it out (`round` is
# AS2's half-up), to warn before a selection runs off a 1080-tall screen in
# the panel's tallest state: a player target, with every section and the perks.
_REF_H = 1080


def _px(fs: int, ratio: float) -> int:
    return math.floor(fs * ratio + 0.5)


def _stacked(lines: list[int], fs: int) -> int:
    line = _px(fs, 1.4)
    stat_line = line + _px(fs, 0.15)
    bodies = [n * stat_line for n in lines if n > 0] + [_px(fs, 2.4)]  # the perk icons last
    sections = sum(_px(fs, 0.5 if i == 0 else 0.75) + line + _px(fs, 0.2) + 1 + _px(fs, 0.4) + body
                   for i, body in enumerate(bodies))
    title = _px(_px(fs, 1.25), 1.4) + 2 * _px(fs, 0.25)
    return title + sections + _px(fs, 0.85)


def panel_height(selected: list[Row], fs: int) -> int:
    return _stacked([sum(1 for r in selected if r.group is g) for g in Group], fs)


def pvp_view_height(fs: int) -> int:
    return _stacked([len(lines) for _, _, lines in PVP_VIEW], fs)


def height_warning(selected: list[Row], fs: int) -> bool:
    """True when the panel (or its PvP view, if taller) at body size `fs`
    would be taller than 90 % of a 1080-tall screen."""
    return max(panel_height(selected, fs), pvp_view_height(fs)) > _REF_H * 0.9
