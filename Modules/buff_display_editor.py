"""Kaz Grids — Default Buff Display editor."""

import logging
import re
import shutil
import tkinter as tk
from tkinter import ttk
from pathlib import Path

from ttkbootstrap.dialogs import Messagebox

from .ui_helpers import (
    FONT_BODY, FONT_FORM_LABEL, FONT_SMALL,
    THEME_COLORS, TK_COLORS,
    BTN_DIALOG, INPUT_WIDTH_NUM, LABEL_WIDTH_FORM,
    PAD_INNER, PAD_LF, PAD_TINY, PAD_XS, PAD_SMALL, PAD_TAB,
    MODULE_COLORS,
)
from .ui_widgets import create_dialog_header, app_toast, CollapsibleSection
from .ui_components import create_scrollable_frame
from .window_position import restore_window_position, bind_window_position_save
from .settings_manager import get_setting, set_setting

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================
DIALOG_SIZE = (520, 607)
DIALOG_MIN = (520, 607)

BUFF_FILES = [
    ("Player",   "Views/HUD/CharPortraitLeft.xml"),
    ("Target",   "Views/HUD/CharPortraitRight.xml"),
    ("Top",      "Views/HUD/HUDView.xml"),
    ("Floating", "Views/HUD/FloatingPortraitView.xml"),
]

FILTER_FRIENDLY = 'friendly'
FILTER_HOSTILE = 'hostile'
FILTER_BOTH = 'friendly | hostile'

BADGE_DEFAULT = 'Default'
BADGE_CUSTOMIZED = 'Customized'
BADGE_MISSING = 'Missing'
BADGE_UNSUPPORTED = 'Unsupported'

# Stock icon size is 31; bounds bracket the usable range so a stray
# scroll-wheel can't make the HUD invisible (4px) or destroy layout (200px).
ICON_SIZE_MIN, ICON_SIZE_MAX = 8, 128
SPACING_MIN, SPACING_MAX = 0, 50
COLS_MIN, COLS_MAX = 1, 30

BACKUP_SUFFIX = '.kzgrids.bak'

# First-launch default opens Player only — most users want to verify their
# primary buff bar without scrolling past the rest.
SETTINGS_KEY_SECTION_OPEN = 'buff_display_section_open'
DEFAULT_SECTION_OPEN = {'Player': True, 'Target': False, 'Top': False, 'Floating': False}

_BUFFLISTVIEW_TAG_RE = re.compile(r'<BuffListView\b[^>]*?/>', re.DOTALL)
_KZ_OFF_RE = re.compile(
    r'<!--\s*KZ_OFF\s*(<BuffListView\b[^>]*?/>)\s*KZ_OFF\s*-->',
    re.DOTALL,
)


# ============================================================================
# PATH HELPERS
# ============================================================================
def _resolve_paths(game_path, relpath):
    """Return (default_path, customized_path, source_path).

    source_path is Customized if it exists, else Default, else None.
    """
    base = Path(game_path) / "Data" / "Gui"
    default_path = base / "Default" / relpath
    customized_path = base / "Customized" / relpath
    if customized_path.is_file():
        source_path = customized_path
    elif default_path.is_file():
        source_path = default_path
    else:
        source_path = None
    return default_path, customized_path, source_path


def _detect_custom_ui(game_path):
    """True if Customized/Views/HUD/ contains files we don't manage, or
    Customized/Views/ has any subfolder other than HUD."""
    base = Path(game_path) / "Data" / "Gui" / "Customized" / "Views"
    if not base.is_dir():
        return False
    managed = {Path(rp).name for _, rp in BUFF_FILES}
    hud_dir = base / "HUD"
    if hud_dir.is_dir():
        for entry in hud_dir.iterdir():
            if entry.is_file() and entry.name not in managed:
                if entry.name.endswith(BACKUP_SUFFIX):
                    continue
                return True
            if entry.is_dir():
                return True
    for entry in base.iterdir():
        if entry.is_dir() and entry.name != "HUD":
            return True
        if entry.is_file():
            return True
    return False


