"""The desktop dashboard: a sidebar with overview, settings and log views."""

from __future__ import annotations

import functools
import html
import logging
import os
import queue
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from nicegui import app, events, run, ui

from .. import __version__
from ..backup_engine import BackupEngine, archive_totals, safe_component
from ..mbox_export import export_all
from ..models import THEMES, Account, Settings
from ..paths import app_data_dir, log_path
from ..scheduler import TASK_NAME, install_daily_task, remove_daily_task
from ..secrets import SecretError, protect, unprotect
from ..storage import SettingsStore
from .formatting import (
    LogEntry,
    describe_connection_error,
    fa_datetime,
    fa_digits,
    fa_number,
    fa_size,
    is_valid_schedule_time,
    parse_log,
)
from .theme import APP_CSS, QUASAR_COLORS, THEME_LABELS, THEME_VALUES


VIEWS = (
    ('dashboard', 'پیشخوان', 'space_dashboard'),
    ('settings', 'تنظیمات', 'tune'),
    ('logs', 'گزارش‌ها', 'receipt_long'),
)
AVATAR_COLORS = ('#2563eb', '#0891b2', '#7c3aed', '#db2777', '#ea580c', '#059669', '#4f46e5', '#0d9488')
LEVEL_NAMES = {'DEBUG': 'جزئیات', 'INFO': 'اطلاعات', 'WARNING': 'هشدار', 'ERROR': 'خطا', 'CRITICAL': 'بحرانی'}
LOG_LINE_LIMIT = 400
NEW_MESSAGES = re.compile(r'^(\d+) پیام جدید$')
BUTTON = 'no-caps'


@dataclass(slots=True)
class Job:
    """A running backup or MBOX export, as shown by the progress display."""

    kind: str
    emails: list[str]
    email: str = ''
    folder: str = ''
    folder_index: int = 0
    folder_total: int = 0
    message_index: int = 0
    message_total: int = 0

    @property
    def fraction(self) -> float | None:
        """Progress of the slow part: messages of the current folder, else folders of the account.

        Folders differ wildly in size (INBOX usually holds nearly everything), so weighting
        folders equally would park the bar at a few percent for most of a first backup.
        """
        if self.message_total:
            return min(1.0, self.message_index / self.message_total)
        if self.folder_total:
            return (self.folder_index - 1) / self.folder_total
        return None

    @property
    def account_position(self) -> int:
        return self.emails.index(self.email) + 1 if self.email in self.emails else 0


def open_folder(path: Path) -> None:
    if os.name == 'nt':
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', str(path)])
    else:
        subprocess.Popen(['xdg-open', str(path)])


def in_page(handler):
    """Run an async handler inside the page root rather than the slot of the element that started it.

    The triggering button often lives in a refreshable that is rebuilt while the handler awaits;
    NiceGUI would then have no slot, hence no client, for the ``ui.notify`` that follows.
    """
    @functools.wraps(handler)
    async def wrapper(self: 'Dashboard', *args, **kwargs):
        with self.root:
            return await handler(self, *args, **kwargs)
    return wrapper


def button(*args, color: str | None = None, **kwargs) -> ui.button:
    """``ui.button`` without NiceGUI's implicit primary colour, so the stylesheet decides."""
    return ui.button(*args, color=color, **kwargs)


def avatar_color(text: str) -> str:
    return AVATAR_COLORS[sum(map(ord, text.casefold())) % len(AVATAR_COLORS)]


def last_result_text(account: Account) -> str:
    match = NEW_MESSAGES.match(account.last_status)
    if not match:
        return fa_digits(account.last_status)
    count = int(match.group(1))
    return f'{fa_number(count)} پیام جدید' if count else 'بدون پیام جدید'


