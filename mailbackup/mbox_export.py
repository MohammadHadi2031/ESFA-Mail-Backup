from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from email.parser import BytesHeaderParser
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Callable

from .backup_engine import safe_component
from .models import Account, Settings
from .storage import SettingsStore, StateStore


ExportProgress = Callable[[str, str, int, int], None]
FROM_LINE = re.compile(rb'^(>*From )', re.MULTILINE)
INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MBOX_DIR_NAME = 'MBOX'
HEADER_LIMIT = 64 * 1024


@dataclass(slots=True)
class ExportResult:
    root: Path
    accounts: int = 0
    files: int = 0
    messages: int = 0
    errors: list[str] = field(default_factory=list)


def readable_component(value: str, limit: int = 72) -> str:
    return INVALID_NAME.sub('_', value).strip(' .')[:limit] or '_'


def _unique(name: str, taken: set[str]) -> str:
    candidate = name
    index = 2
    while candidate.casefold() in taken:
        candidate = f'{name} ({index})'
        index += 1
    taken.add(candidate.casefold())
    return candidate


def _envelope_line(message: bytes) -> bytes:
    sender = 'MAILER-DAEMON'
    stamp = time.gmtime()
    try:
        headers = BytesHeaderParser().parsebytes(message[:HEADER_LIMIT])
        address = parseaddr(headers.get('From', ''))[1]
        if address and ' ' not in address:
            sender = address
        raw_date = headers.get('Date')
        if raw_date:
            stamp = parsedate_to_datetime(raw_date).timetuple()
    except (ValueError, TypeError, OverflowError):
        pass
    return f'From {sender} {time.strftime("%a %b %d %H:%M:%S %Y", stamp)}\n'.encode('utf-8', errors='replace')


def _append_message(handle, message: bytes) -> None:
    handle.write(_envelope_line(message))
    handle.write(FROM_LINE.sub(rb'>\1', message))
    if not message.endswith(b'\n'):
        handle.write(b'\n')
    handle.write(b'\n')


def _sorted_messages(folder_dir: Path) -> list[Path]:
    def key(path: Path) -> tuple[int, int, str]:
        generation = path.parent.name
        return (
            int(generation) if generation.isdigit() else 0,
            int(path.stem) if path.stem.isdigit() else 0,
            path.name,
        )

    return sorted(folder_dir.rglob('*.eml'), key=key)


def _folder_names(account: Account, state: dict) -> dict[str, str]:
    folders = state.get('accounts', {}).get(account.account_id, {}).get('folders', {})
    names: dict[str, str] = {}
    for entry in folders.values():
        display = str(entry.get('display_name') or '')
        if display:
            names[safe_component(display)] = display
    return names


def export_account(
    account: Account,
    backup_root: Path,
    target_root: Path,
    state: dict,
    progress: ExportProgress | None = None,
) -> tuple[int, int]:
    """Convert one account's stored .eml tree into one .mbox file per mail folder."""
    source = backup_root / safe_component(account.email)
    if not source.is_dir():
        return 0, 0
    target = target_root / readable_component(account.email)
    target.mkdir(parents=True, exist_ok=True)
    names = _folder_names(account, state)
    folder_dirs = sorted(item for item in source.iterdir() if item.is_dir())
    taken: set[str] = set()
    files = 0
    messages = 0
    for index, folder_dir in enumerate(folder_dirs, start=1):
        display = names.get(folder_dir.name, folder_dir.name)
        if progress:
            progress(account.email, display, index, len(folder_dirs))
        sources = _sorted_messages(folder_dir)
        if not sources:
            continue
        mbox_path = target / f'{_unique(readable_component(display), taken)}.mbox'
        temporary = mbox_path.with_suffix('.mbox.part')
        with temporary.open('wb') as handle:
            for item in sources:
                _append_message(handle, item.read_bytes())
                messages += 1
        temporary.replace(mbox_path)
        files += 1
    return files, messages


def export_all(
    settings: Settings | None = None,
    progress: ExportProgress | None = None,
    settings_store: SettingsStore | None = None,
    state_store: StateStore | None = None,
    logger: logging.Logger | None = None,
) -> ExportResult:
    logger = logger or logging.getLogger('mailbackup')
    settings = settings or (settings_store or SettingsStore()).load()
    if not settings.backup_root:
        raise ValueError('ابتدا پوشه مقصد بکاپ را در تنظیمات انتخاب کنید.')
    backup_root = Path(settings.backup_root)
    if not backup_root.is_dir():
        raise ValueError('پوشه بکاپ پیدا نشد؛ ابتدا یک بار بکاپ بگیرید.')
    target_root = backup_root / MBOX_DIR_NAME
    target_root.mkdir(parents=True, exist_ok=True)
    state = (state_store or StateStore()).load()
    result = ExportResult(root=target_root)
    for account in settings.accounts:
        try:
            files, messages = export_account(account, backup_root, target_root, state, progress)
        except OSError as exc:
            logger.exception('MBOX export failed for %s', account.email)
            result.errors.append(f'{account.email}: {exc}')
            continue
        if files:
            result.accounts += 1
            result.files += files
            result.messages += messages
    logger.info('MBOX export finished: %d files, %d messages', result.files, result.messages)
    return result
