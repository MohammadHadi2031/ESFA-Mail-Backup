from __future__ import annotations

import argparse
import multiprocessing
import os
import queue
import subprocess
import sys
from pathlib import Path

from mailbackup.backup_engine import BackupEngine
from mailbackup.logging_setup import configure_logging
from mailbackup.mbox_export import export_all
from mailbackup.models import Account
from mailbackup.paths import log_path
from mailbackup.scheduler import install_daily_task, remove_daily_task
from mailbackup.secrets import protect
from mailbackup.storage import SettingsStore, ensure_app_directories


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--run-backup', action='store_true')
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--port', type=int, default=8765)
    arguments, _ = parser.parse_known_args()
    return arguments


ARGS = parse_arguments()
ensure_app_directories()
LOGGER = configure_logging()


def run_headless() -> int:
    try:
        result = BackupEngine(logger=LOGGER).run_all()
        return 1 if result.failures else 0
    except Exception:
        LOGGER.exception('Scheduled backup failed')
        return 1


if ARGS.run_backup:
    raise SystemExit(run_headless())


from nicegui import run, ui  # noqa: E402


APP_CSS = r'''
:root {
  --brand: #2563eb;
  --brand-2: #0ea5e9;
  --ink: #0f172a;
  --muted: #64748b;
  --surface: rgba(255, 255, 255, .88);
}
html, body { direction: rtl; font-family: Tahoma, "Segoe UI", sans-serif; color: var(--ink); }
body { background: radial-gradient(circle at 85% 5%, #dbeafe 0, transparent 28%), radial-gradient(circle at 10% 90%, #cffafe 0, transparent 30%), #f8fafc; }
.q-page { min-height: 100vh !important; }
.topbar { background: rgba(255,255,255,.78); backdrop-filter: blur(18px); border-bottom: 1px solid rgba(148,163,184,.20); }
.brand-mark { width: 44px; height: 44px; border-radius: 14px; display: grid; place-items: center; color: white; background: linear-gradient(135deg, var(--brand), var(--brand-2)); box-shadow: 0 12px 30px rgba(37,99,235,.28); }
.page-shell { width: min(1180px, calc(100vw - 34px)); margin: 0 auto; padding: 24px 0 34px; }
.hero { border: 1px solid rgba(148,163,184,.18); background: linear-gradient(135deg, rgba(255,255,255,.96), rgba(239,246,255,.90)); box-shadow: 0 22px 55px rgba(15,23,42,.08); border-radius: 24px; padding: 25px 28px; }
.glass-card { background: var(--surface); border: 1px solid rgba(148,163,184,.18); box-shadow: 0 14px 36px rgba(15,23,42,.06); border-radius: 20px; }
.stat-card { min-height: 118px; padding: 18px 20px; }
.stat-icon { width: 42px; height: 42px; border-radius: 14px; display: grid; place-items: center; }
.section-title { font-size: 18px; font-weight: 800; letter-spacing: -.2px; }
.muted { color: var(--muted); }
.account-row { transition: transform .18s ease, box-shadow .18s ease; }
.account-row:hover { transform: translateY(-2px); box-shadow: 0 18px 42px rgba(15,23,42,.09); }
.soft-input .q-field__control { border-radius: 13px !important; background: #fff; }
.primary-button { border-radius: 13px; padding: 8px 18px; font-weight: 700; box-shadow: 0 10px 22px rgba(37,99,235,.20); }
.secondary-button { border-radius: 13px; padding: 8px 16px; font-weight: 700; }
.q-tab { border-radius: 12px; min-height: 42px; }
.q-tab--active { background: #eff6ff; }
.q-dialog__inner > div { border-radius: 22px !important; }
.log-box { direction: ltr; text-align: left; background: #0b1220; color: #cbd5e1; border-radius: 16px; padding: 16px; font-family: Consolas, monospace; font-size: 12px; white-space: pre-wrap; max-height: 340px; overflow: auto; }
@media (max-width: 720px) { .page-shell { width: calc(100vw - 20px); } .hero { padding: 20px; } }
'''


