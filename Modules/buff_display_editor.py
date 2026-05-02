"""
Kaz Grids — Default Buff Display editor.

Modal dialog for tuning the in-game HUD buff/debuff display attributes
(icon size, spacing, max columns, filter, on/off) on four portrait XML
files: Player + Target (CharPortraitLeft/Right.xml), Top (HUDView.xml),
and Floating (FloatingPortraitView.xml). Writes always go to Customized/,
never to Default/. Mirrors the source byte-for-byte: blank fields stay
out of the write attrs so the source's existing value (or absence) is
preserved. Section open/closed state persists across opens. Surgical
regex edits + one-shot backups protect custom UIs. Takes the KzGridsApp
instance as first arg.
"""

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

# Files we manage (relpath under <game>/Data/Gui/{Default,Customized}/).
# Order is the section order in the dialog; Player/Target lead because
# they're the most-edited surfaces.
BUFF_FILES = [
    ("Player",   "Views/HUD/CharPortraitLeft.xml"),
    ("Target",   "Views/HUD/CharPortraitRight.xml"),
    ("Top",      "Views/HUD/HUDView.xml"),
    ("Floating", "Views/HUD/FloatingPortraitView.xml"),
]

# Filter literal values written to XML.
FILTER_FRIENDLY = 'friendly'
FILTER_HOSTILE = 'hostile'
FILTER_BOTH = 'friendly | hostile'  # canonical spaced form

# Origin badges
BADGE_DEFAULT = 'Default'
BADGE_CUSTOMIZED = 'Customized'
BADGE_MISSING = 'Missing'
BADGE_UNSUPPORTED = 'Unsupported'

# Spinbox bounds. Stock icon size is 31; bounds bracket the usable range so a
# stray scroll-wheel can't make the HUD invisible (4px) or destroy the layout (200px).
ICON_SIZE_MIN, ICON_SIZE_MAX = 8, 128
SPACING_MIN, SPACING_MAX = 0, 50
COLS_MIN, COLS_MAX = 1, 30

# Backup file suffix
BACKUP_SUFFIX = '.kzgrids.bak'

# Per-section open/closed state persists across dialog opens. First-launch
# default opens Player only — most users want to verify their primary buff
# bar without scrolling past the rest.
SETTINGS_KEY_SECTION_OPEN = 'buff_display_section_open'
DEFAULT_SECTION_OPEN = {'Player': True, 'Target': False, 'Top': False, 'Floating': False}

# Regex: match a single self-closing <BuffListView ... />.  Used both inside
# a normal file and inside a KZ_OFF comment wrapper (the wrapper doesn't
# break the inner tag's pattern).
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

    source_path is the file we read attrs from: Customized if it exists,
    else Default, else None (file genuinely missing).
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
    Customized/Views/ has any subfolder other than HUD. Drives the banner.
    """
    base = Path(game_path) / "Data" / "Gui" / "Customized" / "Views"
    if not base.is_dir():
        return False
    managed = {Path(rp).name for _, rp in BUFF_FILES}
    hud_dir = base / "HUD"
    if hud_dir.is_dir():
        for entry in hud_dir.iterdir():
            if entry.is_file() and entry.name not in managed:
                # Ignore our own backups.
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
    """Pull an attribute's quoted value out of an XML tag string, or None."""
    m = re.search(rf'\b{re.escape(attr_name)}\s*=\s*"([^"]*)"', tag_text)
    return m.group(1) if m else None


def _replace_attr(tag_text, attr_name, value):
    """Set an attribute's value inside a self-closing tag string.

    Replaces the existing value when present; otherwise injects the
    attribute just before the closing `/>`. The four attrs this dialog
    manages (icon_size, icon_spacing, max_columns, filter) are all
    documented BuffListView attributes — AoC's parser handles them
    whether or not the source file lists them.
    """
    pattern = re.compile(rf'(\b{re.escape(attr_name)}\s*=\s*")[^"]*(")')
    new_text, n = pattern.subn(lambda m: m.group(1) + value + m.group(2), tag_text)
    if n:
        return new_text
    # Attribute missing — inject before the closing /> (the matching regex
    # guarantees the tag ends with />, possibly preceded by whitespace).
    m = re.search(r'(\s*/>)\s*$', tag_text)
    if not m:
        return tag_text  # defensive — shouldn't happen given the caller's regex
    return tag_text[:m.start()] + f' {attr_name}="{value}"' + m.group(1)


