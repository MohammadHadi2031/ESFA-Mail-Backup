from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path


TASK_NAME = 'ESFA Mail Backup'
LEGACY_TASK_NAMES = ('Hetzner Mail Backup',)


def executable_command() -> tuple[str, str]:
    if getattr(sys, 'frozen', False):
        return str(Path(sys.executable).resolve()), '--run-backup'
    python = Path(sys.executable)
    pythonw = python.with_name('pythonw.exe') if os.name == 'nt' else python
    script = Path(__file__).resolve().parents[1] / 'app.py'
    return str(pythonw), f'"{script}" --run-backup'


def _powershell(script: str) -> subprocess.CompletedProcess[str]:
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    return subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
        check=True,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )


def install_daily_task(time_value: str) -> None:
    if os.name != 'nt':
        raise RuntimeError('زمان‌بندی خودکار فقط روی ویندوز قابل فعال‌سازی است.')
    hour, minute = map(int, time_value.split(':', 1))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError('ساعت زمان‌بندی معتبر نیست.')
    executable, arguments = executable_command()
    escaped_executable = executable.replace("'", "''")
    escaped_arguments = arguments.replace("'", "''")
    escaped_name = TASK_NAME.replace("'", "''")
    script = f"""
$action = New-ScheduledTaskAction -Execute '{escaped_executable}' -Argument '{escaped_arguments}'
$trigger = New-ScheduledTaskTrigger -Daily -At '{hour:02d}:{minute:02d}'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 12)
Register-ScheduledTask -TaskName '{escaped_name}' -Action $action -Trigger $trigger -Settings $settings -Description 'Incremental IMAP backup' -Force | Out-Null
"""
    _powershell(script)
    _remove_legacy_tasks()


def remove_daily_task() -> None:
    if os.name != 'nt':
        return
    _unregister(TASK_NAME)
    _remove_legacy_tasks()


def _remove_legacy_tasks() -> None:
    """Drop tasks left behind by earlier releases that used a different name."""
    for name in LEGACY_TASK_NAMES:
        _unregister(name)


def _unregister(task_name: str) -> None:
    name = task_name.replace("'", "''")
    _powershell(f"Unregister-ScheduledTask -TaskName '{name}' -Confirm:$false -ErrorAction SilentlyContinue")

