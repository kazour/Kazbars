"""Damage Numbers generator — bake settings into the lean AS2, compile it into the SWF.

``generate()`` copies the shipped ``assets/damageinfo/src/__Packages`` tree to a temp
dir and regex-rewrites each named constant to ``game_default + offset`` (the bake-map
lives in :mod:`damageinfo_settings`). ``build_damageinfo()`` then copies the pristine
game ``DamageInfo.swf`` and compiles the baked sources into that copy
(``compile_as2``), replacing the damage-number classes while leaving the SWF's symbols
and timeline intact. Two entry points are forced so ``FixOnLoad`` (which makes the
container's ``onLoad`` fire) survives the inject. A ``font`` other than Hyborian draws
the text larger (``DEFAULT_TEXT_SCALE`` rewritten to ``swf_font.dn_scale``) and, after
the compile, replaces the SWF's ``_ConanFont`` import with that face's two embedded
fonts (``swf_font.set_damage_font``). Pure build logic; no Tk.
"""

import logging
import re
import shutil
import tempfile
from pathlib import Path

from . import damageinfo_settings as dis
from .build_utils import compile_as2
from .overlay import HYBORIAN, font_blob_path
from .swf_font import SwfFontError, dn_scale, set_damage_font

logger = logging.getLogger(__name__)

# Entry points compiled into the SWF (relative to the __Packages classpath root).
# FixOnLoad is force-compiled so the NumbersContainer symbol's registered class
# survives the inject (otherwise the container's onLoad never fires).
ENTRY_POINTS = (
    'MainDamageNumbers.as',
    'com/helperFramework/display/FixOnLoad.as',
)

# The stock text scale a non-Hyborian face rewrites (Hyborian keeps the file byte for byte).
_TEXT_SCALE_FILE = 'numbersTypes/DamageTextAbstract.as'
_TEXT_SCALE_STOCK = 'var DEFAULT_TEXT_SCALE = 1;'


class DamageInfoGenerator:
    """Copies the AS2 source tree to a temp dir and bakes setting offsets into it."""

    def __init__(self, source_pkg: str | Path, settings: dict) -> None:
        self.source_pkg = Path(source_pkg)
        self.settings = dis.validate_all_settings(settings)

    def generate(self, output_pkg: str | Path) -> bool:
        """Copy the source tree to ``output_pkg`` and apply every bake. Returns success.

        A bake whose pattern matches nothing is a HARD failure (returns False), not a
        warning — that means the AS2 source drifted from the bake-map, and shipping the
        stock value silently would leave a slider doing nothing in-game with no error.
        """
        output_pkg = Path(output_pkg)
        try:
            shutil.copytree(self.source_pkg, output_pkg, dirs_exist_ok=True)
            ok = True
            for file_rel, replacements in self._modifications().items():
                target = output_pkg / file_rel
                if not target.exists():
                    logger.error('Damage Numbers bake target missing: %s', file_rel)
                    ok = False
                    continue
                if not self._apply(target, replacements):
                    ok = False
            return ok
        except OSError:
            logger.exception('Damage Numbers source generation failed')
            return False

    def _modifications(self) -> dict[str, list[tuple[str, str]]]:
        """Group (pattern, replacement) bakes by their target .as file."""
        mods: dict[str, list[tuple[str, str]]] = {}
        for key, meta in dis.GLOBAL_SETTINGS.items():
            repl = self._replacement(key, meta, self.settings[key])
            if repl is not None:
                mods.setdefault(meta['file'], []).append(repl)
        scale = dn_scale(self.settings['font'])
        if scale != 100:
            mods.setdefault(_TEXT_SCALE_FILE, []).append(
                (re.escape(_TEXT_SCALE_STOCK), f'var DEFAULT_TEXT_SCALE = {scale / 100};'))
        return mods

    def _replacement(self, key: str, meta: dict, offset) -> tuple[str, str] | None:
        final = dis.compute_final_value(key, offset)
        formatted = f'{float(final):.4g}' if dis.is_float_key(key) else str(int(final))
        if key == 'shadow_blur':
            # Dual-axis: rewrite both blurX and blurY (groups 2 and 3) at once.
            return (meta['pattern'], rf'\g<1>{formatted},{formatted}')
        return (meta['pattern'], rf'\g<1>{formatted}')

    def _apply(self, target: Path, replacements: list[tuple[str, str]]) -> bool:
        """Apply every (pattern, replacement) to one file. Returns False if any matched nothing."""
        content = target.read_text(encoding='utf-8')
        ok = True
        for pattern, repl in replacements:
            content, count = re.subn(pattern, repl, content)
            if count == 0:
                logger.error('Damage Numbers bake pattern matched nothing in %s: %s', target.name, pattern)
                ok = False
        target.write_text(content, encoding='utf-8')
        return ok


def build_damageinfo(assets_path: str | Path, settings: dict,
                     output_swf: str | Path) -> tuple[bool, str]:
    """Bake + compile the modded ``DamageInfo.swf`` to ``output_swf``.

    Copies the pristine game SWF shipped under ``assets/damageinfo/`` and injects the
    baked classes into it. Returns ``(success, message)``.
    """
    assets_path = Path(assets_path)
    output_swf = Path(output_swf)

    di_dir = assets_path / 'damageinfo'
    pristine = di_dir / 'DamageInfo.swf'
    source_pkg = di_dir / 'src' / '__Packages'

    for label, p in (('pristine SWF', pristine), ('AS2 source', source_pkg)):
        if not p.exists():
            return False, f'Damage Numbers {label} missing: {p}'

    temp_dir = Path(tempfile.mkdtemp(prefix='damageinfo_'))
    try:
        temp_pkg = temp_dir / '__Packages'
        generator = DamageInfoGenerator(source_pkg, settings)
        if not generator.generate(temp_pkg):
            return False, 'Failed to bake Damage Numbers source (a setting pattern matched nothing — see log).'

        entries = [temp_pkg / e for e in ENTRY_POINTS]
        missing = [e for e in entries if not e.exists()]
        if missing:
            return False, f'Damage Numbers entry point not found: {missing[0]}'

        shutil.copy2(pristine, output_swf)
        ok, err = compile_as2([temp_pkg], output_swf, entries)
        if not ok:
            output_swf.unlink(missing_ok=True)  # don't leave a pristine/partial SWF at the caller's path
            return False, f'Damage Numbers compile failed:\n{err}'

        font = generator.settings['font']
        if font != HYBORIAN:
            blob = font_blob_path(assets_path / 'kazbars', font)
            try:
                output_swf.write_bytes(set_damage_font(output_swf.read_bytes(), font,
                                                       blob.read_bytes() if blob else None))
            except (OSError, SwfFontError) as e:
                output_swf.unlink(missing_ok=True)
                return False, f"Couldn't set Damage Numbers in {font}:\n{e}"

        size = output_swf.stat().st_size
        return True, f'DamageInfo.swf built ({size:,} bytes)'
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
