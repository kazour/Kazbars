# Third-party material in KazBars

KazBars itself is licensed under the GNU General Public License v2.0 or later (see `LICENSE`).
The following parts are not KazBars's own work and keep their own terms.

## as2c / MTASC — ActionScript 2 compiler

KazBars compiles its grids with as2c (GPL-2.0-or-later), a Python port of MTASC 1.14 that
also carries MTASC's `std/` and `std8/` class headers. Its source ships in the KazBars
repository under `src/as2c/` (<https://github.com/kazour/Kazbars>). MTASC is
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

## Fonts embedded in KazBars.swf and DamageInfo.swf (SIL Open Font License 1.1)

The overlay Font dropdown offers nine open-licence faces besides Arial and the game's own
Verdana, and the Damage Numbers font list eight more, embedded in DamageInfo.swf instead.
Build & Install writes the chosen face's glyph outlines into the SWF, and the app carries all
seventeen as data under `src/kazbars/assets/kazbars/fonts/` (`<slug>.bin`). Each is licensed
under the **SIL Open Font License, Version 1.1**, which these fonts keep; they are not covered
by KazBars's license. The full licence text and copyright notice of each ship with the app in
`src/kazbars/assets/kazbars/fonts/LICENSES/<slug>.txt`, and the notice is also stored in the
font's DefineFontName tag inside the SWF.

| Font | Copyright | Licence text |
|---|---|---|
| Roboto | 2011 The Roboto Project Authors (https://github.com/googlefonts/roboto-classic) | `LICENSES/roboto.txt` |
| Inter | 2020 The Inter Project Authors (https://github.com/rsms/inter) | `LICENSES/inter.txt` |
| Noto Sans | 2022 The Noto Project Authors (https://github.com/notofonts/latin-greek-cyrillic) | `LICENSES/noto-sans.txt` |
| Source Sans 3 | 2010-2020 Adobe (http://www.adobe.com/), with Reserved Font Name 'Source'. All Rights Reserved. Source is a trademark of Adobe in the United States and/or other countries. | `LICENSES/source-sans-3.txt` |
| PT Sans | (c) 2010, ParaType Ltd. (http://www.paratype.com/public), with Reserved Font Names "PT Sans" and "ParaType" | `LICENSES/pt-sans.txt` |
| Fira Sans | (c) 2012-2015, The Mozilla Foundation and Telefonica S.A. | `LICENSES/fira-sans.txt` |
| Barlow Semi Condensed | 2017 The Barlow Project Authors (https://github.com/jpt/barlow) | `LICENSES/barlow-semi-condensed.txt` |
| Exo 2 | 2013 The Exo 2 Project Authors (https://github.com/googlefonts/Exo-2.0) | `LICENSES/exo-2.txt` |
| Alegreya Sans | 2013 The Alegreya Sans Project Authors (https://github.com/huertatipografica/Alegreya-Sans) | `LICENSES/alegreya-sans.txt` |
| Bangers (Damage Numbers only) | 2010 The Bangers Project Authors (https://github.com/googlefonts/bangers) | `LICENSES/bangers.txt` |
| Lilita One (Damage Numbers only) | 2011 Juan Montoreano (juan@remolacha.biz), with Reserved Font Names "Lilita One" | `LICENSES/lilita-one.txt` |
| Rubik Black (Damage Numbers only) | 2015 The Rubik Project Authors (https://github.com/googlefonts/rubik) | `LICENSES/rubik-black.txt` |
| Bungee (Damage Numbers only) | 2023 The Bungee Project Authors (https://github.com/djrrb/Bungee) | `LICENSES/bungee.txt` |
| Changa One (Damage Numbers only) | 2011, Eduardo Tunni (http://www.tipo.net.ar), with Reserved Font Name "Changa" | `LICENSES/changa-one.txt` |
| Cinzel Decorative Black (Damage Numbers only) | 2012 Natanael Gama (info@ndiscovered.com), with Reserved Font Name 'Cinzel' | `LICENSES/cinzel-decorative-black.txt` |
| Alfa Slab One (Damage Numbers only) | 2016 The Alfa Slab One Project Authors (http://www.jmsole.cl / info@jmsole.cl), with Reserved Font Name "Alfa Slab". | `LICENSES/alfa-slab-one.txt` |
| Bevan (Damage Numbers only) | 2016 The Bevan Project Authors (https://github.com/googlefonts/BevanFont) | `LICENSES/bevan.txt` |

The glyph data is embedded in KazBars.swf under the internal font names "Arial" and "Arial
Bold", solely as a lookup handle: the generated ActionScript asks the game's Flash player for
`Arial`, and the player takes its outlines only from the SWF. The two fonts `base.swf` ships are
replaced whole, so no outline or notice of Arial (Monotype) remains in such a KazBars.swf. The
Reserved Font Names above ("Source", "PT Sans", "ParaType", "Lilita One", "Changa", "Cinzel"
and the others listed) are not used as a font name anywhere; DamageInfo.swf carries its face the
same way, under "Arial".

The outlines are the fonts' own, changed only as fitting a SWF font tag requires: subsetting to
the 115 characters the overlay draws, instancing the variable fonts (Roboto, Inter, Noto Sans,
Source Sans 3, Exo 2) at weights 400 and 700, removing overlapping contours, rounding to whole
twips, and, for Inter, Fira Sans, Barlow Semi Condensed, Exo 2 and Alegreya Sans, substituting
the font's own tabular figures for the digits so timers keep their width. The tags carry
Arial's line metrics and no kerning table. They are Modified Versions in the licence's sense.

Verdana, and Damage Numbers' default Hyborian, are the game's own fonts: the SWF imports them
from the player's own install at run time, and nothing of either face is copied into KazBars.

## GG (GigaUI Ultimate)

The overlay Font dropdown also offers **GG**, the typeface of GigaUI Ultimate, a custom
interface for Age of Conan by Giga (https://github.com/BooroH/GigaUI-Ultimate). Its Medium and
Bold faces are taken from that repository at commit 9c1ad23f9a6c92d979a365acb372d2004c16dabd,
where they are published with the interface. They are prepared the same way as the faces above
(`fonts/gg.bin`), with one difference: GG has no tabular figures, so each digit is centred in
the widest digit's advance. That repository carries no licence file. GG is included at the
direction of the KazBars maintainer, who states that its author ships it openly for Age of
Conan interface use. The Damage Numbers font list also offers **GG Comic**, the same
repository's GG Comic Black (`fonts/gg-comic.bin`, the one face used for both regular and
bold), on the same terms. The notices are in `LICENSES/gg.txt` and `LICENSES/gg-comic.txt`. It
is not covered by KazBars's license.

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