# ============================================================================
# XML EDITS (regex-only, no parser)
# ============================================================================
def _read_attr(tag_text, attr_name):
    m = re.search(rf'\b{re.escape(attr_name)}\s*=\s*"([^"]*)"', tag_text)
    return m.group(1) if m else None


def _replace_attr(tag_text, attr_name, value):
    """Set an attribute inside a self-closing tag, injecting before `/>` if absent.

    Caller guarantees the tag matches `_BUFFLISTVIEW_TAG_RE` (so it ends with
    `/>`). The four attrs this dialog manages are all documented BuffListView
    attributes — AoC's parser handles them whether or not the source listed them.
    """
    pattern = re.compile(rf'(\b{re.escape(attr_name)}\s*=\s*")[^"]*(")')
    new_text, n = pattern.subn(lambda m: m.group(1) + value + m.group(2), tag_text)
    if n:
        return new_text
    m = re.search(r'(\s*/>)\s*$', tag_text)
    assert m is not None, "caller guarantees the tag ends with />"
    return tag_text[:m.start()] + f' {attr_name}="{value}"' + m.group(1)


def _normalise_filter(raw):
    """Map a raw filter= value to FILTER_FRIENDLY/HOSTILE/BOTH, or raw if no fit.

    Strips whitespace around the pipe so 'friendly|hostile',
    'friendly | hostile', and 'hostile|friendly' all map to BOTH.
    """
    if raw is None:
        return None
    parts = [p.strip() for p in raw.split('|')]
    parts = [p for p in parts if p]
    parts_lower = sorted(p.lower() for p in parts)
    if parts_lower == ['friendly', 'hostile']:
        return FILTER_BOTH
    if len(parts) == 1:
        v = parts[0].lower()
        if v == 'friendly':
            return FILTER_FRIENDLY
        if v == 'hostile':
            return FILTER_HOSTILE
    return raw


def _read_bufflistview(xml_text):
    """Extract attrs from a <BuffListView /> in the file.

    Returns dict (icon_size, icon_spacing, max_columns, filter, enabled), or
    None if no <BuffListView> tag is present. enabled is False when wrapped in
    a KZ_OFF comment.
    """
    enabled = True
    m_off = _KZ_OFF_RE.search(xml_text)
    if m_off:
        enabled = False
        tag_text = m_off.group(1)
    else:
        m = _BUFFLISTVIEW_TAG_RE.search(xml_text)
        if not m:
            return None
        tag_text = m.group(0)

    return {
        'icon_size':    _read_attr(tag_text, 'icon_size'),
        'icon_spacing': _read_attr(tag_text, 'icon_spacing'),
        'max_columns':  _read_attr(tag_text, 'max_columns'),
        'filter':       _normalise_filter(_read_attr(tag_text, 'filter')),
        'enabled':      enabled,
    }


def _write_bufflistview(xml_text, attrs, enabled):
    """Apply attrs to the file's <BuffListView /> in place.

    `attrs` keys (icon_size, icon_spacing, max_columns, filter) with a None
    value are left untouched. Skip-when-equal keeps unrelated bytes identical
    so a one-field edit produces a one-field diff. KZ_OFF wrap is stripped
    before edits and re-applied if `enabled` is False. Returns None if the
    file has no <BuffListView> tag at all.
    """
    m_off = _KZ_OFF_RE.search(xml_text)
    if m_off:
        xml_text = xml_text[:m_off.start()] + m_off.group(1) + xml_text[m_off.end():]

    m = _BUFFLISTVIEW_TAG_RE.search(xml_text)
    if not m:
        return None

    new_tag = m.group(0)
    for attr_name in ('icon_size', 'icon_spacing', 'max_columns', 'filter'):
        value = attrs.get(attr_name)
        if value is None or _read_attr(new_tag, attr_name) == value:
            continue
        new_tag = _replace_attr(new_tag, attr_name, value)

    if not enabled:
        new_tag = f'<!--KZ_OFF {new_tag} KZ_OFF-->'

    return xml_text[:m.start()] + new_tag + xml_text[m.end():]


