"""KazBars — self-contained profile share strings (pure codec, no Tk).

A profile export is a portable ``KZBARS1:<base64(gzip(json))>`` string that
embeds not just the profile but **any user-DB buffs it references** — so a
profile built around custom buffs survives a paste into a fresh install whose
shipped database has never heard of them.

  - ``encode_profile(profile, embedded_buffs)`` → the string.
  - ``decode_profile(string)`` → ``(profile, embedded_buffs)``; raises
    ``ValueError`` on anything malformed/truncated.
  - ``collect_referenced_user_buffs(profile, by_id, by_name, provenance)`` →
    exactly the referenced buffs whose provenance is ``user`` (resolving both
    int-ID and legacy name refs to ``ids[0]``), so the export is self-contained.
  - ``merge_imported_buffs(delta_store, embedded_buffs, existing_ids)`` →
    skip-on-collision merge of embedded buffs into ``database_user.json``.

Pure — stdlib + ``buff_db_layers`` (the ``ids[0]`` identity helper) only.
"""

import base64
import binascii
import gzip
import json

from . import buff_db_layers

PREFIX = "KZBARS1:"


def encode_profile(profile, embedded_buffs):
    """Pack ``{profile, buffs}`` → ``KZBARS1:<base64(gzip(json))>``."""
    payload = {"profile": profile, "buffs": embedded_buffs}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return PREFIX + base64.b64encode(gzip.compress(raw)).decode("ascii")


def decode_profile(string):
    """``KZBARS1:…`` → ``(profile, embedded_buffs)``. Raises ``ValueError`` on a
    wrong prefix or corrupt/truncated payload."""
    s = (string or "").strip()
    if not s.startswith(PREFIX):
        raise ValueError("That doesn't look like a KazBars profile string.")
    try:
        packed = base64.b64decode(s[len(PREFIX):], validate=True)
        raw = gzip.decompress(packed)
        payload = json.loads(raw.decode("utf-8"))
    except (binascii.Error, OSError, EOFError, ValueError, UnicodeDecodeError) as e:
        raise ValueError("This profile string is corrupt or incomplete.") from e
    if not isinstance(payload, dict) or not isinstance(payload.get("profile"), dict):
        raise ValueError("This profile string is missing its profile data.")
    buffs = payload.get("buffs", [])
    return payload["profile"], buffs if isinstance(buffs, list) else []


def collect_referenced_user_buffs(profile, by_id, by_name, provenance):
    """The user-provenance buffs a profile references — the ones an importer
    wouldn't already have. Walks whitelist + slotAssignments, resolving both int
    IDs and legacy name strings to ``ids[0]``, then keeps only ``user`` buffs."""
    referenced = set()

    def _add(ref):
        if isinstance(ref, bool):
            return
        if isinstance(ref, int):
            entry = by_id.get(ref)
        elif isinstance(ref, str):
            entry = by_name.get(ref)
        else:
            return
        if entry and entry.get("ids"):
            referenced.add(entry["ids"][0])

    for grid in profile.get("grids", []):
        for ref in grid.get("whitelist", []):
            _add(ref)
        for val in grid.get("slotAssignments", {}).values():
            if isinstance(val, list):
                for ref in val:
                    _add(ref)
            else:
                _add(val)

    out = []
    seen = set()
    for rid in referenced:
        if provenance.get(rid) == "user" and rid in by_id and rid not in seen:
            out.append(by_id[rid])
            seen.add(rid)
    return out


def merge_imported_buffs(delta_store, embedded_buffs, existing_ids):
    """Merge embedded buffs into ``database_user.json`` via ``delta_store``,
    skipping any whose ``ids[0]`` already exists (in the effective DB or the
    delta). Structurally malformed embedded entries (a crafted/corrupt share
    string) are dropped. Returns ``(added, skipped)``; writes only if
    something was added."""
    delta = delta_store.load()
    have = set(existing_ids)
    for b in delta["buffs"]:
        key = buff_db_layers._identity(b)
        if key is not None:
            have.add(key)
    added = skipped = 0
    for b in embedded_buffs:
        if not buff_db_layers.is_valid_buff(b):
            continue
        key = buff_db_layers._identity(b)
        if key in have:
            skipped += 1
        else:
            delta["buffs"].append(b)
            have.add(key)
            added += 1
    if added:
        delta_store.save(delta)
    return added, skipped
