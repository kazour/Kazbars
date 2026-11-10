"""Pins between the AS2 stubs and the Python that bakes their data.

A slot's text is sized twice: the floor, the caps and the box formula in
`overlay_size` (what the generator bakes and the grid card's hint states), and
the placement in `KazBarsGridView.createTexts` (what the game draws). The
compiler does no cross-check, so nothing else would notice one side moving
without the other. The constants both share are asserted against the stub.

AVM1 keeps fields and methods in one namespace: a field set on an instance hides
a method of the same name on any class up its chain, and every call to it then
fails at run time ("CallMethod - 'x' is not a method"). The panel chains are
checked for that, and for a subclass redeclaring a field its base already has.

Run: `pytest tests/test_as2_stub_pins.py` (from repo root).
"""

import re

import pytest

from kazbars.overlay_size import GUTTER, TIMER_DIGITS_EM_E4
from kazbars.paths import KAZBARS_ASSETS

STUBS = KAZBARS_ASSETS / "stubs"


def _stub(name):
    return (STUBS / f"{name}.as").read_text(encoding="utf-8").replace("\r\n", "\n")


def _slot_text():
    """The view's text section: `mkTF` and `createTexts`, up to the icon section."""
    src = _stub("KazBarsGridView")
    start = src.index("private function mkTF(")
    return src[start:src.index("// Icons:", start)]


def test_the_stub_states_the_geometry_the_size_model_measures():
    assert "NATIVE_SIZE:Number = 64;" in _stub("KazBarsGridView")
    src = _slot_text()
    for size in ("sp", "tp", "n"):
        assert f"Math.ceil({size} * 6 / 5) + {GUTTER}" in src, size
    # overlay_size.inset, the stack counter's inset from the top and right edges.
    assert "var ins:Number = Math.max(2, Math.round(sz / 12));" in src
    assert "var sX:Number = sz - sW - ins;" in src
    assert 'mkTF(s, "stk", 13, sX, ins, ' in src
    assert "if (tH <= sz - ins - sH) tY = Math.max(Math.min(tY, sz - tH), ins + sH);" in src
    digits = TIMER_DIGITS_EM_E4 / 10_000
    assert f"Math.ceil(tp * {digits}) + {GUTTER}" in src
    assert f"var sW:Number = Math.ceil(sp * {digits}) + {GUTTER};" in src  # "x" and three digits


def test_the_stack_counter_reads_x_and_the_count():
    src = _stub("KazBarsGridView")
    body = src[src.index("private function draw("):src.index("private function hide(")]
    assert 'var t:String = (k > 0) ? "x" + String(k) : "";' in body


def test_the_stub_reads_the_baked_keys_and_converts_once_to_native_units():
    src = _slot_text()
    for key in ("cfg.iconSize", "cfg.stackFont", "cfg.timerFont", "cfg.timerYOffset",
                "cfg.timerStyle"):
        assert key in src, key
    assert "K = NATIVE_SIZE / c.iconSize;" in _stub("KazBarsGridView")
    assert "Math.round(size * K)" in src
    assert "x * K, y * K, w * K" in src


def test_the_floor_and_the_caps_live_in_the_size_model_alone():
    src = _slot_text()
    for gone in ("least", "Math.floor(", "Math.min(cfg.", "Math.max(cfg."):
        assert gone not in src, gone


def test_one_function_makes_every_slot_from_the_grids_own_cfg():
    src = _stub("KazBarsGridView")
    start = src.index("private function slot(")
    body = src[start:src.index("\n    }\n", start)]
    assert "createTexts(s);" in body
    assert "(cfg.iconSize / NATIVE_SIZE) * 100" in body
    assert src.count("createTexts(") == 2


def test_the_onslaught_heads_its_guards_guard_and_sizes_its_alerts_from_the_bake():
    src = _stub("KazBarsOnslaught")
    assert '"GUARD");' in src and '"GUARDS"' not in src, "one header word per tier, like SKULL"
    assert "ALF = Number(cfg.alertFontSize);" in src
    assert 'makeTF(m, "t", FX[1], 0, AW, ALH, ALF,' in src, "the banners take the baked size"


def _parent(src):
    m = re.search(r"^class \w+ extends (\w+)", src, re.M)
    return m.group(1) if m else None