class Dashboard:
    def __init__(
        self,
        store: SettingsStore | None = None,
        engine: BackupEngine | None = None,
        logger: logging.Logger | None = None,
        *,
        native: bool = False,
    ) -> None:
        self.store = store or SettingsStore()
        self.logger = logger or logging.getLogger('mailbackup')
        self.engine = engine or BackupEngine(settings_store=self.store, logger=self.logger)
        self.native = native
        self.events: queue.Queue[tuple] = queue.Queue()
        self.job: Job | None = None
        self.view = 'dashboard'
        self.views: dict[str, ui.element] = {}
        self.nav: dict[str, ui.button] = {}
        self.log_filter = 'all'
        self.progress_meta: ui.element | None = None
        self.progress_bar: ui.linear_progress | None = None
        self.dark: ui.dark_mode | None = None
        self.root: ui.element | None = None

    # ------------------------------------------------------------------ layout

    def build(self) -> None:
        settings = self.store.load()
        ui.add_head_html('<meta name="color-scheme" content="light dark">')
        ui.add_css(APP_CSS)
        ui.colors(**QUASAR_COLORS)
        self.dark = ui.dark_mode(THEME_VALUES[settings.theme])
        with ui.element('div').classes('app-shell') as self.root:
            self._sidebar()
            with ui.element('main').classes('app-main'):
                for key, render in (
                    ('dashboard', self._dashboard_view),
                    ('settings', self.settings_view),
                    ('logs', self._logs_view),
                ):
                    with ui.column().classes('view') as container:
                        render()
                    self.views[key] = container
        self.show_view('dashboard')
        ui.timer(0.25, self._consume_progress)
        ui.timer(0.1, self._backfill_archive_totals, once=True)

    @in_page
    async def _backfill_archive_totals(self) -> None:
        """Archives made before totals were recorded get them counted once, in the background."""
        settings = self.store.load()
        pending = [account for account in settings.accounts if account.last_run and not account.archived_messages]
        if not settings.backup_root or not pending:
            return
        root = Path(settings.backup_root)
        totals = await run.io_bound(
            lambda: {account.account_id: archive_totals(root / safe_component(account.email)) for account in pending}
        )
        settings = self.store.load()
        changed = False
        for account in settings.accounts:
            messages, size = totals.get(account.account_id, (0, 0))
            if messages and not account.archived_messages:
                account.archived_messages, account.archived_bytes = messages, size
                changed = True
        if changed:
            self.store.save(settings)
            self._refresh_overview()

    def show_view(self, key: str) -> None:
        self.view = key
        for name, container in self.views.items():
            container.set_visibility(name == key)
        for name, button in self.nav.items():
            if name == key:
                button.classes(add='active')
            else:
                button.classes(remove='active')
        if key == 'logs':
            self.log_entries.refresh()

    def _sidebar(self) -> None:
        with ui.element('aside').classes('sidebar'):
            with ui.element('div').classes('brand'):
                with ui.element('div').classes('brand-mark'):
                    ui.icon('mark_email_read', size='22px')
                with ui.column().classes('gap-0'):
                    ui.label('ESFA Mail Backup').classes('brand-name ltr')
                    ui.label('بکاپ امن و افزایشی ایمیل').classes('brand-tagline')
            ui.label('منو').classes('nav-label')
            for key, title, icon in VIEWS:
                self.nav[key] = button(title, icon=icon, on_click=lambda k=key: self.show_view(k)) \
                    .props(f'flat {BUTTON}').classes('nav-item').mark(f'nav-{key}')
            with ui.element('div').classes('sidebar-foot'):
                self.runtime_status()
                with ui.column().classes('foot-note gap-0'):
                    ui.label('فقط به سرور IMAP شما متصل می‌شود.')
                    ui.label(f'نسخه {fa_digits(__version__)}')

    @ui.refreshable
    def runtime_status(self) -> None:
        settings = self.store.load()
        with ui.element('div').classes('runtime').mark('runtime'):
            if self.job:
                ui.icon('sync', size='18px').classes('spin text-brand')
                ui.label('در حال بکاپ‌گیری…' if self.job.kind == 'backup' else 'در حال ساخت MBOX…')
            elif settings.scheduled:
                ui.element('span').classes('dot')
                ui.label(f'بکاپ خودکار: هر روز {fa_digits(settings.schedule_time)}')
            else:
                ui.element('span').classes('dot off')
                ui.label('بکاپ خودکار خاموش است')

    def _refresh_overview(self) -> None:
        self.hero.refresh()
        self.setup_steps.refresh()
        self.stats.refresh()
        self.account_list.refresh()
        self.verification_tips.refresh()
        self.runtime_status.refresh()

    # --------------------------------------------------------------- dashboard

    def _dashboard_view(self) -> None:
        self.hero()
        self.setup_steps()
        self.stats()
        self.account_list()
        self.verification_tips()

    @ui.refreshable
    def verification_tips(self) -> None:
        settings = self.store.load()
        if not any(account.archived_messages for account in settings.accounts):
            return  # nothing backed up yet to verify
        with ui.element('div').classes('panel panel-pad').mark('verification-tips'):
            ui.label('مطمئن شوید بکاپ سالم است').classes('panel-title')
            ui.label('هر فایل دقیقاً یک پیام ایمیل استاندارد است؛ نیازی به خود برنامه برای بازبینی نیست.').classes('panel-sub')
            with ui.element('div').classes('facts mt-3'):
                for icon, text in (
                    ('mail_outline', 'روی «بازکردن پوشه» بزنید و یک فایل ‎.eml را دابل‌کلیک کنید؛ '
                     'ویندوز آن را با برنامه ایمیل پیش‌فرض (مثلاً Outlook) باز می‌کند و متن و پیوست را می‌بینید.'),
                    ('inventory_2', 'برای مرور همه پیام‌های یک پوشه در یک‌جا، «خروجی MBOX» را بزنید و فایل ساخته‌شده را '
                     'در Thunderbird ایمپورت کنید.'),
                    ('fact_check', 'تعداد «پیام‌های آرشیوشده» در آمار بالا باید با تعداد واقعی پیام‌های آن حساب روی سرور '
                     'یکی باشد؛ جزئیات هر اجرا هم در تب «گزارش‌ها» ثبت می‌شود.'),
                ):
                    with ui.element('div').classes('fact'):
                        ui.icon(icon, size='18px')
                        ui.label(text)

    def _overall_status(self, settings: Settings) -> tuple[str, str, str, str]:
        if self.job and self.job.kind == 'backup':
            return ('brand', 'autorenew', 'در حال بکاپ‌گیری…',
                    'می‌توانید در این مدت از برنامه استفاده کنید؛ پیام‌ها فقط خوانده می‌شوند و روی سرور تغییری نمی‌کنند.')
        if self.job:
            return 'brand', 'autorenew', 'در حال ساخت خروجی MBOX…', 'پیام‌های ذخیره‌شده به فایل‌های ‎.mbox تبدیل می‌شوند.'
        if not settings.backup_root or not settings.accounts:
            return ('idle', 'waving_hand', 'به ESFA Mail Backup خوش آمدید',
                    'برای شروع، پوشه مقصد را انتخاب و حساب ایمیل خود را اضافه کنید.')
        enabled = [account for account in settings.accounts if account.enabled]
        if not enabled:
            return 'warn', 'pause_circle', 'همه حساب‌ها غیرفعال هستند', 'برای بکاپ‌گیری، دست‌کم یک حساب را فعال کنید.'
        runs = [account.last_run for account in enabled if account.last_run]
        if not runs:
            return ('brand', 'cloud_download', 'آماده اولین بکاپ',
                    'در اولین اجرا همه پوشه‌ها دریافت می‌شوند؛ دفعات بعد فقط پیام‌های جدید.')
        last = fa_datetime(max(runs))
        failed = [account for account in enabled if account.failed]
        if failed:
            return ('err', 'error_outline', 'آخرین بکاپ با خطا تمام شد',
                    f'{fa_number(len(failed))} حساب خطا داشت · آخرین اجرا: {last}')
        waiting = [account for account in enabled if not account.last_run]
        if waiting:
            return ('warn', 'schedule', 'حساب جدید هنوز بکاپ نشده',
                    f'{fa_number(len(waiting))} حساب منتظر اولین بکاپ است · آخرین اجرا: {last}')
        return 'ok', 'verified', 'آرشیو به‌روز است', f'آخرین بکاپ: {last}'

    @ui.refreshable
    def hero(self) -> None:
        settings = self.store.load()
        tone, icon, title, subtitle = self._overall_status(settings)
        busy = self.job is not None
        with ui.element('div').classes('panel hero').mark('hero'):
            with ui.row().classes('w-full items-center gap-4'):
                with ui.element('div').classes(f'status-orb tone-{tone}'):
                    ui.icon(icon, size='28px').classes('spin' if busy else '')
                with ui.column().classes('gap-1 flex-1 min-w-[240px]'):
                    ui.label(title).classes('hero-title').mark('hero-title')
                    ui.label(subtitle).classes('hero-sub')
                with ui.row().classes('items-center gap-2'):
                    button('شروع بکاپ', icon='cloud_download', on_click=self.run_backup) \
                        .props(f'unelevated color=primary {BUTTON}').classes('btn btn-lg') \
                        .mark('run-backup').set_enabled(not busy)
                    button('خروجی MBOX', icon='inventory_2', on_click=self.export_mbox) \
                        .props(f'flat {BUTTON}').classes('btn btn-ghost').mark('export-mbox') \
                        .tooltip('ساخت یک فایل ‎.mbox برای هر پوشه؛ قابل ایمپورت در Thunderbird').set_enabled(not busy)
                    button(icon='folder_open', on_click=self.open_backup_folder) \
                        .props('flat').classes('btn btn-ghost').tooltip('بازکردن پوشه بکاپ')
            if busy:
                with ui.element('div').classes('progress-wrap'):
                    self.progress_meta = ui.element('div').classes('progress-meta').mark('progress')
                    with self.progress_meta:
                        ui.label('در حال اتصال…')
                    self.progress_bar = ui.linear_progress(value=0, show_value=False, size='8px') \
                        .props('rounded color=primary indeterminate').classes('progress-bar')
                self._render_progress()
            else:
                with ui.element('div').classes('dest'):
                    ui.icon('folder', size='18px')
                    ui.label('مقصد بکاپ:').classes('whitespace-nowrap')
                    if settings.backup_root:
                        ui.label(settings.backup_root).classes('path-chip ltr').tooltip(settings.backup_root)
                    else:
                        ui.label('هنوز انتخاب نشده').classes('text-warn font-semibold')
                    button('تغییر', on_click=lambda: self.show_view('settings')) \
                        .props(f'flat dense {BUTTON}').classes('link-btn')

    @ui.refreshable
    def setup_steps(self) -> None:
        settings = self.store.load()
        has_root, has_accounts = bool(settings.backup_root), bool(settings.accounts)
        steps = [
            ('پوشه مقصد', 'محل ذخیره فایل‌های بکاپ روی این سیستم یا یک درایو دیگر.',
             has_root, 'انتخاب پوشه', lambda: self.show_view('settings'), True),
            ('حساب ایمیل', 'صندوق‌هایی که باید از آن‌ها بکاپ گرفته شود.',
             has_accounts, 'افزودن حساب', lambda: self.account_dialog(), True),
            ('اولین بکاپ', 'دریافت کامل همه پوشه‌ها؛ از آن پس فقط پیام‌های جدید.',
             any(account.last_run for account in settings.accounts), 'شروع بکاپ', self.run_backup,
             has_root and has_accounts and self.job is None),
            ('بکاپ خودکار', 'اجرای روزانه در پس‌زمینه با Task Scheduler ویندوز.',
             settings.scheduled, 'تنظیم زمان‌بندی', lambda: self.show_view('settings'), True),
        ]
        done = sum(step[2] for step in steps)
        if done == len(steps):
            return
        with ui.element('div').classes('panel panel-pad').mark('setup'):
            with ui.element('div').classes('panel-head'):
                with ui.column().classes('gap-0'):
                    ui.label('راه‌اندازی در چهار گام').classes('panel-title')
                    ui.label('پس از تکمیل این مراحل، بکاپ‌ها بدون نیاز به شما انجام می‌شوند.').classes('panel-sub')
                with ui.row().classes('items-center gap-2 no-wrap'):
                    ui.label(f'{fa_digits(done)} از {fa_digits(len(steps))}').classes('text-xs muted num whitespace-nowrap')
                    with ui.element('div').classes('meter'):
                        ui.element('div').style(f'width: {done * 100 // len(steps)}%')
            with ui.element('div').classes('steps'):
                highlighted = False
                for index, (title, text, complete, action, handler, allowed) in enumerate(steps, start=1):
                    with ui.element('div').classes('step done' if complete else 'step'):
                        with ui.element('div').classes('step-num'):
                            if complete:
                                ui.icon('check', size='16px')
                            else:
                                ui.label(fa_digits(index))
                        ui.label(title).classes('step-title')
                        ui.label(text).classes('step-text')
                        if not complete:
                            primary = not highlighted and allowed
                            highlighted = highlighted or primary
                            button(action, on_click=handler) \
                                .props(f'{"unelevated color=primary" if primary else "flat"} dense {BUTTON}') \
                                .classes('btn' if primary else 'btn btn-ghost').style('min-height: 34px') \
                                .set_enabled(allowed)

    @ui.refreshable
    def stats(self) -> None:
        settings = self.store.load()
        if not settings.accounts:
            return
        enabled = sum(account.enabled for account in settings.accounts)
        messages = sum(account.archived_messages for account in settings.accounts)
        size = sum(account.archived_bytes for account in settings.accounts)
        tiles = [
            ('alternate_email', 'brand', 'حساب‌های ایمیل', fa_number(len(settings.accounts)),
             'همه فعال' if enabled == len(settings.accounts) else f'{fa_number(enabled)} حساب فعال'),
            ('mark_email_read', 'ok', 'پیام‌های آرشیوشده', fa_number(messages), 'در همه پوشه‌ها'),
            ('storage', 'brand', 'حجم آرشیو', fa_size(size), 'فایل‌های ‎.eml روی دیسک'),
            ('event_repeat', 'ok' if settings.scheduled else 'idle', 'بکاپ خودکار',
             fa_digits(settings.schedule_time) if settings.scheduled else 'خاموش',
             'هر روز' if settings.scheduled else 'از تنظیمات فعال کنید'),
        ]
        with ui.element('div').classes('stats').mark('stats'):
            for icon, tone, label, value, hint in tiles:
                with ui.element('div').classes('panel stat'):
                    with ui.element('div').classes('stat-top'):
                        ui.label(label).classes('stat-label')
                        with ui.element('div').classes(f'stat-icon tone-{tone}'):
                            ui.icon(icon, size='18px')
                    ui.label(value).classes('stat-value num')
                    ui.label(hint).classes('stat-hint')

    @ui.refreshable
    def account_list(self) -> None:
        settings = self.store.load()
        with ui.element('div').classes('page-head'):
            with ui.column().classes('gap-0'):
                ui.label('حساب‌های ایمیل').classes('panel-title text-base')
                ui.label('هر حساب جداگانه بکاپ می‌شود و خطای یک حساب جلوی بقیه را نمی‌گیرد.').classes('panel-sub')
            button('افزودن حساب', icon='add', on_click=lambda: self.account_dialog()) \
                .props(f'unelevated color=primary {BUTTON}').classes('btn').mark('add-account')
        with ui.element('div').classes('panel'):
            if not settings.accounts:
                with ui.element('div').classes('empty'):
                    with ui.element('div').classes('empty-icon'):
                        ui.icon('forward_to_inbox', size='30px')
                    ui.label('هنوز حسابی اضافه نشده است').classes('font-bold text-base')
                    ui.label('اولین صندوق ایمیل خود را اضافه کنید تا بکاپ‌گیری شروع شود.').classes('muted text-sm')
            for account in settings.accounts:
                self._account_row(account)

    def _account_row(self, account: Account) -> None:
        kind = 'err' if account.failed else ('ok' if account.last_run else 'idle')
        with ui.element('div').classes('account' if account.enabled else 'account disabled').mark(f'account:{account.email}'):
            ui.label((account.email[:1] or '@').upper()).classes('avatar').style(f'background: {avatar_color(account.email)}')
            with ui.element('div').classes('account-main'):
                ui.label(account.email).classes('account-email ltr')
                ui.label(f'{account.server}:{account.port}').classes('account-server ltr')
                with ui.element('div').classes('account-status'):
                    ui.element('span').classes(f'dot dot-{kind}')
                    if kind == 'err':
                        ui.label(account.last_status).classes('account-error').tooltip(account.last_status)
                    elif kind == 'ok':
                        ui.label(f'آخرین بکاپ {fa_datetime(account.last_run)} · {last_result_text(account)}')
                    else:
                        ui.label('هنوز بکاپ گرفته نشده')
                    if not account.enabled:
                        ui.label('غیرفعال').classes('chip chip-idle')
            if account.archived_messages:
                with ui.element('div').classes('account-meta'):
                    ui.label(f'{fa_number(account.archived_messages)} پیام').classes('font-semibold ink-2')
                    ui.label(fa_size(account.archived_bytes))
            with ui.element('div').classes('account-actions'):
                ui.switch(value=account.enabled, on_change=lambda e, a=account: self.set_enabled(a, e.value)) \
                    .props('dense color=positive').tooltip('شرکت در بکاپ‌گیری').mark('account-enabled')
                button(icon='wifi_tethering', on_click=lambda e, a=account: self.test_saved_account(a, e.sender)) \
                    .props('flat round').classes('icon-btn').tooltip('آزمایش اتصال').mark('account-test')
                button(icon='edit', on_click=lambda a=account: self.account_dialog(a)) \
                    .props('flat round').classes('icon-btn').tooltip('ویرایش').mark('account-edit')
                button(icon='delete_outline', on_click=lambda a=account: self.confirm_delete(a)) \
                    .props('flat round').classes('icon-btn danger').tooltip('حذف').mark('account-delete')

    # ---------------------------------------------------------------- settings

    @ui.refreshable
    def settings_view(self) -> None:
        settings = self.store.load()
        with ui.element('div').classes('page-head'):
            with ui.column().classes('gap-0'):
                ui.label('تنظیمات').classes('page-title')
                ui.label('محل ذخیره، زمان‌بندی و ظاهر برنامه.').classes('page-sub')

        with ui.element('div').classes('panel panel-pad'):
            ui.label('پوشه مقصد بکاپ').classes('panel-title')
            ui.label('برای هر حساب یک زیرپوشه ساخته و هر پیام به‌صورت یک فایل ‎.eml ذخیره می‌شود. '
                     'بهتر است پوشه روی درایوی غیر از ویندوز یا یک درایو شبکه باشد.').classes('panel-sub')
            with ui.element('div').classes('form-row mt-4'):
                destination = ui.input(value=settings.backup_root, placeholder=r'D:\EmailBackup') \
                    .props('outlined dense clearable').classes('field ltr-input flex-1 min-w-[260px]').mark('destination')
                button('انتخاب…', icon='folder', on_click=lambda: self.choose_folder(destination)) \
                    .props(f'flat {BUTTON}').classes('btn btn-ghost')
                button('ذخیره', icon='check', on_click=lambda: self.save_destination(destination.value)) \
                    .props(f'unelevated color=primary {BUTTON}').classes('btn').mark('save-destination')

        with ui.element('div').classes('panel panel-pad'):
            with ui.element('div').classes('panel-head'):
                ui.label('بکاپ خودکار روزانه').classes('panel-title')
                if settings.scheduled:
                    ui.label(f'فعال · هر روز {fa_digits(settings.schedule_time)}').classes('chip chip-ok').mark('schedule-state')
                else:
                    ui.label('غیرفعال').classes('chip chip-idle').mark('schedule-state')
            ui.label(f'یک وظیفه با نام «{TASK_NAME}» در Task Scheduler ویندوز ساخته می‌شود. '
                     'اگر سیستم در آن ساعت خاموش باشد، بکاپ پس از روشن‌شدن اجرا خواهد شد.').classes('panel-sub')
            with ui.element('div').classes('form-row mt-4 items-center'):
                schedule = ui.input('ساعت اجرا', value=settings.schedule_time, placeholder='01:00') \
                    .props('outlined dense mask="##:##"').classes('field ltr-input w-36').mark('schedule-time')
                button('به‌روزرسانی ساعت' if settings.scheduled else 'فعال‌سازی',
                          icon='event_available', on_click=lambda: self.enable_schedule(schedule.value)) \
                    .props(f'unelevated color=primary {BUTTON}').classes('btn').mark('enable-schedule')
                if settings.scheduled:
                    button('غیرفعال‌کردن', icon='event_busy', on_click=self.disable_schedule) \
                        .props(f'flat color=negative {BUTTON}').classes('btn').mark('disable-schedule')

        with ui.element('div').classes('panel panel-pad'):
            with ui.element('div').classes('panel-head'):
                with ui.column().classes('gap-0'):
                    ui.label('ظاهر برنامه').classes('panel-title')
                    ui.label('حالت تیره یا روشن، یا هماهنگ با تنظیمات ویندوز.').classes('panel-sub')
                ui.toggle(THEME_LABELS, value=settings.theme, on_change=self.set_theme) \
                    .props(f'unelevated {BUTTON} toggle-color=primary').classes('seg').mark('theme')

        with ui.element('div').classes('panel panel-pad'):
            ui.label('حریم خصوصی و امنیت').classes('panel-title')
            with ui.element('div').classes('facts mt-3'):
                for text in (
                    'رمزها با Windows DPAPI رمزنگاری می‌شوند و فقط همین کاربر ویندوز می‌تواند آن‌ها را بازیابی کند.',
                    'صندوق‌ها فقط‌خواندنی باز می‌شوند؛ هیچ پیامی روی سرور حذف یا «خوانده‌شده» نمی‌شود.',
                    'تنها اتصال شبکه، IMAP روی TLS به سروری است که خودتان وارد کرده‌اید.',
                    'هیچ داده یا آماری به جای دیگری ارسال نمی‌شود.',
                ):
                    with ui.element('div').classes('fact'):
                        ui.icon('verified_user', size='18px')
                        ui.label(text)
            with ui.element('div').classes('dest'):
                ui.icon('settings', size='18px')
                ui.label('تنظیمات و گزارش‌ها:').classes('whitespace-nowrap')
                ui.label(str(app_data_dir())).classes('path-chip ltr')
                button('بازکردن', on_click=lambda: self._open(app_data_dir())) \
                    .props(f'flat dense {BUTTON}').classes('link-btn')

    # -------------------------------------------------------------------- logs

    def _logs_view(self) -> None:
        with ui.element('div').classes('page-head'):
            with ui.column().classes('gap-0'):
                ui.label('گزارش‌ها').classes('page-title')
                ui.label('رویدادهای بکاپ و خطاها؛ جدیدترین در بالا.').classes('page-sub')
            with ui.row().classes('items-center gap-2'):
                ui.toggle({'all': 'همه', 'problems': 'هشدار و خطا'}, value=self.log_filter, on_change=self._set_log_filter) \
                    .props(f'unelevated {BUTTON} toggle-color=primary').classes('seg').mark('log-filter')
                button(icon='refresh', on_click=lambda: self.log_entries.refresh()) \
                    .props('flat').classes('btn btn-ghost').tooltip('تازه‌سازی')
                button(icon='folder_open', on_click=lambda: self._open(log_path().parent)) \
                    .props('flat').classes('btn btn-ghost').tooltip('بازکردن پوشه گزارش‌ها')
        self.log_entries()

    def _set_log_filter(self, event: events.ValueChangeEventArguments) -> None:
        self.log_filter = event.value or 'all'
        self.log_entries.refresh()

    @staticmethod
    def _read_log() -> list[LogEntry]:
        try:
            lines = log_path().read_text(encoding='utf-8', errors='replace').splitlines()
        except FileNotFoundError:
            return []
        except OSError as exc:
            return [LogEntry('', 'ERROR', str(exc))]
        return list(reversed(parse_log(lines[-LOG_LINE_LIMIT:])))

    @ui.refreshable
    def log_entries(self) -> None:
        entries = self._read_log()
        if self.log_filter == 'problems':
            entries = [entry for entry in entries if entry.is_problem]
        with ui.element('div').classes('panel').mark('log-panel'):
            if not entries:
                with ui.element('div').classes('empty'):
                    with ui.element('div').classes('empty-icon'):
                        ui.icon('receipt_long', size='30px')
                    ui.label('هشدار یا خطایی ثبت نشده است.' if self.log_filter == 'problems'
                             else 'هنوز گزارشی ثبت نشده است.').classes('font-bold text-base')
                    ui.label('پس از اولین بکاپ، رویدادها اینجا نمایش داده می‌شوند.').classes('muted text-sm')
                return
            rows = ''.join(
                f'<div class="log-row lvl-{entry.level.lower()}">'
                f'<span class="log-time">{html.escape(entry.stamp)}</span>'
                f'<span class="log-level">{LEVEL_NAMES.get(entry.level, html.escape(entry.level))}</span>'
                f'<pre class="log-msg">{html.escape(entry.message)}</pre></div>'
                for entry in entries
            )
            ui.html(f'<div class="log-list">{rows}</div>', sanitize=False).classes('w-full')

    # ----------------------------------------------------------------- dialogs

    def account_dialog(self, existing: Account | None = None) -> None:
        defaults = existing or Account(email='')
        # Dialogs live at the page root: the buttons that open them sit in sections that are
        # rebuilt (e.g. when a backup finishes), which would otherwise take the open dialog along.
        with self.root, ui.dialog() as dialog, ui.card().classes('w-[540px] max-w-[95vw] p-0 gap-0').mark('account-dialog'):
            dialog.on_value_change(lambda e: e.value or dialog.delete())
            with ui.row().classes('w-full items-start gap-3 no-wrap px-6 pt-6'):
                with ui.element('div').classes('stat-icon tone-brand').style('width: 42px; height: 42px; border-radius: 12px'):
                    ui.icon('alternate_email', size='22px')
                with ui.column().classes('gap-0 flex-1'):
                    ui.label('ویرایش حساب ایمیل' if existing else 'افزودن حساب ایمیل').classes('panel-title text-lg')
                    ui.label('اطلاعات ورود IMAP را وارد کنید؛ اتصال همیشه رمزنگاری‌شده (TLS) است.').classes('panel-sub')
                button(icon='close', on_click=dialog.close).props('flat round dense').classes('icon-btn')
            with ui.column().classes('w-full gap-3 px-6 pt-5'):
                email = ui.input('آدرس ایمیل یا نام کاربری', value=defaults.email) \
                    .props('outlined autofocus').classes('field ltr-input w-full').mark('account-email')
                password = ui.input(
                    'رمز عبور', password=True, password_toggle_button=True,
                    placeholder='برای حفظ رمز فعلی خالی بگذارید' if existing else '',
                ).props('outlined').classes('field ltr-input w-full').mark('account-password')
                with ui.row().classes('w-full gap-3 no-wrap'):
                    server = ui.input('سرور IMAP', value=defaults.server) \
                        .props('outlined').classes('field ltr-input flex-1').mark('account-server')
                    port = ui.number('پورت', value=defaults.port, min=1, max=65535,
                                     format='%.0f').props('outlined').classes('field ltr-input w-28').mark('account-port')
                ui.label('برای Hetzner Mail: سرور mail.your-server.de و پورت 993').classes('text-xs muted')
                enabled = ui.switch('در بکاپ‌گیری شرکت کند', value=defaults.enabled) \
                    .props('color=positive')
                banner = ui.element('div').classes('banner').mark('account-banner')
                banner.set_visibility(False)

            def show_banner(success: bool, text: str) -> None:
                banner.clear()
                banner.classes(replace=f'banner banner-{"ok" if success else "err"}')
                with banner:
                    ui.icon('check_circle' if success else 'error_outline', size='20px')
                    ui.label(text).classes('flex-1')
                banner.set_visibility(True)

            def read_form() -> Account | None:
                address = (email.value or '').strip()
                host = (server.value or '').strip()
                if not address or not host or not port.value:
                    ui.notify('ایمیل، سرور و پورت را وارد کنید.', type='warning')
                    return None
                if not 1 <= int(port.value) <= 65535:
                    ui.notify('شماره پورت معتبر نیست.', type='warning')
                    return None
                return Account(email=address, server=host, port=int(port.value), enabled=bool(enabled.value))

            async def test_form() -> None:
                candidate = read_form()
                if candidate is None:
                    return
                try:
                    secret = password.value or (unprotect(existing.password_token) if existing else '')
                except SecretError as exc:
                    show_banner(False, str(exc))
                    return
                if not secret:
                    ui.notify('برای آزمایش، رمز عبور را وارد کنید.', type='warning')
                    return
                banner.set_visibility(False)
                test_button.props('loading')
                try:
                    await run.io_bound(self.engine.test_connection, candidate, secret)
                except Exception as exc:
                    self.logger.warning('Connection test failed for %s: %s', candidate.email, exc)
                    outcome = (False, describe_connection_error(exc))
                else:
                    outcome = (True, 'اتصال برقرار شد و ورود با موفقیت انجام شد.')
                if dialog.is_deleted:  # closed while the test was running
                    return
                test_button.props(remove='loading')
                show_banner(*outcome)

            def save_account() -> None:
                candidate = read_form()
                if candidate is None:
                    return
                if not existing and not password.value:
                    ui.notify('رمز عبور را وارد کنید.', type='warning')
                    return
                settings = self.store.load()
                if any(
                    item.email.casefold() == candidate.email.casefold()
                    and item.server.casefold() == candidate.server.casefold()
                    and (existing is None or item.account_id != existing.account_id)
                    for item in settings.accounts
                ):
                    ui.notify('این حساب قبلاً اضافه شده است.', type='warning')
                    return
                try:
                    token = protect(password.value) if password.value else existing.password_token  # type: ignore[union-attr]
                except Exception as exc:
                    ui.notify(str(exc), type='negative')
                    return
                if existing:
                    target = next((item for item in settings.accounts if item.account_id == existing.account_id), None)
                    if target is None:
                        ui.notify('حساب موردنظر پیدا نشد.', type='negative')
                        return
                    target.email, target.server, target.port = candidate.email, candidate.server, candidate.port
                    target.enabled, target.password_token = candidate.enabled, token
                else:
                    candidate.password_token = token
                    settings.accounts.append(candidate)
                self.store.save(settings)
                ui.notify(f'حساب {candidate.email} ذخیره شد.', type='positive')
                self._refresh_overview()
                dialog.close()  # last: closing deletes the dialog and with it this handler's slot

            password.on('keydown.enter', save_account)
            with ui.row().classes('w-full items-center gap-2 px-6 py-5'):
                test_button = button('آزمایش اتصال', icon='wifi_tethering', on_click=test_form) \
                    .props(f'flat {BUTTON}').classes('btn btn-ghost').mark('account-test-form')
                ui.space()
                button('انصراف', on_click=dialog.close).props(f'flat {BUTTON}').classes('btn')
                button('ذخیره', icon='check', on_click=save_account) \
                    .props(f'unelevated color=primary {BUTTON}').classes('btn').mark('account-save')
        dialog.open()

    def confirm_delete(self, account: Account) -> None:
        with self.root, ui.dialog() as dialog, ui.card().classes('w-[440px] max-w-[95vw] p-6 items-center gap-2').mark('delete-dialog'):
            dialog.on_value_change(lambda e: e.value or dialog.delete())
            with ui.element('div').classes('empty-icon tone-err'):
                ui.icon('delete_outline', size='30px')
            ui.label('این حساب از برنامه حذف شود؟').classes('panel-title text-lg')
            ui.label(account.email).classes('ltr muted')
            ui.label('فایل‌های بکاپ‌شده روی دیسک باقی می‌مانند و حذف نمی‌شوند.').classes('text-xs muted text-center')

            def remove() -> None:
                settings = self.store.load()
                settings.accounts = [item for item in settings.accounts if item.account_id != account.account_id]
                self.store.save(settings)
                ui.notify(f'حساب {account.email} حذف شد.', type='info')
                self._refresh_overview()
                dialog.close()

            with ui.row().classes('w-full justify-center gap-2 mt-3'):
                button('انصراف', on_click=dialog.close).props(f'flat {BUTTON}').classes('btn')
                button('حذف حساب', icon='delete', on_click=remove) \
                    .props(f'unelevated color=negative {BUTTON}').classes('btn').mark('confirm-delete')
        dialog.open()

    # ----------------------------------------------------------------- actions

    def set_enabled(self, account: Account, value: bool) -> None:
        settings = self.store.load()
        for item in settings.accounts:
            if item.account_id == account.account_id:
                item.enabled = bool(value)
        self.store.save(settings)
        self._refresh_overview()

    @in_page
    async def test_saved_account(self, account: Account, trigger: ui.button | None = None) -> None:
        if trigger:
            trigger.props('loading')
        try:
            secret = unprotect(account.password_token)
            await run.io_bound(self.engine.test_connection, account, secret)
        except Exception as exc:
            ui.notify(f'اتصال {account.email} ناموفق بود: {describe_connection_error(exc)}', type='negative', multi_line=True)
        else:
            ui.notify(f'اتصال {account.email} برقرار است.', type='positive')
        finally:
            if trigger and not trigger.is_deleted:
                trigger.props(remove='loading')

    def save_destination(self, value: str | None) -> None:
        path = (value or '').strip().strip('"')
        if not path:
            ui.notify('مسیر پوشه مقصد را وارد کنید.', type='warning')
            return
        if not Path(path).is_absolute():
            ui.notify(r'مسیر کامل پوشه را وارد کنید؛ مثلاً D:\EmailBackup', type='warning')
            return
        settings = self.store.load()
        settings.backup_root = path
        self.store.save(settings)
        ui.notify('پوشه مقصد ذخیره شد.', type='positive')
        self._refresh_overview()
        self.settings_view.refresh()

    @in_page
    async def enable_schedule(self, value: str | None) -> None:
        value = (value or '').strip()
        if not is_valid_schedule_time(value):
            ui.notify('ساعت را به‌صورت ۲۴ ساعته وارد کنید؛ مثلاً 01:30', type='warning')
            return
        try:
            await run.io_bound(install_daily_task, value)
        except Exception:
            self.logger.exception('Could not register the scheduled task')
            ui.notify('فعال‌سازی زمان‌بندی ناموفق بود؛ جزئیات در بخش گزارش‌ها ثبت شد.', type='negative', multi_line=True)
            return
        settings = self.store.load()
        settings.schedule_time, settings.scheduled = value, True
        self.store.save(settings)
        ui.notify(f'بکاپ خودکار فعال شد؛ هر روز ساعت {fa_digits(value)}.', type='positive')
        self._refresh_overview()
        self.settings_view.refresh()

    @in_page
    async def disable_schedule(self) -> None:
        try:
            await run.io_bound(remove_daily_task)
        except Exception:
            self.logger.exception('Could not remove the scheduled task')
            ui.notify('غیرفعال‌کردن زمان‌بندی ناموفق بود؛ جزئیات در بخش گزارش‌ها ثبت شد.', type='negative')
            return
        settings = self.store.load()
        settings.scheduled = False
        self.store.save(settings)
        ui.notify('بکاپ خودکار غیرفعال شد.', type='info')
        self._refresh_overview()
        self.settings_view.refresh()

    def set_theme(self, event: events.ValueChangeEventArguments) -> None:
        theme = event.value if event.value in THEMES else 'auto'
        if self.dark is not None:
            self.dark.set_value(THEME_VALUES[theme])
        settings = self.store.load()
        settings.theme = theme
        self.store.save(settings)

    @in_page
    async def choose_folder(self, target: ui.input) -> None:
        if not self.native:
            ui.notify('در حالت مرورگر، مسیر پوشه را در کادر بنویسید.', type='info')
            return
        import webview

        current = (target.value or '').strip()
        try:
            # The native window lives in a separate process; this proxies the call to it.
            selected = await app.native.main_window.create_file_dialog(  # type: ignore[union-attr]
                dialog_type=webview.FileDialog.FOLDER,
                directory=current if current and Path(current).is_dir() else '',
            )
        except Exception:
            self.logger.exception('Folder picker failed')
            ui.notify('پنجره انتخاب پوشه باز نشد؛ مسیر را در کادر بنویسید.', type='warning')
            return
        if selected:
            target.value = selected[0]

    def open_backup_folder(self) -> None:
        root = self.store.load().backup_root
        if not root:
            ui.notify('ابتدا پوشه مقصد را در تنظیمات انتخاب کنید.', type='warning')
            self.show_view('settings')
            return
        Path(root).mkdir(parents=True, exist_ok=True)
        self._open(Path(root))

    def _open(self, path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
            open_folder(path)
        except OSError as exc:
            ui.notify(str(exc), type='negative')

    # ------------------------------------------------------------ backup jobs

    @in_page
    async def run_backup(self) -> None:
        if self.job:
            return
        settings = self.store.load()
        if not settings.backup_root:
            ui.notify('ابتدا پوشه مقصد بکاپ را انتخاب کنید.', type='warning')
            self.show_view('settings')
            return
        emails = [account.email for account in settings.accounts if account.enabled]
        if not emails:
            ui.notify('هیچ حساب فعالی برای بکاپ وجود ندارد.', type='warning')
            return
        self._start_job('backup', emails)
        try:
            result = await run.io_bound(
                self.engine.run_all,
                lambda email, folder, index, total: self.events.put(('folder', email, folder, index, total)),
                lambda index, total: self.events.put(('message', index, total)),
            )
        except Exception as exc:
            ui.notify(str(exc), type='negative', multi_line=True)
        else:
            if result.failures:
                ui.notify(f'بکاپ تمام شد، اما {fa_number(result.failures)} حساب خطا داشت؛ جزئیات در گزارش‌ها.',
                          type='warning', multi_line=True)
            elif result.new_messages:
                ui.notify(f'بکاپ کامل شد؛ {fa_number(result.new_messages)} پیام جدید ذخیره شد.', type='positive')
            else:
                ui.notify('بکاپ کامل شد؛ پیام جدیدی وجود نداشت و آرشیو به‌روز است.', type='positive')
        finally:
            self._finish_job()

    @in_page
    async def export_mbox(self) -> None:
        if self.job:
            return
        settings = self.store.load()
        self._start_job('export', [account.email for account in settings.accounts])
        try:
            result = await run.io_bound(
                export_all, None,
                lambda email, folder, index, total: self.events.put(('folder', email, folder, index, total)),
                self.store, None, self.logger,
            )
        except Exception as exc:
            ui.notify(str(exc), type='negative', multi_line=True)
        else:
            if result.files:
                ui.notify(f'{fa_number(result.files)} فایل MBOX شامل {fa_number(result.messages)} پیام ساخته شد.',
                          type='positive')
                self._open(result.root)
            else:
                ui.notify('پیام ذخیره‌شده‌ای برای تبدیل پیدا نشد؛ ابتدا یک بار بکاپ بگیرید.', type='warning')
            for error in result.errors:
                ui.notify(error, type='negative', multi_line=True)
        finally:
            self._finish_job()

    def _drain_events(self) -> list[tuple]:
        drained = []
        while True:
            try:
                drained.append(self.events.get_nowait())
            except queue.Empty:
                return drained

    def _start_job(self, kind: str, emails: list[str]) -> None:
        self._drain_events()
        self.job = Job(kind=kind, emails=emails)
        self.hero.refresh()
        self.setup_steps.refresh()
        self.runtime_status.refresh()

    def _finish_job(self) -> None:
        # Progress events still queued belong to the finished job; drop them so they
        # cannot overwrite the final status (the old UI showed a stale folder here).
        self.job = None
        self._drain_events()
        self.progress_meta = self.progress_bar = None
        self._refresh_overview()
        if self.view == 'logs':
            self.log_entries.refresh()

    def _consume_progress(self) -> None:
        if not self.job:
            return
        drained = self._drain_events()
        for event in drained:
            if event[0] == 'folder':
                _, self.job.email, self.job.folder, self.job.folder_index, self.job.folder_total = event
                self.job.message_index = self.job.message_total = 0
            else:
                _, self.job.message_index, self.job.message_total = event
        if drained:
            self._render_progress()

    def _render_progress(self) -> None:
        job = self.job
        if job is None or self.progress_meta is None or not job.email:
            return
        fraction = job.fraction
        self.progress_meta.clear()
        with self.progress_meta:
            if len(job.emails) > 1:
                ui.label(f'حساب {fa_digits(job.account_position)} از {fa_digits(len(job.emails))}').classes('num')
                ui.label('·').classes('sep')
            ui.label(job.email).classes('ltr font-semibold')
            ui.label('·').classes('sep')
            ui.label(job.folder).classes('ltr')
            ui.label('·').classes('sep')
            ui.label(f'پوشه {fa_digits(job.folder_index)} از {fa_digits(job.folder_total)}').classes('num')
            if job.message_total:
                ui.label('·').classes('sep')
                ui.label(f'پیام {fa_number(job.message_index)} از {fa_number(job.message_total)}').classes('num')
            if fraction is not None:
                ui.label(f'{fa_digits(round(fraction * 100))}٪').classes('progress-pct num')
        if fraction is not None and self.progress_bar is not None:
            self.progress_bar.props(remove='indeterminate')
            self.progress_bar.set_value(fraction)