def _normalise_filter(raw):
    """Map a raw filter= value to one of FILTER_FRIENDLY/HOSTILE/BOTH.

    Strips whitespace around the pipe so 'friendly|hostile',
    'friendly | hostile', and 'hostile|friendly' all map to BOTH.
    Returns the raw string verbatim if it doesn't fit the three cases.
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

    Returns a dict with keys: icon_size, icon_spacing, max_columns, filter,
    enabled (False if wrapped in a KZ_OFF comment, True otherwise). Returns
    None if no <BuffListView> tag is present anywhere.
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

    `attrs` is a dict with optional keys: icon_size, icon_spacing,
    max_columns, filter. None or missing keys are left untouched. If the
    tag is currently wrapped in <!--KZ_OFF ... KZ_OFF-->, we unwrap first
    so attribute edits land on the bare tag, then re-wrap if enabled is
    False. Returns the new file text, or None if the file has no
    <BuffListView> tag at all (caller must surface an error and skip).
    """
    # Unwrap any existing KZ_OFF span so we can edit the bare tag.
    m_off = _KZ_OFF_RE.search(xml_text)
    if m_off:
        xml_text = xml_text[:m_off.start()] + m_off.group(1) + xml_text[m_off.end():]

    m = _BUFFLISTVIEW_TAG_RE.search(xml_text)
    if not m:
        return None

    new_tag = m.group(0)
    for attr_name in ('icon_size', 'icon_spacing', 'max_columns', 'filter'):
        value = attrs.get(attr_name)
        if value is None:
            continue
        # Skip if the on-disk value already matches — keeps the file
        # byte-identical when the user only touched a different field
        # (the file's stated promise: surgical regex edits).
        if _read_attr(new_tag, attr_name) == value:
            continue
        new_tag = _replace_attr(new_tag, attr_name, value)

    if not enabled:
        new_tag = f'<!--KZ_OFF {new_tag} KZ_OFF-->'

    return xml_text[:m.start()] + new_tag + xml_text[m.end():]


def _backup_once(customized_path):
    """Copy customized_path → customized_path.kzgrids.bak iff the .bak
    doesn't already exist. Idempotent. Lets the user recover their
    pre-Kaz-Grids state by hand.
    """
    bak = customized_path.with_name(customized_path.name + BACKUP_SUFFIX)
    if customized_path.is_file() and not bak.exists():
        try:
            shutil.copy2(customized_path, bak)
        except OSError as e:
            logger.warning("Could not write backup %s: %s", bak, e)


# ============================================================================
# POINT/INT PARSING (defensive — Spinbox values can be empty mid-typing)
# ============================================================================
def _maybe_int(value):
    """Parse value to int, or None if blank/unparseable. Used so blanks
    don't materialise as zero — they stay out of the write attrs and the
    source's existing value (or absence) is preserved.
    """
    try:
        s = str(value).strip()
        return int(s) if s else None
    except (ValueError, TypeError):
        return None


def _parse_point(raw):
    """Pull (x, y) from 'Point(31,31)'. Returns None on parse failure."""
    if raw is None:
        return None
    m = re.match(r'\s*Point\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)\s*$', raw)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _format_point(x, y):
    return f'Point({x},{y})'


def _bind_label_wraplength(label, container):
    """Reflow label.wraplength to track container width on resize, so an
    inline message in a resizable dialog doesn't wrap shorter than it has
    to. Min 120 keeps the label readable at the dialog's minsize."""
    pad = PAD_INNER * 2
    container.bind(
        '<Configure>',
        lambda e: label.configure(wraplength=max(120, e.width - pad)),
        add='+',
    )


