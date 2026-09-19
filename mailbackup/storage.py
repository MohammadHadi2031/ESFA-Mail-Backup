from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

from .models import Settings
from .paths import app_data_dir, config_path, legacy_app_data_dir, state_path


_LOCK = RLock()


def _atomic_json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name, suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_path()

    def load(self) -> Settings:
        with _LOCK:
            if not self.path.exists():
                return Settings()
            try:
                return Settings.from_dict(json.loads(self.path.read_text(encoding='utf-8-sig')))
            except (OSError, ValueError, TypeError):
                damaged = self.path.with_suffix('.damaged.json')
                try:
                    os.replace(self.path, damaged)
                except OSError:
                    pass
                return Settings()

    def save(self, settings: Settings) -> None:
        with _LOCK:
            _atomic_json_write(self.path, settings.to_dict())


class StateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or state_path()

    def load(self) -> dict[str, Any]:
        with _LOCK:
            if not self.path.exists():
                return {'accounts': {}}
            try:
                value = json.loads(self.path.read_text(encoding='utf-8-sig'))
                return value if isinstance(value, dict) else {'accounts': {}}
            except (OSError, ValueError, TypeError):
                return {'accounts': {}}

    def save(self, value: dict[str, Any]) -> None:
        with _LOCK:
            _atomic_json_write(self.path, value)


def ensure_app_directories() -> None:
    _migrate_legacy_app_data()
    app_data_dir().mkdir(parents=True, exist_ok=True)


def _migrate_legacy_app_data() -> None:
    """Carry settings and logs over from the pre-rename data directory, once."""
    current = app_data_dir()
    legacy = legacy_app_data_dir()
    if current.exists() or not legacy.is_dir() or current == legacy:
        return
    with _LOCK:
        try:
            current.parent.mkdir(parents=True, exist_ok=True)
            legacy.rename(current)
        except OSError:
            pass

