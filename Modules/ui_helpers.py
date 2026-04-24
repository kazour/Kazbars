"""
Kaz Grids — Design tokens.

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
    'purple':     '#9b59b6',   # Grids nav accent
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

# Button width standards
BTN_SMALL = 7             # Add, Edit, Delete, Clear, Copy
BTN_MEDIUM = 12           # Export, Import, Reset, Browse
BTN_LARGE = 20            # Build & Install, Generate & Install

# Scanline overlay alpha (0-255). Used for CRT decorative scanline overlays.
SCANLINE_ALPHA = 12

# Module accent colors (grids-only)
MODULE_COLORS = {
    'grids': '#3498db',   # Blue
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



