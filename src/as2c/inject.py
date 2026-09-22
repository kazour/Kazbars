"""SWF surgery — put compiled classes into an existing movie the way mtasc's `-swf` mode does.

Observed contract (see docs/inject-contract.md for the probes):

* Every existing compiled class — a contiguous `DefineSprite, ExportAssets(__Packages.X),
  DoInitAction` triple — is removed unless `keep` is set. (mtasc removes *any* such triple
  regardless of the export name; we require the `__Packages.` prefix so an authored symbol can
  never be deleted by accident.)
* The new classes go in as `DefineSprite(id) + ExportAssets(id, "__Packages.<path>")
  + DoInitAction(id, code)` triples (the sprite claims one frame), ids counting up from
  0x5000, all long-form headers.
* Insertion point in the target frame: immediately before the frame's last tag when that tag
  is a `DoAction` (a frame script, which must run after the classes exist); otherwise right
  before the frame's `ShowFrame`. The test is made on the tag list *before* stale classes are
  removed.
* `DoInitAction` tags that register a library symbol to a class (Flash's exact
  `Object.registerClass` sequence) are moved to just after the injected classes, in their
  original order, so the class exists when they run. A warning is returned when such a tag
  names a class that was not compiled.
* The output keeps the input's compression and gets the requested SWF version.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import avm1, swf

FIRST_CLASS_ID = 0x5000


@dataclass
class InjectResult:
    warnings: list[str]


def registered_class(tag: swf.Tag) -> str | None:
    """The class name a symbol-registration DoInitAction binds, or None if the tag isn't one.

    Flash writes: Push "<class>"; GetVariable; Push "<symbol>", 2, "Object"; GetVariable;
    Push "registerClass"; CallMethod; Pop; End.
    """
    if tag.code != swf.TAG_DO_INIT_ACTION:
        return None
    acts = [a for _, a in avm1.decode_actions(tag.actions())]
    codes = [a.code for a in acts]
    if codes == [avm1.PUSH, 0x1C, avm1.PUSH, 0x1C, avm1.PUSH, 0x52, 0x17]:
        p0, p1, p2 = acts[0].values, acts[2].values, acts[4].values
        if (len(p0) == 1 and isinstance(p0[0], avm1.Str)
                and len(p1) == 3 and isinstance(p1[0], avm1.Str) and isinstance(p1[1], avm1.Int)
                and p1[2] == avm1.Str('Object') and p2 == [avm1.Str('registerClass')]):
            return p0[0].value
        return None
    if codes == [avm1.CONSTANT_POOL, avm1.PUSH, 0x1C, avm1.PUSH, 0x1C, avm1.PUSH, 0x52, 0x17]:
        pool = acts[0].strings
        p0, p1, p2 = acts[1].values, acts[3].values, acts[5].values
        if (len(pool) == 3 and pool[1:] == ['Object', 'registerClass'] and p0 == [avm1.Const8(0)]
                and len(p1) == 3 and p1[0] == avm1.Const8(0) and isinstance(p1[1], avm1.Int)
                and p1[2] == avm1.Const8(1) and p2 == [avm1.Const8(2)]):
            return pool[0]
    return None


def is_mtasc_main(tag: swf.Tag) -> bool:
    """A DoAction produced by a previous `-main` run (its pool starts with MTASC_MAIN)."""
    if tag.code != swf.TAG_DO_ACTION:
        return False
    acts = avm1.decode_actions(tag.actions())
    if not acts:
        return False
    a = acts[0][1]
    return a.code == avm1.CONSTANT_POOL and bool(a.strings) and a.strings[0] == 'MTASC_MAIN'


def _is_class_triple(tags: list[swf.Tag], i: int) -> bool:
    if i + 2 >= len(tags):
        return False
    a, b, c = tags[i], tags[i + 1], tags[i + 2]
    if a.code != swf.TAG_DEFINE_SPRITE or b.code != swf.TAG_EXPORT_ASSETS or c.code != swf.TAG_DO_INIT_ACTION:
        return False
    exports = b.exports()
    if len(exports) != 1 or not exports[0][1].startswith('__Packages.'):
        return False
    return exports[0][0] == a.sprite_id() == c.sprite_id()


def inject(movie: swf.Movie, classes: list[tuple[str, bytes]], version: int = 8,
           keep: bool = False, frame: int = 1, main_code: bytes | None = None) -> InjectResult:
    """Inject `classes` (dotted name, action bytes) into `movie` in place.

    `main_code` is the `-main` bootstrap DoAction; it goes after the classes and replaces a
    previous run's (recognised by its MTASC_MAIN pool entry)."""
    warnings: list[str] = []
    tags = movie.tags

    # Locate the target frame: the tags before its ShowFrame.
    show_frames = [i for i, t in enumerate(tags) if t.code == swf.TAG_SHOW_FRAME]
    if frame < 1 or frame > len(show_frames):
        raise ValueError(f'frame {frame} does not exist in the movie ({len(show_frames)} frames)')
    frame_end = show_frames[frame - 1]
    frame_start = show_frames[frame - 2] + 1 if frame > 1 else 0

    # Anchor: the frame's last tag if it is a DoAction, else the ShowFrame. A previous -main
    # bootstrap sitting there is dropped instead.
    anchor_tag = tags[frame_end]
    stale_main = None
    if frame_end - 1 >= frame_start and tags[frame_end - 1].code == swf.TAG_DO_ACTION:
        if is_mtasc_main(tags[frame_end - 1]):
            stale_main = tags[frame_end - 1]
        else:
            anchor_tag = tags[frame_end - 1]

    # Strip stale classes (whole movie) and pull out symbol-registration inits (target frame).
    kept: list[swf.Tag] = []
    moved: list[swf.Tag] = []
    i = 0
    while i < len(tags):
        if not keep and _is_class_triple(tags, i):
            i += 3
            continue
        t = tags[i]
        if t is stale_main:
            i += 1
            continue
        if frame_start <= i < frame_end and t is not anchor_tag:
            cls = registered_class(t)
            if cls is not None:
                moved.append(t)
                i += 1
                continue
        kept.append(t)
        i += 1

    compiled = {name for name, _ in classes}
    for t in moved:
        cls = registered_class(t)
        if cls not in compiled:
            warnings.append(f'a library symbol registers class {cls}, which was not compiled; '
                            f'add it to the command line')

    new_tags: list[swf.Tag] = []
    used = {t.sprite_id() for t in kept if t.code == swf.TAG_DEFINE_SPRITE}
    next_id = FIRST_CLASS_ID
    for name, code in classes:
        while next_id in used:
            next_id += 1
        cid = next_id
        next_id += 1
        sprite = swf.define_sprite(cid, 1)
        export = swf.export_assets([(cid, '__Packages.' + name)])
        init = swf.do_init_action(cid, code)
        for t in (sprite, export, init):
            t.long = True
        new_tags += [sprite, export, init]
    new_tags += moved
    if main_code is not None:
        t = swf.do_action(main_code)
        t.long = True
        new_tags.append(t)

    at = next(i for i, t in enumerate(kept) if t is anchor_tag)
    movie.tags = kept[:at] + new_tags + kept[at:]
    movie.version = version
    return InjectResult(warnings)

