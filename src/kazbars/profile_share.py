"""KazBars — self-contained profile export files (pure data layer, no Tk).

A profile export is one JSON file — the envelope ``{format, export_schema,
profile, buffs}`` — that embeds not just the document but **any user-DB buffs
it references**, so a profile built around custom buffs survives import into
a fresh install whose shipped database has never heard of them.

  - ``build_export(registry, doc, by_id, by_name, provenance)`` → envelope.
  - ``parse_export(raw)`` → ``(profile_raw, embedded_buffs)``; accepts the
    envelope or a bare document (a file copied straight out of ``profiles/``
    — no buffs ride along); raises ``ValueError`` otherwise. The profile
    itself is validated downstream by ``profile_document.validate_document``
    (which is also what gives an old-format profile its "older KazBars"
    rejection).
  - ``collect_embedded_buffs(...)`` → exactly the referenced buffs whose
    provenance is ``user``, sourced from each registered section's
    ``harvest_refs`` hook (int-ID and legacy name refs both resolve to
    ``ids[0]``).
  - ``merge_imported_buffs(delta_store, embedded_buffs, existing_ids,
    existing_names)`` → merge into ``database_user.json``: skip on an ID
    collision, rename on a name-only collision.

Pure — stdlib + ``buff_db_layers`` (the ``ids[0]`` identity helper) only.
"""

import copy

from . import buff_db_layers

EXPORT_FORMAT = 'kazbars-profile-export'
EXPORT_SCHEMA = 1


def build_export(registry, doc, by_id, by_name, provenance):
    """The export envelope for `doc`: full document (deep-copied) plus every
    referenced user-provenance buff."""
    return {
        'format': EXPORT_FORMAT,
        'export_schema': EXPORT_SCHEMA,
        'profile': copy.deepcopy(doc),
        'buffs': collect_embedded_buffs(registry, doc, by_id, by_name, provenance),
    }


def parse_export(raw):
    """A loaded JSON object → ``(profile_raw, embedded_buffs)``.

    Accepts the export envelope or a bare profile document; anything else
    raises ``ValueError`` with a user-presentable message. Old-format bare
    profiles pass through so the document gate downstream rejects them with
    its own "older KazBars" message."""
    if not isinstance(raw, dict):
        raise ValueError("That file isn't a KazBars profile.")
    if raw.get('format') == EXPORT_FORMAT:
        schema = raw.get('export_schema', 1)
        if isinstance(schema, int) and schema > EXPORT_SCHEMA:
            raise ValueError('This export needs a newer KazBars — update the app first.')
        profile = raw.get('profile')
        if not isinstance(profile, dict):
            raise ValueError('This export file is missing its profile data.')
        buffs = raw.get('buffs', [])
        return profile, buffs if isinstance(buffs, list) else []
    if any(key in raw for key in ('modules', 'schema', 'profile_schema', 'grids')):
        return raw, []
    raise ValueError("That file isn't a KazBars profile.")


def collect_embedded_buffs(registry, doc, by_id, by_name, provenance):
    """The user-provenance buffs `doc` references — the ones an importer
    wouldn't already have. Refs come from each registered section's
    ``harvest_refs`` hook; int IDs and legacy name strings both resolve to
    ``ids[0]``; only ``user`` buffs embed (stock/OTA the importer has).
    Deterministic order (sorted by primary id)."""
    referenced = set()
    modules = doc.get('modules', {})
    for spec in registry.specs():
        if spec.harvest_refs is None:
            continue
        for ref in spec.harvest_refs(modules.get(spec.key, {})):
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
