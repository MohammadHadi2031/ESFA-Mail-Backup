from mailbackup.models import Account, AccountResult, BackupResult, Settings


def test_unknown_config_fields_are_ignored() -> None:
    account = Account.from_dict({'email': 'a@example.com', 'future_field': 123})
    assert account.email == 'a@example.com'


def test_backup_result_totals() -> None:
    result = BackupResult(accounts=[
        AccountResult(account_id='1', email='a@example.com', new_messages=4),
        AccountResult(account_id='2', email='b@example.com', new_messages=2, success=False),
    ])
    assert result.new_messages == 6
    assert result.failures == 1


def test_settings_from_partial_dictionary() -> None:
    settings = Settings.from_dict({'accounts': [{'email': 'a@example.com'}]})
    assert settings.schedule_time == '01:00'
    assert settings.accounts[0].server == 'mail.your-server.de'



def test_theme_falls_back_to_auto_for_unknown_values() -> None:
    assert Settings.from_dict({'theme': 'neon'}).theme == 'auto'
    assert Settings.from_dict({'theme': 'dark'}).to_dict()['theme'] == 'dark'


def test_configs_from_older_versions_load_with_empty_archive_totals() -> None:
    account = Account.from_dict({'email': 'a@example.com', 'last_status': 'خطا: timeout'})
    assert (account.archived_messages, account.archived_bytes) == (0, 0)
    assert account.failed