def _backup_once(customized_path):
    """Copy customized_path → customized_path.kzgrids.bak iff .bak doesn't
    already exist. Lets the user recover their pre-Kaz-Grids state by hand."""
    bak = customized_path.with_name(customized_path.name + BACKUP_SUFFIX)
    if customized_path.is_file() and not bak.exists():
        try:
            shutil.copy2(customized_path, bak)
        except OSError as e:
            logger.warning("Could not write backup %s: %s", bak, e)


def _maybe_int(value):
    """Parse value to int, or None if blank/unparseable. Blanks must not
    materialise as zero — they stay out of the write attrs so the source's
    existing value (or absence) is preserved."""
    try:
        s = str(value).strip()
        return int(s) if s else None
    except (ValueError, TypeError):
        return None


def _parse_point(raw):
    """Pull (x, y) from 'Point(31,31)'. None on parse failure."""
    if raw is None:
        return None
    m = re.match(r'\s*Point\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)\s*$', raw)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _format_point(x, y):
    return f'Point({x},{y})'


# ============================================================================
# UI HELPERS
# ============================================================================
def _muted(parent, **kwargs):
    """ttk.Label preset with FONT_SMALL + muted foreground."""
    kwargs.setdefault('font', FONT_SMALL)
    kwargs.setdefault('foreground', THEME_COLORS['muted'])
    return ttk.Label(parent, **kwargs)


def _bind_label_wraplength(label, container):
    """Reflow label.wraplength to track container width. Min 120 keeps the
    label readable at the dialog's minsize."""
    pad = PAD_INNER * 2
    container.bind(
        '<Configure>',
        lambda e: label.configure(wraplength=max(120, e.width - pad)),
        add='+',
    )


def _render_inline_message(parent, text):
    msg = ttk.Label(
        parent, text=text,
        font=FONT_BODY, foreground=THEME_COLORS['muted'],
        wraplength=460, justify='left',
    )
    msg.pack(anchor='w')
    _bind_label_wraplength(msg, parent)


