"""Tests for `classes` — the twelve class ids the per-class grids key on, and
a grid's `class` key: read only when one of the twelve, written only when
set, baked as `cls: <id>`; and `free_id`, the id a copied grid gets.

Run: `pytest tests/test_classes.py` (from repo root).
"""

from kazbars.buff_database import BuffDatabase
from kazbars.classes import CLASSES, by_id, id_of
from kazbars.grid_model import create_default_grid, validate_grid
from kazbars.grids_generator import CodeGenerator, free_id
from kazbars.paths import KAZBARS_ASSETS
from kazbars.prefs import _validate_grids_tab


def test_twelve_distinct_ids_grouped_by_archetype_in_tab_order():
    assert len({c.id for c in CLASSES}) == 12
    assert [c.archetype for c in CLASSES] == [0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3]
    assert [c.short for c in CLASSES] == ["Guard", "Conq", "DT", "PoM", "ToS", "BS",
                                          "Barb", "Sin", "Ranger", "Demo", "Necro", "HoX"]
    assert by_id(31).name == "Dark Templar"
    assert by_id(0) is None and by_id(19) is None and by_id(True) is None


def test_the_inspect_panel_names_the_same_class_ids():
    data = (KAZBARS_ASSETS / "stubs" / "KazBarsInspectData.as").read_text(encoding="utf-8")
    for c in CLASSES:
        assert f"{c.id}:" in data.replace(" ", ""), c


def test_only_one_of_the_twelve_ids_reads_as_a_class():
    def cls(**kw):
        return validate_grid(dict(create_default_grid(), **kw)).get("class")
    assert cls() is None
    assert cls(**{"class": 31}) == 31
    assert cls(**{"class": 19}) is None
    assert cls(**{"class": "31"}) is None
    assert cls(**{"class": None}) is None
    assert id_of(44) == 44 and id_of(7) is None


def test_a_class_grid_bakes_cls_last_and_an_all_grid_none():
    db = BuffDatabase()
    db.load_layers(KAZBARS_ASSETS / "Database.json")
    grids = [validate_grid({"id": "G", "whitelist": [222609], "class": 44}),
             validate_grid({"id": "H", "type": "target", "whitelist": [222609]})]
    _, data = CodeGenerator(grids, db, "0.0.0").generate()
    assert "            enableFlashing: true,\n            cls: 44\n        };" in data
    assert data.count("cls: ") == 1


def test_a_copy_gets_an_id_clear_of_every_archive_key():
    assert free_id(["Buffs"], "Buffs DT") == "Buffs DT"
    assert free_id(["Buffs", "Buffs_DT"], "Buffs DT") == "Buffs DT_2"
    assert free_id(["Buffs DT", "Buffs DT_2"], "Buffs DT") == "Buffs DT_3"


def test_the_tab_pref_is_a_class_or_all():
    assert [_validate_grids_tab(v) for v in (31, 0, 7, "31", None, True)] == [31, 0, 0, 0, 0, 0]
