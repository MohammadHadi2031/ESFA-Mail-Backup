"""UI tests: a simulated user drives the real dashboard; Windows and IMAP are faked (see conftest)."""

from __future__ import annotations

import asyncio
import imaplib
from pathlib import Path

from nicegui import ui
from nicegui.testing import User

from mailbackup.backup_engine import safe_component


async def open_settings(user: User) -> None:
    await user.open('/')
    user.find(marker='nav-settings').click()
    await user.should_see('محل ذخیره، زمان‌بندی و ظاهر برنامه.')


# ------------------------------------------------------------------ first run

async def test_first_run_greets_and_lists_setup_steps(user: User) -> None:
    await user.open('/')
    await user.should_see('ESFA Mail Backup')
    await user.should_see('به ESFA Mail Backup خوش آمدید')
    await user.should_see('راه‌اندازی در چهار گام')
    await user.should_see('هنوز حسابی اضافه نشده است')
    await user.should_see('بکاپ خودکار خاموش است')
    await user.should_not_see(marker='stats')


async def test_sidebar_switches_between_views(user: User) -> None:
    await user.open('/')
    await user.should_not_see('محل ذخیره، زمان‌بندی و ظاهر برنامه.')
    user.find(marker='nav-settings').click()
    await user.should_see('محل ذخیره، زمان‌بندی و ظاهر برنامه.')
    await user.should_not_see('راه‌اندازی در چهار گام')
    user.find(marker='nav-logs').click()
    await user.should_see('هنوز گزارشی ثبت نشده است.')
    user.find(marker='nav-dashboard').click()
    await user.should_see('راه‌اندازی در چهار گام')


async def test_setup_steps_disappear_once_everything_is_configured(user: User, env, account_factory) -> None:
    env.seed(backup_root=str(env.root / 'backup'), scheduled=True,
             accounts=[account_factory(last_run='2026-01-01T01:00:00', last_status='4 پیام جدید')])
    await user.open('/')
    await user.should_not_see(marker='setup')
    await user.should_see('آرشیو به‌روز است')
    await user.should_see(marker='stats')


# ------------------------------------------------------------------- accounts

async def test_adding_an_account_encrypts_the_password(user: User, env) -> None:
    await user.open('/')
    user.find(marker='add-account').click()
    user.find(marker='account-email').type('user@example.com')
    user.find(marker='account-password').type('s3cret')
    user.find(marker='account-save').click()

    await user.should_not_see(marker='account-dialog')
    await user.should_see(marker='account:user@example.com')
    await user.should_see('هنوز بکاپ گرفته نشده')
    [account] = env.settings.accounts
    assert (account.email, account.server, account.port) == ('user@example.com', 'mail.your-server.de', 993)
    assert account.password_token == 'token:s3cret'


async def test_new_account_needs_a_password(user: User, env) -> None:
    await user.open('/')
    user.find(marker='add-account').click()
    user.find(marker='account-email').type('user@example.com')
    user.find(marker='account-save').click()
    await user.should_see('رمز عبور را وارد کنید.')
    await user.should_see(marker='account-dialog')
    assert env.settings.accounts == []


async def test_duplicate_account_is_rejected(user: User, env, account_factory) -> None:
    env.seed(accounts=[account_factory('user@example.com')])
    await user.open('/')
    user.find(marker='add-account').click()
    user.find(marker='account-email').type('USER@example.com')
    user.find(marker='account-password').type('x')
    user.find(marker='account-save').click()
    await user.should_see('این حساب قبلاً اضافه شده است.')
    assert len(env.settings.accounts) == 1


async def test_connection_test_explains_failures_inside_the_dialog(user: User, env) -> None:
    env.engine.connection_error = imaplib.IMAP4.error(b'[AUTHENTICATIONFAILED] Authentication failed.')
    await user.open('/')
    user.find(marker='add-account').click()
    user.find(marker='account-email').type('user@example.com')
    user.find(marker='account-password').type('wrong')
    user.find(marker='account-test-form').click()
    await user.should_see('نام کاربری یا رمز عبور اشتباه است.')

    env.engine.connection_error = None
    user.find(marker='account-test-form').click()
    await user.should_see('اتصال برقرار شد و ورود با موفقیت انجام شد.')
    await user.should_not_see('نام کاربری یا رمز عبور اشتباه است.')
    assert env.engine.tested[-1] == ('user@example.com', 'mail.your-server.de', 'wrong')


