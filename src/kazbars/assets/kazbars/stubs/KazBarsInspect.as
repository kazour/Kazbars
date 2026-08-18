// KazBarsInspect.as - Target inspect panel: a combat sheet for the current
// target in the visual language of the game's default inspect window.
// Runtime-drawn chrome + dynamic text fields (Arial resolves against the faces
// embedded in base.swf), so it needs no new symbols.
//
// Reading rules are measured engine behaviour, not style: gear and rating ids
// never fire SignalStatChanged and signal-time reads race the server, so the
// 250 ms GetStat poll is the data path; 3 clean passes settle before the panel
// shows; id 1 + id 54 collapsing together is the logout/zone teardown burst,
// not data. Every synthesis constant below is a level-80 measurement, so an
// off-80 target shows raw ratings with the %-decodes suppressed.
//
// The PvP section and the Perks row are baked config gates (showPvp /
// showPerks). The Perks row shows the slotted AA perk buffs detected on a
// player target's buff list as game icons, RDB-loaded through the same
// ImageLoader path the grids use; a player slots at most 6 (2 General,
// 2 Archetype, 2 Class — some Class perks cost both slots). Hovering an icon
// names it from a baked table, hit-tested off a Mouse listener rather than
// rollover handlers — see hoverTick().
//
// Positioning mirrors the stopwatch: X/Y, font size and collapsed state baked
// into config are the first-session defaults (the name strip shows live
// coordinates while dragging), and drag + collapse persist via the archive
// (inx/iny/inc, master switch
// inv). All geometry
// derives from fontSize.
//
// Driven from KazBars: createPanel() in onLoad, setSubject() from
// SlotTargetChanged (first statement, so clears and raw tids both arrive),
// loadState()/saveState() from the module archive, previewOn()/previewOff()
// from the shared preview, cleanup() on deactivate.
class KazBarsInspect {
    private var rootClip:MovieClip;

    // Config (set by configure())
    private var START_X:Number;
    private var START_Y:Number;
    private var START_COLLAPSED:Boolean;
    private var FS:Number;
    private var SHOW_PVP:Boolean;
    private var SHOW_PERKS:Boolean;

    // Geometry — every value is Math.round(FS x ratio), so the panel scales
    // as one piece.
    private var PAD:Number;       // 0.85  plate padding
    private var LABEL_W:Number;   // 8.6   label column
    private var COL_GAP:Number;   // 0.85  label -> value gap
    private var VALUE_W:Number;   // 12.0  value column
    private var NAME_FS:Number;   // 1.15  name header font size
    private var TITLE_H:Number;   // 1.85  title band — the stopwatch's, so the
                                  //       family's expanded title bars match
    private var NAME_GAP:Number;  // 0.5   name -> first section header
    private var SECT_GAP:Number;  // 0.75  space above a section header
    private var RULE_GAP:Number;  // 0.2   header baseline -> 1px rule
    private var ROWS_GAP:Number;  // 0.4   rule -> first stat row
    private var LEAD:Number;      // 0.15  TextFormat leading
    private var BTN:Number;       // 1.1   collapse-button box
    private var ICO:Number;       // 2.4   perk icon box
    private var ICO_GAP:Number;   // 0.35  gap between perk icons
    private var TIP_PAD:Number;   // 0.3   perk-name chip padding, and its gap
                                  //       above the icon row
    private var COLL_W:Number;    // 15.8  collapsed plate: the stopwatch's
    private var COLL_H:Number;    // 2.0   190x24 at the default FS 12
    private var COLL_PAD:Number;  // 0.55  collapsed plate padding
    private var W:Number;         // 2xPAD + LABEL_W + COL_GAP + VALUE_W

    // UI
    private var m_Panel:MovieClip;
    private var bg:MovieClip;
    private var body:MovieClip;
    private var collapseBtn:MovieClip;
    private var collapsed:Boolean;
    private var panelVis:Boolean;     // mirrors m_Panel._visible; hoverTick
                                      // asks every mouse move
    private var titleH:Number;
    private var fullH:Number;
    private var nameTF:TextField;
    private var collTF:TextField;     // the collapsed bar's whole content
    private var curW:Number;
    private var dragX:Number;         // panel position at press, so a
    private var dragY:Number;         // collapsed press that never moved
                                      // reads as a click (endDrag)
    private var pveHdrTF:TextField;
    private var pvpHdrTF:TextField;
    private var pveLabTF:TextField;
    private var pveValTF:TextField;
    private var pvpLabTF:TextField;
    private var pvpValTF:TextField;
    private var dragMC:MovieClip;
    private var coordTF:TextField;
    private var curH:Number;
    private var m_ruleA:Number;   // rule offsets from the last layout pass,
    private var m_ruleB:Number;   // replayed on collapse; -1 = not on screen
    private var m_ruleC:Number;   // perks-section rule, same replay contract
    private var perksHdrTF:TextField;
    private var perkSlots:Array;      // 6 boxes, each with an m_icon child
    private var perkLoaders:Array;    // one MovieClipLoader per slot
    private var perksShown:Boolean;
    private var perkRowY:Number;      // icon row top from the last layout
                                      // pass; hoverTick's hit test
    private var tipMC:MovieClip;      // perk-name chip, hidden until hovered
    private var tipTF:TextField;
    private var tipSlot:Number;       // slot the chip is drawn for, -1 = none
    private var mouseLsnr:Object;     // hover source; see hoverTick()

    // Subject / poll state
    private var m_Subject:Object;
    private var subjName:String;
    private var subjKey:String;
    private var subjIsPlayer:Number;  // 1 player, 0 not, -1 unanswered
    private var subjPlayer:Boolean;   // the isPlayer() gate, settled once a
                                      // pass — six call sites ask it
    private var aaOn:Boolean;         // +100-all-attrs AA visible on subject
    private var curPerks:Array;       // detected perks, table order, capped at 6
    private var curPerkRanks:Array;   // the same six slots as ranks, for names
    private var iconInst:Object;      // "i<buffId>" -> icon instance; static
                                      // game data, so read once not per pass
    private var pollIv:Number;
    private var curV:Object;      // stat id -> settled mode-2 value
    private var m1Str:Number;     // raw mode-1 804 / 814 — the pre-%-multiplier
    private var m1Dex:Number;     // attribute sum, CDI attr term only
    private var haveFull:Boolean;
    private var warmup:Number;
    private var previewMode:Boolean;
    private var active:Boolean;
    private var pvpShown:Boolean;

    // Render cache — assign only on change; TextField.text writes are the
    // expensive part and most 250 ms passes change nothing
    private var lastName:String;
    private var lastPve:String;
    private var lastPvp:String;
    private var lastPerks:String;

    private var watchIds:Array;
    private var gateIds:Array;
    private var SPELL_IDS:Array;
    private var CLASS_NAMES:Object;
    private var AA_BUFF_ID:Number;
    private var PERK_IDS:Object;      // "i<buffId>" -> display rank
    private var PERK_GEN_MAX:Number;  // last General rank
    private var PERK_ARCH_MAX:Number; // last Archetype rank
    private var PERK_2SLOT:Object;    // "r<rank>" -> costs both class slots
    private var PERK_NAMES:Array;     // rank -> perk name, for the hover chip
    private var PERK_EDGE:Array;      // per-slot-pair border colour
    private var PERK_FILL:Array;      // per-slot-pair plate colour
    private var DASH:String;

