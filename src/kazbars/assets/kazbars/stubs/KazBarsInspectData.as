// KazBarsInspectData.as - The inspect panel's baked tables, split from the
// logic the way KazBarsData carries the grid config: one static init() the
// KazBarsInspect constructor pulls from. Every value here is measured game
// data — ids, ranks, names, the watch list — documented in
// docs/inspect-panel.md; read that before changing any number. Referenced
// only by KazBarsInspect, so it compiles in only on inspect-enabled builds.
class KazBarsInspectData {

    public static function init():Object {
        var d:Object = {};

        // Magic damage per school: cold is the low-range outlier as in every
        // school family (157 prot, 162 CR); the other four cluster at 876-879.
        d.spellIds = [158, 876, 877, 878, 879];

        // "Immeasurable Empowerment", the +100-all-attributes AA passive —
        // the ubiquitous member of the attribute-buff layer the sheet's CDI
        // excludes, and the one the panel can see and undo.
        d.aaBuffId = 4279994;

        // Slotted-perk buff id -> display rank: 113 perks, 114 ids, mostly in
        // contiguous per-archetype and per-class blocks over 4279889-4282396.
        // The pool shape is fixed and every block fills its quota exactly --
        // 9 General, 5 per archetype, 7 per class -- which is what settles
        // the one ambiguous pair (Guardian stops at 4281426; Void of Madness
        // 4281429 is the Dark Templar's seventh). Rank is id order, so the
        // row reads General -> archetype -> class and stays stable.
        // Two entries break the block pattern and are NOT typos:
        //   4279994 is also aaBuffId -- the bugged +100-all-attrs passive
        //     IS a slotted General perk, so it is in both.
        //   4483617 (Point Blank Shot) is the Ranger's seventh, added by a
        //     later patch far outside the band. 4282385 shares its rank as
        //     an alias, so whichever id the game applies renders one icon.
        d.perkIds = {i4279889: 0, i4279980: 1, i4279994: 2, i4279995: 3, i4279996: 4,
                     i4279997: 5, i4280003: 6, i4280004: 7, i4280005: 8, i4280100: 9,
                     i4280101: 10, i4280167: 11, i4280208: 12, i4280209: 13, i4280766: 14,
                     i4280968: 15, i4280978: 16, i4280980: 17, i4280981: 18, i4281007: 19,
                     i4281008: 20, i4281009: 21, i4281010: 22, i4281011: 23, i4281107: 24,
                     i4281108: 25, i4281109: 26, i4281110: 27, i4281111: 28, i4281211: 29,
                     i4281212: 30, i4281213: 31, i4281214: 32, i4281215: 33, i4281216: 34,
                     i4281217: 35, i4281420: 36, i4281421: 37, i4281422: 38, i4281423: 39,
                     i4281424: 40, i4281425: 41, i4281426: 42, i4281429: 43, i4281445: 44,
                     i4281446: 45, i4281447: 46, i4281451: 47, i4281452: 48, i4281453: 49,
                     i4281564: 50, i4281565: 51, i4281566: 52, i4281567: 53, i4281568: 54,
                     i4281571: 55, i4281572: 56, i4281728: 57, i4281729: 58, i4281730: 59,
                     i4281731: 60, i4281732: 61, i4281733: 62, i4281734: 63, i4281884: 64,
                     i4281885: 65, i4281886: 66, i4281887: 67, i4281888: 68, i4281889: 69,
                     i4281890: 70, i4281940: 71, i4281941: 72, i4281942: 73, i4281943: 74,
                     i4281944: 75, i4281945: 76, i4281946: 77, i4282096: 78, i4282100: 79,
                     i4282105: 80, i4282107: 81, i4282108: 82, i4282109: 83, i4282110: 84,
                     i4282139: 85, i4282140: 86, i4282142: 87, i4282156: 88, i4282159: 89,
                     i4282160: 90, i4282161: 91, i4282300: 92, i4282301: 93, i4282302: 94,
                     i4282303: 95, i4282304: 96, i4282305: 97, i4282306: 98, i4282307: 99,
                     i4282308: 100, i4282309: 101, i4282310: 102, i4282311: 103,
                     i4282312: 104, i4282313: 105, i4282381: 106, i4282382: 107,
                     i4282383: 108, i4282384: 109, i4282385: 112, i4282387: 110,
                     i4282396: 111, i4483617: 112};

        // The game's own perk bar has six FIXED slots in three colour-coded
        // pairs -- General, Archetype, Class -- so a perk renders into its
        // own pair rather than filling left to right. The table is ordered
        // General, then the four archetypes, then the twelve classes, so two
        // rank boundaries are the whole category test.
        d.perkGenMax = 8;
        d.perkArchMax = 28;

        // Three of every class's seven perks cost BOTH class slots (36 in
        // all, maintainer-marked off the in-game perk UI). The game paints
        // such a perk across both boxes, so the panel does too -- keyed by
        // rank, since that is what placePerks already carries.
        d.perk2Slot = {r29: 1, r30: 1, r31: 1, r36: 1, r37: 1, r38: 1, r43: 1, r44: 1,
                       r45: 1, r50: 1, r51: 1, r52: 1, r57: 1, r58: 1, r62: 1, r64: 1,
                       r65: 1, r66: 1, r71: 1, r72: 1, r73: 1, r78: 1, r79: 1, r80: 1,
                       r85: 1, r86: 1, r87: 1, r92: 1, r93: 1, r94: 1, r99: 1, r100: 1,
                       r101: 1, r106: 1, r107: 1, r112: 1};

        // Rank -> name for the hover chip, so an icon the player cannot place
        // still reads. Baked rather than read off the buff (no name field is
        // confirmed on a buff-list entry) and indexed by the same rank the row
        // already carries. Rank 112 is the Ranger's aliased pair -- both ids
        // are the one perk, and the name is the real one, Point Blank Shot.
        d.perkNames = ["Pressing Strikes", "Chromatic Warding",
                       "Immeasurable Empowerment", "Precise Strikes",
                       "Fortifying Empowerment", "Field of War", "Quick Steps",
                       "Decisive Strikes", "Elusive Nature", "Prelate at Arms",
                       "Empowered Mending", "Steadfast Faith", "Deliverance",
                       "Divine Luster", "Rear Guard", "Empowered Vitality", "Resolve",
                       "Vindication", "Avoid Entanglements", "Flanking",
                       "Tainted Weapons", "Liberation", "Avoid Entrapment",
                       "Arcane Plunder", "Ethereal Escape", "Unbinding Charm",
                       "Enchanter", "Will of the Sublime", "Transcendence",
                       "Prince of Terror", "From the Beyond", "Red Shadows of Xotli",
                       "Quickening Death", "Enslaving Fire", "Feeding the Pyre",
                       "Hunger for More", "Stall the Advance", "Prime Initiative",
                       "Sustaining Wrath", "Champion Spirit", "Deliberate Reprisal",
                       "Counterweight", "Master at Arms", "Void of Madness",
                       "Scarab Knight", "Blood Shroud", "Death Lord", "Crimson Succor",
                       "Unwilling Sacrifice", "Sanguine Infusion", "Rally",
                       "One Last Push", "Battlefield Commander", "Assail",
                       "Break Through", "Rout", "Besiege", "Shimmering Invocation",
                       "Emissary of Elysium", "Wandering Disciple",
                       "Shield of Brilliance", "Inclusion", "Blessed Soul",
                       "Light the Path", "Sleuth of Bears", "Spirit of Yggdrasil",
                       "Vision of the Sky", "Feral Growl", "Maul", "Surge of Bile",
                       "Ursine Bond", "Idol of Dark Rejuvenation",
                       "Coils of the Serpent", "Eyes of Set", "Leviathan's Call",
                       "Constriction", "Forked Lightning", "Lull", "Master Assassin",
                       "Choking Powder", "Cover of Dusk", "Disfigure", "Dance of Death",
                       "Castration", "Sins of the Flesh", "Tools at Hand",
                       "At the Gates", "What it Takes", "Bone Shatter", "Upheaval",
                       "Without Warning", "Determination", "Boil Blood",
                       "Ruinous Power", "Unleash the Underworld", "Renegotiation",
                       "Ring of Fire", "Cacodemon", "Bindings of the Skylord",
                       "Unearthly Apprentice", "Supreme Lich", "Nightmare Companions",
                       "Decays of Nature", "Chilling Breath", "Funeral Rites",
                       "Withered Blasphemy", "Hunting Hawk", "Crossfire",
                       "Jarring Shot", "Clout", "Deadly Draw", "Running Shot",
                       "Point Blank Shot"];

        // Per-slot-pair border and plate colours — the game's General /
        // Archetype / Class colour coding.
        d.perkEdge = [0x4A7FA5, 0xA34A4A, 0x555555];
        d.perkFill = [0x0F1C26, 0x260F0F, 0x151515];

        // Class id 67 -> sheet name; all twelve classes measured off live
        // targets. An unmapped id (a future patch?) still just omits the
        // class rather than guess one.
        d.classNames = {c18: "Barbarian", c20: "Guardian", c22: "Conqueror",
                        c24: "Priest of Mitra", c28: "Tempest of Set",
                        c29: "Bear Shaman", c31: "Dark Templar",
                        c34: "Assassin", c39: "Ranger", c41: "Necromancer",
                        c43: "Herald of Xotli", c44: "Demonologist"};

        d.watchIds = [
            1, 27, 525, 54, 67, 70, 507,
            448, 450, 451, 334, 157, 926, 927, 928, 929, 911,
            902, 167, 905, 906, 907, 908,
            312, 711, 713, 804, 808, 810, 814, 1403,
            875, 866, 867, 868, 869, 870, 871, 872, 873,
            162, 1007, 1008, 1009, 1010, 1095, 1096,
            861, 158, 876, 877, 878, 879, 1041,
            1000016, 1000017, 1000018,
            454, 458, 225, 226, 656, 658
        ];

        // Collapsed, the only thing on screen is a static label, so the pass
        // reads what the teardown gate needs to notice a dead subject and
        // nothing else at all: 2 reads, not 65.
        d.gateIds = [1, 54];

        return d;
    }
}
