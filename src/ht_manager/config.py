from __future__ import annotations

from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import EnvSettingsSource


class SettingsError(Exception):
    """Raised when required configuration is missing or invalid."""


class _CustomEnvSettings(EnvSettingsSource):
    """Custom env settings source that doesn't JSON-parse comma-separated lists."""

    def decode_complex_value(self, field_name: str, field, value: str) -> Any:
        # For certain fields, don't use JSON decoding; let field validators handle parsing
        if field_name in ("admin_role_ids", "public_api_origins"):
            return value
        return super().decode_complex_value(field_name, field, value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    discord_token: str
    discord_guild_id: int
    database_url: str
    ctftime_team_id: str
    results_channel_id: int
    ctf_forum_channel_id: int
    admin_role_ids: list[int]
    member_role_id: int | None = None
    bot_log_channel_id: int | None = None
    ctf_resource_retention_days: int = 60
    public_api_origins: list[str] = []
    log_level: str = "INFO"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            _CustomEnvSettings(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )

    @field_validator("admin_role_ids", mode="before")
    @classmethod
    def _split_admin_role_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(item) for item in value.split(",") if item.strip()]
        return value

    @field_validator("public_api_origins", mode="before")
    @classmethod
    def _split_public_api_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


def get_settings() -> Settings:
    try:
        return Settings()
    except Exception as exc:
        raise SettingsError(
            "Invalid or missing configuration. Check your .env file against "
            f".env.example. Details: {exc}"
        ) from exc
