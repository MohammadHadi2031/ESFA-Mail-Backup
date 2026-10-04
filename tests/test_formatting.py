from __future__ import annotations

import imaplib
import socket
import ssl
from datetime import datetime

import pytest

from mailbackup.gui.formatting import (
    describe_connection_error,
    fa_datetime,
    fa_digits,
    fa_number,
    fa_size,
    gregorian_to_jalali,
    is_valid_schedule_time,
    parse_log,
)


@pytest.mark.parametrize(('gregorian', 'jalali'), [
    ((2023, 3, 21), (1402, 1, 1)),
    ((2024, 3, 20), (1403, 1, 1)),
    ((2025, 3, 20), (1403, 12, 30)),  # 1403 is a leap year
    ((2025, 3, 21), (1404, 1, 1)),
    ((2025, 12, 22), (1404, 10, 1)),
    ((2026, 10, 4), (1405, 7, 12)),
])
def test_gregorian_to_jalali(gregorian: tuple[int, int, int], jalali: tuple[int, int, int]) -> None:
    assert gregorian_to_jalali(*gregorian) == jalali


def test_persian_numbers_and_sizes() -> None:
    assert fa_digits('01:30') == '۰۱:۳۰'
    assert fa_number(1234567) == '۱٬۲۳۴٬۵۶۷'
    assert fa_size(0) == '۰ بایت'
    assert fa_size(1023) == '۱۰۲۳ بایت'
    assert fa_size(4_300_000) == '۴٫۱ مگابایت'
    assert fa_size(150 * 1024 ** 2) == '۱۵۰ مگابایت'
    assert fa_size(3 * 1024 ** 3) == '۳ گیگابایت'


def test_relative_jalali_timestamps() -> None:
    now = datetime(2026, 10, 4, 20, 0)
    assert fa_datetime('2026-10-04T18:37:24', now) == 'امروز، ۱۸:۳۷'
    assert fa_datetime('2026-10-03T01:00:00', now) == 'دیروز، ۰۱:۰۰'
    assert fa_datetime('2026-09-01T01:00:00', now) == '۱۰ شهریور، ۰۱:۰۰'
    assert fa_datetime('2025-01-01T01:00:00', now) == '۱۲ دی ۱۴۰۳، ۰۱:۰۰'
    assert fa_datetime('not a date', now) == 'not a date'


@pytest.mark.parametrize(('value', 'valid'), [
    ('00:00', True), ('01:30', True), ('23:59', True),
    ('24:00', False), ('12:60', False), ('1:30', False), ('', False), (None, False), ('ab:cd', False),
])
def test_schedule_time_validation(value: str | None, valid: bool) -> None:
    assert is_valid_schedule_time(value) is valid


def test_log_entries_keep_tracebacks_together() -> None:
    entries = parse_log([
        '2026-10-04 18:37:24,713 [INFO] Starting backup for a@example.com',
        '2026-10-04 18:37:30,001 [ERROR] Backup failed for a@example.com',
        'Traceback (most recent call last):',
        '  ConnectionResetError',
    ])
    assert [(entry.stamp, entry.level) for entry in entries] == [
        ('2026-10-04 18:37:24', 'INFO'), ('2026-10-04 18:37:30', 'ERROR'),
    ]
    assert entries[1].message.endswith('ConnectionResetError')
    assert [entry.is_problem for entry in entries] == [False, True]


@pytest.mark.parametrize(('error', 'expected'), [
    (imaplib.IMAP4.error(b'[AUTHENTICATIONFAILED] Authentication failed.'), 'نام کاربری یا رمز عبور اشتباه است.'),
    (socket.gaierror(11001, 'getaddrinfo failed'), 'سرور پیدا نشد؛ نشانی سرور IMAP و اتصال اینترنت را بررسی کنید.'),
    (ssl.SSLError(1, '[SSL: WRONG_VERSION_NUMBER] wrong version number'), 'اتصال امن (TLS) برقرار نشد؛ پورت را بررسی کنید (معمولاً 993).'),
    (TimeoutError('timed out'), 'سرور در زمان مقرر پاسخ نداد؛ نشانی سرور، پورت و اتصال اینترنت را بررسی کنید.'),
    (ConnectionRefusedError(10061, 'refused'), 'سرور اتصال را نپذیرفت؛ پورت را بررسی کنید.'),
    (imaplib.IMAP4.error(b'[UNAVAILABLE] Try later'), '[UNAVAILABLE] Try later'),
])
def test_connection_errors_are_explained(error: Exception, expected: str) -> None:
    assert describe_connection_error(error) == expected
