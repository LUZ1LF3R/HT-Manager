from pathlib import Path

import pytest
from pytest import MonkeyPatch

from ht_manager.config import SettingsError, get_settings

REQUIRED_ENV = {
    "DISCORD_TOKEN": "fake-token",
    "DISCORD_GUILD_ID": "123456789",
    "DATABASE_URL": "postgresql+asyncpg://ht_manager:ht_manager@localhost:5432/ht_manager",
    "CTFTIME_TEAM_ID": "999",
    "RESULTS_CHANNEL_ID": "111",
    "CTF_CATEGORY_ID": "222",
    "CTF_ARCHIVE_CATEGORY_ID": "333",
    "ADMIN_ROLE_IDS": "1,2,3",
}


def test_settings_loads_from_env(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)

    settings = get_settings()

    assert settings.discord_token == "fake-token"
    assert settings.discord_guild_id == 123456789
    assert settings.admin_role_ids == [1, 2, 3]
    assert settings.ctf_resource_retention_days == 60


def test_settings_missing_required_raises_actionable_error(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    for key in REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DISCORD_TOKEN", "fake-token")

    with pytest.raises(SettingsError) as exc_info:
        get_settings()

    assert ".env.example" in str(exc_info.value)


def test_settings_empty_admin_role_ids_raises_error(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ADMIN_ROLE_IDS", "")

    with pytest.raises(SettingsError):
        get_settings()


def test_settings_loads_from_dotenv_file(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    # Clear environment variables to ensure .env file is the source
    for key in REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)

    # Write a real .env file
    env_content = "\n".join(f"{k}={v}" for k, v in REQUIRED_ENV.items())
    Path(".env").write_text(env_content)

    settings = get_settings()

    assert settings.discord_token == "fake-token"
    assert settings.discord_guild_id == 123456789
    assert settings.admin_role_ids == [1, 2, 3]
    assert settings.ctf_resource_retention_days == 60
