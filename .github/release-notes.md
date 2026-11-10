## What's New in v3.2.1

Grids, the Cast timer and the Onslaught tracker now stay where you put them on screens above 1080p — update KazBars, then Build & Install.

### Fixed

**Positions jumping inward** — on screens above 1080p, grids, Cast timer bars and the Onslaught board and alerts could land further in after `/reloadui` or a relog and save that spot (seen after importing a 3.1 profile); they now load where you left them, and only opening preview mode pulls them onto the screen.

The Stopwatch, Console and Inspect Target panels weren't affected.

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
