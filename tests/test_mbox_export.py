from __future__ import annotations

import mailbox
from pathlib import Path

from mailbackup.backup_engine import safe_component
from mailbackup.mbox_export import export_all, readable_component
from mailbackup.models import Account, Settings
from mailbackup.storage import StateStore


def _message(subject: str, body: str) -> bytes:
    return (
        f'From: Ali <ali@example.com>\r\n'
        f'To: user@example.com\r\n'
        f'Subject: {subject}\r\n'
        f'Date: Mon, 03 Mar 2025 10:00:00 +0000\r\n'
        f'\r\n'
        f'{body}\r\n'
    ).encode('utf-8')


def _prepare(tmp_path: Path) -> tuple[Settings, StateStore]:
    account = Account(email='user@example.com')
    backup_root = tmp_path / 'backup'
    folder_dir = backup_root / safe_component(account.email) / safe_component('پیام‌های ارسالی') / '17'
    folder_dir.mkdir(parents=True)
    (folder_dir / '2.eml').write_bytes(_message('Second', 'From the top\r\nplain line'))
    (folder_dir / '10.eml').write_bytes(_message('Third', 'body'))
    (folder_dir / '1.eml').write_bytes(_message('First', 'body'))
    state_store = StateStore(tmp_path / 'state.json')
    state_store.save({'accounts': {account.account_id: {'folders': {
        'Sent': {'display_name': 'پیام‌های ارسالی', 'uid_validity': 17, 'uid_next': 11},
    }}}})
    return Settings(backup_root=str(backup_root), accounts=[account]), state_store


def test_export_writes_one_mbox_per_folder(tmp_path: Path) -> None:
    settings, state_store = _prepare(tmp_path)
    result = export_all(settings=settings, state_store=state_store)

    assert result.files == 1
    assert result.messages == 3
    assert not result.errors
    target = result.root / readable_component('user@example.com') / 'پیام‌های ارسالی.mbox'
    assert target.exists()
    assert not list(result.root.rglob('*.part'))

    box = mailbox.mbox(target)
    try:
        subjects = [message['Subject'] for message in box]
    finally:
        box.close()
    assert subjects == ['First', 'Second', 'Third']


def test_export_escapes_from_lines_and_is_repeatable(tmp_path: Path) -> None:
    settings, state_store = _prepare(tmp_path)
    first = export_all(settings=settings, state_store=state_store)
    target = first.root / readable_component('user@example.com') / 'پیام‌های ارسالی.mbox'
    content = target.read_bytes()
    assert b'\n>From the top' in content
    assert content.count(b'\nFrom ali@example.com ') + content.startswith(b'From ali@example.com ') == 3

    second = export_all(settings=settings, state_store=state_store)
    assert second.messages == 3
    assert target.read_bytes() == content


def test_export_without_backup_root_is_rejected(tmp_path: Path) -> None:
    settings = Settings(backup_root='', accounts=[Account(email='user@example.com')])
    try:
        export_all(settings=settings, state_store=StateStore(tmp_path / 'state.json'))
    except ValueError as exc:
        assert 'پوشه مقصد' in str(exc)
    else:
        raise AssertionError('expected ValueError')
