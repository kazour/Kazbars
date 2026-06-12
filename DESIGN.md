---
name: KazBars
description: Buff/debuff grid overlay editor for Age of Conan, with a CRT-tinted dark UI.
colors:
  text-bright: "#FFFFFF"
  text-body: "#C0C7CE"
  text-muted: "#B0B0B0"
  text-dim: "#888888"
  text-disabled: "#666666"
  surface-base: "#222222"
  surface-sub: "#1a1a1a"
  surface-outer: "#0a0a0a"
  surface-input: "#2f2f2f"
  surface-hover: "#2a2a2a"
  surface-active: "#333333"
  selection-bg: "#555555"
  border: "#444444"
  border-menu: "#3a3a3a"
  separator: "#333333"
  action-cyan: "#3498db"
  signal-success: "#00bc8c"
  signal-warning: "#f39c12"
  signal-danger: "#e74c3c"
  database-nav-purple: "#9b59b6"
  player-cyan: "#3498db"
  target-orange: "#e67e22"
  cast-timer-rose: "#CF6F93"
  phosphor-green: "#4A7A5A"
  phosphor-amber: "#8A7040"
  phosphor-dim: "#1A2B22"
  crt-glow: "#224433"
  phosphor-green-bright: "#33FF66"
  phosphor-amber-bright: "#FFAA33"
  pixel-border: "#2a2a2a"
  tracker-idle: "#CCCCCC"
  tracker-warning: "#FFDD66"
  tracker-alert: "#FF7744"
  tracker-active: "#99DD66"
  tracker-player: "#6ea0ff"
  overlay-transparent-key: "#010101"
typography:
  display:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "normal"
  display-glow:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "26px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "normal"
  headline:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "14px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "normal"
  title:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "13px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "normal"
  symbol:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "normal"
  body-lg:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "10px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
  body:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "9px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
  section:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "10px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "normal"
  label:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "9px"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "normal"
  small:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "8px"
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: "normal"
  small-bold:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "8px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "normal"
  tiny:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "7px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "normal"
rounded:
  sharp: "0px"
  hairline: "1px"
  soft: "2px"
  default: "3px"
spacing:
  micro: "1px"
  button-gap: "2px"
  tiny: "3px"
  xs: "4px"
  sm: "5px"
  md: "6px"
  lf: "8px"
  tab: "10px"
  inner: "12px"
  collapse-indent: "14px"
  list-item: "15px"
  radio-indent: "18px"
  section-gap: "20px"
components:
  button-primary:
    backgroundColor: "{colors.signal-success}"
    textColor: "{colors.text-bright}"
    typography: "{typography.section}"
    rounded: "{rounded.default}"
    padding: "6px 16px"
    width: "20ch"
  button-default:
    backgroundColor: "{colors.surface-input}"
    textColor: "{colors.text-body}"
    typography: "{typography.body}"
    rounded: "{rounded.default}"
    padding: "4px 10px"
    width: "12ch"
  button-small:
    backgroundColor: "{colors.surface-input}"
    textColor: "{colors.text-body}"
    typography: "{typography.body}"
    rounded: "{rounded.default}"
    padding: "3px 6px"
    width: "7ch"
  input:
    backgroundColor: "{colors.surface-input}"
    textColor: "{colors.text-bright}"
    typography: "{typography.body}"
    rounded: "{rounded.soft}"
    padding: "4px 6px"
  card-labelframe:
    backgroundColor: "{colors.surface-base}"
    textColor: "{colors.text-body}"
    typography: "{typography.section}"
    rounded: "{rounded.soft}"
    padding: "12px"
  menu-bar:
    backgroundColor: "{colors.surface-sub}"
    textColor: "{colors.text-body}"
    typography: "{typography.body}"
    height: "26px"
    padding: "0 4px"
  menu-bar-hover:
    backgroundColor: "{colors.surface-input}"
    textColor: "{colors.text-body}"
  menu-bar-active:
    backgroundColor: "{colors.surface-input}"
    textColor: "{colors.text-bright}"
    accentLine: "{colors.phosphor-green}"
    accentLineHeight: "2px"
  dialog-header:
    backgroundColor: "{colors.surface-sub}"
    textColor: "{colors.action-cyan}"
    typography: "{typography.title}"
    padding: "8px 12px"
  status-bar:
    backgroundColor: "{colors.surface-sub}"
    textColor: "{colors.text-body}"
    typography: "{typography.small}"
    padding: "4px 8px"
  toast:
    backgroundColor: "{colors.surface-input}"
    textColor: "{colors.text-bright}"
    typography: "{typography.body}"
    rounded: "{rounded.soft}"
    padding: "6px 10px"
