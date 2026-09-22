# Third-party material in KazBars

KazBars itself is licensed under the GNU General Public License v2.0 or later (see `LICENSE`).
The following parts are not KazBars's own work and keep their own terms.

## as2c / MTASC — ActionScript 2 compiler

KazBars compiles its grids with [as2c](https://github.com/kazour/as2c) (GPL-2.0-or-later), a
Python port of MTASC 1.14 that also carries MTASC's `std/` and `std8/` class headers. MTASC is
© 2004–2008 Nicolas Cannasse / Motion-Twin, GNU GPL version 2 or later; its source code is at
<https://github.com/ncannasse/mtasc>. The SWF files the compiler produces are not covered by
its license.

## Deeps — combat-log parsers

`src/kazbars/deeps_parsers.py` ports the Rust parsers of Veni's *Deeps* (Real-time damage and
heal overlay for Age of Conan, <https://github.com/lostagista/Deeps>), jointly authored by
Veni and Kaz, under the MIT License:

> MIT License
>
> Copyright (c) 2026 Veni (lostagista) and Kazour
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

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