async def test_editing_keeps_the_stored_password_when_left_blank(user: User, env, account_factory) -> None:
    env.seed(accounts=[account_factory()])
    await user.open('/')
    user.find(marker='account-edit').click()
    await user.should_see('ویرایش حساب ایمیل')

    user.find(marker='account-test-form').click()  # empty password field: test with the stored one
    await user.should_see('اتصال برقرار شد و ورود با موفقیت انجام شد.')
    assert env.engine.tested[-1] == ('user@example.com', 'mail.your-server.de', 'old-secret')

    user.find(marker='account-server').clear().type('imap.example.com')
    user.find(marker='account-save').click()
    await user.should_not_see(marker='account-dialog')
    [account] = env.settings.accounts
    assert account.server == 'imap.example.com'
    assert account.password_token == 'token:old-secret'


async def test_deleting_an_account_asks_first(user: User, env, account_factory) -> None:
    env.seed(accounts=[account_factory()])
    await user.open('/')
    user.find(marker='account-delete').click()
    await user.should_see('این حساب از برنامه حذف شود؟')
    assert len(env.settings.accounts) == 1

    user.find(marker='confirm-delete').click()
    await user.should_see('هنوز حسابی اضافه نشده است')
    assert env.settings.accounts == []


async def test_account_switch_pauses_backups_for_that_account(user: User, env, account_factory) -> None:
    env.seed(backup_root=str(env.root / 'backup'), accounts=[account_factory()])
    await user.open('/')
    user.find(marker='account-enabled').click()
    await user.should_see('غیرفعال')
    await user.should_see('همه حساب‌ها غیرفعال هستند')
    assert env.settings.accounts[0].enabled is False

    user.find(marker='run-backup').click()
    await user.should_see('هیچ حساب فعالی برای بکاپ وجود ندارد.')


# ------------------------------------------------------------------- settings

async def test_saving_the_destination_does_not_touch_the_scheduler(user: User, env) -> None:
    await open_settings(user)
    user.find(marker='destination').type('relative\\folder')
    user.find(marker='save-destination').click()
    await user.should_see(r'مسیر کامل پوشه را وارد کنید؛ مثلاً D:\EmailBackup')
    assert env.settings.backup_root == ''

    target = str(env.root / 'mail-archive')
    user.find(marker='destination').clear().type(target)
    user.find(marker='save-destination').click()
    await user.should_see('پوشه مقصد ذخیره شد.')
    assert env.settings.backup_root == target
    assert env.settings.scheduled is False
    assert env.calls['install'] == []


async def test_schedule_time_is_validated_before_registering_the_task(user: User, env) -> None:
    await open_settings(user)
    user.find(marker='schedule-time').clear().type('25:00')
    user.find(marker='enable-schedule').click()
    await user.should_see('ساعت را به‌صورت ۲۴ ساعته وارد کنید؛ مثلاً 01:30')
    assert env.calls['install'] == []

    user.find(marker='schedule-time').clear().type('02:30')
    user.find(marker='enable-schedule').click()
    await user.should_see('فعال · هر روز ۰۲:۳۰')
    await user.should_see('بکاپ خودکار: هر روز ۰۲:۳۰')
    assert env.calls['install'] == ['02:30']
    assert (env.settings.scheduled, env.settings.schedule_time) == (True, '02:30')


async def test_scheduler_failure_is_reported_and_not_saved(user: User, env) -> None:
    env.install_error = RuntimeError('Access is denied.')
    await open_settings(user)
    user.find(marker='enable-schedule').click()
    await user.should_see('فعال‌سازی زمان‌بندی ناموفق بود؛ جزئیات در بخش گزارش‌ها ثبت شد.')
    assert env.settings.scheduled is False


async def test_disabling_the_schedule_removes_the_task(user: User, env) -> None:
    env.seed(scheduled=True, schedule_time='03:15')
    await open_settings(user)
    await user.should_see('فعال · هر روز ۰۳:۱۵')
    user.find(marker='disable-schedule').click()
    await user.should_see('بکاپ خودکار غیرفعال شد.')
    await user.should_see('غیرفعال')
    assert env.calls['remove'] == [True]
    assert env.settings.scheduled is False


async def test_theme_choice_is_applied_and_remembered(user: User, env) -> None:
    await open_settings(user)
    toggle = next(iter(user.find(kind=ui.toggle, marker='theme').elements))
    with user:
        toggle.value = 'dark'
    assert env.settings.theme == 'dark'
    assert env.dashboard.dark is not None and env.dashboard.dark.value is True


# -------------------------------------------------------------------- backups

async def test_backup_without_destination_leads_to_settings(user: User, env, account_factory) -> None:
    env.seed(accounts=[account_factory()])
    await user.open('/')
    user.find(marker='run-backup').click()
    await user.should_see('ابتدا پوشه مقصد بکاپ را انتخاب کنید.')
    await user.should_see('محل ذخیره، زمان‌بندی و ظاهر برنامه.')


