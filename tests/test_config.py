from pathlib import Path

import pytest

from ht_manager.config import SettingsError, get_settings

REQUIRED_ENV = {
    "DISCORD_TOKEN": "fake-token",
    "DISCORD_GUILD_ID": "123456789",
    "DATABASE_URL": "postgresql+asyncpg://ht_manager:ht_manager@localhost:5432/ht_manager",
    "CTFTIME_TEAM_ID": "999",
    "RESULTS_CHANNEL_ID": "111",
    "CTF_FORUM_CHANNEL_ID": "222",
    "ADMIN_ROLE_IDS": "1,2,3",
}


def test_settings_loads_from_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)

    settings = get_settings()

    assert settings.discord_token == "fake-token"
    assert settings.discord_guild_id == 123456789
    assert settings.admin_role_ids == [1, 2, 3]
    assert settings.ctf_resource_retention_days == 60
    assert settings.public_api_origins == []


def test_settings_missing_required_raises_actionable_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key in REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DISCORD_TOKEN", "fake-token")

    with pytest.raises(SettingsError) as exc_info:
        get_settings()

    assert ".env.example" in str(exc_info.value)


def test_settings_loads_from_dotenv_file(monkeypatch, tmp_path):
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
    assert settings.public_api_origins == []
