from __future__ import annotations

import os
from pathlib import Path

from .paths import app_data_dir


class BackupAlreadyRunning(RuntimeError):
    pass


class BackupLock:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (app_data_dir() / 'backup.lock')
        self._handle = None

    def __enter__(self) -> 'BackupLock':
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._handle.close()
            self._handle = None
            raise BackupAlreadyRunning('یک عملیات بکاپ دیگر در حال اجرا است.') from exc
        return self

    def __exit__(self, *_: object) -> None:
        if not self._handle:
            return
        try:
            if os.name == 'nt':
                import msvcrt
                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None

