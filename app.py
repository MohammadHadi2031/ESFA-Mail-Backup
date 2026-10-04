from __future__ import annotations

import argparse
import multiprocessing
import sys
from pathlib import Path

from mailbackup.backup_engine import BackupEngine
from mailbackup.logging_setup import configure_logging
from mailbackup.storage import ensure_app_directories


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--run-backup', action='store_true')
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--port', type=int, default=8765)
    arguments, _ = parser.parse_known_args()
    return arguments


ARGS = parse_arguments()
ensure_app_directories()
LOGGER = configure_logging()


def run_headless() -> int:
    try:
        result = BackupEngine(logger=LOGGER).run_all()
        return 1 if result.failures else 0
    except Exception:
        LOGGER.exception('Scheduled backup failed')
        return 1


if ARGS.run_backup:
    raise SystemExit(run_headless())


from nicegui import app, ui  # noqa: E402

from mailbackup.gui.dashboard import Dashboard  # noqa: E402
from mailbackup.gui.theme import FAVICON  # noqa: E402


# Native window icon (title bar / taskbar): same mark as the exe icon, bundled by PyInstaller.
ASSETS_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets'
WINDOW_ICON = ASSETS_DIR / 'app.ico'


@ui.page('/')
def index() -> None:
    Dashboard(logger=LOGGER, native=not ARGS.browser).build()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    run_options = dict(
        host='127.0.0.1',
        title='ESFA Mail Backup',
        favicon=FAVICON if ARGS.browser else WINDOW_ICON,
        native=not ARGS.browser,
        reload=False,
        port=ARGS.port,
        show=ARGS.browser,
        storage_secret='local-desktop-only',
        language='fa-IR',
    )
    if not ARGS.browser:
        run_options['window_size'] = (1200, 800)
        app.native.window_args['min_size'] = (960, 640)
    ui.run(**run_options)
