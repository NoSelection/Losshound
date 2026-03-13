from __future__ import annotations

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="losshound",
        description="Losshound — Lightweight Windows network diagnosis tool",
    )
    parser.add_argument(
        "--cli", action="store_true",
        help="Run in CLI mode (no GUI)",
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to configuration file",
    )
    parser.add_argument(
        "--log-level", type=str, default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    from losshound.core.config import load_config
    config = load_config(args.config)

    if args.log_level:
        config.log_level = args.log_level

    from losshound.core.logger import setup_logging
    setup_logging(config.log_level)

    if args.cli:
        from losshound.cli.runner import run_cli
        run_cli(config)
    else:
        _run_gui(config)


def _run_gui(config):
    from PySide6.QtWidgets import QApplication
    from losshound.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Losshound")
    app.setApplicationVersion("0.1.0")

    window = MainWindow(config)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
