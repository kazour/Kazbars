"""The AS2 ``KazBars*`` class names are load-bearing and must not be renamed.

``base.swf`` bootstraps the overlay with ``m_Module = new KazBars(this)``. The
generated classes and the shipped stubs must keep their ``KazBars``-prefixed
names: a Python-side rename compiles cleanly and then silently fails to bind
in-game, and undoing it needs a Flash CS6 re-export of ``base.fla``/``base.swf``.

Pure text assertions -- no MTASC, no ``base.swf``, so this runs on any platform.
``test_grids_generator.py`` already covers the Console/CastTimer/Stopwatch/Inspect
stubs behaviourally; the names checked here are the ones nothing else pins.
See docs/architecture.md -> Build pipeline.
"""

from pathlib import Path

from kazbars.buff_database import BuffDatabase
from kazbars.grids_generator import CodeGenerator

ASSETS = Path(__file__).resolve().parents[1] / 'src' / 'kazbars' / 'assets' / 'kazbars'
STUBS = ASSETS / 'stubs'


def _db():
    db = BuffDatabase()
    path = ASSETS / 'Database.json'
    if path.exists():
        db.load(path)
    else:
        db.buffs = []
    return db


def test_generator_emits_the_bootstrapped_class_names():
    main, data = CodeGenerator([], _db(), '0.0.0').generate()
    assert 'class KazBars {' in main, (
        'the main generated class must be named KazBars -- base.swf calls '
        'new KazBars(this) and will not bind to anything else'
    )
    assert 'class KazBarsData {' in data


def test_every_stub_declares_a_kazbars_prefixed_class():
    # Non-recursive on purpose: the stubs/ subdirectories carry vendored helpers
    # (com/Utils/ID32.as and friends) that are not KazBars* classes.
    stubs = sorted(STUBS.glob('*.as'))
    assert stubs, f'no AS2 stubs found under {STUBS}'
    for path in stubs:
        text = path.read_text(encoding='utf-8', errors='replace')
        declared = [
            line.strip().split()[1]
            for line in text.splitlines()
            if line.strip().startswith('class ') and len(line.strip().split()) > 1
        ]
        assert declared, f'{path.name} declares no class'
        assert all(name.startswith('KazBars') for name in declared), (
            f'{path.name} declares {declared}; every stub class must keep its '
            f'KazBars* name or the base.swf bind breaks'
        )
        assert path.stem in declared, (
            f'{path.name} must declare a class matching its filename, got {declared}'
        )