# ============================================================================
# SECTION (one per file)
# ============================================================================
class _Section:
    """One row in the dialog: header + form for a single XML file."""

    STATE_OK = 'ok'
    STATE_MISSING = 'missing'
    STATE_UNSUPPORTED = 'unsupported'

    def __init__(self, dialog, label, relpath, on_change):
        self.dialog = dialog
        self.label = label
        self.relpath = relpath
        self.on_change = on_change

        self.customized_path = None
        self.source_path = None
        self.state = self.STATE_OK
        self._source_text = None

        self.icon_size_var = tk.StringVar()
        self.spacing_var = tk.StringVar()
        self.cols_var = tk.StringVar()
        self.filter_var = tk.StringVar()
        self.enabled_var = tk.BooleanVar(value=True)

        self._baseline = None
        self._last_snapshot = None

        self._row_labels = []
        self._badge_var = tk.StringVar(value='')
        self._frame = None
        self._toggle = None
        self._filter_hint = None

    @property
    def _source_is_customized(self):
        return self.source_path is not None and self.source_path == self.customized_path

    # ------------------------------------------------------------------
    # Loading & state derivation
    # ------------------------------------------------------------------
    def load(self, game_path):
        try:
            _, self.customized_path, self.source_path = _resolve_paths(
                game_path, self.relpath
            )
            if self.source_path is None:
                self.state = self.STATE_MISSING
                return
            xml_text = self.source_path.read_text(encoding='utf-8')
            attrs = _read_bufflistview(xml_text)
            if attrs is None:
                self.state = self.STATE_UNSUPPORTED
                return
            self.state = self.STATE_OK
            self._source_text = xml_text
            self._populate_vars(attrs)
            self._baseline = self._snapshot()
            self._last_snapshot = self._baseline
        except OSError as e:
            logger.warning("Could not read %s: %s", self.source_path, e)
            self.state = self.STATE_MISSING
        finally:
            self._refresh_badge()

    def _populate_vars(self, attrs):
        # Custom UIs may have non-square icons or non-uniform spacing; we
        # collapse to the first coord (X / W) and the user's next edit squares it.
        size_xy = _parse_point(attrs.get('icon_size'))
        spacing_xy = _parse_point(attrs.get('icon_spacing'))
        max_cols = _maybe_int(attrs.get('max_columns'))
        raw_filter = attrs.get('filter')
        flt = raw_filter if raw_filter in (FILTER_FRIENDLY, FILTER_HOSTILE, FILTER_BOTH) else ''

        self.icon_size_var.set(str(size_xy[0]) if size_xy else '')
        self.spacing_var.set(str(spacing_xy[0]) if spacing_xy else '')
        self.cols_var.set(str(max_cols) if max_cols is not None else '')
        self.filter_var.set(flt)
        self.enabled_var.set(bool(attrs.get('enabled', True)))

    def _snapshot(self):
        return (
            self.icon_size_var.get(), self.spacing_var.get(),
            self.cols_var.get(), self.filter_var.get(),
            bool(self.enabled_var.get()),
        )

    def dirty(self):
        if self.state != self.STATE_OK:
            return False
        return self._snapshot() != self._baseline

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------
    def build(self, parent, initial_open=True):
        cs = CollapsibleSection(parent, title=self.label, initially_open=initial_open)
        self._frame = cs

        _muted(cs.header_frame, textvariable=self._badge_var).pack(side='right')

        content = cs.content
        _muted(content, text=self.relpath).pack(anchor='w', pady=(0, PAD_LF))

        if self.state == self.STATE_MISSING:
            _render_inline_message(
                content,
                "This file isn't in your game folder. Verify your install.",
            )
            return cs

        if self.state == self.STATE_UNSUPPORTED:
            _render_inline_message(
                content,
                "This file's buff list element isn't in the standard format. "
                "Edit it manually or contact your UI mod author.",
            )
            return cs

        toggle_row = ttk.Frame(content)
        toggle_row.pack(fill='x', pady=(0, PAD_LF))
        self._toggle = ttk.Checkbutton(
            toggle_row, text="Show buff list",
            variable=self.enabled_var, command=self._on_change,
        )
        self._toggle.pack(side='left')

        self._add_int_row(content, "Icon size:", self.icon_size_var,
                          ICON_SIZE_MIN, ICON_SIZE_MAX, unit="px")
        self._add_int_row(content, "Icon spacing:", self.spacing_var,
                          SPACING_MIN, SPACING_MAX, unit="px")
        self._add_int_row(content, "Max columns:", self.cols_var,
                          COLS_MIN, COLS_MAX)
        self._add_filter_row(content)

        self._apply_disabled_style()
        self._refresh_filter_hint()
        return cs

    def _add_int_row(self, parent, label_text, var, lo, hi, unit=None):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=PAD_TINY)
        lbl = ttk.Label(row, text=label_text, font=FONT_FORM_LABEL,
                        foreground=THEME_COLORS['muted'], width=LABEL_WIDTH_FORM, anchor='w')
        lbl.pack(side='left')
        self._row_labels.append(lbl)

        spin = ttk.Spinbox(row, from_=lo, to=hi, textvariable=var,
                           width=INPUT_WIDTH_NUM, command=self._on_change)
        spin.pack(side='left')
        spin.bind('<KeyRelease>', lambda e: self._on_change())

        if unit:
            unit_lbl = _muted(row, text=unit)
            unit_lbl.pack(side='left', padx=(PAD_XS, 0))
            self._row_labels.append(unit_lbl)

    def _add_filter_row(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=PAD_TINY)
        lbl = ttk.Label(row, text="Filter:", font=FONT_FORM_LABEL,
                        foreground=THEME_COLORS['muted'], width=LABEL_WIDTH_FORM, anchor='w')
        lbl.pack(side='left')
        self._row_labels.append(lbl)

        for text, value in (("Friendly",            FILTER_FRIENDLY),
                            ("Hostile",             FILTER_HOSTILE),
                            ("Friendly + Hostile",  FILTER_BOTH)):
            rb = ttk.Radiobutton(row, text=text, variable=self.filter_var,
                                 value=value, command=self._on_change)
            rb.pack(side='left', padx=(0, PAD_TAB))

        # Inline note when no filter is set in the source — makes the
        # all-radios-unselected state legible (otherwise it can read as
        # "broken" instead of "intentionally blank, mirrors the file").
        self._filter_hint = _muted(row, text='')
        self._filter_hint.pack(side='left')

    # ------------------------------------------------------------------
    # Change handling
    # ------------------------------------------------------------------
    def _on_change(self):
        snap = self._snapshot()
        if snap == self._last_snapshot:
            return
        self._last_snapshot = snap
        self._apply_disabled_style()
        self._refresh_filter_hint()
        self._refresh_badge()
        self.on_change()

    def _refresh_filter_hint(self):
        if self._filter_hint is None:
            return
        text = "(no filter set in source)" if self.filter_var.get() == '' else ''
        if self._filter_hint.cget('text') != text:
            self._filter_hint.configure(text=text)

    def _apply_disabled_style(self):
        """Mute row labels when the buff list is toggled off (inputs stay
        editable so the user can preconfigure a hidden list)."""
        if self.state != self.STATE_OK:
            return
        on = bool(self.enabled_var.get())
        color = THEME_COLORS['muted'] if on else TK_COLORS['dim_text']
        for lbl in self._row_labels:
            try:
                lbl.configure(foreground=color)
            except tk.TclError:
                pass  # widget destroyed during teardown

    def _refresh_badge(self):
        if self.state == self.STATE_MISSING:
            text = f"[{BADGE_MISSING}]"
        elif self.state == self.STATE_UNSUPPORTED:
            text = f"[{BADGE_UNSUPPORTED}]"
        else:
            origin = BADGE_CUSTOMIZED if self._source_is_customized else BADGE_DEFAULT
            suffix = " · Modified" if self.dirty() else ""
            text = f"[{origin}{suffix}]"
        if self._badge_var.get() != text:
            self._badge_var.set(text)

    def focus_first(self):
        """Move focus to this section's first focusable widget. Returns True
        if focus was set, False if there's nothing focusable. Expands a
        collapsed section so focus lands on a visible widget."""
        if self.state != self.STATE_OK or self._toggle is None:
            return False
        if self._frame is not None and not self._frame.is_open:
            self._frame.expand()
        self._toggle.focus_set()
        return True

    @property
    def is_open(self):
        return bool(self._frame and self._frame.is_open)

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------
    def write_to_disk(self):
        if self.state != self.STATE_OK or self.source_path is None or self.customized_path is None:
            return
        # Reuse text read at load() time — the source file hasn't changed
        # under us within a single dialog session.
        source_text = self._source_text
        if source_text is None:
            source_text = self.source_path.read_text(encoding='utf-8')

        # Only fields with a valid value land in attrs. Blanks and unparseable
        # entries stay out so the source's existing attribute — or its absence —
        # is preserved. Numeric fields are clamped so a typed value past the
        # spinbox arrows (e.g. 999) can't reach the file.
        attrs = {}
        int_specs = (
            (self.icon_size_var, ICON_SIZE_MIN, ICON_SIZE_MAX, 'icon_size',    lambda v: _format_point(v, v)),
            (self.spacing_var,   SPACING_MIN,   SPACING_MAX,   'icon_spacing', lambda v: _format_point(v, v)),
            (self.cols_var,      COLS_MIN,      COLS_MAX,      'max_columns',  str),
        )
        for var, lo, hi, key, fmt in int_specs:
            n = _maybe_int(var.get())
            if n is not None:
                attrs[key] = fmt(max(lo, min(hi, n)))
        flt = self.filter_var.get()
        if flt in (FILTER_FRIENDLY, FILTER_HOSTILE, FILTER_BOTH):
            attrs['filter'] = flt

        new_text = _write_bufflistview(source_text, attrs, bool(self.enabled_var.get()))
        if new_text is None:
            raise RuntimeError(
                f"<BuffListView> element not found in {self.source_path}"
            )

        self.customized_path.parent.mkdir(parents=True, exist_ok=True)
        _backup_once(self.customized_path)
        self.customized_path.write_text(new_text, encoding='utf-8')

    def load_after_write(self):
        """Re-read after a successful write so source_path/baseline reflect
        the new on-disk state (Customized now wins for this file)."""
        self.source_path = self.customized_path
        try:
            xml_text = self.source_path.read_text(encoding='utf-8')
        except OSError:
            return
        attrs = _read_bufflistview(xml_text)
        if attrs is not None:
            self._source_text = xml_text
            self._populate_vars(attrs)
            self._baseline = self._snapshot()
            self._last_snapshot = self._baseline
        self._refresh_badge()