class Dashboard:
    def __init__(self) -> None:
        self.store = SettingsStore()
        self.engine = BackupEngine(settings_store=self.store, logger=LOGGER)
        self.progress_events: queue.Queue[tuple[str, str, int, int]] = queue.Queue()
        self.backup_running = False
        self.progress_label = None
        self.progress_bar = None
        self.run_button = None
        self.export_button = None

    def build(self) -> None:
        ui.add_head_html('<meta name="color-scheme" content="light"><meta name="theme-color" content="#f8fafc">')
        ui.add_css(APP_CSS)
        ui.colors(primary='#2563eb', secondary='#0ea5e9', accent='#14b8a6', positive='#16a34a', negative='#dc2626')

        with ui.header().classes('topbar h-[72px] items-center px-5'):
            with ui.row().classes('w-full max-w-[1180px] mx-auto items-center justify-between no-wrap'):
                with ui.row().classes('items-center gap-3 no-wrap'):
                    with ui.element('div').classes('brand-mark'):
                        ui.icon('mark_email_read', size='26px')
                    with ui.column().classes('gap-0'):
                        ui.label('ESFA Mail Backup').classes('text-base font-bold')
                        ui.label('بکاپ امن و افزایشی ایمیل').classes('text-xs muted')
                ui.badge('نسخه ۱.۰').props('outline color=primary').classes('px-3 py-2 rounded-xl')

        with ui.column().classes('page-shell gap-5'):
            self._hero()
            self.stats()
            with ui.tabs().classes('w-full bg-white/70 rounded-2xl p-1 shadow-sm') as tabs:
                accounts_tab = ui.tab('حساب‌های ایمیل', icon='alternate_email')
                settings_tab = ui.tab('تنظیمات و زمان‌بندی', icon='tune')
                logs_tab = ui.tab('گزارش‌ها', icon='receipt_long')
            with ui.tab_panels(tabs, value=accounts_tab).classes('w-full bg-transparent p-0'):
                with ui.tab_panel(accounts_tab).classes('p-0 pt-2'):
                    self.account_cards()
                with ui.tab_panel(settings_tab).classes('p-0 pt-2'):
                    self.settings_panel()
                with ui.tab_panel(logs_tab).classes('p-0 pt-2'):
                    self.logs_panel()

        ui.timer(0.25, self._consume_progress)

    def _hero(self) -> None:
        with ui.row().classes('hero w-full items-center justify-between gap-5'):
            with ui.column().classes('gap-2'):
                ui.label('آرشیو ایمیل‌ها، بدون نگرانی').classes('text-2xl md:text-3xl font-black')
                ui.label('همه پوشه‌ها را یک‌بار دریافت کنید؛ دفعات بعد فقط تغییرات جدید ذخیره می‌شوند.').classes('muted text-sm md:text-base')
                self.progress_label = ui.label('آماده اجرای بکاپ').classes('text-xs text-blue-700 font-bold mt-2')
                self.progress_bar = ui.linear_progress(value=0, show_value=False).props('rounded color=primary track-color=blue-1').classes('w-72')
                self.progress_bar.set_visibility(False)
            with ui.row().classes('items-center gap-2'):
                self.run_button = ui.button('شروع بکاپ', icon='cloud_download', on_click=self.run_backup).props('unelevated color=primary').classes('primary-button')
                self.export_button = ui.button('خروجی MBOX', icon='archive', on_click=self.export_mbox).props('outline color=primary').classes('secondary-button').tooltip('ساخت فایل‌های .mbox از بکاپ‌های ذخیره‌شده')
                ui.button('بازکردن پوشه', icon='folder_open', on_click=self.open_backup_folder).props('outline color=primary').classes('secondary-button')

    @ui.refreshable
    def stats(self) -> None:
        settings = self.store.load()
        active = sum(account.enabled for account in settings.accounts)
        successful = sum(bool(account.last_run) and not account.last_status.startswith('خطا') for account in settings.accounts)
        values = [
            ('mail', str(len(settings.accounts)), 'حساب ثبت‌شده', 'bg-blue-50 text-blue-600'),
            ('verified_user', str(active), 'حساب فعال', 'bg-emerald-50 text-emerald-600'),
            ('task_alt', str(successful), 'آخرین اجرای موفق', 'bg-violet-50 text-violet-600'),
            ('schedule', settings.schedule_time, 'زمان اجرای روزانه', 'bg-amber-50 text-amber-600'),
        ]
        with ui.row().classes('w-full grid grid-cols-2 lg:grid-cols-4 gap-3'):
            for icon, value, label, colors in values:
                with ui.card().classes('glass-card stat-card w-full'):
                    with ui.row().classes('items-center justify-between w-full no-wrap'):
                        with ui.column().classes('gap-1'):
                            ui.label(value).classes('text-2xl font-black')
                            ui.label(label).classes('text-xs muted')
                        with ui.element('div').classes(f'stat-icon {colors}'):
                            ui.icon(icon, size='23px')

    @ui.refreshable
    def account_cards(self) -> None:
        settings = self.store.load()
        with ui.column().classes('w-full gap-3'):
            with ui.row().classes('w-full items-center justify-between'):
                with ui.column().classes('gap-0'):
                    ui.label('حساب‌های ایمیل').classes('section-title')
                    ui.label('صندوق‌هایی که باید بکاپ‌گیری شوند را مدیریت کنید.').classes('text-xs muted')
                ui.button('افزودن حساب', icon='add', on_click=lambda: self.account_dialog()).props('unelevated color=primary').classes('primary-button')
            if not settings.accounts:
                with ui.card().classes('glass-card w-full items-center py-12'):
                    ui.icon('mark_email_unread', size='56px').classes('text-blue-200')
                    ui.label('هنوز حسابی اضافه نشده است').classes('font-bold text-lg')
                    ui.label('اولین حساب ایمیل خود را اضافه کنید.').classes('muted text-sm')
            for account in settings.accounts:
                status_color = 'positive' if account.last_run and not account.last_status.startswith('خطا') else ('negative' if account.last_status.startswith('خطا') else 'grey')
                with ui.card().classes('glass-card account-row w-full p-5'):
                    with ui.row().classes('w-full items-center justify-between gap-4'):
                        with ui.row().classes('items-center gap-4 min-w-0'):
                            with ui.avatar(icon='alternate_email', color='blue-1', text_color='primary').classes('shadow-sm'):
                                pass
                            with ui.column().classes('gap-1 min-w-0'):
                                ui.label(account.email).classes('font-bold truncate')
                                ui.label(f'{account.server}:{account.port}').classes('text-xs muted')
                                with ui.row().classes('items-center gap-2'):
                                    ui.badge('فعال' if account.enabled else 'غیرفعال', color='positive' if account.enabled else 'grey').props('rounded')
                                    ui.badge(account.last_status, color=status_color).props('outline rounded').classes('max-w-64 truncate')
                        with ui.row().classes('items-center gap-1'):
                            ui.button(icon='wifi_tethering', on_click=lambda a=account: self.test_saved_account(a)).props('flat round color=primary').tooltip('آزمایش اتصال')
                            ui.button(icon='edit', on_click=lambda a=account: self.account_dialog(a)).props('flat round color=grey-7').tooltip('ویرایش')
                            ui.button(icon='delete_outline', on_click=lambda a=account: self.confirm_delete(a)).props('flat round color=negative').tooltip('حذف')

    @ui.refreshable
    def settings_panel(self) -> None:
        settings = self.store.load()
        with ui.card().classes('glass-card w-full p-6'):
            ui.label('تنظیمات بکاپ').classes('section-title')
            ui.label('پوشه مقصد و زمان اجرای خودکار روزانه را تعیین کنید.').classes('text-xs muted mb-3')
            with ui.column().classes('w-full gap-4'):
                with ui.row().classes('w-full items-end gap-2 no-wrap'):
                    destination = ui.input('پوشه مقصد', value=settings.backup_root, placeholder=r'D:\EmailBackup').props('outlined').classes('soft-input flex-grow')
                    ui.button('انتخاب', icon='folder', on_click=lambda: self.choose_folder(destination)).props('outline color=primary').classes('secondary-button')
                schedule = ui.input('ساعت اجرای روزانه', value=settings.schedule_time, placeholder='01:00').props('outlined mask="##:##"').classes('soft-input w-48')
                with ui.row().classes('items-center gap-3'):
                    ui.icon('info', color='primary')
                    ui.label('اگر سیستم در ساعت تعیین‌شده خاموش باشد، بکاپ پس از روشن‌شدن اجرا خواهد شد.').classes('text-xs muted')
                with ui.row().classes('gap-2 mt-2'):
                    async def save_and_schedule() -> None:
                        current = self.store.load()
                        current.backup_root = (destination.value or '').strip()
                        current.schedule_time = (schedule.value or '').strip()
                        try:
                            await run.io_bound(install_daily_task, current.schedule_time)
                            current.scheduled = True
                            self.store.save(current)
                            ui.notify('تنظیمات ذخیره و زمان‌بندی فعال شد.', type='positive')
                            self.stats.refresh()
                            self.settings_panel.refresh()
                        except Exception as exc:
                            ui.notify(str(exc), type='negative', multi_line=True)

                    async def disable_schedule() -> None:
                        try:
                            await run.io_bound(remove_daily_task)
                            current = self.store.load()
                            current.scheduled = False
                            self.store.save(current)
                            ui.notify('زمان‌بندی غیرفعال شد.', type='info')
                            self.settings_panel.refresh()
                        except Exception as exc:
                            ui.notify(str(exc), type='negative')

                    ui.button('ذخیره و فعال‌سازی', icon='event_available', on_click=save_and_schedule).props('unelevated color=primary').classes('primary-button')
                    if settings.scheduled:
                        ui.button('غیرفعال‌کردن زمان‌بندی', icon='event_busy', on_click=disable_schedule).props('outline color=negative').classes('secondary-button')
            with ui.separator().classes('my-4'):
                pass
            with ui.row().classes('items-center gap-3'):
                ui.icon('security', size='28px').classes('text-emerald-600')
                with ui.column().classes('gap-0'):
                    ui.label('ذخیره امن اطلاعات ورود').classes('font-bold')
                    ui.label('رمزها با Windows DPAPI رمزنگاری می‌شوند و فقط همین کاربر ویندوز می‌تواند آن‌ها را بازیابی کند.').classes('text-xs muted')

    @ui.refreshable
    def logs_panel(self) -> None:
        path = log_path()
        content = 'هنوز گزارشی ثبت نشده است.'
        if path.exists():
            try:
                lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
                content = '\n'.join(lines[-250:]) or content
            except OSError as exc:
                content = str(exc)
        with ui.card().classes('glass-card w-full p-6'):
            with ui.row().classes('w-full items-center justify-between'):
                with ui.column().classes('gap-0'):
                    ui.label('گزارش عملیات').classes('section-title')
                    ui.label('آخرین رویدادها و خطاهای بکاپ').classes('text-xs muted')
                with ui.row().classes('gap-1'):
                    ui.button(icon='refresh', on_click=self.logs_panel.refresh).props('flat round color=primary').tooltip('تازه‌سازی')
                    ui.button(icon='folder_open', on_click=self.open_log_folder).props('flat round color=grey-7').tooltip('بازکردن پوشه گزارش')
            ui.label(content).classes('log-box w-full mt-4')

    def account_dialog(self, existing: Account | None = None) -> None:
        with ui.dialog() as dialog, ui.card().classes('w-[520px] max-w-[95vw] p-6'):
            ui.label('ویرایش حساب ایمیل' if existing else 'افزودن حساب ایمیل').classes('text-xl font-black')
            ui.label('اطلاعات اتصال امن IMAP را وارد کنید.').classes('text-xs muted mb-2')
            email = ui.input('آدرس ایمیل / نام کاربری', value=existing.email if existing else '').props('outlined').classes('soft-input w-full')
            password = ui.input('رمز عبور', password=True, password_toggle_button=True, placeholder='برای ویرایش بدون تغییر، خالی بگذارید' if existing else '').props('outlined').classes('soft-input w-full')
            with ui.row().classes('w-full gap-3 no-wrap'):
                server = ui.input('سرور IMAP', value=existing.server if existing else 'mail.your-server.de').props('outlined').classes('soft-input flex-grow')
                port = ui.number('پورت', value=existing.port if existing else 993, min=1, max=65535, format='%.0f').props('outlined').classes('soft-input w-32')
            enabled = ui.switch('حساب فعال باشد', value=existing.enabled if existing else True).props('color=positive')

            async def test_form() -> None:
                if not email.value or not password.value:
                    ui.notify('برای آزمایش، ایمیل و رمز عبور را وارد کنید.', type='warning')
                    return
                candidate = Account(email=email.value.strip(), server=server.value.strip(), port=int(port.value))
                try:
                    await run.io_bound(self.engine.test_connection, candidate, password.value)
                    ui.notify('اتصال با موفقیت برقرار شد.', type='positive')
                except Exception as exc:
                    ui.notify(f'اتصال ناموفق: {exc}', type='negative', multi_line=True)

            def save_account() -> None:
                if not email.value or not server.value or not port.value:
                    ui.notify('ایمیل، سرور و پورت الزامی هستند.', type='warning')
                    return
                if not existing and not password.value:
                    ui.notify('رمز عبور الزامی است.', type='warning')
                    return
                try:
                    token = existing.password_token if existing and not password.value else protect(password.value)
                except Exception as exc:
                    ui.notify(str(exc), type='negative')
                    return
                settings = self.store.load()
                if existing:
                    target = next((item for item in settings.accounts if item.account_id == existing.account_id), None)
                    if not target:
                        ui.notify('حساب موردنظر پیدا نشد.', type='negative')
                        return
                    target.email = email.value.strip()
                    target.server = server.value.strip()
                    target.port = int(port.value)
                    target.enabled = bool(enabled.value)
                    target.password_token = token
                else:
                    settings.accounts.append(Account(
                        email=email.value.strip(), server=server.value.strip(), port=int(port.value),
                        enabled=bool(enabled.value), password_token=token,
                    ))
                self.store.save(settings)
                dialog.close()
                self.account_cards.refresh()
                self.stats.refresh()
                ui.notify('حساب ذخیره شد.', type='positive')

            with ui.row().classes('w-full justify-end gap-2 mt-3'):
                ui.button('انصراف', on_click=dialog.close).props('flat color=grey-7')
                ui.button('آزمایش اتصال', icon='wifi_tethering', on_click=test_form).props('outline color=primary').classes('secondary-button')
                ui.button('ذخیره', icon='save', on_click=save_account).props('unelevated color=primary').classes('primary-button')
        dialog.open()

    def confirm_delete(self, account: Account) -> None:
        with ui.dialog() as dialog, ui.card().classes('w-[430px] max-w-[95vw] p-6'):
            ui.icon('warning_amber', size='44px').classes('text-amber-500 self-center')
            ui.label('حساب از برنامه حذف شود؟').classes('text-lg font-black self-center')
            ui.label(account.email).classes('muted self-center')
            ui.label('فایل‌های بکاپ‌شده از روی دیسک حذف نمی‌شوند.').classes('text-xs muted self-center')

            def remove() -> None:
                settings = self.store.load()
                settings.accounts = [item for item in settings.accounts if item.account_id != account.account_id]
                self.store.save(settings)
                dialog.close()
                self.account_cards.refresh()
                self.stats.refresh()
                ui.notify('حساب حذف شد.', type='info')

            with ui.row().classes('w-full justify-center gap-2 mt-3'):
                ui.button('انصراف', on_click=dialog.close).props('flat')
                ui.button('حذف حساب', icon='delete', on_click=remove).props('unelevated color=negative')
        dialog.open()

    async def test_saved_account(self, account: Account) -> None:
        from mailbackup.secrets import unprotect
        try:
            password = unprotect(account.password_token)
            await run.io_bound(self.engine.test_connection, account, password)
            ui.notify(f'اتصال {account.email} موفق بود.', type='positive')
        except Exception as exc:
            ui.notify(f'اتصال ناموفق: {exc}', type='negative', multi_line=True)

    async def run_backup(self) -> None:
        if self.backup_running:
            return
        self.backup_running = True
        self.run_button.disable()
        self.export_button.disable()
        self.progress_bar.set_visibility(True)
        self.progress_bar.props('indeterminate')
        self.progress_label.set_text('در حال اتصال و بررسی صندوق‌ها...')

        def progress(email: str, folder: str, current: int, total: int) -> None:
            self.progress_events.put((email, folder, current, total))

        try:
            result = await run.io_bound(self.engine.run_all, progress)
            if result.failures:
                ui.notify(f'بکاپ تمام شد؛ {result.failures} حساب خطا داشت.', type='warning')
                self.progress_label.set_text(f'پایان با {result.failures} خطا — گزارش‌ها را بررسی کنید')
            else:
                ui.notify(f'{result.new_messages} ایمیل جدید ذخیره شد.', type='positive')
                self.progress_label.set_text(f'بکاپ موفق — {result.new_messages} پیام جدید')
        except Exception as exc:
            ui.notify(str(exc), type='negative', multi_line=True)
            self.progress_label.set_text('بکاپ ناموفق بود — گزارش‌ها را بررسی کنید')
        finally:
            self.backup_running = False
            self.run_button.enable()
            self.export_button.enable()
            self.progress_bar.set_visibility(False)
            self.account_cards.refresh()
            self.stats.refresh()
            self.logs_panel.refresh()

    async def export_mbox(self) -> None:
        if self.backup_running:
            ui.notify('تا پایان بکاپ جاری صبر کنید.', type='warning')
            return
        self.backup_running = True
        self.run_button.disable()
        self.export_button.disable()
        self.progress_bar.set_visibility(True)
        self.progress_bar.props('indeterminate')
        self.progress_label.set_text('در حال ساخت فایل‌های MBOX...')

        def progress(email: str, folder: str, current: int, total: int) -> None:
            self.progress_events.put((email, folder, current, total))

        try:
            result = await run.io_bound(export_all, None, progress, self.store, None, LOGGER)
            if not result.files:
                ui.notify('پیام ذخیره‌شده‌ای برای تبدیل پیدا نشد؛ ابتدا یک بار بکاپ بگیرید.', type='warning')
                self.progress_label.set_text('خروجی MBOX ساخته نشد')
            else:
                ui.notify(f'{result.files} فایل MBOX شامل {result.messages} پیام ساخته شد.', type='positive')
                self.progress_label.set_text(f'خروجی MBOX آماده است — {result.files} فایل در پوشه MBOX')
                self._open_folder(result.root)
            for error in result.errors:
                ui.notify(error, type='negative', multi_line=True)
        except Exception as exc:
            ui.notify(str(exc), type='negative', multi_line=True)
            self.progress_label.set_text('ساخت خروجی MBOX ناموفق بود')
        finally:
            self.backup_running = False
            self.run_button.enable()
            self.export_button.enable()
            self.progress_bar.set_visibility(False)
            self.logs_panel.refresh()

    def _consume_progress(self) -> None:
        try:
            while True:
                email, folder, current, total = self.progress_events.get_nowait()
                self.progress_label.set_text(f'{email} — {folder} ({current} از {total})')
        except queue.Empty:
            pass

    async def choose_folder(self, input_element) -> None:
        if ARGS.browser:
            ui.notify('در حالت مرورگر، مسیر پوشه را در کادر وارد کنید.', type='info')
            return

        def choose() -> str | None:
            try:
                import webview
                if not webview.windows:
                    return None
                result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
                return result[0] if result else None
            except Exception:
                return None

        selected = await run.io_bound(choose)
        if selected:
            input_element.value = selected
            input_element.update()

    def open_backup_folder(self) -> None:
        path = self.store.load().backup_root
        if not path:
            ui.notify('ابتدا پوشه مقصد را در تنظیمات انتخاب کنید.', type='warning')
            return
        Path(path).mkdir(parents=True, exist_ok=True)
        self._open_folder(Path(path))

    def open_log_folder(self) -> None:
        log_path().parent.mkdir(parents=True, exist_ok=True)
        self._open_folder(log_path().parent)

    @staticmethod
    def _open_folder(path: Path) -> None:
        try:
            if os.name == 'nt':
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(path)])
            else:
                subprocess.Popen(['xdg-open', str(path)])
        except OSError as exc:
            ui.notify(str(exc), type='negative')


@ui.page('/')
def index() -> None:
    Dashboard().build()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    run_options = dict(
        host='127.0.0.1',
        title='ESFA Mail Backup',
        native=not ARGS.browser,
        reload=False,
        port=ARGS.port,
        show=ARGS.browser,
        storage_secret='local-desktop-only',
        language='fa-IR',
    )
    if not ARGS.browser:
        run_options['window_size'] = (1180, 780)
    ui.run(**run_options)
