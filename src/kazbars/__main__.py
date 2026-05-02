"""KazBars entry point — `python -m kazbars`."""

import logging

from kazbars.app import KazBarsApp


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    app = KazBarsApp()
    app.mainloop()


if __name__ == "__main__":
    main()
