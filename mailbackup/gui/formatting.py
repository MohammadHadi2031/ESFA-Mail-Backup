"""Persian presentation helpers: digits, sizes, Jalali dates and log parsing."""

from __future__ import annotations

import re
import socket
import ssl
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable


PERSIAN_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
JALALI_MONTHS = (
    'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
    'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند',
)
SIZE_UNITS = ('بایت', 'کیلوبایت', 'مگابایت', 'گیگابایت', 'ترابایت')
SCHEDULE_TIME = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
LOG_LINE = re.compile(r'^(?P<stamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[(?P<level>[A-Z]+)\] (?P<message>.*)$')
PROBLEM_LEVELS = ('WARNING', 'ERROR', 'CRITICAL')


def fa_digits(value: object) -> str:
    return str(value).translate(PERSIAN_DIGITS)


def fa_number(value: int) -> str:
    return fa_digits(f'{value:,}').replace(',', '٬')


def fa_size(num_bytes: int) -> str:
    size = float(max(num_bytes, 0))
    unit = 0
    while size >= 1024 and unit < len(SIZE_UNITS) - 1:
        size /= 1024
        unit += 1
    text = f'{size:.0f}' if unit == 0 or size >= 100 else f'{size:.1f}'.removesuffix('.0')
    return f'{fa_digits(text).replace(".", "٫")} {SIZE_UNITS[unit]}'


def gregorian_to_jalali(year: int, month: int, day: int) -> tuple[int, int, int]:
    """Arithmetic Gregorian → Solar Hijri conversion (accurate for the modern era)."""
    month_offsets = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    leap_year = year + 1 if month > 2 else year
    days = (
        355666 + 365 * year + (leap_year + 3) // 4 - (leap_year + 99) // 100
        + (leap_year + 399) // 400 + day + month_offsets[month - 1]
    )
    jalali_year = -1595 + 33 * (days // 12053)
    days %= 12053
    jalali_year += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jalali_year += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jalali_year, 1 + days // 31, 1 + days % 31
    return jalali_year, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def fa_date(value: date, today: date | None = None) -> str:
    today = today or date.today()
    if value == today:
        return 'امروز'
    if value == today - timedelta(days=1):
        return 'دیروز'
    year, month, day = gregorian_to_jalali(value.year, value.month, value.day)
    text = f'{fa_digits(day)} {JALALI_MONTHS[month - 1]}'
    if year != gregorian_to_jalali(today.year, today.month, today.day)[0]:
        text += f' {fa_digits(year)}'
    return text


def fa_datetime(value: str, now: datetime | None = None) -> str:
    """Render an ISO timestamp as e.g. «امروز، ۱۸:۳۷» or «۱۲ مهر، ۰۱:۰۰»."""
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    now = now or datetime.now()
    return f'{fa_date(moment.date(), now.date())}، {fa_digits(moment.strftime("%H:%M"))}'


def describe_connection_error(exc: BaseException) -> str:
    """Turn a raw imaplib/socket/ssl failure into an actionable Persian sentence."""
    if isinstance(exc, socket.gaierror):
        return 'سرور پیدا نشد؛ نشانی سرور IMAP و اتصال اینترنت را بررسی کنید.'
    if isinstance(exc, ssl.SSLCertVerificationError):
        return 'گواهی امنیتی سرور معتبر نیست؛ به همین دلیل اتصال برقرار نشد.'
    if isinstance(exc, ssl.SSLError):
        return 'اتصال امن (TLS) برقرار نشد؛ پورت را بررسی کنید (معمولاً 993).'
    if isinstance(exc, TimeoutError):
        return 'سرور در زمان مقرر پاسخ نداد؛ نشانی سرور، پورت و اتصال اینترنت را بررسی کنید.'
    if isinstance(exc, ConnectionRefusedError):
        return 'سرور اتصال را نپذیرفت؛ پورت را بررسی کنید.'
    text = str(exc)
    if text.startswith(("b'", 'b"')):
        text = text[2:-1]
    lowered = text.lower()
    if any(marker in lowered for marker in ('authenticationfailed', 'authentication failed', 'login failed', 'invalid credentials')):
        return 'نام کاربری یا رمز عبور اشتباه است.'
    return text


def is_valid_schedule_time(value: str | None) -> bool:
    return bool(value and SCHEDULE_TIME.match(value.strip()))


@dataclass(slots=True)
class LogEntry:
    stamp: str
    level: str
    message: str

    @property
    def is_problem(self) -> bool:
        return self.level in PROBLEM_LEVELS


def parse_log(lines: Iterable[str]) -> list[LogEntry]:
    """Group raw log lines into entries; traceback lines stay with the entry above them."""
    entries: list[LogEntry] = []
    for line in lines:
        match = LOG_LINE.match(line)
        if match:
            entries.append(LogEntry(match['stamp'], match['level'], match['message']))
        elif entries:
            entries[-1].message += '\n' + line
        elif line.strip():
            entries.append(LogEntry('', 'INFO', line))
    return entries
