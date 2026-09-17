from eventserver.config import Settings


def test_database_url_percent_encodes_password() -> None:
    settings = Settings(mysql_user="root", mysql_password="p@ss:#word")
    assert "p%40ss%3A%23word" in settings.database_url
    assert settings.database_url.startswith("mysql+pymysql://")


def test_csv_environment_settings_are_parsed(monkeypatch) -> None:
    monkeypatch.setenv("INITIAL_ADMIN_OPENIDS", "first,second")
    settings = Settings(_env_file=None)
    assert settings.initial_admin_openids == ("first", "second")