def _members(src, marker):
    """Class members (4-space indent, not a function's locals) declared with `marker`."""
    out = set()
    for line in src.splitlines():
        if not line.startswith("    ") or line.startswith("     "):
            continue
        t = line[4:]
        for prefix in ("public ", "private "):
            t = t.removeprefix(prefix)
        t = t.removeprefix("static ")
        if t.startswith(marker):
            name = re.match(r"\w+", t[len(marker):])
            if name:
                out.add(name.group(0))
    return out


def _chain(cls):
    chain = [cls]
    while (parent := _parent(_stub(chain[-1]))) is not None:
        chain.append(parent)
    return chain


PANELS = ("KazBarsOnslaught", "KazBarsInspect", "KazBarsConsole", "KazBarsPreviewPanel",
          "KazBarsStopwatch")


@pytest.mark.parametrize("cls", PANELS)
def test_no_field_shares_a_name_with_a_method_up_or_down_its_chain(cls):
    chain = _chain(cls)
    assert len(chain) > 1, f"{cls} no longer extends anything"
    fields = set().union(*(_members(_stub(c), "var ") for c in chain))
    methods = set().union(*(_members(_stub(c), "function ") for c in chain))
    assert not fields & methods, f"{' < '.join(chain)} declare {sorted(fields & methods)}"


@pytest.mark.parametrize("cls", PANELS)
def test_no_subclass_redeclares_a_field_of_its_base(cls):
    chain = _chain(cls)
    own = _members(_stub(chain[0]), "var ")
    inherited = set().union(*(_members(_stub(c), "var ") for c in chain[1:]))
    assert not own & inherited, f"{cls} redeclares {sorted(own & inherited)}"


def test_the_preview_panel_has_a_row_group_per_kind_of_grid():
    """Overhead grids get their own rows, between the target grids and the tools."""
    src = _stub("KazBarsPreviewPanel")
    begin = src[src.index("public function begin()"):src.index("public function addGrid(")]
    labels = re.findall(r'label: "([^"]+)"', begin)
    assert labels == ["Player Grids", "Target Grids", "Overhead Grids", "Tools"]
    assert "groups[3].rows.push" in src
    tpl = (KAZBARS_ASSETS / "KazBars.as.template").read_text(encoding="utf-8")
    assert re.search(r"//#if PLATE\n\s+for \(i = 0; i < overhead\.smp\.length; i\+\+\) "
                     r"ppanel\.addGrid\(overhead\.smp\[i\]\);\n//#end", tpl.replace("\r\n", "\n"))


def test_overhead_and_screen_grids_share_one_archive_key():
    """Both grid stubs persist a grid's switch as gk_<key>_v (keys are unique
    across all grids), and the overhead stub only ever touches its own
    friendly/hostile cfgs — a rename on one side, or a dropped filter, would
    silently stop the round-trip or stomp a floating grid's key."""
    key = r'"gk_" \+ [\w.\[\]]+\.key \+ "_v"'
    assert re.search(key, _stub("KazBarsGrids"))
    oh = _stub("KazBarsOverhead")
    assert len(re.findall(key, oh)) == 2          # loadState + saveState
    seed = oh[oh.index("public function configure("):oh.index("public function onClass(")]
    assert 'if (g.type != "friendly" && g.type != "hostile") continue;' in seed
    assert "all.push(g);" in seed
    for fn in ("loadState", "saveState"):
        body = oh[oh.index(f"public function {fn}("):]
        body = body[:body.index("\n    }\n")]
        assert "all.length" in body and "d.CFG.grids" not in body, fn


def _fn_body(src, fn):
    start = src.index(f" function {fn}(")
    return src[start:src.index("\n    }\n", start)]


@pytest.mark.parametrize("cls, loads, seats", [
    ("KazBarsGrids", ("loadState",), "previewOn"),
    ("KazBarsCastTimer", ("loadState", "applyPos"), "dressForDrag"),
    ("KazBarsOnslaught", ("loadState",), "previewOn"),
])
def test_loading_never_clamps_a_hud_position(cls, loads, seats):
    """The stage can read short when the archive loads; a clamp there would pull
    a spot inward and the next save would keep it. Entering preview seats it."""
    src = _stub(cls)
    for fn in loads:
        assert "clampPos" not in _fn_body(src, fn), (cls, fn)
    assert "clampPos" in _fn_body(src, seats), (cls, seats)