    public function KazBarsInspect(owner:KazBars, root:MovieClip) {
        rootClip = root;
        m_Subject = null;
        subjName = "";
        subjKey = "";
        curV = {};
        m1Str = 0;
        m1Dex = 0;
        iconInst = {};
        subjPlayer = false;
        panelVis = false;
        perkRowY = 0;
        haveFull = false;
        warmup = 0;
        previewMode = false;
        active = true;
        pvpShown = false;
        lastName = "";
        lastPve = "";
        lastPvp = "";
        curW = 0;
        curH = 0;
        aaOn = false;
        curPerks = new Array();
        curPerkRanks = new Array();
        lastPerks = "";
        perksShown = false;
        tipSlot = -1;
        DASH = String.fromCharCode(8212);
        collapsed = false;
        titleH = 0;
        fullH = 0;
        subjIsPlayer = -1;
        // Magic damage per school: cold is the low-range outlier as in every
        // school family (157 prot, 162 CR); the other four cluster at 876-879.
        SPELL_IDS = [158, 876, 877, 878, 879];
        // "Immeasurable Empowerment", the +100-all-attributes AA passive —
        // the ubiquitous member of the attribute-buff layer the sheet's CDI
        // excludes, and the one the panel can see and undo.
        AA_BUFF_ID = 4279994;
        // Slotted-perk buff id -> display rank: 113 perks, 114 ids, mostly in
        // contiguous per-archetype and per-class blocks over 4279889-4282396.
        // The pool shape is fixed and every block fills its quota exactly --
        // 9 General, 5 per archetype, 7 per class -- which is what settles
        // the one ambiguous pair (Guardian stops at 4281426; Void of Madness
        // 4281429 is the Dark Templar's seventh). Rank is id order, so the
        // row reads General -> archetype -> class and stays stable.
        // Two entries break the block pattern and are NOT typos:
        //   4279994 is also AA_BUFF_ID -- the bugged +100-all-attrs passive
        //     IS a slotted General perk, so it is in both.
        //   4483617 (Point Blank Shot) is the Ranger's seventh, added by a
        //     later patch far outside the band. 4282385 shares its rank as
        //     an alias, so whichever id the game applies renders one icon.
        PERK_IDS = {i4279889: 0, i4279980: 1, i4279994: 2, i4279995: 3, i4279996: 4,
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
        PERK_GEN_MAX = 8;
        PERK_ARCH_MAX = 28;
        // Three of every class's seven perks cost BOTH class slots (36 in
        // all, maintainer-marked off the in-game perk UI). The game paints
        // such a perk across both boxes, so the panel does too -- keyed by
        // rank, since that is what placePerks already carries.
        PERK_2SLOT = {r29: 1, r30: 1, r31: 1, r36: 1, r37: 1, r38: 1, r43: 1, r44: 1,
                      r45: 1, r50: 1, r51: 1, r52: 1, r57: 1, r58: 1, r62: 1, r64: 1,
                      r65: 1, r66: 1, r71: 1, r72: 1, r73: 1, r78: 1, r79: 1, r80: 1,
                      r85: 1, r86: 1, r87: 1, r92: 1, r93: 1, r94: 1, r99: 1, r100: 1,
                      r101: 1, r106: 1, r107: 1, r112: 1};
        // Rank -> name for the hover chip, so an icon the player cannot place
        // still reads. Baked rather than read off the buff (no name field is
        // confirmed on a buff-list entry) and indexed by the same rank the row
        // already carries. Rank 112 is the Ranger's aliased pair -- both ids
        // are the one perk, and the name is the real one, Point Blank Shot.
        PERK_NAMES = ["Pressing Strikes", "Chromatic Warding",
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
        PERK_EDGE = [0x4A7FA5, 0xA34A4A, 0x555555];
        PERK_FILL = [0x0F1C26, 0x260F0F, 0x151515];
        // Class id 67 -> sheet name; all twelve classes measured off live
        // targets. An unmapped id (a future patch?) still just omits the
        // class rather than guess one.
        CLASS_NAMES = {c18: "Barbarian", c20: "Guardian", c22: "Conqueror",
                       c24: "Priest of Mitra", c28: "Tempest of Set",
                       c29: "Bear Shaman", c31: "Dark Templar",
                       c34: "Assassin", c39: "Ranger", c41: "Necromancer",
                       c43: "Herald of Xotli", c44: "Demonologist"};
        watchIds = [
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
        gateIds = [1, 54];
    }

    // =========================================================================
    // Setup
    // =========================================================================

    public function configure(cfg:Object):Void {
        if (cfg == null) return;
        START_X = Number(cfg.x);
        START_Y = Number(cfg.y);
        START_COLLAPSED = (cfg.collapsed == true);
        SHOW_PVP = (cfg.showPvp != false);
        SHOW_PERKS = (cfg.showPerks != false);
        FS = Number(cfg.fontSize);
        if (isNaN(FS) || FS < 8) FS = 12;
        PAD = Math.round(FS * 0.85);
        LABEL_W = Math.round(FS * 8.6);
        COL_GAP = Math.round(FS * 0.85);
        VALUE_W = Math.round(FS * 12);
        NAME_FS = Math.round(FS * 1.15);
        TITLE_H = Math.round(FS * 1.85);
        NAME_GAP = Math.round(FS * 0.5);
        SECT_GAP = Math.round(FS * 0.75);
        RULE_GAP = Math.round(FS * 0.2);
        ROWS_GAP = Math.round(FS * 0.4);
        LEAD = Math.round(FS * 0.15);
        BTN = Math.round(FS * 1.1);
        ICO = Math.round(FS * 2.4);
        ICO_GAP = Math.round(FS * 0.35);
        TIP_PAD = Math.round(FS * 0.3);
        // Collapsed the panel is a labelled bar, not a folded sheet, and it
        // is sized to sit beside the stopwatch's own collapsed bar: these
        // ratios land on its 190x24 at the default FS 12 and scale with the
        // rest of the panel from there.
        COLL_W = Math.round(FS * 15.8);
        COLL_H = Math.round(FS * 2);
        COLL_PAD = Math.round(FS * 0.55);
        W = PAD * 2 + LABEL_W + COL_GAP + VALUE_W;
    }

    public function createPanel():Void {
        // The host re-runs onLoad on this same instance; without this the old
        // interval and clip both leak.
        if (pollIv != null) {
            clearInterval(pollIv);
            pollIv = null;
        }
        if (mouseLsnr != null) {
            Mouse.removeListener(mouseLsnr);
            mouseLsnr = null;
        }
        if (m_Panel != null) m_Panel.removeMovieClip();
        m_Panel = rootClip.createEmptyMovieClip("kbInspect", rootClip.getNextHighestDepth());
        m_Panel._x = START_X;
        m_Panel._y = START_Y;
        m_Panel._visible = false;
        panelVis = false;

        collapsed = START_COLLAPSED;

        bg = m_Panel.createEmptyMovieClip("chrome", m_Panel.getNextHighestDepth());
        // Everything below the name strip, so collapsing is one _visible toggle.
        body = m_Panel.createEmptyMovieClip("body", m_Panel.getNextHighestDepth());

        nameTF = makeTF(m_Panel, "name", PAD,
                        Math.floor((TITLE_H - Math.round(NAME_FS * 1.4)) / 2),
                        W - PAD * 2 - BTN, Math.round(NAME_FS * 1.4),
                        NAME_FS, true, 0xF7A22B, "left");
        // Collapsed, the bar carries a static label and nothing else — no
        // target name, so no reason for a pass to read one. Its own field
        // rather than a re-formatted name strip: a TextFormat swap per fold
        // would have to be re-applied to the text every time.
        collTF = makeTF(m_Panel, "coll", COLL_PAD, 0, COLL_W - COLL_PAD * 2 - BTN,
                        Math.round(FS * 1.4), FS, true, 0xF7A22B, "left");
        collTF.text = "Inspect";
        collTF._y = Math.floor((COLL_H - collTF._height) / 2);
        collTF._visible = false;
        pveHdrTF = makeTF(body, "pveHdr", PAD, 0, LABEL_W, Math.round(FS * 1.4),
                          FS, true, 0xF7A22B, "left");
        pveHdrTF.autoSize = "left";
        pveHdrTF.text = "PvE";
        pvpHdrTF = makeTF(body, "pvpHdr", PAD, 0, LABEL_W, Math.round(FS * 1.4),
                          FS, true, 0xF7A22B, "left");
        pvpHdrTF.autoSize = "left";
        pvpHdrTF.text = "PvP";

        pveLabTF = makeTF(body, "pveLab", PAD, 0, LABEL_W, 10, FS, false, 0xC8C0B0, "left");
        pveValTF = makeTF(body, "pveVal", PAD + LABEL_W + COL_GAP, 0, VALUE_W, 10,
                          FS, false, 0x7AC142, "left");
        pvpLabTF = makeTF(body, "pvpLab", PAD, 0, LABEL_W, 10, FS, false, 0xC8C0B0, "left");
        pvpValTF = makeTF(body, "pvpVal", PAD + LABEL_W + COL_GAP, 0, VALUE_W, 10,
                          FS, false, 0x7AC142, "left");
        pveLabTF.autoSize = "left";
        pveValTF.autoSize = "left";
        pvpLabTF.autoSize = "left";
        pvpValTF.autoSize = "left";

        // Assigned once: absent data renders as the dash rather than dropping
        // a row, so layout() re-runs only on the PvP-visibility flip.
        pveLabTF.text = "Health\nArmor\nHoly Prot\nUnholy Prot\nCold Prot\nElec Prot\nFire Prot"
                      + "\nCritigation Chance\nCritigation Amount\nHeal Rating\nBonus Spell Dmg"
                      + "\nCombat Rating\nWeapon Dmg M/R\nCritical Chance\nCritical Damage"
                      + "\nTenacity\nFerocity";
        pvpLabTF.text = "Armor\nHoly Prot\nUnholy Prot\nCold Prot\nElec Prot\nFire Prot"
                      + "\nBonus Spell Dmg\nCombat Rating\nKills / Deaths";

        perksHdrTF = makeTF(body, "perksHdr", PAD, 0, LABEL_W, Math.round(FS * 1.4),
                            FS, true, 0xF7A22B, "left");
        perksHdrTF.autoSize = "left";
        perksHdrTF.text = "Perks";

        // Six slot boxes (the game's perk cap); an empty hairline box is the
        // row's em dash. Three levels on purpose: the box draws on the
        // unscaled slot, `hold` carries the scale, and the icon loads into
        // hold.m_icon. loadClip REPLACES its target clip and onLoadInit then
        // normalizes the arrival to 64x64 — so any scale set on the target
        // itself is overwritten, and the scale has to live on the parent.
        // Inset by 1 so the icon sits inside the border rather than over it.
        perkSlots = new Array();
        perkLoaders = new Array();
        var pi:Number = 0;
        while (pi < 6) {
            var ps:MovieClip = body.createEmptyMovieClip("perk" + pi, body.getNextHighestDepth());
            ps._x = PAD + pi * (ICO + ICO_GAP);
            var pair:Number = Math.floor(pi / 2);
            ps.beginFill(Number(PERK_FILL[pair]), 100);
            ps.lineStyle(1, Number(PERK_EDGE[pair]), 100);
            rectPath(ps, 0, 0, ICO, ICO);
            ps.endFill();
            var hold:MovieClip = ps.createEmptyMovieClip("hold", ps.getNextHighestDepth());
            hold._x = hold._y = 1;
            hold._xscale = hold._yscale = (ICO - 2) / 64 * 100;
            hold.createEmptyMovieClip("m_icon", hold.getNextHighestDepth());
            ps._ico = -1;
            ps._want = false;
            perkSlots.push(ps);
            perkLoaders.push(new MovieClipLoader());
            perkLoaders[pi].addListener(this);
            this["pcb" + pi] = mkPerkCB(pi);
            pi++;
        }
        // The clips are fresh even when the render cache is warm.
        lastPerks = "";

        // Re-seed from the cache: on a re-onLoad it is still warm, so
        // assign-on-change would write nothing and leave these blank.
        nameTF.text = lastName;
        pveValTF.text = lastPve;
        pvpValTF.text = lastPvp;

        // Shown only while dragging — a copyable readout for pinning a spot
        // in the app. Right-aligned against the collapse glyph, the family
        // convention (stopwatch, console), so it stays clear of the name.
        coordTF = makeTF(m_Panel, "coords", PAD, PAD, W - PAD * 2 - BTN, Math.round(FS * 1.3),
                         Math.max(9, Math.round(FS * 0.8)), false, 0x999999, "right");
        coordTF._visible = false;

        // Name strip only: a whole-plate drag would eat combat clicks.
        dragMC = m_Panel.createEmptyMovieClip("drag", m_Panel.getNextHighestDepth());
        dragMC._self = this;
        dragMC.useHandCursor = true;
        dragMC.onPress = function() { this._self.beginDrag(this); };
        dragMC.onRelease = dragMC.onReleaseOutside = function() { this._self.endDrag(this); };

        collapseBtn = m_Panel.createEmptyMovieClip("btnCollapse", m_Panel.getNextHighestDepth());
        collapseBtn._x = W - PAD - BTN;
        collapseBtn._y = Math.floor((TITLE_H - BTN) / 2);
        collapseBtn._self = this;
        collapseBtn.useHandCursor = true;
        var btf:TextField = makeTF(collapseBtn, "label", 0, 0, BTN, BTN + 2,
                                   Math.max(9, Math.round(FS * 0.9)), true, 0xC8C0B0, "center");
        collapseBtn.onRelease = function() { this._self.toggleCollapsed(); };
        collapseBtn.onRollOver = function() { this.label.textColor = 0xF7A22B; };
        collapseBtn.onRollOut = function() { this.label.textColor = 0xC8C0B0; };

        // Perk-name chip, drawn last so it sits over the row it names. Opaque
        // where the plate is 90 — it lands on top of icons and a rule.
        tipMC = m_Panel.createEmptyMovieClip("perkTip", m_Panel.getNextHighestDepth());
        tipMC._visible = false;
        tipTF = makeTF(tipMC, "label", TIP_PAD, TIP_PAD, LABEL_W, Math.round(FS * 1.4),
                       FS, false, 0xC8C0B0, "left");
        tipTF.autoSize = "left";
        tipSlot = -1;
        // The hover source is a Mouse listener, NOT rollover handlers on the
        // slots: button handlers put a clip in button mode, and the row would
        // then swallow left clicks the way a whole-plate drag would. Nothing
        // in the panel is interactive except the drag strip and the button.
        // With the row baked off it is never installed at all — otherwise it
        // runs on every mouse move for a row that cannot render.
        if (SHOW_PERKS) {
            var selfM:KazBarsInspect = this;
            mouseLsnr = {onMouseMove: function() { selfM.hoverTick(); }};
            Mouse.addListener(mouseLsnr);
        }

        layout();

        var self:KazBarsInspect = this;
        pollIv = setInterval(function() { self.pollTick(); }, 250);
    }

    private function makeTF(parent:MovieClip, id:String, x:Number, y:Number, w:Number,
                            h:Number, size:Number, bold:Boolean, col:Number,
                            align:String):TextField {
        var tf:TextField = parent.createTextField(id, parent.getNextHighestDepth(), x, y, w, h);
        tf.selectable = false;
        tf.embedFonts = false;
        tf.multiline = true;
        tf.wordWrap = false;
        var fmt:TextFormat = new TextFormat();
        fmt.font = "Arial";
        fmt.size = size;
        fmt.bold = bold;
        fmt.align = align;
        fmt.color = col;
        fmt.leading = LEAD;
        tf.setNewTextFormat(fmt);
        return tf;
    }

    // =========================================================================
    // Layout / collapse
    // =========================================================================

    private function layout():Void {
        if (m_Panel == null) return;
        titleH = TITLE_H;
        var y:Number = TITLE_H + NAME_GAP;

        pveHdrTF._y = y;
        y += pveHdrTF._height + RULE_GAP;
        var rule1:Number = y;
        y += 1 + ROWS_GAP;
        pveLabTF._y = y;
        pveValTF._y = y;
        y += pveLabTF._height;

        var rule2:Number = -1;
        pvpHdrTF._visible = pvpShown;
        pvpLabTF._visible = pvpShown;
        pvpValTF._visible = pvpShown;
        if (pvpShown) {
            y += SECT_GAP;
            pvpHdrTF._y = y;
            y += pvpHdrTF._height + RULE_GAP;
            rule2 = y;
            y += 1 + ROWS_GAP;
            pvpLabTF._y = y;
            pvpValTF._y = y;
            y += pvpLabTF._height;
        }

        var rule3:Number = -1;
        perksHdrTF._visible = perksShown;
        var pi:Number = 0;
        while (pi < perkSlots.length) { perkSlots[pi]._visible = perksShown; pi++; }
        if (perksShown) {
            y += SECT_GAP;
            perksHdrTF._y = y;
            y += perksHdrTF._height + RULE_GAP;
            rule3 = y;
            y += 1 + ROWS_GAP;
            pi = 0;
            while (pi < perkSlots.length) { perkSlots[pi]._y = y; pi++; }
            perkRowY = y;   // hoverTick hit-tests against this, not the clip
            y += ICO;
        }
        fullH = y + PAD;
        m_ruleA = rule1;
        m_ruleB = rule2;
        m_ruleC = rule3;

        applyCollapsed();
    }

    public function toggleCollapsed():Void {
        collapsed = !collapsed;
        applyCollapsed();
        // Collapsed passes read the title ids only, so an expand has nothing
        // to paint from — take the full pass now rather than show a quarter
        // second of the sheet the panel was folded on.
        if (!collapsed && !previewMode && m_Subject != null) pollTick();
    }

    // The two states are different plates, not one plate at two heights: the
    // sheet at W x fullH, and a labelled bar at COLL_W x COLL_H. Everything
    // that sits on the title line — button, drag strip, drag readout — moves
    // to whichever plate is on screen.
    private function applyCollapsed():Void {
        if (m_Panel == null) return;
        hideTip();
        body._visible = !collapsed;
        nameTF._visible = !collapsed;
        collTF._visible = collapsed;
        collapseBtn.label.text = collapsed ? "+" : "-";
        curW = collapsed ? COLL_W : W;
        curH = collapsed ? COLL_H : fullH;
        var pad:Number = collapsed ? COLL_PAD : PAD;
        collapseBtn._x = curW - pad - BTN;
        collapseBtn._y = Math.floor(((collapsed ? COLL_H : TITLE_H) - BTN) / 2);
        coordTF._x = pad;
        coordTF._y = collapsed ? collTF._y
                               : Math.floor((TITLE_H - Math.round(FS * 1.3)) / 2);
        coordTF._width = curW - pad * 2 - BTN;
        // Stops short of the collapse button so it keeps its own press. The
        // strip is the title line only when expanded — a whole-plate drag
        // would eat combat clicks — but collapsed the bar IS the title line.
        dragMC.clear();
        dragMC.beginFill(0, 0);
        rectPath(dragMC, 0, 0, curW - pad - BTN, collapsed ? COLL_H : titleH);
        dragMC.endFill();
        drawChrome(curW, curH, collapsed ? -1 : m_ruleA, collapsed ? -1 : m_ruleB,
                   collapsed ? -1 : m_ruleC);
    }

    private function drawChrome(w:Number, h:Number, rule1:Number, rule2:Number,
                                rule3:Number):Void {
        bg.clear();
        bg.beginFill(0x0C0A07, 90);
        rectPath(bg, 0, 0, w, h);
        bg.endFill();
        bg.lineStyle(1, 0x000000, 100);
        rectPath(bg, 0, 0, w, h);
        bg.lineStyle(1, 0x4A3B22, 100);
        rectPath(bg, 1, 1, w - 2, h - 2);
        // Title separator (expanded only — collapsed the bar IS the title
        // line), then the section-header rules; a negative offset means that
        // section is off screen (collapsed, or a target with no PvP block).
        bg.lineStyle(1, 0x6B5324, 100);
        if (h > COLL_H) {
            bg.moveTo(PAD, TITLE_H);
            bg.lineTo(W - PAD, TITLE_H);
        }
        if (rule1 >= 0) {
            bg.moveTo(PAD, rule1);
            bg.lineTo(W - PAD, rule1);
        }
        if (rule2 >= 0) {
            bg.moveTo(PAD, rule2);
            bg.lineTo(W - PAD, rule2);
        }
        if (rule3 >= 0) {
            bg.moveTo(PAD, rule3);
            bg.lineTo(W - PAD, rule3);
        }
    }

    private function rectPath(mc:MovieClip, x:Number, y:Number, w:Number, h:Number):Void {
        mc.moveTo(x, y);
        mc.lineTo(x + w, y);
        mc.lineTo(x + w, y + h);
        mc.lineTo(x, y + h);
        mc.lineTo(x, y);
    }

    // =========================================================================
    // Subject (Character first, Dynel wrapper fallback)
    // =========================================================================

    // Takes the raw tid, so clears and non-Character dynels both arrive here.
    public function setSubject(tid:Object):Void {
        var isNull:Boolean = (tid == null);
        try {
            if (!isNull && tid.GetType != undefined && tid.GetType() == _global.Enums.TypeID.e_Type_None) isNull = true;
        } catch (e:Object) { isNull = true; }
        if (isNull) {
            m_Subject = null;
            subjIsPlayer = -1;
            resetScan();
            updateVisibility();
            return;
        }
        var subj:Object = resolveTarget(tid);
        if (subj == null) {
            m_Subject = null;
            subjIsPlayer = -1;
            resetScan();
            updateVisibility();
            return;
        }
        var k:String = keyOf(subj);
        if (m_Subject != null && k == subjKey) {
            m_Subject = subj;   // same entity re-targeted: keep the warm cache
            return;
        }
        m_Subject = subj;
        subjKey = k;
        subjName = safeName(subj);
        subjIsPlayer = classify(tid, subj);
        resetScan();
        updateVisibility();
    }

    // ID32 carries the engine's own classifiers. -1 means it never answered.
    private function classify(tid:Object, subj:Object):Number {
        var id:Object = tid;
        if (id == null || id.IsPlayer == undefined) {
            id = null;
            try { id = subj.GetID(); } catch (e:Object) { id = null; }
        }
        if (id != null && id.IsPlayer != undefined) {
            try { return (id.IsPlayer() == true) ? 1 : 0; } catch (e2:Object) {}
        }
        return -1;
    }

    private function resolveTarget(tid:Object):Object {
        if (tid == null) return null;
        var ch:Object = null;
        try {
            ch = com.GameInterface.Game.Character.GetCharacter(tid);
        } catch (e:Object) { ch = null; }
        if (ch == null || ch.GetStat == undefined) {
            try {
                var dy:Object = com.GameInterface.Game.Dynel.GetDynel(tid);
                if (dy != null && dy.GetStat != undefined) return dy;
            } catch (e2:Object) {}
            if (ch != null && ch.GetStat == undefined) return null;
        }
        return ch;
    }

    private function keyOf(obj:Object):String {
        try {
            var id:Object = obj.GetID();
            return String(id.GetType()) + ":" + String(id.GetInstance());
        } catch (e:Object) {}
        return "n:" + safeName(obj);
    }

    private function safeName(obj:Object):String {
        try { return String(obj.GetName()); } catch (e:Object) { return "?"; }
    }

    private function resetScan():Void {
        haveFull = false;
        warmup = 0;
        curV = {};
        m1Str = 0;
        m1Dex = 0;
        subjPlayer = false;
        aaOn = false;
        curPerks = new Array();
        curPerkRanks = new Array();
        lastName = "";
        lastPve = "";
        lastPvp = "";
        // Unloads the icons as well as resetting the key: a new subject with
        // no perks renders the same empty key the cache already holds, so
        // clearing the string alone would strand the old subject's icons.
        clearPerkSlots();
    }

    // =========================================================================
    // Poll — the whole watch list every pass; the poll IS the settle re-read
    // =========================================================================

    public function pollTick():Void {
        if (!active) return;
        if (m_Subject == null) return;

        // Logout/zone collapses every id to 0 in one burst; id 1 and id 54
        // going together is that burst, not a stat change.
        if (haveFull && gv(1) != 0 && gv(54) != 0) {
            var t1 = null;
            var t54 = null;
            try { t1 = m_Subject.GetStat(1, 2); t54 = m_Subject.GetStat(54, 2); } catch (eT:Object) {}
            var z1:Boolean = (t1 == null || t1 == undefined || t1 == 0);
            var z54:Boolean = (t54 == null || t54 == undefined || t54 == 0);
            if (z1 && z54) {
                // Drop the dead handle: keeping it lets the warm-up count
                // three null passes and re-show a phantom all-dash sheet.
                m_Subject = null;
                subjKey = "";
                subjName = "";
                subjIsPlayer = -1;
                resetScan();
                updateVisibility();
                return;
            }
        }

        // Collapsed reads the teardown gate's two ids only; expanding runs a
        // full pass at once (toggleCollapsed), so the sheet is never stale.
        var ids:Array = collapsed ? gateIds : watchIds;
        var i:Number = 0;
        while (i < ids.length) {
            var sid:Number = Number(ids[i]);
            var v = null;
            try { v = m_Subject.GetStat(sid, 2); } catch (e:Object) {}
            curV[sid] = v;
            i++;
        }
        if (!collapsed) {
            subjPlayer = evalPlayer();
            // Mode-1 side-reads: the CDI attr term uses the PRE-multiplier
            // attribute sum — mode 2 is post %-multiplier (a x1.05 Dex feat
            // moved m2 by 97x1.05 while m1 moved by the item's flat 97).
            var r1 = null;
            try { r1 = m_Subject.GetStat(804, 1); } catch (e1a:Object) {}
            m1Str = Number(r1);
            if (isNaN(m1Str)) m1Str = 0;
            r1 = null;
            try { r1 = m_Subject.GetStat(814, 1); } catch (e1b:Object) {}
            m1Dex = Number(r1);
            if (isNaN(m1Dex)) m1Dex = 0;
            // The buff-list pass: the AA's presence corrects the CDI attr
            // term, and any known perk buff feeds the Perks row. Both are
            // player-only — the AA rides an attribute term that is zero
            // without attributes, and the row is player-gated — so nothing
            // else walks the list. Bosses carry the longest buff lists in
            // the game and not one entry of one is ever ours.
            if (subjPlayer) {
                var aa:Boolean = false;
                var pk:Array = new Array();
                try {
                    var bl:Object = m_Subject.m_BuffList;
                    if (bl != null) {
                        for (var bk:String in bl) {
                            var bb:Object = bl[bk];
                            if (bb == null) continue;
                            if (bb.m_BuffId == AA_BUFF_ID) {
                                aa = true;
                                if (!SHOW_PERKS) break;
                            }
                            if (SHOW_PERKS) {
                                var bkey:String = "i" + bb.m_BuffId;
                                var rank = PERK_IDS[bkey];
                                if (rank != undefined) {
                                    // A buff's icon never changes, so the
                                    // engine answers this once per id per
                                    // session rather than 4x a second.
                                    var pin:Number = Number(iconInst[bkey]);
                                    if (isNaN(pin)) {
                                        pin = 0;
                                        try { pin = Number(bb.m_Icon.GetInstance()); } catch (eIc:Object) {}
                                        if (isNaN(pin)) pin = 0;
                                        if (pin > 0) iconInst[bkey] = pin;
                                    }
                                    pk.push({r: Number(rank), inst: pin});
                                }
                            }
                        }
                    }
                } catch (eBL:Object) {}
                aaOn = aa;
                if (SHOW_PERKS) {
                    var placed:Object = placePerks(pk);
                    curPerks = placed.inst;
                    curPerkRanks = placed.rank;
                }
            }
        }
        if (!haveFull) {
            // ~750 ms: login/zone/retarget repopulation settles inside it.
            warmup++;
            if (warmup < 3) return;
            haveFull = true;
        }
        if (previewMode) return;
        render();
    }

    // =========================================================================
    // Stat access + sheet syntheses (field-measured, sheet-exact at level 80)
    // =========================================================================

    // Keyed by the raw id: a full render asks this ~195 times, and building
    // a key string per ask was the panel's largest source of AVM1 garbage.
    private function gv(sid:Number):Number {
        var v = curV[sid];
        if (v == null || v == undefined) return 0;
        var n:Number = Number(v);
        if (isNaN(n)) return 0;
        return n;
    }

    private function has(sid:Number):Boolean {
        return gv(sid) != 0;
    }

    // attribute sheet value from the x10+10 encoding; 0 = absent (mobs)
    private function attrSheet(sid:Number):Number {
        var r:Number = gv(sid);
        if (r == 0) return 0;
        return Math.round((r - 10) / 10);
    }

    // mode-1 attribute: the pre-%-multiplier additive sum, same encoding
    private function attrM1(raw:Number):Number {
        if (raw == 0) return 0;
        return Math.round((raw - 10) / 10);
    }

    // Gates the PvP block, the Perks row, the title's class name and every
    // player-only line; both signals must agree. IsPlayer() is measured
    // truthful on players but never sampled on a mob, so it vetoes rather
    // than confirms alone. Attributes must be DECODED — raw, an NPC template
    // carrying them at base reads 10, which put a PvP block on city guards.
    // Settled once a pass into subjPlayer: six call sites ask, and each ask
    // is four stat decodes.
    private function evalPlayer():Boolean {
        var hasAttrs:Boolean = attrSheet(804) > 4 || attrSheet(808) > 4
                            || attrSheet(810) > 4 || attrSheet(814) > 4;
        if (subjIsPlayer >= 0) return (subjIsPlayer == 1) && hasAttrs;
        return hasAttrs;
    }

    private function lvlOK():Boolean {
        return gv(54) == 80;
    }

    // linear rating law: effect% = classBase + rating/36.6
    private function pctOf(r:Number):Number {
        return Math.round(r / 36.6 * 10) / 10;
    }

    // linear v/a to 50%, then 100 - 5000/(50 + v/a); a = 219.6 armor,
    // 73.7 protection. Negative stat space floors at 0%.
    private function mitCurve(v:Number, a:Number):Number {
        if (v <= 0) return 0;
        var q:Number = v / a;
        return (q <= 50) ? q : (100 - 5000 / (50 + q));
    }

    // displayed % = base mit + invul x (1 - mit), where the per-type invul
    // column = per-type id + 911 (the all-type component)
    private function sheetMit(baseMit:Number, invulId:Number):Number {
        var inv:Number = gv(invulId) + gv(911);
        return Math.round((baseMit + inv * (1 - baseMit / 100)) * 10) / 10;
    }

    // floor(comp x (1 + BonusArmor% 450)) + 2 x Str
    private function armorTotal():Number {
        return Math.floor(gv(448) * (1 + gv(450) / 100)) + 2 * attrSheet(804);
    }

    // school comp + floor(flat 451 x (1 + BonusProt% 334)) + attr/2
    // (Int for Cold/Elec/Fire, Wis for Holy/Unholy)
    private function protTotal(schoolId:Number, attrId:Number):Number {
        return gv(schoolId) + Math.floor(gv(451) * (1 + gv(334) / 100)) + Math.floor(attrSheet(attrId) / 2);
    }

    // The equipped weapon type is unreadable; characters stack their own
    // school's CR, so the largest component is it.
    private function gearSchoolCR():Number {
        var ids:Array = [866, 867, 868, 869, 870, 871, 872, 873];
        var best:Number = 0;
        var i:Number = 0;
        while (i < ids.length) {
            var v:Number = gv(Number(ids[i]));
            if (v > best) best = v;
            i++;
        }
        return best;
    }

    // 3 x Str (Dex for the dagger class 34 and Rangers 39 — both named by
    // the sheet's own tooltip) + untyped 875 + equipped-school CR + every
    // typed magic CR; the PvP tab adds 225 on top. The attr term uses the
    // MODE-1 attribute (the pre-%-multiplier sum — the sheet's own basis,
    // two chars digit-exact) minus the +100-all-attrs AA (Immeasurable
    // Empowerment) when the subject's buff list shows it — the AA is
    // bugged in-game and never feeds this rating. Flat attr buffs other
    // than the AA still inflate the term.
    private function cdiPvE():Number {
        var c:Number = gv(67);
        var att:Number = (c == 34 || c == 39) ? attrM1(m1Dex) : attrM1(m1Str);
        if (aaOn) att -= 100;
        if (att < 0) att = 0;
        return 3 * att + gv(875) + gearSchoolCR() + gv(162) + gv(1007) + gv(1008) + gv(1009) + gv(1010);
    }

    // =========================================================================
    // Line builders — "Rating (Effect%)", dash when absent, effect off-80
    // =========================================================================

    private function fmt1(n:Number):String {
        var r:Number = Math.round(n * 10) / 10;
        var s:String = String(r);
        if (s.indexOf(".") == -1) s += ".0";
        return s;
    }

    private function healthLine():String {
        if (!has(1) && !has(27)) return DASH;
        var s:String = gv(27) + " / " + gv(1);
        if (has(525)) s += " (" + gv(525) + "%)";
        return s;
    }

    private function mitLine(v:Number, invulId:Number, a:Number):String {
        if (v == 0) return DASH;
        if (!lvlOK()) return String(v);
        return v + " (" + fmt1(sheetMit(mitCurve(v, a), invulId)) + "%)";
    }

    // zero-base linear decode (critigation, tenacity)
    private function pctLine(r:Number):String {
        if (r == 0) return DASH;
        if (!lvlOK()) return String(r);
        return r + " (" + fmt1(pctOf(r)) + "%)";
    }

    // Rating share only: the sheet's per-character feat/AA base is absent from
    // stat space and not class-keyed, so inventing one would inflate this.
    private function critDmgLine():String {
        return pctLine(gv(711));
    }

    private function critChanceLine():String {
        var r:Number = gv(312);
        if (r == 0) return DASH;
        if (!lvlOK()) return String(r);
        var wpnBase:Number = (gv(67) == 34) ? 5 : 2.5;
        return r + " (" + fmt1(r / 36.6 + wpnBase) + "%)";
    }

    // Rating + the Celestial Gaze range it buys (the main beneficiary):
    // 271 + HR x 0.2761 to 292 + HR x 0.2761. Player-only.
    private function healLine():String {
        if (!subjPlayer) return DASH;
        var r:Number = gv(713);
        if (r == 0) return DASH;
        if (!lvlOK()) return String(r);
        return r + " (" + Math.round(271 + r * 0.2761) + "-" + Math.round(292 + r * 0.2761) + ")";
    }

    // 861 + schoolComponent + round(0.6 x mainAttr) + BaseSpellDamage% 1041.
    // Main attribute is max(Int, Wis) — priests lead on Wis, mages on Int —
    // avoiding an unmeasured class table, like the school CR above. Only the
    // highest school shows: a caster stacks exactly one. The PvP row adds the
    // per-school gap 226 on top — one value for all schools, the 458 shape.
    private function spellLine(add:Number):String {
        if (!subjPlayer || !lvlOK()) return DASH;
        // Mana-less classes (Ranger measured; Barbarian predicted) sheet the
        // whole per-school block at 0 even when 861/1041 carry residue —
        // max mana 507 is the gate.
        if (gv(507) == 0) return DASH;
        var best:Number = 0;
        var i:Number = 0;
        while (i < SPELL_IDS.length) {
            var v:Number = gv(Number(SPELL_IDS[i]));
            if (v > best) best = v;
            i++;
        }
        var attr:Number = Math.max(attrSheet(808), attrSheet(810));
        var total:Number = gv(861) + best + Math.round(attr * 0.6) + gv(1041) + add;
        if (total == 0) return DASH;
        return String(total);
    }

    // Sheet Ferocity = floor(1403/10), the x10-encoded gear component and
    // nothing else — a char with 1403=0 sheets Ferocity 0 even while the
    // old base candidate 864 reads 33 (864 is the engine's "Player Flags"
    // state id, not a rating). Effect is 0.15 x total on all five AOE
    // surfaces (sheet pair 260 -> 39.0%). Player-only.
    private function ferLine():String {
        if (!subjPlayer) return DASH;
        var t:Number = Math.floor(gv(1403) / 10);
        if (t == 0) return DASH;
        if (!lvlOK()) return String(t);
        return t + " (" + fmt1(t * 0.15) + "%)";
    }

    // Weapon Damage % pair (1095 melee / 1096 ranged, x100) — the sheet's
    // Melee/Ranged values verbatim. No synthesis, no gates: stance and
    // proc swings and Reave-type feat multipliers are already inside the
    // ids. Dashed only when both are absent.
    private function wdLine():String {
        var m:Number = gv(1095);
        var r:Number = gv(1096);
        if (m == 0 && r == 0) return DASH;
        return fmt1(m / 100) + "% / " + fmt1(r / 100) + "%";
    }

    // rating + flat effect (the sheet's Effect column = the DPS add)
    private function cdiLine(add:Number):String {
        var r:Number = cdiPvE();
        if (r == 0) return DASH;
        r += add;
        if (!lvlOK()) return String(r);
        return r + " (" + Math.round(r / 36.6) + ")";
    }

    // "Name Class (Level/PvPLevel)". Class only when the player gate agrees
    // AND id 67 maps (all twelve measured); the level part drops what is
    // absent, so a mob reads "Name (83)" and a PvP-level-0 player "Name (80)".
    private function titleLine():String {
        var s:String = subjName;
        if (subjPlayer) {
            var cn:String = CLASS_NAMES["c" + gv(67)];
            if (cn != undefined) s += " " + cn;
        }
        var lvl:Number = gv(54);
        if (lvl > 0) {
            var pl:Number = gv(70);
            s += " (" + lvl + ((pl > 0) ? ("/" + pl) : "") + ")";
        }
        return s;
    }

    private function pveValues():String {
        var armorVal:Number = (attrSheet(804) > 0) ? armorTotal() : gv(448);
        var g:Array = new Array();
        g.push(healthLine());
        g.push(mitLine(armorVal, 902, 219.6));
        g.push(mitLine(protTotal(928, 810), 907, 73.7));
        g.push(mitLine(protTotal(929, 810), 908, 73.7));
        g.push(mitLine(protTotal(157, 808), 167, 73.7));
        g.push(mitLine(protTotal(927, 808), 906, 73.7));
        g.push(mitLine(protTotal(926, 808), 905, 73.7));
        g.push(pctLine(gv(1000016)));
        g.push(pctLine(gv(1000018)));
        g.push(healLine());
        g.push(spellLine(0));
        g.push(cdiLine(0));
        g.push(wdLine());
        g.push(critChanceLine());
        g.push(critDmgLine());
        g.push(pctLine(gv(1000017)));
        g.push(ferLine());
        return g.join("\n");
    }

    private function pvpValues():String {
        var armorVal:Number = (attrSheet(804) > 0) ? armorTotal() : gv(448);
        var g:Array = new Array();
        g.push(mitLine(armorVal + gv(454), 902, 219.6));
        g.push(mitLine(protTotal(928, 810) + gv(458), 907, 73.7));
        g.push(mitLine(protTotal(929, 810) + gv(458), 908, 73.7));
        g.push(mitLine(protTotal(157, 808) + gv(458), 167, 73.7));
        g.push(mitLine(protTotal(927, 808) + gv(458), 906, 73.7));
        g.push(mitLine(protTotal(926, 808) + gv(458), 905, 73.7));
        g.push(spellLine(gv(226)));
        g.push(cdiLine(gv(225)));
        g.push(gv(656) + " / " + gv(658));   // 0 / 0 is real data, not absence
        return g.join("\n");
    }

    // =========================================================================
    // Render / preview
    // =========================================================================

    private function render():Void {
        if (m_Panel == null || m_Subject == null || !haveFull) {
            updateVisibility();
            return;
        }
        // Collapsed, the bar is a static label — nothing on it moves with the
        // target, so there is nothing to paint and nothing was read.
        if (collapsed) {
            updateVisibility();
            return;
        }
        var wantPvp:Boolean = subjPlayer && SHOW_PVP;
        var wantPerks:Boolean = subjPlayer && SHOW_PERKS;
        if (wantPvp != pvpShown || wantPerks != perksShown) {
            pvpShown = wantPvp;
            perksShown = wantPerks;
            layout();
        }
        var t:String = titleLine();
        if (t != lastName) {
            lastName = t;
            nameTF.text = t;
        }
        var s:String = pveValues();
        if (s != lastPve) {
            lastPve = s;
            pveValTF.text = s;
        }
        if (pvpShown) {
            var p:String = pvpValues();
            if (p != lastPvp) {
                lastPvp = p;
                pvpValTF.text = p;
            }
        }
        if (perksShown) renderPerks();
        updateVisibility();
    }

    // =========================================================================
    // Perks row — detected perk buffs as RDB icons in the game's own layout:
    // three colour-coded slot pairs, General / Archetype / Class
    // =========================================================================

    // Returns {inst, rank}, six entries each, -1 for an empty slot. Rank
    // order in (insertion sort over <= 6 live entries, rank-variant
    // duplicates collapsing to the first seen), then each perk drops into
    // its category's own pair the way the game's perk bar lays them out.
    // 0 is a real value here -- a perk whose buff carries no icon still
    // holds its slot -- so only -1 means empty. The rank rides along for the
    // hover chip: the icon instance does not identify the perk.
    private function placePerks(pk:Array):Object {
        var srt:Array = new Array();
        var i:Number = 0;
        while (i < pk.length) {
            var e:Object = pk[i];
            var j:Number = 0;
            var dup:Boolean = false;
            while (j < srt.length) {
                if (srt[j].r == e.r) { dup = true; break; }
                if (srt[j].r > e.r) break;
                j++;
            }
            if (!dup) srt.splice(j, 0, e);
            i++;
        }
        var out:Array = [-1, -1, -1, -1, -1, -1];
        var rnk:Array = [-1, -1, -1, -1, -1, -1];
        i = 0;
        while (i < srt.length) {
            var r:Number = srt[i].r;
            var b:Number = (r <= PERK_GEN_MAX) ? 0 : ((r <= PERK_ARCH_MAX) ? 2 : 4);
            // A pair holds two; anything beyond that is dropped rather than
            // spilling into the next category's colour. A two-slot perk
            // claims both boxes with the same icon, the way the game draws
            // it -- so it needs both free, or it is just the pair's second.
            if (out[b] == -1) {
                out[b] = srt[i].inst;
                rnk[b] = r;
                if (PERK_2SLOT["r" + r] != undefined && out[b + 1] == -1) {
                    out[b + 1] = srt[i].inst;
                    rnk[b + 1] = r;
                }
            } else if (out[b + 1] == -1) {
                out[b + 1] = srt[i].inst;
                rnk[b + 1] = r;
            }
            i++;
        }
        return {inst: out, rank: rnk};
    }

    // Assign-on-change like the value columns: the joined slot list is the
    // cache, and only slots whose icon actually changed reload. Ranks are in
    // the key too — two perks can share one icon, and the chip must not name
    // the one that left.
    private function renderPerks():Void {
        var key:String = curPerks.join(",") + "|" + curPerkRanks.join(",");
        if (key == lastPerks) return;
        lastPerks = key;
        hideTip();
        // Pass 1: settle every slot's target instance and drop stale art, so
        // pass 2 can see the whole row when it decides what to request.
        var i:Number = 0;
        while (i < perkSlots.length) {
            var s:MovieClip = perkSlots[i];
            var inst:Number = Number(curPerks[i]);
            if (isNaN(inst)) inst = -1;
            var rk:Number = Number(curPerkRanks[i]);
            s._rank = isNaN(rk) ? -1 : rk;
            if (s._ico != inst) {
                s._ico = inst;
                try { s.hold.m_icon.unloadMovie(); } catch (eU:Object) {}
                s._want = (inst > 0);
            }
            i++;
        }
        // Pass 2: one request per DISTINCT instance, one clip per answer.
        // RequestRDBImage answers a given id once -- a second request for an
        // id already in flight never calls back -- and a same-tick second
        // loadClip of one URL double-binds a shared movie def that the
        // retarget unload then releases twice: a client heap crash, isolated
        // in-game. So a dup slot KEEPS _want as its pending mark, and
        // onPerkIcon re-requests the id for it after the first answer lands
        // (the id is out of flight by then) -- sharers resolve as a chain of
        // single-clip loads. Dedup is only against instances requested on
        // THIS pass: a slot that kept its art issued no request, so it
        // cannot serve a partner that has just come to want the same
        // instance.
        var reqd:Array = new Array();
        i = 0;
        while (i < perkSlots.length) {
            var sl:MovieClip = perkSlots[i];
            if (sl._want) {
                var dup:Boolean = false;
                var j:Number = 0;
                while (j < reqd.length) {
                    if (reqd[j] == sl._ico) { dup = true; break; }
                    j++;
                }
                if (!dup) {
                    sl._want = false;
                    reqd.push(sl._ico);
                    try {
                        com.Utils.ImageLoader.RequestRDBImage(
                            new com.Utils.ID32(1010008, sl._ico), this, "pcb" + i);
                    } catch (eR:Object) {}
                }
            }
            i++;
        }
    }

    private function mkPerkCB(i:Number):Function {
        var self:KazBarsInspect = this;
        return function(url:String, ok:Boolean):Void { self.onPerkIcon(i, url, ok); };
    }

    private function onPerkIcon(i:Number, url:String, ok:Boolean):Void {
        var s:MovieClip = (perkSlots != null) ? MovieClip(perkSlots[i]) : null;
        if (s == null || s.hold == null) return;
        // The slot was cleared (or re-targeted) between request and answer;
        // only a positive instance was ever requested.
        if (!ok || url == null || url.length == 0 || s._ico <= 0) return;
        // One clip per answer -- NEVER loadClip one URL into two targets in
        // the same tick: the two binds share one movie def, the retarget
        // unload releases it twice, and the heap corruption crashes the
        // client an inspection later (isolated in-game via the serve-one
        // probe). The partner of a two-slot perk still holds _want, so chain
        // it: re-issue the request now that this answer took the id out of
        // flight, and its own callback paints it next.
        try { perkLoaders[i].loadClip(url, s.hold.m_icon); } catch (e:Object) {}
        var inst:Number = s._ico;
        var j:Number = 0;
        while (j < perkSlots.length) {
            var t:MovieClip = perkSlots[j];
            if (t != null && t._want && t._ico == inst) {
                t._want = false;
                try {
                    com.Utils.ImageLoader.RequestRDBImage(
                        new com.Utils.ID32(1010008, inst), this, "pcb" + j);
                } catch (eR:Object) {}
                break;
            }
            j++;
        }
    }

    // MovieClipLoader listener: standardize the loaded RDB icon to the 64x64
    // native size — the slot's m_icon container is pre-scaled to ICO/64, so
    // the icon lands exactly in the box.
    public function onLoadInit(mc:MovieClip):Void {
        if (mc == null) return;
        try {
            mc._xscale = mc._yscale = 100;
            var scale:Number = 6400 / Math.max(mc._width, mc._height);
            mc._xscale = mc._yscale = scale;
            mc.cacheAsBitmap = true;
        } catch (e:Object) {}
    }

    private function clearPerkSlots():Void {
        if (perkSlots == null) return;
        var i:Number = 0;
        while (i < perkSlots.length) {
            var s:MovieClip = perkSlots[i];
            s._ico = -1;
            s._rank = -1;
            s._want = false;
            try { s.hold.m_icon.unloadMovie(); } catch (e:Object) {}
            i++;
        }
        hideTip();
        lastPerks = "";
    }

    // Hover -> perk name. Driven by mouse movement rather than rollover
    // handlers so the row stays click-through (createPanel), and hit-tested
    // arithmetically in panel space: the boxes are a known pitch from PAD, so
    // no hitTest call and no dependence on where rootClip sits.
    public function hoverTick():Void {
        // Every mouse move, for the life of the module — and in combat the
        // camera drags the mouse continuously. So: cached AS state first
        // (the row is off screen for most of a session), and the native
        // _ymouse / _xmouse reads only for a pointer already in the panel.
        if (!perksShown || collapsed || previewMode || !panelVis) {
            hideTip();
            return;
        }
        if (m_Panel == null || tipMC == null || perkSlots == null) return;
        var top:Number = perkRowY;
        var my:Number = m_Panel._ymouse;
        if (my < top || my > top + ICO) {
            hideTip();
            return;
        }
        var pitch:Number = ICO + ICO_GAP;
        var mx:Number = m_Panel._xmouse - PAD;
        var i:Number = Math.floor(mx / pitch);
        // The gaps between the boxes are not the boxes.
        if (i < 0 || i > 5 || mx - i * pitch > ICO) {
            hideTip();
            return;
        }
        showTip(i);
    }

    private function showTip(i:Number):Void {
        var r:Number = Number(perkSlots[i]._rank);
        if (isNaN(r) || r < 0 || PERK_NAMES[r] == undefined) {
            hideTip();
            return;
        }
        // Redraw only on a slot change; the pointer moves inside a box for
        // many frames, and renderPerks clears the cache when the row changes.
        if (tipSlot != i) {
            tipSlot = i;
            tipTF.text = String(PERK_NAMES[r]);
            var tw:Number = Math.round(tipTF._width) + TIP_PAD * 2;
            var th:Number = Math.round(tipTF._height) + TIP_PAD * 2;
            tipMC.clear();
            tipMC.beginFill(0x0C0A07, 100);
            rectPath(tipMC, 0, 0, tw, th);
            tipMC.endFill();
            tipMC.lineStyle(1, 0x4A3B22, 100);
            rectPath(tipMC, 0, 0, tw, th);
            // Centred over its icon, then clamped inside the plate — the
            // longest name is wider than a box and the end slots would hang
            // off the frame.
            var cx:Number = PAD + i * (ICO + ICO_GAP) + Math.round((ICO - tw) / 2);
            tipMC._x = Math.max(PAD, Math.min(cx, W - PAD - tw));
            tipMC._y = perkSlots[0]._y - th - TIP_PAD;
        }
        tipMC._visible = true;
    }

    // tipSlot >= 0 exactly when the chip is up, so an already-hidden chip
    // costs one compare rather than two property writes per mouse move.
    private function hideTip():Void {
        if (tipSlot < 0 || tipMC == null) return;
        tipSlot = -1;
        tipMC._visible = false;
    }

    // Master switch (preview control panel + archive): folds into the one
    // visibility gate, so live sheets and the canned preview sheet both obey it.
    public function isActive():Boolean {
        return active;
    }

    public function setActive(shown:Boolean):Void {
        active = shown;
        updateVisibility();
    }

    private function updateVisibility():Void {
        if (m_Panel == null) return;
        var vis:Boolean = active && (previewMode || (m_Subject != null && haveFull));
        if (vis != panelVis) {
            panelVis = vis;
            m_Panel._visible = vis;
        }
        if (!vis) hideTip();
    }

    // Canned full-footprint sheet, so the panel can be positioned untargeted.
    // Sections follow the baked gates; the perk boxes stay empty — there are
    // no canned RDB icons to fill them with.
    public function previewOn():Void {
        if (m_Panel == null) return;
        previewMode = true;
        if (pvpShown != SHOW_PVP || perksShown != SHOW_PERKS) {
            pvpShown = SHOW_PVP;
            perksShown = SHOW_PERKS;
            layout();
        }
        clearPerkSlots();
        nameTF.text = "Preview Bear Shaman (80/10)";
        pveValTF.text = "11527 / 23093 (49%)\n12492 (55.7%)\n3233 (23.4%)\n3228 (23.2%)"
                      + "\n3090 (22.6%)\n3090 (22.6%)\n3090 (22.6%)\n2196 (60.0%)\n2202 (60.2%)"
                      + "\n2196 (877-898)\n1726\n3312 (90)\n20.5% / 2.0%\n467 (15.3%)\n431 (11.8%)"
                      + "\n2112 (57.7%)\n260 (39.0%)";
        pvpValTF.text = "8230 (38.1%)\n3090 (42.5%)\n3090 (42.5%)\n3090 (42.5%)\n3090 (42.5%)"
                      + "\n3090 (42.5%)\n1844\n5269 (144)\n18304 / 16264";
        updateVisibility();
    }

    public function previewOff():Void {
        if (m_Panel == null) return;
        previewMode = false;
        // Force a live reassign: the canned sheet bypassed the cache.
        lastName = "";
        lastPve = "";
        lastPvp = "";
        lastPerks = "";
        if (m_Subject != null && haveFull) {
            render();
        } else {
            if (pvpShown || perksShown) {
                pvpShown = false;
                perksShown = false;
                layout();
            }
            updateVisibility();
        }
    }

    // =========================================================================
    // Drag + persistence (module config archive — permanent for every user)
    // =========================================================================

    public function beginDrag(da:MovieClip):Void {
        // Bounds derive from fontSize, so a big enough panel inverts the rect
        // and gets yanked off-screen; floored, it pins to the top-left.
        m_Panel.startDrag(false, 0, 0, Math.max(0, Stage.width - curW),
                          Math.max(0, Stage.height - curH));
        dragX = m_Panel._x;
        dragY = m_Panel._y;
        coordTF._visible = true;
        updateCoords();
        var self:KazBarsInspect = this;
        da.onMouseMove = function() { self.updateCoords(); };
    }

    public function endDrag(da:MovieClip):Void {
        m_Panel.stopDrag();
        delete da.onMouseMove;
        coordTF._visible = false;
        // Collapsed, the bar is small and labelled and reads as a button, so
        // a press that never moved it opens the sheet; a real drag still
        // just moves it. Expanded, the name strip only drags — a stray click
        // beside the target's name must not fold the sheet away.
        if (collapsed && Math.abs(m_Panel._x - dragX) < 2
                      && Math.abs(m_Panel._y - dragY) < 2) {
            toggleCollapsed();
        }
    }

    public function updateCoords():Void {
        coordTF.text = Math.round(m_Panel._x) + ", " + Math.round(m_Panel._y);
    }

    public function loadState(config:Object):Void {
        if (config == null || m_Panel == null) return;
        var v:Object = config.FindEntry("inv");
        if (v !== undefined) setActive(v == 1);
        // Fold state first: the clamp has to measure the plate actually on
        // screen. Clamping a sheet against the collapsed bar's height let a
        // saved spot near the bottom edge hang off it.
        var c:Object = config.FindEntry("inc");
        if (c !== undefined) {
            collapsed = (c == 1);
            applyCollapsed();
        }
        var x:Object = config.FindEntry("inx");
        var y:Object = config.FindEntry("iny");
        if (x !== undefined && y !== undefined) {
            m_Panel._x = clampPos(Number(x), Stage.width - curW);
            m_Panel._y = clampPos(Number(y), Stage.height - curH);
        }
    }

    public function saveState(config:Object):Void {
        if (config == null || m_Panel == null) return;
        config.ReplaceEntry("inx", m_Panel._x);
        config.ReplaceEntry("iny", m_Panel._y);
        config.ReplaceEntry("inc", collapsed ? 1 : 0);
        config.ReplaceEntry("inv", active ? 1 : 0);
    }

    private function clampPos(v:Number, max:Number):Number {
        if (isNaN(v) || v < 0) return 0;
        if (v > max) return max;
        return v;
    }

    public function cleanup():Void {
        if (pollIv != null) {
            clearInterval(pollIv);
            pollIv = null;
        }
        if (mouseLsnr != null) {
            Mouse.removeListener(mouseLsnr);
            mouseLsnr = null;
        }
        if (perkLoaders != null) {
            var i:Number = 0;
            while (i < perkLoaders.length) {
                if (perkLoaders[i] != null) {
                    perkLoaders[i].removeListener(this);
                    perkLoaders[i] = null;
                }
                i++;
            }
            perkLoaders = null;
            perkSlots = null;
        }
        m_Subject = null;
        previewMode = false;
        if (m_Panel != null) {
            m_Panel.removeMovieClip();
            m_Panel = null;
        }
    }
}
