## What's New in v3.2.0

A big update: overhead grids that float over characters' heads, grids per class, one Overlay size and Font for everything drawn in game, and two new extras — the Console and the Onslaught tracker. KazBars now keeps one profile instead of a library, so read the first section before your first build.

### Upgrading from 3.1

**One profile now, not a library.** KazBars keeps a single profile, saved as a YAML file, and autosaves it. The first time you launch over an older install, the profile you were using becomes your profile and a toast names it. Your other old profiles stay on disk untouched — Import profile in the File menu opens any of them.

**Your 3.1 files still import.** Profile and grid files are YAML now, but a profile exported from 3.1 imports as before, and restoring a 3.1 backup brings back the profile it had active.

**Your in-game sizes carry over.** Icons from 32 to 92 px and text from 8 to 28 pt convert to the new Size sliders without changing on screen, and the shared panel text size you had set becomes the Stopwatch and Inspect Target size.

### Added

**Per-class grids** — a tab for All classes and one for each of the twelve classes. A character builds its class's grids plus those on All classes, so one profile covers every character you play; a grid card's Move menu moves or copies a grid to another class.

**Overhead grids** — icons that float over characters' heads. A Friendly grid draws over your group and, with Over me ticked, you; a Hostile grid draws over your target and anyone fighting you or your group. Each has a Height to clear the game's nameplate and a Range past which it hides.

**One Overlay size and Font for everything KazBars draws in game** — the Overlay dropdown sets the scale with ten entries named for the screen, from 720p compact to 2160p large, and the Font dropdown offers GG, Arial, Verdana and nine open fonts. Every grid and panel then has its own Size slider that shows the real in-game size. A grid can also set its own Timer text and Stack text size when Auto isn't what you want.

**Console** — the buff console is its own extra now. The Buffs tab lists every buff and debuff on you and your target with its buff ID; the Casts tab shows how each of your and your target's casts ended — finished, interrupted or lost — and how long it took. Off by default

**Onslaught tracker** — for Skull Gate and Kuthchemes: a board of the bosses, skulls and minis in view with their health, the wave timer, Valkyrie Hylda's health with alerts at 50% and 25%, spawn alerts, and AoE warnings. A skull standing at a camp shows the camp's name and guards can get grouped separately. Off by default

**Share grids** — Export grid on a grid card saves that one grid to a file; Import grid in the File menu adds a file's grids to the class tab you're on, along with any custom buffs they use.

**A Font for Damage Numbers** — keep the game's own Hyborian, or pick one of nine heavy display faces such as Bangers, Bungee or Cinzel Decorative Black, built into the mod on your next Build & Install.

**Inspect Target** — Up to 112 stats in seven groups, in your own order, or the twelve Summary rows if you leave it alone. Player targets get a PvP tab with PvP combat stats, protections, bonus spell damage and their K/D record. Your settings carry over.

**Timers as digits, a bar, or off, and Applied by me** — Bar draws a line along the icon's bottom edge that shrinks as the time runs out, and overhead grids start on it. Applied by me, on a grid card, shows an effect only while you're the one who applied it.

**Three ways to start** — the first-launch dialog offers Use Defaults, Import Profile and Start Empty side by side; Import Profile makes a shared profile yours from the start. With exactly one Age of Conan install on the PC, the game folder is already filled in.

### Changed

**Grid cards draw the grid to scale** — click a dynamic grid's preview to pick its buffs, or a static grid's slot to fill it; right-click a slot to clear it. The ⚙ cog opens Grid Settings, and every change shows on the card before you apply it. The Tracked Buffs button and the Slot Assignment window are gone.

**A new starter layout** — five grids laid out for 1080p that land proportionally on any screen: Raid_Debuffs; We_Survive, an overhead band over friendly heads, yours included; Tank; Wrack_Torment_Ruin; and CC, an overhead band over hostile heads tracking 56 crowd-control debuffs. Every extra starts off. Reset profile to defaults in the File menu brings it back, after asking.

**Extras cards sit beside Build & Install** — Cast timer, Damage numbers, Inspect Target and Onslaught tracker. Click a card for its settings; flip its switch to ship it in your next build. Console and Stopwatch open from the Extras menu.

**Buff edits save themselves** — the Database tab's Save button is gone; every change is written the moment you confirm it.

**Smaller download** — about 6 MB lighter than 3.1.1, from 24 MB to 18 MB.

**KazBars is licensed under the GNU GPL v2 or later.** Nothing changes in how you use it.

### Removed

**The profile list and its commands** — New, New from template, Duplicate, Rename and Delete went with the library. Your old profiles stay on disk, and Import profile opens them.

**Per-grid font spinboxes and the shared panel text size** — one Size slider per grid and per panel replaces them; Timer text and Stack text cover per-grid text sizes.

**Two Inspect Target switches, and its console switch** — Show the PvP section and Track slotted perks are gone: PvP is a tab now, and perks always show on a player target. The console is its own extra — if you had it on, switch it on again under Console in the Extras menu.

**Start collapsed, in the Stopwatch and Inspect Target** — a panel opens unfolded the first time it loads; after that the game remembers your fold, as before.

### Fixed

**More of KazBars works from the keyboard** — Esc closes the game resolution, backup and welcome dialogs and hides the Deeps and Ethram-Fal windows without stopping them; settings dialogs confirm on Enter from anywhere; Alt+↑ / Alt+↓ reorders a grid card.

**Easier to read** — the Deeps and Ethram-Fal windows keep their last line in view, warning text uses a lighter red, and the game folder in the bottom bar shows in full.

**Your profile is safer** — Import profile asks before replacing yours; a profile held by an antivirus scan or sync tool at startup is left untouched instead of set aside; restoring a 3.1 backup lands on the profile it had active, and a new backup is never mistaken for a 3.1 one.

---

## Install

1. Download `KazBars.zip` below and extract it anywhere — Windows 10 or 11, nothing else to install (no Python). Upgrading from 3.0.1 or earlier? Extract it over your existing KazBars folder instead — your profile and settings survive, and from then on KazBars offers updates itself.
2. Run `KazBars.exe` as Administrator.
3. The first-run setup window opens. Point it at your Age of Conan folder.
4. Pick a starting point: **Use Defaults** (a ready-made layout of five grids for common raid buffs and debuffs), **Import Profile** (a profile file someone shared with you) or **Start Empty** (build your own from scratch).
5. Click `Build & Install`. Close the game and the patcher for your first build. After that, rebuild anytime and type `/reloadui` in-game.
6. Launch the game from its own executable, not the patcher — KazBars offers to create a desktop shortcut (DX10 or DX9) after your first build. Launching this way is what keeps your setup in place.

Positioning happens in-game: press Shift+Ctrl+Alt for preview mode and drag your grids and panels where you want them. The game remembers where you left them, across relogs and restarts.

Once you know the flow, make it yours: `+ Add Grid` for your own layouts, then click a grid's preview to pick what it watches (on a static grid, click a slot).

> **SmartScreen warning**: on a first install, Windows may flag the `.exe` as unrecognized. Click **More info** → **Run anyway**. Updates KazBars installs on its own don't trigger it. KazBars is unsigned because code signing certificates aren't justified for a hobby project. If you want to verify the download, `KazBars.zip.sha256` is attached alongside the zip — compare it with `Get-FileHash "KazBars.zip"` in PowerShell.
