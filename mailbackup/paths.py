from __future__ import annotations

import os
from pathlib import Path


APP_DIR_NAME = 'EsfaMailBackup'
LEGACY_APP_DIR_NAME = 'HetznerMailBackup'


def app_data_dir() -> Path:
    root = os.environ.get('LOCALAPPDATA')
    if root:
        return Path(root) / APP_DIR_NAME
    return Path.home() / '.esfa-mail-backup'


def legacy_app_data_dir() -> Path:
    root = os.environ.get('LOCALAPPDATA')
    if root:
        return Path(root) / LEGACY_APP_DIR_NAME
    return Path.home() / '.hetzner-mail-backup'


def config_path() -> Path:
    return app_data_dir() / 'config.json'


def state_path() -> Path:
    return app_data_dir() / 'state.json'


def log_dir() -> Path:
    return app_data_dir() / 'logs'


def log_path() -> Path:
    return log_dir() / 'application.log'