---

# Design System: KazBars

## 1. Overview

**Creative North Star: "The Phosphor Bench"**

KazBars is a workbench for buff data. Functional density carries most of the surface (Aseprite/Reaper energy: tight rows, small text, dense forms, no decorative whitespace), and the CRT/phosphor language is reserved for the moments where the tool talks back: the Build & Install status icon, the CRT-styled dialog header, the Ethram Fal seed timer overlay, and the 2px phosphor underline beneath the active top-menu cascade. Most of the app is a quiet dark workbench. A handful of surfaces glow.

The system is built on ttkbootstrap-darkly as a base palette and inherits its tonal grammar (`#222` working surface, `#1a1a1a` chrome, `#2f2f2f` inputs). On top of that base, a deliberate retro layer (`phosphor_green`, `phosphor_amber`, `crt_glow`, scanline overlays) carries the brand. That layer is decoration-only by contract: phosphor colors are off-limits for body text and interactive states because they fail WCAG contrast on the dark bg, and `_RETRO_COLORS` is named with a leading underscore to mark it private.

This system explicitly rejects the four directions called out in PRODUCT.md: generic SaaS dashboard polish, Twitch/Discord neon, Windows 11 Settings acrylic, and WeakAuras in-game addon chrome. None of those are starting points; all of them are anti-patterns.

**Key Characteristics:**
- Dark-by-design (ttkbootstrap-darkly base, never light theme).
- Tight density: 8-10px workhorse type, sub-10px paddings throughout, sharp corners (0-3px radius).
- Single typeface (Segoe UI). No serif, no display family, no monospace.
- Flat surfaces with tonal layering for depth. No box-shadows.
- Phosphor glow is a punctuation mark, not a coat of paint.
- Color is semantic first (success / warning / danger / accent). Decorative phosphor lives in a separate, private namespace.

## 2. Colors

A bootstrap-darkly grayscale base, semantic state colors borrowed from the same palette, and a private CRT/phosphor layer used only on canvas-drawn signal moments. Workhorse colors carry functional names; phosphor colors keep their material-language names because that *is* their character.

### Primary

The system has no single brand color carrying the surface. The closest thing to a primary action is **Signal Success**: every surface's single primary button carries it, with Build & Install (the moment of payoff) as the flagship.

