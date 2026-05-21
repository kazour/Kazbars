"""
KazBars — Design tokens.

Fonts, colors, layout/padding constants, and the one ttk style setup
call. Every other UI concern lives in a focused sibling module.
"""

from tkinter import ttk

# ============================================================================
# SHARED FONT CONSTANTS
# ============================================================================
FONT_FAMILY = 'Segoe UI'
FONT_HEADING = ('Segoe UI', 14, 'bold')
FONT_BODY_LG = ('Segoe UI', 10)
FONT_SECTION = ('Segoe UI', 10, 'bold')
FONT_BODY = ('Segoe UI', 9)
FONT_FORM_LABEL = ('Segoe UI', 9)
FONT_SMALL_BOLD = ('Segoe UI', 8, 'bold')
FONT_SMALL = ('Segoe UI', 8)
FONT_TINY = ('Segoe UI', 7, 'bold')               # Slot count badges, compact labels
FONT_SYMBOL = ('Segoe UI', 13)                    # Symbol/glyph labels (×, +, etc.)
FONT_DIALOG_HEADER = ('Segoe UI', 13, 'bold')    # CRT-styled dialog header text
FONT_STATUS_ICON = ('Segoe UI', 26, 'bold')      # Build status icon (main)
FONT_STATUS_ICON_LG = ('Segoe UI', 28, 'bold')   # Build status icon (glow layers)

# ============================================================================
# THEME COLOR CONSTANTS (darkly theme)
# ============================================================================
# Semantic colors for ttk widget foreground text
THEME_COLORS = {
    'heading':    '#FFFFFF',   # Section headings
    'body':       '#C0C7CE',   # Body/descriptions (~7.2:1 WCAG AAA on #222)
    'muted':      '#B0B0B0',   # Hints, placeholders (~6.0:1 on #222)
    'accent':     '#3498db',   # Links, emphasis
    'warning':    '#f39c12',   # Warnings
    'danger':     '#e74c3c',   # Errors
    'success':    '#00bc8c',   # Success
    'info_value': '#3498db',   # Info display values
    'purple':     '#9b59b6',   # Database nav accent
    # Buff classification tints — paired with the type label, never standalone.
    # Buff stays at 'body'; debuff/misc carry a desaturated hue at AAA contrast on #222.
    'type_debuff': '#F0A0A0',  # Muted red (~7.6:1 AAA)
    'type_misc':   '#E0C880',  # Warm gold (~9.3:1 AAA)
}

# Colors for raw tk widgets (Canvas, Listbox, Text) that ttkbootstrap can't theme
TK_COLORS = {
    'bg':         '#222222',   # darkly background
    'input_bg':   '#2f2f2f',   # darkly input background
    'input_fg':   '#ffffff',   # darkly input text
    'select_bg':  '#555555',   # darkly selection background
    'select_fg':  '#ffffff',   # darkly selection text
    'border':     '#444444',   # subtle border
    'separator':  '#333333',   # thin separator lines
    'status_bg':  '#1a1a1a',   # status bar background (darker than main bg)
    'dim_text':   '#888888',   # dimmed text on dark bg (unassigned slots, disabled labels)
}

# Overlay-specific colors (Windows transparency hack — not theme colors)
OVERLAY_COLORS = {
    'transparent': '#010101',  # Windows -transparentcolor key
    'bg_outer':    '#0a0a0a',  # Outer background (near-black, distinct from transparent key)
}


# ============================================================================
# LAYOUT CONSTANTS
# ============================================================================
PAD_TAB = 10              # Padding inside tab frames
PAD_INNER = 12            # Padding inside LabelFrames
PAD_ROW = 6               # Vertical gap between setting rows
PAD_BUTTON_GAP = 2        # Horizontal gap between buttons
PAD_TIP_BAR = (0, 4)      # Vertical padding for tip bar
PAD_COLLAPSE_INDENT = 14  # Left indent for CollapsibleSection content
PAD_RADIO_INDENT = 18     # Left indent for sub-labels beneath radio buttons
PAD_MICRO = 1             # Tight button grouping (preset buttons, action rows)
PAD_TINY = 3              # Minimal gap
PAD_XS = 4                # Asymmetric element spacing (widget-to-widget gaps)
PAD_SMALL = 5             # Compact dialog padding, widget horizontal gaps
PAD_MID = 6               # Sidebar section padding
PAD_LF = 8                # LabelFrame internal padding (dialogs)
PAD_LIST_ITEM = 15        # Section/item left indent
PAD_SECTION_GAP = 20      # Visual separation between button groups