async def test_backup_shows_live_progress_then_a_clean_result(user: User, env, account_factory) -> None:
    env.seed(backup_root=str(env.root / 'backup'), accounts=[account_factory()])
    env.engine.pause = True
    await user.open('/')
    user.find(marker='run-backup').click()

    assert await asyncio.to_thread(env.engine.paused.wait, 5)
    await user.should_see('در حال بکاپ‌گیری…')
    await user.should_see('پیام ۲ از ۳', retries=10)
    await user.should_see('پوشه ۱ از ۲')
    await user.should_see('۶۷٪')

    env.engine.resume.set()
    await user.should_see('آرشیو به‌روز است', retries=20)
    await user.should_see('بکاپ کامل شد؛ ۳ پیام جدید ذخیره شد.')
    await asyncio.sleep(0.6)  # let the progress timer tick: late events must not resurface
    await user.should_not_see(marker='progress')
    await user.should_not_see('پوشه ۲ از ۲')
    await user.should_see('۳ پیام جدید')


async def test_open_dialog_survives_a_backup_finishing(user: User, env, account_factory) -> None:
    env.seed(backup_root=str(env.root / 'backup'), accounts=[account_factory()])
    env.engine.pause = True
    await user.open('/')
    user.find(marker='run-backup').click()
    assert await asyncio.to_thread(env.engine.paused.wait, 5)

    user.find(marker='add-account').click()
    user.find(marker='account-email').type('second@example.com')
    env.engine.resume.set()
    await user.should_see('آرشیو به‌روز است', retries=20)  # the account list has been rebuilt by now

    user.find(marker='account-password').type('pw')
    user.find(marker='account-save').click()
    await user.should_see(marker='account:second@example.com')
    assert [account.email for account in env.settings.accounts] == ['user@example.com', 'second@example.com']


async def test_backup_failure_is_shown_on_the_dashboard(user: User, env, account_factory) -> None:
    env.seed(backup_root=str(env.root / 'backup'), accounts=[account_factory()])
    env.engine.error = 'connection reset'
    await user.open('/')
    user.find(marker='run-backup').click()
    await user.should_see('آخرین بکاپ با خطا تمام شد', retries=20)
    await user.should_see('بکاپ تمام شد، اما ۱ حساب خطا داشت؛ جزئیات در گزارش‌ها.')
    await user.should_see('خطا: connection reset')


async def test_mbox_export_writes_files_and_opens_the_folder(user: User, env, account_factory) -> None:
    backup = env.root / 'backup'
    account = account_factory()
    message_dir = backup / safe_component(account.email) / safe_component('INBOX') / '7'
    message_dir.mkdir(parents=True)
    (message_dir / '1.eml').write_bytes(b'From: a@example.com\r\nSubject: hi\r\n\r\nbody\r\n')
    env.seed(backup_root=str(backup), accounts=[account])

    await user.open('/')
    user.find(marker='export-mbox').click()
    await user.should_see('۱ فایل MBOX شامل ۱ پیام ساخته شد.', retries=20)
    assert env.calls['open'] == [backup / 'MBOX']
    assert len(list((backup / 'MBOX').rglob('*.mbox'))) == 1


async def test_existing_archives_get_their_totals_counted(user: User, env, account_factory) -> None:
    backup = env.root / 'backup'
    account = account_factory(last_run='2026-01-01T01:00:00', last_status='0 پیام جدید')
    folder = backup / safe_component(account.email) / safe_component('INBOX') / '7'
    folder.mkdir(parents=True)
    for uid in (1, 2):
        (folder / f'{uid}.eml').write_bytes(b'x' * 1000)
    (folder / '3.eml.part').write_bytes(b'interrupted download')
    env.seed(backup_root=str(backup), accounts=[account])

    await user.open('/')
    await user.should_see('۲ کیلوبایت', retries=20)
    await user.should_see('۲ پیام')
    assert (env.settings.accounts[0].archived_messages, env.settings.accounts[0].archived_bytes) == (2, 2000)


# ----------------------------------------------------------------------- logs

async def test_log_view_highlights_problems_and_filters_them(user: User, env) -> None:
    log_file = Path(env.root / 'appdata' / 'EsfaMailBackup' / 'logs' / 'application.log')
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(
        '2026-10-04 18:37:24,713 [INFO] Starting backup for user@example.com\n'
        '2026-10-04 18:37:30,001 [ERROR] Backup failed for user@example.com\n'
        'Traceback (most recent call last):\n'
        '  ConnectionResetError: <reset>\n',
        encoding='utf-8',
    )
    await user.open('/')
    user.find(marker='nav-logs').click()
    await user.should_see('Starting backup for user@example.com')
    await user.should_see('lvl-error')
    await user.should_see('ConnectionResetError: &lt;reset&gt;')  # escaped, never rendered as HTML

    toggle = next(iter(user.find(kind=ui.toggle, marker='log-filter').elements))
    with user:
        toggle.value = 'problems'
    await user.should_not_see('Starting backup for user@example.com')
    await user.should_see('Backup failed for user@example.com')
