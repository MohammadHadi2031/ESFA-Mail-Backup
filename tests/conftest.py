from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Callable

import pytest
from nicegui import context
from nicegui.testing import User
from nicegui.testing.user_notify import UserNotify
from nicegui.testing.user_simulation import user_simulation

from mailbackup.gui import dashboard as dashboard_module
from mailbackup.gui.dashboard import Dashboard
from mailbackup.models import Account, AccountResult, BackupResult, Settings
from mailbackup.storage import SettingsStore


class FakeEngine:
    """Stands in for BackupEngine: no network, scripted results, optional pause mid-run."""

    def __init__(self, store: SettingsStore) -> None:
        self.store = store
        self.tested: list[tuple[str, str, str]] = []
        self.connection_error: Exception | None = None
        self.new_messages = 3
        self.error = ''
        self.pause = False
        self.paused = threading.Event()
        self.resume = threading.Event()

    def test_connection(self, account: Account, password: str) -> None:
        self.tested.append((account.email, account.server, password))
        if self.connection_error:
            raise self.connection_error

    def run_all(self, progress=None, message_progress=None) -> BackupResult:
        settings = self.store.load()
        result = BackupResult()
        for account in (item for item in settings.accounts if item.enabled):
            progress(account.email, 'INBOX', 1, 2)
            message_progress(2, 3)
            if self.pause:
                self.paused.set()
                assert self.resume.wait(5), 'test never resumed the backup'
            # Queued right before returning: the old UI let such late events overwrite the final status.
            progress(account.email, 'Archive', 2, 2)
            item = AccountResult(
                account_id=account.account_id, email=account.email, new_messages=self.new_messages,
                archived_messages=self.new_messages, archived_bytes=2048, success=not self.error, error=self.error,
            )
            account.last_run = item.finished_at
            account.last_status = f'{item.new_messages} پیام جدید' if item.success else f'خطا: {item.error}'
            if item.success:
                account.archived_messages, account.archived_bytes = item.archived_messages, item.archived_bytes
            result.accounts.append(item)
        self.store.save(settings)
        return result


@dataclass
class Environment:
    root: Path
    store: SettingsStore
    engine: FakeEngine
    calls: dict[str, list] = field(default_factory=lambda: {'install': [], 'remove': [], 'open': []})
    dashboards: list[Dashboard] = field(default_factory=list)
    install_error: Exception | None = None

    def seed(self, **settings_fields) -> Settings:
        settings = Settings(**settings_fields)
        self.store.save(settings)
        return settings

    @property
    def settings(self) -> Settings:
        return self.store.load()

    @property
    def dashboard(self) -> Dashboard:
        return self.dashboards[-1]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Environment:
    """Isolated app data, plus recorders for everything that would touch Windows or the network."""
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'appdata'))
    store = SettingsStore(tmp_path / 'appdata' / 'EsfaMailBackup' / 'config.json')
    environment = Environment(root=tmp_path, store=store, engine=FakeEngine(store))

    def install(time_value: str) -> None:
        if environment.install_error:
            raise environment.install_error
        environment.calls['install'].append(time_value)

    original_notify = UserNotify.__call__

    def notify_needing_a_live_slot(self: UserNotify, message: str, **kwargs) -> None:
        # The real ui.notify resolves context.client and fails once the element that started the
        # handler is deleted (e.g. a button inside a refreshed section); the simulated one would not.
        _ = context.client
        original_notify(self, message, **kwargs)

    monkeypatch.setattr(UserNotify, '__call__', notify_needing_a_live_slot)
    monkeypatch.setattr(dashboard_module, 'protect', lambda password: f'token:{password}')
    monkeypatch.setattr(dashboard_module, 'unprotect', lambda token: token.removeprefix('token:'))
    monkeypatch.setattr(dashboard_module, 'install_daily_task', install)
    monkeypatch.setattr(dashboard_module, 'remove_daily_task', lambda: environment.calls['remove'].append(True))
    monkeypatch.setattr(dashboard_module, 'open_folder', lambda path: environment.calls['open'].append(Path(path)))
    return environment


@pytest.fixture
async def user(env: Environment, caplog: pytest.LogCaptureFixture) -> AsyncIterator[User]:
    def root() -> None:
        dashboard = Dashboard(store=env.store, engine=env.engine)  # type: ignore[arg-type]
        env.dashboards.append(dashboard)
        dashboard.build()

    async with user_simulation(root=root) as simulated:
        yield simulated
    # The app's own logger records expected failures; anything NiceGUI logs as an error is a UI bug.
    errors = [r for r in caplog.get_records('call') if r.levelname == 'ERROR' and not r.name.startswith('mailbackup')]
    if errors:
        pytest.fail('UI errors were logged: ' + '; '.join(r.getMessage() for r in errors), pytrace=False)


@pytest.fixture
def account_factory(env: Environment) -> Callable[..., Account]:
    def make(email: str = 'user@example.com', **fields) -> Account:
        fields.setdefault('password_token', 'token:old-secret')
        return Account(email=email, **fields)
    return make