# Canvas-drawn geometry — pixel sizes for canvases (mini-previews, step badges).
# Distinct from PAD_*: these size canvases, not widget padding.
GRID_PREVIEW_PX = 80           # Mini preview canvas inside each editor card
STEP_BADGE_PX = 20             # Numbered step badge in the tip bar
CELL_PX = 10                   # Default mini-grid cell side
CELL_PX_LARGE = 20             # Mini-grid cell side for 1x1 grids
CELL_GAP = 2                   # Gap between mini-grid cells
PRESET_CARD_SQUARE = 130       # 3x3 grid, 1x1 slot, and Custom preset
PRESET_CARD_BAR_LONG = 200     # Long axis for bar-shaped preset previews
PRESET_CARD_BAR_SHORT = 100    # Short axis for bar-shaped preset previews
PRESET_LABEL_AREA = 28         # Reserved label area at bottom of preset cards

# Button width standards (button text in chars)
BTN_SMALL = 7             # Add, Edit, Delete, Clear, Copy
BTN_DIALOG = 10           # Cancel + verb pair in dialog footers
BTN_MEDIUM = 12           # Export, Import, Reset, Browse
BTN_LARGE = 20            # Build & Install, Generate & Install

# Form input widths (input text in chars). Reserved for inputs reused 2+ places.
# One-off widths (a name field, a stack spinbox) stay as literal numbers.
INPUT_WIDTH_NUM    = 5    # Numeric spinboxes
INPUT_WIDTH_TYPE   = 10   # Compact type/state dropdowns
INPUT_WIDTH_FILTER = 18   # Filter category combobox
INPUT_WIDTH_SEARCH = 20   # Search entries
LABEL_WIDTH_FORM   = 14   # Left-column form labels (fits "Icon spacing:" + 1ch)

# Scanline overlay alpha (0-255). Used for CRT decorative scanline overlays.
SCANLINE_ALPHA = 12

# Module accent colors
MODULE_COLORS = {
    'grids':        '#3498db',   # Blue
    'live_tracker': '#3498db',   # Blue — Live Tracker editor panel header
    'deeps':        '#3498db',   # Blue — Deeps panel header (sibling to live_tracker)
}

# Retro/CRT decorative colors — DECORATIVE ONLY.
# Do not use for text or interactive states (fails WCAG contrast on #222 bg).
# Use THEME_COLORS for all readable text. These are for CRT tinting, glow layers, and accents.
_RETRO_COLORS = {
    'phosphor_green':  '#4A7A5A',   # Desaturated green — decorative accents, CRT tint
    'phosphor_amber':  '#8A7040',   # Warm amber — hover tints, secondary accents
    'phosphor_dim':    '#1A2B22',   # Near-black green — CRT background tint
    'crt_glow':        '#224433',   # Subtle glow behind header text
    'pixel_border':    '#2a2a2a',   # Pixel-art cell borders
    'green_bright':    '#33FF66',   # Full phosphor — ONLY for 1-2px accent lines
    'amber_bright':    '#FFAA33',   # Full amber — ONLY for tiny highlight details
}

# Grid type accent colors (player vs target differentiation)
GRID_TYPE_COLORS = {
    'player': '#3498db',   # Blue
    'target': '#e67e22',   # Orange
}


# ============================================================================
# CUSTOM TTK STYLES
# ============================================================================
def setup_custom_styles(root):
    """Configure custom ttk styles for a more polished look. Call once at startup."""
    style = ttk.Style()

    # Card-style LabelFrame
    style.configure('Card.TLabelframe', borderwidth=1)
    style.configure('Card.TLabelframe.Label',
                    font=FONT_SECTION,
                    foreground=THEME_COLORS['body'])

    # Treeview empty-area background — match working surface so list panels
    # don't show ttkbootstrap's lighter default below the last row.
    style.configure('Treeview', fieldbackground=TK_COLORS['bg'], background=TK_COLORS['bg'])
    # NOTE: Treeview.Heading is styled in `style_treeview_heading()` below,
    # NOT here — ttkbootstrap's create_treeview_style runs lazily on first
    # Treeview instantiation and overwrites any heading config done at boot.


def style_treeview_heading():
    """Apply visible column dividers to Treeview headings.

    Must be called *after* a Treeview widget has been constructed.
    ttkbootstrap's create_treeview_style hardcodes `relief=FLAT, padding=5`
    on `Treeview.Heading` and runs lazily when the first Treeview is created,
    so any styling done before that gets clobbered.

    Visual: a subtly lifted heading strip with hairline column dividers —
    just enough contrast to find the resize edges, not so much that it
    reads as a row of boxes.
    """
    style = ttk.Style()
    style.configure('Treeview.Heading',
                    background='#2a2a2a',
                    relief='solid',
                    borderwidth=1,
                    bordercolor='#353535',
                    padding=(10, 6))

    # Type-tinted Radiobutton labels (Add Grid wizard). Bold so the colored
    # label reads as semantic identity, not as just "decorated text".
    for name, color in (('Player', GRID_TYPE_COLORS['player']),
                        ('Target', GRID_TYPE_COLORS['target'])):
        style_name = f'{name}.TRadiobutton'
        style.configure(style_name, foreground=color, font=FONT_SECTION)
        style.map(style_name,
                  foreground=[('disabled', TK_COLORS['dim_text']),
                              ('!disabled', color)])



