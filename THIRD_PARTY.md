# Third-party material in KazBars

KazBars itself is licensed under the GNU General Public License v2.0 or later (see `LICENSE`).
The following parts are not KazBars's own work and keep their own terms.

## MTASC — ActionScript 2 compiler

`src/kazbars/assets/compiler/` ships `mtasc.exe` 1.14 and its `std/` and `std8/` class
headers. MTASC is © 2004–2008 Nicolas Cannasse / Motion-Twin, licensed under the GNU GPL
version 2 or later. Its source code is available at <https://github.com/ncannasse/mtasc>.
KazBars runs it as a separate program; the SWF files it produces are not covered by its license.

## Deeps — combat-log parsers

`src/kazbars/deeps_parsers.py` ports the Rust parsers of Veni's *Deeps* (Real-time damage and
heal overlay for Age of Conan, <https://github.com/lostagista/Deeps>), jointly authored by
Veni and Kaz, and is included here with the author's permission.

## Age of Conan game files (Funcom)

`src/kazbars/assets/damageinfo/DamageInfo.swf` is a file from *Age of Conan: Unchained* and
remains © Funcom. The ActionScript sources under `src/kazbars/assets/damageinfo/src/` were
decompiled from that file (with JPEXS Free Flash Decompiler) and modified for the Damage
Numbers feature; they are derived from Funcom's code, are **not** covered by KazBars's license,
and are distributed only as a modification to the game the user already owns. That SWF also
embeds the GreenSock TweenLite classes (© GreenSock), untouched.

## Redistributed libraries (binary release only)

The release zip is built with PyInstaller and bundles the Python runtime and these packages,
each under its own license: Python (PSF), ttkbootstrap (MIT), Pillow (MIT-CMU),
pywin32 (PSF), pywinstyles (CC0-1.0). PyInstaller's bootloader is GPL-2.0-or-later with the
exception that permits bundling programs under any license.
