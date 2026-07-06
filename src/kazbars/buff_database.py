"""KazBars — Buff database (pure data layer).

JSON load/save plus in-memory indexes and search. No Tk, no ttkbootstrap —
safe to import from CI without the UI extra.

v2 Format:
{
    "name": "Buff Name",
    "ids": [id1, id2, ...],
    "category": "#Category",
    "type": "buff" | "debuff" | "misc",
    "stacking": true,      // optional - IDs represent stack levels
    "partialList": true,   // optional - IDs don't start from stack 1
    "stackStart": 1,       // optional - first stack level to track (default: 1)
    "stackEnd": 10         // optional - last stack level to track, complete list only (0 = all)
}
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


TYPE_FILTER_MAP = {"Buff": "buff", "Debuff": "debuff", "Misc": "misc"}


class BuffDatabase:
    """Handles loading, searching, and managing the buff database."""

    def __init__(self):
        self.buffs = []
        self.categories = []
        self.by_id = {}
        self.by_name = {}
        self.grouped_buffs = []
        self.provenance = {}        # ids[0] -> 'stock' | 'content' | 'user'
        self._layer_paths = None    # remembered by load_layers so reload() can re-merge

    def load(self, json_path):
        """Load a single v2 database file (back-compat / tests). For the app's
        layered load use `load_layers`."""
        from . import buff_db_layers
        try:
            with open(json_path, encoding='utf-8') as f:
                data = json.load(f)
            raw = data.get('buffs', []) if isinstance(data, dict) else []
            if not isinstance(raw, list):
                raw = []
            self.buffs = buff_db_layers._keep_valid(raw, Path(json_path).name)
            self.provenance = {}
            self._rebuild_indexes()
            return True
        except (OSError, json.JSONDecodeError) as e:
            logger.error("Error loading buff database: %s", e)
            return False

    def load_layers(self, stock_path, content_path=None, user_delta_path=None,
                    stock_fallback_path=None):
        """Merge stock <- content <- user deltas into `self.buffs` (user wins),
        record `self.provenance`, and rebuild indexes. On unreadable stock, falls
        back to `stock_fallback_path` (the bundled `.default`) **in memory** —
        never writes `assets/`. Paths are remembered so `reload()` can re-merge
        (e.g. after an OTA content swap). Returns True if any buff loaded."""
        from . import buff_db_layers
        self._layer_paths = (stock_path, content_path, user_delta_path, stock_fallback_path)
        stock = buff_db_layers._read_buffs(stock_path)
        if not stock and stock_fallback_path:
            logger.warning("Stock buff DB unreadable — using bundled default (in memory)")
            stock = buff_db_layers._read_buffs(stock_fallback_path)
        content = buff_db_layers._read_buffs(content_path)
        user_buffs, deleted = buff_db_layers._read_user_delta(user_delta_path)
        self.buffs, self.provenance = buff_db_layers.merge_layers(
            stock, content, user_buffs, deleted)
        self._rebuild_indexes()
        return bool(self.buffs)

    def reload(self):
        """Re-run the layered merge from the paths `load_layers` was last called
        with. Used after the OTA updater swaps `content/` (Phase 4)."""
        if self._layer_paths is not None:
            self.load_layers(*self._layer_paths)

    def current_floor(self):
        """The stock <- content floor (no user deltas) the editor diffs against
        to compute deltas and badge each row. Re-read from the remembered layer
        paths, mirroring the boot-time corrupt-stock fallback. Returns
        (floor_buffs, floor_provenance)."""
        if self._layer_paths is None:
            return [], {}
        from . import buff_db_layers
        stock_path, content_path, _user, fallback = self._layer_paths
        return buff_db_layers.load_floor(stock_path, content_path, stock_fallback_path=fallback)

    def _rebuild_indexes(self):
        """Rebuild internal indexes after data changes."""
        cats = set()
        self.by_id = {}
        self.by_name = {}
        for b in self.buffs:
            cats.add(b.get('category', 'Unknown'))
            ids = b.get('ids', [])
            for bid in ids:
                self.by_id[bid] = b
            self.by_name[b['name']] = b
        self.categories = sorted(cats)
        self.grouped_buffs = list(self.buffs)

    def search(self, query="", category=None, buff_type=None):
        """
        Search buffs by query, category, and type.

        Args:
            query: Search string (matches name or ID)
            category: Category filter (None = all)
            buff_type: Type filter - "buff", "debuff", "misc" (None = all)
        """
        results = []
        query_lower = query.lower()

        for buff in self.grouped_buffs:
            if category and buff.get('category') != category:
                continue
            if buff_type and buff.get('type', 'buff') != buff_type:
                continue
            if query_lower:
                name_match = query_lower in buff.get('name', '').lower()
                id_match = any(query_lower in str(bid) for bid in buff.get('ids', []))
                if not name_match and not id_match:
                    continue
            results.append(buff)

        type_order = {'buff': 0, 'debuff': 1, 'misc': 2}
        return sorted(results, key=lambda b: (type_order.get(b.get('type', 'buff'), 9), b.get('name', '')))

    def get_type(self, buff_id):
        """Get buff type by ID (buff/debuff/misc)."""
        buff = self.by_id.get(buff_id)
        if buff:
            return buff.get('type', 'buff')
        return 'buff'

    def is_debuff(self, buff_id):
        """Check if buff is a debuff."""
        return self.get_type(buff_id) == 'debuff'

    def get_entry_by_name(self, name):
        """Return entry dict for the given entry name, or None."""
        return self.by_name.get(name)

    def add_buff(self, buff_data):
        """Add a new buff entry."""
        self.buffs.append(buff_data)
        self._rebuild_indexes()

    def update_buff(self, old_ids, new_data):
        """Update an existing buff entry."""
        for i, buff in enumerate(self.buffs):
            buff_ids = buff.get('ids', [])
            if set(buff_ids) == set(old_ids):
                self.buffs[i] = new_data
                break
        self._rebuild_indexes()

    def remove_buff(self, ids):
        """Remove a buff entry by its IDs."""
        self.buffs = [b for b in self.buffs if set(b.get('ids', [])) != set(ids)]
        self._rebuild_indexes()

    def rename_category(self, old_name, new_name):
        """Rename a category across all buff entries."""
        for buff in self.buffs:
            if buff.get('category') == old_name:
                buff['category'] = new_name
        self._rebuild_indexes()
