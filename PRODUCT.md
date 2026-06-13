# Product

## Register

product

## Users

Age of Conan players who run a buff/debuff icon grid overlay during play. Two distinct contexts:

1. **One-time setup (the long tail).** A player downloads KazBars, opens it, loads the default profile, maybe tweaks one or two grids, hits Build & Install, and never opens the editor again. Most users live here. They are not power users of *this app*; they are power users of *the game*. The editor is a means to an end.
2. **Live raid coordination (Ethram Fal).** When a raid pulls Ethram Fal, every player has the Live Tracker open during the fight. The seven-stage Viscous Seed / Lotus Fixation / Syphon cycle is mandatory information for a smooth pull. Glances at the tracker happen between mechanics, often while the player is repositioning or casting. Stakes are real: a missed timer wipes the raid. The real-time Deeps meter shares this context — another transparent overlay glanced at mid-fight — though its numbers inform rather than decide wipe-or-survive.

A small fraction of users return to the editor when swapping characters, classes, or fight contexts. They benefit from speed, but the design priority is the first audience.

## Product Purpose

KazBars is a desktop companion for Age of Conan: one editor that compiles in-game overlays and drives live combat HUDs. The tools share infrastructure (the AS2/SWF build pipeline, the combat-log readers, the transparent always-on-top overlay layer), and each is a first-class job:

- **Grids — buff-grid overlay compiler (the flagship).** The editor lets a player describe icon grids (player vs. target, dynamic vs. static, sort/group/timer/flash rules) and one click compiles them to ActionScript 2, then deploys them to the game folder. After that the player types `/reloadui` in chat and forgets the editor exists.
- **Live Tracker — Ethram Fal cycle HUD.** An always-on-top overlay that reads the game's combat log and shows the current stage and timer of the seven-stage Viscous Seed / Lotus Fixation / Syphon cycle. Mandatory information for a smooth pull.
- **Deeps — real-time damage/heal meter.** A transparent overlay showing five live numbers (DPS out, DPS in, HPS out, HPS in, and net ΔHP in), tailed from the combat log. Glanced at mid-fight the same way the Live Tracker is.
- **Damage Numbers — floating-combat-text mod.** An Extras-menu popup that re-tunes AoC's stock `DamageInfo.swf` by baking per-setting offsets (position, color, column grouping) into the game's overlay. Opt-in and off by default; when off the stock file is left untouched.
- **Stopwatch — in-game count-up timer.** A draggable Start/Pause/Reset panel compiled into the overlay, gated on so it ships only when the player wants it.

Success is measured the way good tools are: a player who set their grids up six months ago should still have them working today, with no thought given to the editor; a raid running Ethram Fal should never wipe because someone's tracker glitched, distracted them, or rendered ambiguously.

## Brand Personality

Three words: **honest, characterful, fast.**

- **Honest.** The README admits the .exe is unsigned because a hobby project doesn't justify a code-signing certificate, and tells the user exactly how to bypass SmartScreen. UI copy carries the same plainness. No marketing varnish, no false urgency, no "Pro tips" or "Did you know?" interruptions.
- **Characterful.** KazBars is a tool for a 2008 MMO with a small dedicated player base. The CRT/phosphor accents (`phosphor_green`, `phosphor_amber`, `crt_glow`, scanline overlays, glow layers on the build status icon, the CRT-styled dialog header font) are deliberate. They are not nostalgia for its own sake; they signal that this app belongs to a specific community and a specific era of gaming, not to the SaaS template economy.
- **Fast.** The editor is a thing you do once. It should not feel like a configuration wizard. The Live Tracker is a thing you read in 200ms while a boss casts. It should feel weightless.

Voice: direct, second-person, calm. Acknowledges that the user knows the game better than the tool does. Never apologetic, never breathless. When something fails, it says what failed and what to do, in that order.

## Anti-references

The four directions that would betray the brand. The product must thread between all of them.

1. **Generic SaaS dashboard (Stripe / Linear / Vercel-style enterprise dark UI).** Glass panels, soft gradients, hero metric tiles, identical icon-headline-paragraph card grids, polish substituted for character. KazBars is not a B2B product; treating it like one drains the personality that makes the community trust it.
2. **Twitch / Discord gamer UI.** Neon purple/blurple, heavy bloom and glow effects, cluttered side rails, big avatars, "gamery" badges. The category-reflex direction. Loud where KazBars should be tight.
3. **Windows 11 Settings.** Fluent-acrylic panels, oversized whitespace, soft pastels, vague labels. Loses the tool-character entirely; reads as a system utility no one chose to install.
4. **WeakAuras / in-game addon UI.** Raised bevels, heavy chrome, tabs-within-tabs option panels, dense settings dialogs that look like they ship inside the game. KazBars is the *editor* for an in-game overlay, not the overlay itself. The editor lives on the desktop and should look like it does.

## Design Principles

Five principles, derived from the above. Each is strategic (it shapes decisions), not visual (it picks colors).

1. **Configure once, trust forever.** Most users will only ever see the editor a handful of times. The first-launch path and default profile carry the most weight. Optimize for "the user lands on a working setup with minimum input"; do not optimize for the power user editing for the hundredth time.
2. **The Live Tracker is sacred.** When that panel is open, the player is in combat with seven other people depending on the timer. It must be glanceable, undistracting, and reliable. It does not advertise itself, surface tooltips, animate decoratively, or compete for attention with the game underneath. Different rules apply here than to the editor.
3. **Earn the retro.** The CRT/phosphor language is character, not wallpaper. Apply it where it signals something meaningful: build status (the moment of payoff), dialog headers (a punctuated event), the Ethram Fal seed timer (the brand-defining surface). Do not coat every panel in scanlines; that turns character into noise.
4. **Tool-honest, not gamer-loud.** Match the functional density of a developer tool (Sublime, Reaper, Aseprite) more than the visual energy of a streaming overlay. Trust the user to read text. Avoid icon-only navigation, neon emphasis, and decorative motion. Density is fine; chrome is not.
5. **Hobby-project candor.** The README's voice (direct, plain, occasionally self-deprecating) is the product voice. Error messages name the actual problem. Empty states say what's missing. There are no "Pro tips," no "Quick wins," no marketing-shaped microcopy anywhere in the app.

## Accessibility & Inclusion

- **Contrast.** Body text already targets WCAG AAA on the dark theme (`#C0C7CE` on `#222`, ~7.2:1). Maintain that bar for any new readable text. Decorative phosphor colors (`phosphor_green`, etc.) are explicitly off-limits for text and interactive states; they live in `_RETRO_COLORS` and are commented as decoration-only.
- **Reduced motion.** The Live Tracker is the highest-stakes surface. Decorative motion (pulses, fades, scanline shimmer) must be optional or absent there. Editor animations should be brief and skippable.
- **Keyboard.** Menu-bar keyboard access has shipped — the custom top menu bar is now reachable and navigable from the keyboard. The rest of the editor is still mouse-first; full keyboard navigation through grid lists and dialog forms remains the ongoing quality target rather than a launch blocker.
- **Color blindness.** Buff/Debuff/Misc classification uses color (grey/red/golden) but is also disambiguated by category labels in the database. Keep the dual encoding when adding new state colors; never rely on hue alone.
- **Scope.** Screen-reader support and full WCAG 2.2 AA conformance are not committed goals for this hobby project. Aim for the legible, contrast-correct, plainly-labelled baseline above and document gaps honestly.
