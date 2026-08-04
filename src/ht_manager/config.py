from __future__ import annotations

from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import NoDecode


class SettingsError(Exception):
    """Raised when required configuration is missing or invalid."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    discord_token: str
    discord_guild_id: int
    database_url: str
    ctftime_team_id: str
    results_channel_id: int
    ctf_forum_channel_id: int
    admin_role_ids: Annotated[list[int], NoDecode]
    member_role_id: int | None = None
    bot_log_channel_id: int | None = None
    ctf_resource_retention_days: int = 60
    public_api_origins: Annotated[list[str], NoDecode] = []
    log_level: str = "INFO"

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
