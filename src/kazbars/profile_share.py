"""KazBars — the profile file's shape and the buffs it carries (pure data
layer, no Tk).

A profile file (`profile.yml`, an export `*.kazbars.yml`, the stock
`Default.yml`) is the document itself under a `format: kazbars-profile` line,
plus — in an export — **the user-DB buffs it references**, so a profile built
around custom buffs survives import into a fresh install whose shipped
database has never heard of them.

  - ``build_profile_file(doc, buffs=())`` → ``{format, **doc, [buffs]}``.
  - ``parse_profile_file(raw)`` → ``(profile_raw, embedded_buffs)``; accepts
    the profile file, the older export envelope ``{format:
    kazbars-profile-export, profile, buffs}`` and a bare
    document (a 3.1 ``profiles/*.json``); raises ``ValueError`` with a
    user-presentable message otherwise (a grids file gets pointed at File ▸
    Import grid…). The profile itself is validated downstream by
    ``profile_document.validate_document`` (which is also what gives an
    old-format profile its "older KazBars" rejection).
  - ``collect_embedded_buffs(...)`` / ``collect_for_refs(...)`` → exactly the
    referenced buffs whose provenance is ``user`` (int-ID and legacy name refs
    both resolve to ``ids[0]``); the first takes the refs from each
    registered section's ``harvest_refs`` hook.
  - ``merge_imported_buffs(delta_store, embedded_buffs, existing_ids,
    existing_names)`` → merge into ``database_user.json``: skip on an ID
    collision, rename on a name-only collision.
  - ``slugify(name)`` → a Windows-safe file name stem.

Pure — stdlib + ``buff_db_layers`` (the ``ids[0]`` identity helper) only.
"""

import re

from . import buff_db_layers

PROFILE_FORMAT = 'kazbars-profile'
PROFILE_EXT = '.kazbars.yml'
GRIDS_FORMAT = 'kazbars-grids'
GRIDS_EXT = '.kazbars-grids.yml'
# The 3.1 export envelope: read, never written.
EXPORT_FORMAT = 'kazbars-profile-export'

_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def slugify(name: str) -> str:
    """A Windows-safe filename stem from a display name. Keeps case and spaces
    (tool-honest, browsable in Explorer); strips illegal chars and trailing
    dots/spaces; never empty."""
    slug = _ILLEGAL_FILENAME_CHARS.sub('', str(name))
    slug = ' '.join(slug.split()).rstrip('. ')
    return slug or 'Profile'


def build_profile_file(doc, buffs=()):
    """The file for `doc`: its `format` line, the document's keys, and
    `buffs` last — only when there are any. A new top-level dict over the
    document's own values: write it, don't edit it."""
    out = {'format': PROFILE_FORMAT, **doc}
    if buffs:
        out['buffs'] = list(buffs)
    return out


def parse_profile_file(raw):
    """A loaded file → ``(profile_raw, embedded_buffs)``.

    Accepts a profile file, the 3.1 export envelope or a bare profile
    document; anything else raises ``ValueError`` with a user-presentable
    message. Old-format bare profiles pass through so the document gate
    downstream rejects them with its own "older KazBars" message."""
    if not isinstance(raw, dict):
        raise ValueError("That file isn't a KazBars profile.")
    fmt = raw.get('format')
    if fmt == PROFILE_FORMAT:
        profile = {k: v for k, v in raw.items() if k not in ('format', 'buffs')}
        return profile, buff_list(raw.get('buffs'))
    if fmt == EXPORT_FORMAT:
        inner = raw.get('profile')
        if not isinstance(inner, dict):
            raise ValueError('This export file is missing its profile data.')
        return inner, buff_list(raw.get('buffs'))
    if fmt == GRIDS_FORMAT:
        raise ValueError("That file is a grids file, not a profile. "
                         "Use File ▸ Import grid… instead.")
    if any(key in raw for key in ('modules', 'schema', 'profile_schema', 'grids')):
        return raw, []
    raise ValueError("That file isn't a KazBars profile.")


def buff_list(buffs):
    return buffs if isinstance(buffs, list) else []


def collect_embedded_buffs(registry, doc, by_id, by_name, provenance):
    """The user-provenance buffs `doc` references — the ones an importer
    wouldn't already have. Refs come from each registered section's
    ``harvest_refs`` hook; see ``collect_for_refs``."""
    refs = []
    modules = doc.get('modules', {})
    for spec in registry.specs():
        if spec.harvest_refs is not None:
            refs.extend(spec.harvest_refs(modules.get(spec.key, {})))
    return collect_for_refs(refs, by_id, by_name, provenance)


def collect_for_refs(refs, by_id, by_name, provenance):
    """The user-provenance buffs `refs` name: int IDs and legacy name strings
    both resolve to ``ids[0]``; only ``user`` buffs embed (stock/OTA the
    importer has). Deterministic order (sorted by primary id)."""
    referenced = set()
    for ref in refs:
        if isinstance(ref, bool):
            continue
        if isinstance(ref, int):
            entry = by_id.get(ref)
        elif isinstance(ref, str):
            entry = by_name.get(ref)
        else:
            continue
        if entry and entry.get('ids'):
            referenced.add(entry['ids'][0])
    return [
        by_id[rid] for rid in sorted(referenced)
        if provenance.get(rid) == 'user' and rid in by_id
    ]


def _unique_name(name, taken):
    """A display name not in ``taken``: ``"X (imported)"``, then
    ``"X (imported 2)"``, …. Mirrors the app's grid-name dedupe convention."""
    candidate = f"{name} (imported)"
    n = 2
    while candidate in taken:
        candidate = f"{name} (imported {n})"
        n += 1
    return candidate


def merge_imported_buffs(delta_store, embedded_buffs, existing_ids, existing_names=frozenset()):
    """Merge embedded buffs into ``database_user.json`` via ``delta_store``.

    A buff colliding on ANY id with the effective DB or the on-disk delta is
    skipped — a shared id would silently re-home an existing buff in ``by_id``.
    A buff whose *name* collides (but whose ids are all new) is kept and renamed
    unique (``"X (imported)"``): the profile's grids reference ids, not names, so
    the buff still resolves while the DB editor stays unambiguous. Structurally
    malformed embedded entries (a crafted/corrupt export file) are dropped.
    Returns ``(added, skipped)`` — renamed buffs count as added; writes only if
    something was added."""
    delta = delta_store.load()
    have_ids = set(existing_ids)
    have_names = set(existing_names)
    for b in delta["buffs"]:
        have_ids.update(b.get("ids", []))
        if b.get("name"):
            have_names.add(b["name"])
    added = skipped = 0
    for b in embedded_buffs:
        if not buff_db_layers.is_valid_buff(b):
            continue
        if any(bid in have_ids for bid in b["ids"]):
            skipped += 1
            continue
        if b["name"] in have_names:
            b = {**b, "name": _unique_name(b["name"], have_names)}
        delta["buffs"].append(b)
        have_ids.update(b["ids"])
        have_names.add(b["name"])
        added += 1
    if added:
        delta_store.save(delta)
    return added, skipped
