from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


THEMES = ('auto', 'light', 'dark')

@dataclass(slots=True)
class Account:
    email: str
    server: str = 'mail.your-server.de'
    port: int = 993
    enabled: bool = True
    account_id: str = field(default_factory=lambda: uuid4().hex)
    password_token: str = ''
    last_status: str = 'هرگز اجرا نشده'
    last_run: str = ''
    archived_messages: int = 0
    archived_bytes: int = 0

    @property
    def failed(self) -> bool:
        return self.last_status.startswith('خطا')

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> 'Account':
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in value.items() if k in allowed})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Settings:
    backup_root: str = ''
    schedule_time: str = '01:00'
    scheduled: bool = False
    theme: str = 'auto'
    accounts: list[Account] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> 'Settings':
        theme = str(value.get('theme', 'auto'))
        return cls(
            backup_root=str(value.get('backup_root', '')),
            schedule_time=str(value.get('schedule_time', '01:00')),
            scheduled=bool(value.get('scheduled', False)),
            theme=theme if theme in THEMES else 'auto',
            accounts=[Account.from_dict(item) for item in value.get('accounts', [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'backup_root': self.backup_root,
            'schedule_time': self.schedule_time,
            'scheduled': self.scheduled,
            'theme': self.theme,
            'accounts': [account.to_dict() for account in self.accounts],
        }


@dataclass(slots=True)
class AccountResult:
    account_id: str
    email: str
    new_messages: int = 0
    folders: int = 0
    archived_messages: int = 0
    archived_bytes: int = 0
    success: bool = True
    error: str = ''
    finished_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec='seconds'))


@dataclass(slots=True)
class BackupResult:
    accounts: list[AccountResult] = field(default_factory=list)

    @property
    def new_messages(self) -> int:
        return sum(item.new_messages for item in self.accounts)

    @property
    def failures(self) -> int:
        return sum(not item.success for item in self.accounts)