- **Action Cyan** (`#3498db`): links, info-value text, the Player grid type, the Grids module accent. The "click here" color across the app.
- **Signal Success** (`#00bc8c`): the surface-primary button style (Build & Install, a dialog's Apply or Export, first-launch Load Default) and build-success status text. At most one per surface.

### Secondary

State colors. Semantic, never decorative.

- **Signal Warning** (`#f39c12`): build warnings, missing-buff notices, attention-needed states.
- **Signal Danger** (`#e74c3c`): errors, destructive confirmations, build failures.
- **Database Nav Purple** (`#9b59b6`): the Database top-nav tab accent. One of the only places purple appears; reserved for that one role.
- **Target Orange** (`#e67e22`): the Target grid type, paired with Player Cyan to differentiate player-vs-target grids at a glance.
- **Cast Timer Rose** (`#CF6F93`): identity accent for the frozen Cast Timer strip pinned above the grid list, carried by its 1px card border (greys to the neutral border via `set_dimmed` when the master enable is off). A muted dusty rose, the hue furthest from the Player/Target/Database palette, so the strip reads as its own thing among the grid cards. The **Player**/**Target** tags next to the title light in `player-cyan`/`target-orange` when the master enable is on (both sides run together) and grey when off; the `overlay` tag after them stays muted (a category label, not identity).

### Tertiary (live tracker semantics)

Used inside the Live Tracker panel only. Higher saturation than the editor palette because the tracker is read in 200ms during combat and must compete with the game underneath.

- **Tracker Idle** (`#CCCCCC`): default / waiting state.
- **Tracker Warning** (`#FFDD66`): attention needed, soon.
- **Tracker Alert** (`#FF7744`): urgent, act now.
- **Tracker Active** (`#99DD66`): action in progress, on track.
- **Tracker Player** (`#6ea0ff`): player names in the cycle list.

### Neutral

The tonal grammar that does the actual work. Memorize these.

- **Text Bright** (`#FFFFFF`): section headings, primary text on dark surfaces. AAA on every neutral here.
- **Text Body** (`#C0C7CE`): body text, descriptions. ~7.2:1 on `#222` (WCAG AAA). The default text color of the app.
- **Text Muted** (`#B0B0B0`): hints, placeholders, accelerator labels in menus. ~6.0:1 on `#222`.
- **Text Dim** (`#888888`): unassigned slot labels, disabled labels on dark bg. Use sparingly; below AAA.
- **Text Disabled** (`#666666`): genuinely-disabled menu items only.
- **Surface Base** (`#222222`): the working surface. The default app bg, ttkbootstrap-darkly canon.
- **Surface Sub** (`#1a1a1a`): chrome layer. Menu bar, status bar, dialog header backgrounds. Always darker than the content it frames.
- **Surface Outer** (`#0a0a0a`): used only on the Ethram Fal overlay outer chrome, distinct from the Windows transparency key.
- **Surface Input** (`#2f2f2f`): input backgrounds, default button bg, toast bg. Lighter than Surface Base; reads as "interactive".
- **Surface Hover** (`#2a2a2a`): menu hover state. One step up from Sub.
- **Surface Active** (`#333333`): menu active / open state, separator color (yes, the same value plays two roles).
- **Selection Bg** (`#555555`): list / treeview selection background.
- **Border** (`#444444`): subtle borders on inputs, frames, tables.
- **Border Menu** (`#3a3a3a`): the dropdown overlay border on the custom menu bar.
- **Separator** (`#333333`): thin separator lines.

### Phosphor (private, decorative-only)

These live in `_RETRO_COLORS` with a leading underscore. **Off-limits for text and interactive states.** They fail WCAG contrast on `#222` and exist solely for canvas-drawn glow layers, CRT tinting, and 1-2px accent details.

- **Phosphor Green** (`#4A7A5A`): desaturated CRT green, tint and accent.
- **Phosphor Amber** (`#8A7040`): warm amber hover tint, secondary CRT accent.
- **Phosphor Dim** (`#1A2B22`): near-black green CRT background tint.
- **CRT Glow** (`#224433`): subtle glow behind canvas-drawn header text.
- **Phosphor Green Bright** (`#33FF66`): full phosphor. **1-2px accent lines only.**
- **Phosphor Amber Bright** (`#FFAA33`): full amber. **Tiny highlight details only.**
- **Pixel Border** (`#2a2a2a`): pixel-art cell borders on the grid preview.

### Named Rules

**The Two-Layer Rule.** The palette has two layers and they do not mix. Layer 1 is the workhorse semantic palette (text, surfaces, signals, module accents). Layer 2 is the phosphor decoration layer. Layer 1 may go anywhere. Layer 2 may *only* be used on canvas-drawn signal moments (build status, dialog header glow, the Ethram Fal seed timer, the active-cascade underline in the top menu bar). Never use a phosphor color for a tk widget background, a label foreground, or an interactive state. The leading underscore on `_RETRO_COLORS` enforces this in code; the rule enforces it in design.

**The 7.2 Rule.** Body text on the dark surface (`Text Body` on `Surface Base`) measures ~7.2:1, comfortably WCAG AAA. New readable text targets the same bar. If a color cannot hit AAA on `#222`, it is decoration, not text.

**The One-Purple Rule.** Purple has exactly one *role*: the Database top-nav tab accent. Incidental palette uses (e.g. a 2-color cycle on the loading screen) are permitted; assigning purple a second documented role anywhere is forbidden without explicit permission. Purple's value is its scarcity.

## 3. Typography

**Display Font:** Segoe UI (sans-serif fallback)
**Body Font:** Segoe UI (sans-serif fallback)
**Label/Mono Font:** Segoe UI (no separate mono family)

**Character:** Single typeface, single voice. Segoe UI is the system default on Windows and reads as native, not designed. The system runs the entire scale (28px down to 7px) on weight contrast alone, never on family contrast. This is deliberate: the app is a tool, not a publication.

### Hierarchy

- **Display** (700 weight, 28px, line-height 1): build status icon glow layer. The largest type in the app. Used in exactly one place.
- **Display Glow** (700 weight, 26px, line-height 1): build status icon main layer, drawn on top of Display. The two together produce the canvas-rendered phosphor glow.
- **Headline** (700 weight, 14px): section headings, the largest readable text in normal flows.
- **Title** (700 weight, 13px): CRT-styled dialog headers. The brand-defining heading style.
- **Symbol** (400 weight, 13px): glyph labels (×, +, etc.) where size needs to match Title but weight should not compete.
- **Section** (700 weight, 10px): LabelFrame headers, primary action button labels. The structural type of the editor.
- **Body Large** (400 weight, 10px): comfortable body text in dialogs.
- **Body** (400 weight, 9px): the workhorse. Default text, form labels, menu items. Most type in the app is this size.
- **Label** (400 weight, 9px): form field labels (alias of Body, kept distinct for semantic intent).
- **Small Bold** (700 weight, 8px): emphasized small text in tight rows.
- **Small** (400 weight, 8px): hints, status bar text, secondary metadata.
- **Tiny** (700 weight, 7px): slot count badges, the smallest readable text. Bold so it survives at this size.

### Named Rules

**The Single-Family Rule.** Segoe UI everywhere. No serif for editorial moments. No monospaced for IDs or file paths. No display face. The discipline is the design.

**The 9px Floor.** Default text is 9px. Anything smaller is a deliberate density choice (slot badges, hints in tight rows) and must be bold to survive. Never set 7-8px regular weight on a real label; it reads as broken, not minimal.

**The Weight-Not-Hue Rule.** Hierarchy is established by weight (400 vs 700) and size, never by tinting body text in another color. Dimming text to indicate disabled is a state change (use Text Dim or Text Disabled), not a hierarchy choice.

## 4. Elevation

The system is **flat with tonal layering**. There are no `box-shadow` equivalents in the editor; depth is conveyed by background steps that walk down the lightness scale. Surface Sub (`#1a1a1a`) sits behind chrome (menu bar, status bar, dialog headers); Surface Base (`#222`) is the working canvas; Surface Input (`#2f2f2f`) is one step up because it reads as interactive; Surface Hover (`#2a2a2a`) is between Sub and Base, used only on the menu bar to nudge the eye without lifting the surface.

CRT glow is **not** elevation. It is a brand effect drawn on canvas (Tk Canvas widgets) by stacking multiple text layers in phosphor colors with progressively narrower size. It exists at exactly two surfaces: the build status icon and the CRT dialog header. Treating it as a generic "glow on hover" pattern would dilute it.

There are no shadows, no acrylic blurs, no glass panels, no soft drop shadows under cards.

### Named Rules

**The Tonal-Layer Rule.** Depth comes from background steps, never from drop shadows. If you need to separate a surface from its parent, change the bg by one step on the neutral scale (Sub → Base → Input). If that's not enough, add a 1px Border or a Separator. Never add a shadow.

**The Glow-As-Punctuation Rule.** CRT phosphor glow appears at exactly two surfaces today (build status icon, CRT dialog header). Adding a third surface requires the same justification as adding a new typeface: the moment must genuinely be brand-defining, and the addition must be canvas-drawn so it does not leak into ttk theme overrides.

## 5. Components

ttkbootstrap-darkly handles the heavy lifting (button, entry, frame, treeview, combobox, scrollbar). The custom layer adds: `Card.TLabelframe` (the only custom ttk style), `CustomMenuBar` (Canvas-based dark menu bar), `ToastManager`, `DragReorderManager`, `CollapsibleSection`, `create_dialog_header` (the CRT-styled header builder), and the canvas-drawn build status / Ethram Fal overlay. All component descriptions below describe tkinter widgets; pixel values translate directly from the spacing scale, but there is no HTML/CSS counterpart.

### Buttons

- **Shape:** Sharp by default. Inherits ttkbootstrap-darkly's near-zero radius (0-3px). Never round buttons.
- **Primary (success):** Signal Success bg with bright text. Carries the single primary action of a surface: Build & Install / Generate & Install at `BTN_LARGE` (20 chars), and the one affirmative action of a dialog or panel (Apply, Export, Load Default, Start Monitoring) at dialog widths. At most one success button per surface. When it has a sibling action, the sibling takes the cyan outline style (Export ▸ success / Import ▸ outline), never a second success.
- **Default:** Surface Input bg with body-color text, ttkbootstrap-darkly default. Width `BTN_MEDIUM` (12 chars) for Export/Import/Reset/Browse, `BTN_SMALL` (7 chars) for Add/Edit/Delete/Clear/Copy. Width tokens are for rows of short labels only — tkinter clips silently, so a label longer than its token is a bug. Sentence-length labels drop the width and size to their text.
- **Outline (secondary accent):** transparent bg, Action Cyan border + label (`info-outline`). The secondary half of a success pair (Export ▸ success / Import ▸ outline) and the bottom-bar tool launchers. Never bare `outline`: darkly's primary (`#375a7f`) measures 2.2:1 on `#222`, failing even the large-text bar.
- **Hover / Focus:** ttkbootstrap-darkly's built-in hover (slight lightness shift). Do not add custom glow, transform, or scale. The button does not move.

### Inputs / Fields

- **Style:** Surface Input bg (`#2f2f2f`), Text Bright fg, 1px Border. Sharp corners (`rounded.soft` = 2px maximum). Inherits ttkbootstrap-darkly's entry / spinbox / combobox styling.
- **Focus:** ttkbootstrap-darkly's default border-color shift. No glow ring.
- **Selection:** Selection Bg (`#555555`), Text Bright fg.
- **Disabled:** Text Disabled fg, no bg change. Reads as inert.

### Menu Bar (custom)

- **Surface:** Surface Sub bg (`#1a1a1a`), Text Body fg, 26px height. Drawn on a `tk.Canvas`, not a native `tk.Menu` (the native one cannot be themed dark on Windows).
- **Hover:** Surface Input bg (`#2f2f2f`), no fg change. Reuses the same "this is interactive" tone as form inputs and buttons.
- **Active (open dropdown):** Surface Input bg + Text Bright fg + a 2px Phosphor Green (`#4A7A5A`) underline beneath the cascade label, 6px inset on each side so it tracks the label, not the cell. The underline is the brand-defining detail; the bg + white text is the secondary cue.
- **Disabled item:** Text Disabled fg.
- **Accelerator label:** Text Muted fg, right-aligned in the dropdown row.
- **Dropdown:** `place()`-positioned Frame overlay (no Toplevel, so no Windows white-flash), 1px Border Menu (`#3a3a3a`) painted via the dropdown frame's own `highlightthickness` (not via a padded inner wrapper — see ttkbootstrap caveat below), 220px minimum width.
- **ttkbootstrap caveat (load-bearing):** under `ttkb.Window`, pack `pady` gaps and empty `tk.Frame` widgets render with the theme bg (`#222222`) instead of the parent frame's actual bg, leaking visible separator lines. Spacers and separators inside the dropdown must be `tk.Canvas` (which always paints) with explicit `width=1` (Canvas defaults to 378px), and the dropdown border must be drawn via `highlightthickness` rather than a padded child frame.

### Card / LabelFrame

- **Shape:** `Card.TLabelframe` style, 1px borderwidth, sharp corners.
- **Background:** Surface Base (the same as the parent). LabelFrames separate by border + label, not by bg shift.
- **Border:** ttkbootstrap-darkly default (subtle).
- **Label:** Section type (10px bold), Text Body fg.
- **Internal Padding:** `PAD_INNER` (12px) for content, `PAD_LF` (8px) for tighter dialog frames.
- **Forbidden:** nested LabelFrames. If you need a sub-grouping, use a Separator + Section header inline; do not box a box.

### Status Bar

- **Surface:** Surface Sub bg, Text Body fg, Small typography. Sits at the bottom of the root window.
- **Interactive elements:** the `Game:` label and current profile name are clickable text styled as plain inline buttons (no underline; the cursor change is the affordance).

### Toast (notifications)

- **Surface:** Surface Input bg, Text Bright fg, 2px radius, `PAD_LF` (8px) padding.
- **Behavior:** stacked bottom-right of the root window, fade in / fade out. Auto-dismiss after a short interval. Never blocks input.

### Confirmation Dialogs

- **Buttons:** the affirmative button names the action ("Delete profile", "Save anyway", "Restore settings") — never Yes/No. Built via `confirm()` (ui_widgets): `Cancel:secondary` on the left, the action button rightmost with initial focus; `danger` style when the action destroys something, `primary` otherwise. Closing the dialog declines.
- **Exception:** a genuine yes/no *question* (the Aoc.exe launcher-bypass prompt) keeps Yes/No — those labels answer the question; a verb would not.
- **Three-way:** the unsaved-changes prompt uses Save / Don't save / Cancel via `MessageDialog` directly.

### Dialog Header (signature)

- **Surface:** Surface Sub bg, Action Cyan fg, Title typography (13px bold).
- **Treatment:** drawn on a `tk.Canvas`, with phosphor glow stacked behind the text via `crt_glow` and a thin scanline overlay (`SCANLINE_ALPHA` = 12 / 255). This is the brand-defining heading; do not approximate it with a regular `ttk.Label`.
- **Padding:** `PAD_LF` (8px) vertical, `PAD_INNER` (12px) horizontal.

### Build Status Icon (signature)

- **Surface:** drawn on a `tk.Canvas`, two stacked text layers (Display 28px Glow + Display Glow 26px) in phosphor colors. The glow is the icon; there is no underlying graphic.
- **States:** building (Action Cyan), success (Signal Success), warning (Signal Warning), failure (Signal Danger).
- **Forbidden:** replacing this with a generic spinner, an emoji, or a Material icon.

### Ethram Fal Live Tracker Overlay (signature, sacred)

- **Surface:** always-on-top Toplevel with `-transparentcolor` set to `#010101` (the Windows hack that makes any pixel of that exact color invisible). Outer chrome uses Surface Outer (`#0a0a0a`) so the chrome is visible even though the surrounding "window" is transparent.
- **Type:** the tracker's own typography (defined in `live_tracker_settings.py`). Reads in 200ms while the player is in combat.
- **Color:** Tracker palette only (Idle / Warning / Alert / Active / Player). Never the editor palette.
- **Motion:** none decorative. Timer changes are state changes, not animations. The tracker does not pulse, fade, or animate decoratively.
- **The sacred rule (PRODUCT.md Principle 2):** when this panel is open, the player is in combat with seven other people depending on the timer. It must not advertise itself, surface tooltips, or compete for attention with the game underneath.

### Named Rules

**The Sharp-Edge Rule.** Maximum corner radius is 3px. Most surfaces are 0-2px. Anything softer reads as a SaaS dashboard, which PRODUCT.md prohibits.

**The Density Rule.** Padding scales bottom-up from `PAD_MICRO` (1px) to `PAD_SECTION_GAP` (20px). Default to the smaller value. If a layout feels cramped, the answer is usually a different *structure*, not more padding.

**The No-Decorative-Motion Rule.** Animations exist only as state changes (toast fade in/out, build status icon transitions, dropdown overlay open/close). No hover bloom, no spring, no decorative pulses anywhere in the editor. The Live Tracker has none at all.

## 6. Do's and Don'ts

### Do:

- **Do** use Text Body (`#C0C7CE`) on Surface Base (`#222`) as the default text on the default surface. That's the workhorse contrast that makes the rest of the system work.
- **Do** reach for `THEME_COLORS` first. Use named semantic keys (`heading`, `body`, `muted`, `accent`, `warning`, `danger`, `success`) for any new readable text or interactive state.
- **Do** inherit from ttkbootstrap-darkly defaults and add only what's missing. The `Card.TLabelframe` style is the bar for "custom enough to justify a new style".
- **Do** use a `tk.Canvas` (not `ttk.Label`) when you need phosphor glow, scanline texture, or stacked-text effects. ttk widgets cannot be themed deeply enough.
- **Do** use the spacing scale (`PAD_*` constants) as your only source of padding values. New magic numbers are a smell.
- **Do** keep buttons sharp. Default radius is 0-3px; anything softer is wrong.
- **Do** treat the Ethram Fal Live Tracker as a separate design problem with its own palette (Tracker Idle / Warning / Alert / Active / Player). It is read in 200ms during combat.

### Don't:

- **Don't** look like a "**generic SaaS dashboard (Stripe / Linear / Vercel-style enterprise dark UI)**". No glass panels, no soft gradients, no hero metric tiles, no identical icon-headline-paragraph card grids. (PRODUCT.md anti-reference 1.)
- **Don't** look like "**Twitch / Discord gamer UI**". No neon purple/blurple, no heavy bloom and glow effects, no cluttered side rails, no big avatars, no "gamery" badges. (PRODUCT.md anti-reference 2.)
- **Don't** look like "**Windows 11 Settings**". No Fluent-acrylic panels, no oversized whitespace, no soft pastels, no vague labels. (PRODUCT.md anti-reference 3.)
- **Don't** look like "**WeakAuras / in-game addon UI**". No raised bevels, no heavy chrome, no tabs-within-tabs option panels, no dialogs that look like they ship inside the game. (PRODUCT.md anti-reference 4.)
- **Don't** use a `phosphor_*` color for anything readable, interactive, or repeated. They fail WCAG contrast on `#222` and that is enforced by their leading-underscore privacy in `_RETRO_COLORS`.
- **Don't** add a `box-shadow` or its tk equivalent (a fake border-shadow drawn on Canvas). Depth comes from background steps and 1px borders. Never shadows.
- **Don't** introduce a second typeface. Segoe UI everywhere. Hierarchy is weight + size, never family.
- **Don't** add corner radius greater than 3px to anything. If a button or input feels "too sharp", the problem is the surrounding spacing or contrast, not the radius.
- **Don't** wrap the Live Tracker in tooltips, hover states, or decorative animations. It is sacred. (PRODUCT.md Principle 2.)
- **Don't** give purple a second role outside the Database top-nav tab. The One-Purple Rule. (Incidental palette pairs are fine.)
- **Don't** use color alone to convey buff classification (Buff grey / Debuff red / Misc gold). Always pair with a category label, per PRODUCT.md's color-blindness commitment.
- **Don't** write marketing-shaped microcopy ("Pro tip", "Quick win", "Did you know?"). Hobby-project candor is the voice. (PRODUCT.md Principle 5.)