# ============================================================================
# SECTION (one per file)
# ============================================================================
class _Section:
    """One row in the dialog: header + form for a single XML file."""

    STATE_OK = 'ok'                # form rendered, editable
    STATE_MISSING = 'missing'       # neither Default nor Customized exists
    STATE_UNSUPPORTED = 'unsupported'  # source file has no <BuffListView>

    def __init__(self, dialog, label, relpath, on_change):
        self.dialog = dialog
        self.label = label
        self.relpath = relpath
        self.on_change = on_change

        self.customized_path = None
        self.source_path = None
        self.source_origin = None     # 'Default' / 'Customized' / None
        self.state = self.STATE_OK

        # Tk variables (only meaningful when state == STATE_OK).
        # Square icons + uniform spacing — written to XML as Point(N,N).
        self.icon_size_var = tk.StringVar()
        self.spacing_var = tk.StringVar()
        self.cols_var = tk.StringVar()
        self.filter_var = tk.StringVar()
        self.enabled_var = tk.BooleanVar(value=True)

        # Snapshot of (icon_size, icon_spacing, max_columns, filter, enabled)
        # taken at load time. Drives dirty().
        self._baseline = None

        # Widgets we mutate in disabled-toggle styling.
        self._row_labels = []

        # Header widgets
        self._badge_var = tk.StringVar(value='')
        self._frame = None  # Built in build()
        self._toggle = None  # First focusable widget when state == STATE_OK
        self._filter_hint = None  # Inline note next to the filter radios

    # ------------------------------------------------------------------
    # Loading & state derivation
    # ------------------------------------------------------------------
    def load(self, game_path):
        """Read attrs from disk and populate vars.  Sets state accordingly."""
        _, self.customized_path, self.source_path = _resolve_paths(
            game_path, self.relpath
        )

        if self.source_path is None:
            self.state = self.STATE_MISSING
            self.source_origin = None
            self._refresh_badge()
            return

        self.source_origin = (
            BADGE_CUSTOMIZED if self.source_path == self.customized_path else BADGE_DEFAULT
        )

        try:
            xml_text = self.source_path.read_text(encoding='utf-8')
        except OSError as e:
            logger.warning("Could not read %s: %s", self.source_path, e)
            self.state = self.STATE_MISSING
            self._refresh_badge()
            return

        attrs = _read_bufflistview(xml_text)
        if attrs is None:
            self.state = self.STATE_UNSUPPORTED
            self._refresh_badge()
            return

        self.state = self.STATE_OK
        self._populate_vars(attrs)
        self._baseline = self._snapshot()
        self._refresh_badge()

    def _populate_vars(self, attrs):
        # Mirror the source XML byte-for-byte. If an attr is absent or in
        # a form we don't recognise, the field stays blank — Apply only
        # writes what the user explicitly sets, so we never overwrite a
        # value we didn't show. Custom UIs may have non-square icons or
        # non-uniform spacing; we collapse to the first coord (X / W) and
        # the user's next edit squares it.
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
        """Build the section as a CollapsibleSection inside parent. Returns
        the section widget so the caller can pack it."""
        cs = CollapsibleSection(parent, title=self.label, initially_open=initial_open)
        self._frame = cs

        # Badge on the right edge of the always-visible header (status stays
        # legible whether the section is expanded or collapsed).
        ttk.Label(cs.header_frame, textvariable=self._badge_var, font=FONT_SMALL,
                  foreground=THEME_COLORS['muted']).pack(side='right')

        content = cs.content

        # Relpath sits at the top of the content (only visible when expanded).
        ttk.Label(content, text=self.relpath, font=FONT_SMALL,
                  foreground=THEME_COLORS['muted']).pack(anchor='w', pady=(0, PAD_LF))

        if self.state == self.STATE_MISSING:
            msg = ttk.Label(
                content,
                text="This file isn't in your game folder. Verify your install.",
                font=FONT_BODY, foreground=THEME_COLORS['muted'],
                wraplength=460, justify='left',
            )
            msg.pack(anchor='w')
            _bind_label_wraplength(msg, content)
            return cs

        if self.state == self.STATE_UNSUPPORTED:
            msg = ttk.Label(
                content,
                text=("This file's buff list element isn't in the standard format. "
                      "Edit it manually or contact your UI mod author."),
                font=FONT_BODY, foreground=THEME_COLORS['muted'],
                wraplength=460, justify='left',
            )
            msg.pack(anchor='w')
            _bind_label_wraplength(msg, content)
            return cs

        # Show buff list (toggle)
        toggle_row = ttk.Frame(content)
        toggle_row.pack(fill='x', pady=(0, PAD_LF))
        toggle = ttk.Checkbutton(toggle_row, text="Show buff list",
                                 variable=self.enabled_var,
                                 command=self._on_change)
        toggle.pack(side='left')
        self._toggle = toggle

        # Form rows pack directly into content; CollapsibleSection's
        # PAD_COLLAPSE_INDENT supplies the left indent.
        self._add_int_row(content, "Icon size:", self.icon_size_var,
                          ICON_SIZE_MIN, ICON_SIZE_MAX, unit="px")
        self._add_int_row(content, "Icon spacing:", self.spacing_var,
                          SPACING_MIN, SPACING_MAX, unit="px")
        self._add_int_row(content, "Max columns:", self.cols_var,
                          COLS_MIN, COLS_MAX)
        self._add_filter_row(content)

        # Apply muted styling now if toggle starts off, and seed the
        # filter hint so it reflects the source's blank-or-set state.
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
            unit_lbl = ttk.Label(row, text=unit, font=FONT_SMALL,
                                 foreground=THEME_COLORS['muted'])
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
        self._filter_hint = ttk.Label(row, text='', font=FONT_SMALL,
                                      foreground=THEME_COLORS['muted'])
        self._filter_hint.pack(side='left')

    # ------------------------------------------------------------------
    # Change handling
    # ------------------------------------------------------------------
    def _on_change(self):
        self._apply_disabled_style()
        self._refresh_filter_hint()
        self._refresh_badge()
        self.on_change()

    def _refresh_filter_hint(self):
        if self._filter_hint is None:
            return
        text = "(no filter set in source)" if self.filter_var.get() == '' else ''
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
                pass

    def _refresh_badge(self):
        if self.state == self.STATE_MISSING:
            self._badge_var.set(f"[{BADGE_MISSING}]")
            return
        if self.state == self.STATE_UNSUPPORTED:
            self._badge_var.set(f"[{BADGE_UNSUPPORTED}]")
            return
        suffix = " · Modified" if self.dirty() else ""
        self._badge_var.set(f"[{self.source_origin}{suffix}]")

    def focus_first(self):
        """Move focus to this section's first focusable widget. Returns
        True if focus was set, False if the section has nothing to focus
        (missing/unsupported file or not yet built). Expands the section
        if it's currently collapsed so focus lands on a visible widget."""
        if self.state != self.STATE_OK or self._toggle is None:
            return False
        if self._frame is not None and not self._frame.is_open:
            self._frame.expand()
        self._toggle.focus_set()
        return True

    @property
    def is_open(self):
        """Current expand state, or None if the section isn't built yet."""
        if isinstance(self._frame, CollapsibleSection):
            return self._frame.is_open
        return None

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------
    def write_to_disk(self):
        """Apply the current form values to the Customized file."""
        if self.state != self.STATE_OK or self.source_path is None or self.customized_path is None:
            return
        # Read the source (Customized if present, else Default) so we
        # preserve every byte outside the BuffListView tag.
        source_text = self.source_path.read_text(encoding='utf-8')

        # Only fields with a valid value land in attrs. Blanks and
        # unparseable entries stay out so the source's existing attribute
        # — or its absence — is preserved. No assumed stock defaults.
        # Numeric fields are clamped to their declared bounds so a typed
        # value past the spinbox arrows (e.g. 999) can't reach the file.
        attrs = {}
        n = _maybe_int(self.icon_size_var.get())
        if n is not None:
            n = max(ICON_SIZE_MIN, min(ICON_SIZE_MAX, n))
            attrs['icon_size'] = _format_point(n, n)
        n = _maybe_int(self.spacing_var.get())
        if n is not None:
            n = max(SPACING_MIN, min(SPACING_MAX, n))
            attrs['icon_spacing'] = _format_point(n, n)
        n = _maybe_int(self.cols_var.get())
        if n is not None:
            n = max(COLS_MIN, min(COLS_MAX, n))
            attrs['max_columns'] = str(n)
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
        # The file just got written to Customized, so source_path flips.
        self.source_path = self.customized_path
        self.source_origin = BADGE_CUSTOMIZED
        try:
            xml_text = self.source_path.read_text(encoding='utf-8')
        except OSError:
            return
        attrs = _read_bufflistview(xml_text)
        if attrs is not None:
            self._populate_vars(attrs)
            self._baseline = self._snapshot()
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

        # Land focus on the first editable section so power users can drive
        # the dialog from the keyboard immediately. after_idle so the toggle
        # widget is fully realized before grabbing focus.
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

        # Always-visible subtitle: names what this dialog edits and what it
        # doesn't. Disambiguates from Kaz Grids' own grid editor (Grids
        # panel), which is a frequent confusion point.
        subtitle = ttk.Frame(self)
        subtitle.pack(fill='x')
        ttk.Label(
            subtitle,
            text="Edit Age of Conan's built-in buff bars. Kaz Grids isn't affected.",
            font=FONT_SMALL, foreground=THEME_COLORS['muted'],
        ).pack(anchor='w', padx=PAD_INNER, pady=(PAD_LF, 0))

        # Conditional banner: shown only when a custom UI is detected.
        if _detect_custom_ui(self.app.game_path):
            banner = tk.Frame(self, bg=TK_COLORS['status_bg'])
            banner.pack(fill='x')
            tk.Label(
                banner, bg=TK_COLORS['status_bg'],
                text="Custom UI detected. Edits stay in your skin.",
                fg=THEME_COLORS['body'], font=FONT_BODY,
            ).pack(anchor='w', padx=PAD_INNER, pady=PAD_LF)

        # Bottom button row packs FIRST so it reserves its height before
        # body claims expansion space — buttons stay visible regardless of
        # how the user resizes the dialog. Apply packs to the right edge,
        # Cancel sits to its left (left-to-right reading order: Cancel | Apply).
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

        # Scrollable body — four sections stack to ~780px; the dialog
        # opens at 607px and the user can resize taller or scroll. Outer
        # padded frame keeps PAD_INNER around the canvas + scrollbar.
        body_pad = ttk.Frame(self, padding=PAD_INNER)
        body_pad.pack(fill='both', expand=True)
        scroll_outer, body, _ = create_scrollable_frame(body_pad)
        scroll_outer.pack(fill='both', expand=True)

        # Per-section open/closed state from settings. Missing keys (new
        # sections added since last save, or first-ever launch) fall through
        # to DEFAULT_SECTION_OPEN — Player open, rest collapsed.
        saved_states = get_setting(SETTINGS_KEY_SECTION_OPEN) or {}

        # Load each section before building so build() sees the resolved
        # state (STATE_OK / STATE_MISSING / STATE_UNSUPPORTED) and renders
        # the form vs the inline message accordingly.
        for i, (label, relpath) in enumerate(BUFF_FILES):
            section = _Section(self, label, relpath, on_change=self._refresh_apply_state)
            if self.app.game_path:
                section.load(self.app.game_path)
            self.sections.append(section)
            initial_open = saved_states.get(label, DEFAULT_SECTION_OPEN.get(label, False))
            sf = section.build(body, initial_open=initial_open)
            # Tight gap between collapsible sections — they carry their own
            # visual chunking (header bar + indented content), so the old
            # PAD_SECTION_GAP would feel cavernous between collapsed rows.
            sf.pack(fill='x', pady=(0 if i == 0 else PAD_LF, 0))

    # ------------------------------------------------------------------
    # Apply / Cancel
    # ------------------------------------------------------------------
    def _refresh_apply_state(self):
        any_dirty = any(s.dirty() for s in self.sections)
        if self._apply_btn is not None:
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
            # Toast for parity with the success path; longer duration so the
            # user can read it. The OS-level reason (permission denied, disk
            # full) lives in the log; the toast names what failed and what to
            # check, in that order.
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
        states = {s.label: s.is_open for s in self.sections if s.is_open is not None}
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
