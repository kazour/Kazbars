"""KazBars entry point — `python -m kazbars`."""

import logging
from logging.handlers import RotatingFileHandler

from kazbars.app import KazBarsApp
from kazbars.paths import app_path


def _configure_logging():
    """Console + rotating file log. A windowed .exe has no console, so the file
    handler is what gives shipped builds a retrievable crash trail."""
    handlers = [logging.StreamHandler()]
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


def main():
    _configure_logging()
    app = KazBarsApp()
    app.mainloop()


if __name__ == "__main__":
    main()
