from __future__ import annotations

import json
from pathlib import Path

from mailbackup.backup_engine import BackupEngine, archive_totals, parse_list_response, safe_component
from mailbackup.imap_utf7 import decode
from mailbackup.models import Account, AccountResult, Settings
from mailbackup.storage import SettingsStore, StateStore


def test_imap_utf7_decode() -> None:
    assert decode('INBOX') == 'INBOX'
    assert decode('A&-B') == 'A&B'
    assert decode('&ZeVnLIqe-') == '日本語'


def test_parse_list_response_skips_noselect() -> None:
    response = [
        b'(\\HasNoChildren) "/" "INBOX"',
        b'(\\HasNoChildren \\Sent) "/" "Sent"',
        b'(\\Noselect) "/" "Container"',
    ]
    assert parse_list_response(response) == [('INBOX', 'INBOX'), ('Sent', 'Sent')]


def test_safe_component_is_stable_and_windows_safe() -> None:
    first = safe_component('Sent/Archive:2026')
    second = safe_component('Sent/Archive:2026')
    assert first == second
    assert '/' not in first
    assert ':' not in first


def test_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / 'config.json'
    store = SettingsStore(path)
    expected = Settings(
        backup_root=r'D:\EmailBackup',
        schedule_time='02:30',
        scheduled=True,
        accounts=[Account(email='user@example.com', password_token='encrypted')],
    )
    store.save(expected)
    actual = store.load()
    assert actual.to_dict() == expected.to_dict()
    assert json.loads(path.read_text(encoding='utf-8'))['accounts'][0]['email'] == 'user@example.com'


def test_damaged_settings_are_recovered(tmp_path: Path) -> None:
    path = tmp_path / 'config.json'
    path.write_text('{not-json', encoding='utf-8')
    settings = SettingsStore(path).load()
    assert settings.accounts == []
    assert path.with_suffix('.damaged.json').exists()


def test_state_round_trip(tmp_path: Path) -> None:
    path = tmp_path / 'state.json'
    store = StateStore(path)
    expected = {'accounts': {'a1': {'folders': {'INBOX': {'uid_next': 42}}}}}
    store.save(expected)
    assert store.load() == expected


class FakeImap:
    def __init__(self) -> None:
        self.searches = 0
        self.fetches = 0

    def select(self, _folder: str, readonly: bool = True):
        assert readonly is True
        return 'OK', [b'2']

    def response(self, name: str):
        return name, [b'17' if name == 'UIDVALIDITY' else b'3']

    def uid(self, command: str, *args):
        if command == 'search':
            self.searches += 1
            return 'OK', [b'1 2']
        if command == 'fetch':
            self.fetches += 1
            uid = args[0]
            return 'OK', [(b'1 (BODY[] {4})', b'mail-' + uid), b')']
        raise AssertionError(command)


def test_folder_backup_is_incremental_and_never_deletes(tmp_path: Path) -> None:
    engine = BackupEngine()
    connection = FakeImap()
    state: dict = {'folders': {}}
    downloaded = engine._backup_folder(connection, tmp_path, 'INBOX', 'INBOX', state)
    assert downloaded == 2
    assert connection.fetches == 2
    files = sorted(tmp_path.rglob('*.eml'))
    assert len(files) == 2

    downloaded_again = engine._backup_folder(connection, tmp_path, 'INBOX', 'INBOX', state)
    assert downloaded_again == 0
    assert connection.fetches == 2
    assert all(path.exists() for path in files)


def test_folder_backup_reports_message_progress(tmp_path: Path) -> None:
    seen: list[tuple[int, int]] = []
    BackupEngine()._backup_folder(FakeImap(), tmp_path, 'INBOX', 'INBOX', {'folders': {}}, lambda *step: seen.append(step))
    assert seen == [(1, 2), (2, 2)]


def test_archive_totals_count_only_finished_messages(tmp_path: Path) -> None:
    folder = tmp_path / 'INBOX' / '17'
    folder.mkdir(parents=True)
    (folder / '1.eml').write_bytes(b'abc')
    (folder / '2.eml').write_bytes(b'defgh')
    (folder / '3.eml.part').write_bytes(b'partial download')
    assert archive_totals(tmp_path) == (2, 8)
    assert archive_totals(tmp_path / 'missing') == (0, 0)


def test_successful_run_records_archive_totals_and_failures_keep_them(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / 'config.json')
    account = Account(email='user@example.com', archived_messages=5, archived_bytes=50)
    store.save(Settings(accounts=[account]))
    engine = BackupEngine(settings_store=store, state_store=StateStore(tmp_path / 'state.json'))

    engine._update_account_status(AccountResult(account.account_id, account.email, success=False, error='boom'))
    saved = store.load().accounts[0]
    assert saved.failed and (saved.archived_messages, saved.archived_bytes) == (5, 50)

    engine._update_account_status(AccountResult(
        account.account_id, account.email, new_messages=2, archived_messages=7, archived_bytes=70,
    ))
    saved = store.load().accounts[0]
    assert not saved.failed
    assert saved.last_status == '2 پیام جدید'
    assert (saved.archived_messages, saved.archived_bytes) == (7, 70)


def test_legacy_app_data_directory_is_migrated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    from mailbackup.paths import app_data_dir, legacy_app_data_dir
    from mailbackup.storage import ensure_app_directories

    legacy = legacy_app_data_dir()
    legacy.mkdir(parents=True)
    (legacy / 'config.json').write_text(json.dumps({'backup_root': r'D:\Mail'}), encoding='utf-8')

    ensure_app_directories()

    assert not legacy.exists()
    assert SettingsStore(app_data_dir() / 'config.json').load().backup_root == r'D:\Mail'