# ============================================================================
# DIALOG
# ============================================================================
class BuffDisplayDialog(tk.Toplevel):
    """Modal editor for Player, Target, Top, and Floating buff display attributes."""

    def __init__(self, app):
        super().__init__(app)
        self.withdraw()
        self.title("Default Buff Bars")
        self.transient(app)
        self.grab_set()

        self.app = app
        self.sections = []
        self._apply_btn = None
        self._apply_enabled = None

        self._create_widgets()
        self._refresh_apply_state()

        restore_window_position(self, 'buff_display_editor', *DIALOG_SIZE, app)
        bind_window_position_save(self, 'buff_display_editor')
        self.minsize(*DIALOG_MIN)
        self.deiconify()

        self.bind('<Escape>', lambda e: self._on_cancel())
        self.bind('<Return>', lambda e: self._on_apply())
        # Persist section open/closed state regardless of how the dialog
        # closes (X button, Cancel, Escape).
        self.protocol('WM_DELETE_WINDOW', self._on_close)

        # after_idle so the toggle widget is fully realized before grabbing focus.
        self.after_idle(self._set_initial_focus)

    def _set_initial_focus(self):
        for s in self.sections:
            if s.focus_first():
                return

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------
    def _create_widgets(self):
        create_dialog_header(self, "DEFAULT BUFF BARS", MODULE_COLORS['grids'])

        # Disambiguates from Kaz Grids' own grid editor (Grids panel) — a
        # frequent confusion point.
        subtitle = ttk.Frame(self)
        subtitle.pack(fill='x')
        _muted(
            subtitle,
            text="Edit Age of Conan's built-in buff bars. Kaz Grids isn't affected.",
        ).pack(anchor='w', padx=PAD_INNER, pady=(PAD_LF, 0))

        if _detect_custom_ui(self.app.game_path):
            banner = tk.Frame(self, bg=TK_COLORS['status_bg'])
            banner.pack(fill='x')
            tk.Label(
                banner, bg=TK_COLORS['status_bg'],
                text="Custom UI detected. Edits stay in your skin.",
                fg=THEME_COLORS['body'], font=FONT_BODY,
            ).pack(anchor='w', padx=PAD_INNER, pady=PAD_LF)

        # Bottom row packs FIRST so it reserves height before body claims
        # expansion space — buttons stay visible regardless of how the user
        # resizes the dialog.
        bottom = ttk.Frame(self, padding=(PAD_INNER, PAD_LF, PAD_INNER, PAD_LF))
        bottom.pack(fill='x', side='bottom')
        self._apply_btn = ttk.Button(
            bottom, text="Apply", command=self._on_apply,
            width=BTN_DIALOG, bootstyle='success',  # type: ignore[call-arg]
        )
        self._apply_btn.pack(side='right')
        ttk.Button(
            bottom, text="Cancel", command=self._on_cancel,
            width=BTN_DIALOG, bootstyle='secondary',  # type: ignore[call-arg]
        ).pack(side='right', padx=(0, PAD_SMALL))

        body_pad = ttk.Frame(self, padding=PAD_INNER)
        body_pad.pack(fill='both', expand=True)
        scroll_outer, body, _ = create_scrollable_frame(body_pad)
        scroll_outer.pack(fill='both', expand=True)

        saved_states = get_setting(SETTINGS_KEY_SECTION_OPEN) or {}

        for i, (label, relpath) in enumerate(BUFF_FILES):
            section = _Section(self, label, relpath, on_change=self._refresh_apply_state)
            if self.app.game_path:
                section.load(self.app.game_path)
            self.sections.append(section)
            initial_open = saved_states.get(label, DEFAULT_SECTION_OPEN.get(label, False))
            sf = section.build(body, initial_open=initial_open)
            # Tight gap — collapsible sections carry their own visual chunking
            # (header bar + indented content) so PAD_SECTION_GAP would feel cavernous.
            sf.pack(fill='x', pady=(0 if i == 0 else PAD_LF, 0))

    # ------------------------------------------------------------------
    # Apply / Cancel
    # ------------------------------------------------------------------
    def _refresh_apply_state(self):
        any_dirty = any(s.dirty() for s in self.sections)
        if self._apply_btn is None or any_dirty == self._apply_enabled:
            return
        self._apply_enabled = any_dirty
        self._apply_btn.configure(state='normal' if any_dirty else 'disabled')

    def _on_apply(self):
        dirty_sections = [s for s in self.sections if s.dirty()]
        if not dirty_sections:
            return
        failures = []
        successes = []
        for section in dirty_sections:
            try:
                section.write_to_disk()
                section.load_after_write()
                successes.append(section.label)
            except (OSError, RuntimeError) as e:
                failures.append((section.label, str(e)))
        self._refresh_apply_state()
        if failures:
            # Failure toast uses key= so retries coalesce. The OS-level reason
            # (permission denied, disk full) lives in the log; the toast names
            # what failed and what to check, in that order.
            names = ", ".join(lbl for lbl, _ in failures)
            for lbl, err in failures:
                logger.warning("Buff Display apply failed for %s: %s", lbl, err)
            app_toast(
                self,
                f"Couldn't write {names}. Check folder permissions and disk space.",
                'danger', duration=10, key='buff_apply_failed',
            )
        else:
            names = ", ".join(successes)
            app_toast(self, f"Saved: {names}", 'success')

    def _on_cancel(self):
        self._on_close()

    def _on_close(self):
        """Single exit path: persist section open/closed state, then destroy.
        Routed from the X button (WM_DELETE_WINDOW), Cancel, and Escape."""
        self._save_section_states()
        self.destroy()

    def _save_section_states(self):
        states = {s.label: s.is_open for s in self.sections}
        if states:
            set_setting(SETTINGS_KEY_SECTION_OPEN, states)


# ============================================================================
# PUBLIC ENTRY
# ============================================================================
def open_buff_display_editor(app):
    """Open the Buff Display Editor dialog. Validates game folder first."""
    if not app.game_path or not Path(app.game_path).is_dir():
        Messagebox.show_warning(
            "No game folder set. Configure one in the bottom bar first.",
            title="No Game Folder",
        )
        return
    BuffDisplayDialog(app)
