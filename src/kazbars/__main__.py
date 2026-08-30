"""KazBars entry point — `python -m kazbars`."""

import logging
import sys
from logging.handlers import RotatingFileHandler

from kazbars import __version__, self_update
from kazbars.app import KazBarsApp
from kazbars.paths import app_path


def _configure_logging():
    """Console + rotating file log. A windowed .exe has no console, so the file
    handler is what gives shipped builds a retrievable crash trail."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        log_dir = app_path() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_dir / "kazbars.log",
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
        )
    except OSError:
        # A read-only or locked install dir must not stop the app launching.
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


def _claim_taskbar_identity():
    """A source run is hosted by python.exe, so the taskbar and Alt-Tab show
    Python's icon (the title bar uses the window icon and is fine). An explicit
    AppUserModelID makes Windows treat the window as its own app. The frozen
    exe already is one — its identity stays untouched so pinned shortcuts keep
    matching."""
    if sys.platform != "win32" or getattr(sys, "frozen", False):
        return
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Kazour.KazBars")
    except (AttributeError, OSError):
        pass


def main():
    apply = self_update.parse_args(sys.argv[1:])
    if apply is not None:
        # Running as the staged exe: swap the install, relaunch it, exit. No
        # logging setup here — run_apply logs into the install's own logs/.
        sys.exit(self_update.run_apply(*apply))
    _configure_logging()
    action, _pending = self_update.startup_action(app_path(), __version__)
    if action == 'retry':
        # An apply died mid-way with the staged exe intact: hand back to it.
        self_update.respawn_apply(app_path())
        return
    _claim_taskbar_identity()
    app = KazBarsApp()
    app.mainloop()


if __name__ == "__main__":
    main()
