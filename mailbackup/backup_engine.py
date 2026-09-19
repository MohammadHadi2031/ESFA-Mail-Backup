from __future__ import annotations

import hashlib
import imaplib
import logging
import re
import ssl
from pathlib import Path
from typing import Callable, Iterable

from .imap_utf7 import decode as decode_imap_utf7
from .locking import BackupLock
from .models import Account, AccountResult, BackupResult, Settings
from .secrets import unprotect
from .storage import SettingsStore, StateStore


ProgressCallback = Callable[[str, str, int, int], None]
LIST_PATTERN = re.compile(rb'^\((?P<flags>.*?)\)\s+(?P<delimiter>NIL|"(?:[^"\\]|\\.)*")\s+(?P<name>.+)$')


def safe_component(value: str, limit: int = 72) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .') or '_'
    digest = hashlib.sha1(value.encode('utf-8', errors='replace')).hexdigest()[:8]
    return f'{sanitized[:limit]}_{digest}'


def _unquote_mailbox(value: bytes) -> str:
    value = value.strip()
    if value.startswith(b'"') and value.endswith(b'"'):
        value = value[1:-1].replace(b'\\"', b'"').replace(b'\\\\', b'\\')
    return value.decode('ascii', errors='replace')


def _quote_mailbox(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def parse_list_response(lines: Iterable[bytes | None]) -> list[tuple[str, str]]:
    folders: list[tuple[str, str]] = []
    for line in lines:
        if not line:
            continue
        match = LIST_PATTERN.match(line)
        if not match or b'\\Noselect' in match.group('flags'):
            continue
        encoded_name = _unquote_mailbox(match.group('name'))
        folders.append((encoded_name, decode_imap_utf7(encoded_name)))
    return folders


def _response_number(connection: imaplib.IMAP4_SSL, name: str, default: int) -> int:
    _, values = connection.response(name)
    if values and values[0]:
        raw = values[0]
        if isinstance(raw, bytes):
            raw = raw.decode('ascii', errors='ignore')
        match = re.search(r'\d+', str(raw))
        if match:
            return int(match.group())
    return default


def _message_bytes(response: list[object]) -> bytes:
    chunks: list[bytes] = []
    for item in response:
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
            chunks.append(item[1])
    if not chunks:
        raise RuntimeError('سرور محتوای پیام را برنگرداند.')
    return b''.join(chunks)


class BackupEngine:
    def __init__(
        self,
        settings_store: SettingsStore | None = None,
        state_store: StateStore | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings_store = settings_store or SettingsStore()
        self.state_store = state_store or StateStore()
        self.logger = logger or logging.getLogger('mailbackup')

    def test_connection(self, account: Account, password: str) -> None:
        context = ssl.create_default_context()
        with imaplib.IMAP4_SSL(account.server, account.port, ssl_context=context, timeout=30) as connection:
            connection.login(account.email, password)

    def run_all(self, progress: ProgressCallback | None = None) -> BackupResult:
        settings = self.settings_store.load()
        if not settings.backup_root:
            raise ValueError('ابتدا پوشه مقصد بکاپ را در تنظیمات انتخاب کنید.')
        Path(settings.backup_root).mkdir(parents=True, exist_ok=True)
        result = BackupResult()
        with BackupLock():
            for account in settings.accounts:
                if not account.enabled:
                    continue
                try:
                    item = self._backup_account(account, settings, progress)
                except Exception as exc:  # each account must not stop the others
                    self.logger.exception('Backup failed for %s', account.email)
                    item = AccountResult(account_id=account.account_id, email=account.email, success=False, error=str(exc))
                result.accounts.append(item)
                self._update_account_status(item)
        return result

    def _backup_account(
        self,
        account: Account,
        settings: Settings,
        progress: ProgressCallback | None,
    ) -> AccountResult:
        self.logger.info('Starting backup for %s', account.email)
        password = unprotect(account.password_token)
        state = self.state_store.load()
        account_state = state.setdefault('accounts', {}).setdefault(account.account_id, {'folders': {}})
        account_root = Path(settings.backup_root) / safe_component(account.email)
        account_root.mkdir(parents=True, exist_ok=True)
        result = AccountResult(account_id=account.account_id, email=account.email)
        context = ssl.create_default_context()
        with imaplib.IMAP4_SSL(account.server, account.port, ssl_context=context, timeout=60) as connection:
            connection.login(account.email, password)
            status, list_data = connection.list()
            if status != 'OK':
                raise RuntimeError('دریافت فهرست پوشه‌های ایمیل ناموفق بود.')
            folders = parse_list_response(list_data)
            if not folders:
                folders = [('INBOX', 'INBOX')]
            total_folders = len(folders)
            for folder_index, (wire_name, display_name) in enumerate(folders, start=1):
                if progress:
                    progress(account.email, display_name, folder_index, total_folders)
                downloaded = self._backup_folder(connection, account_root, wire_name, display_name, account_state)
                result.new_messages += downloaded
                result.folders += 1
                self.state_store.save(state)
            try:
                connection.logout()
            except imaplib.IMAP4.error:
                pass
        self.logger.info('Finished backup for %s: %d new messages', account.email, result.new_messages)
        return result

    def _backup_folder(
        self,
        connection: imaplib.IMAP4_SSL,
        account_root: Path,
        wire_name: str,
        display_name: str,
        account_state: dict,
    ) -> int:
        status, _ = connection.select(_quote_mailbox(wire_name), readonly=True)
        if status != 'OK':
            self.logger.warning('Could not select folder %s', display_name)
            return 0
        uid_validity = _response_number(connection, 'UIDVALIDITY', 0)
        uid_next = _response_number(connection, 'UIDNEXT', 1)
        folder_state = account_state.setdefault('folders', {}).setdefault(wire_name, {})
        previous_validity = int(folder_state.get('uid_validity', -1))
        previous_next = int(folder_state.get('uid_next', 1))
        if previous_validity != uid_validity:
            previous_next = 1
        folder_root = account_root / safe_component(display_name) / str(uid_validity)
        folder_root.mkdir(parents=True, exist_ok=True)
        if uid_next <= previous_next and previous_validity == uid_validity:
            return 0
        criterion = 'ALL' if previous_next <= 1 else f'UID {previous_next}:{max(previous_next, uid_next - 1)}'
        status, values = connection.uid('search', None, criterion)
        if status != 'OK':
            raise RuntimeError(f'جستجوی پیام‌ها در پوشه «{display_name}» ناموفق بود.')
        uids = values[0].split() if values and values[0] else []
        downloaded = 0
        for uid in uids:
            uid_text = uid.decode('ascii')
            target = folder_root / f'{uid_text}.eml'
            if target.exists():
                continue
            status, response = connection.uid('fetch', uid, '(BODY.PEEK[])')
            if status != 'OK':
                raise RuntimeError(f'دریافت پیام UID {uid_text} از «{display_name}» ناموفق بود.')
            temporary = target.with_suffix('.eml.part')
            temporary.write_bytes(_message_bytes(response))
            temporary.replace(target)
            downloaded += 1
        folder_state.update({
            'display_name': display_name,
            'uid_validity': uid_validity,
            'uid_next': uid_next,
        })
        return downloaded

    def _update_account_status(self, result: AccountResult) -> None:
        settings = self.settings_store.load()
        for account in settings.accounts:
            if account.account_id == result.account_id:
                account.last_run = result.finished_at
                account.last_status = (
                    f'{result.new_messages} پیام جدید' if result.success else f'خطا: {result.error[:120]}'
                )
                break
        self.settings_store.save(settings)
