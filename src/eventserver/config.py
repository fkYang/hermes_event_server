from functools import lru_cache
from typing import Annotated
from urllib.parse import quote_plus

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_database: str = "autoqq"
    mysql_user: str = "autoqq"
    mysql_password: str = ""
    mysql_charset: str = "utf8mb4"
    internal_api_token: str = ""
    initial_admin_openids: Annotated[tuple[str, ...], NoDecode] = ()
    default_timezone: str = "Asia/Shanghai"
    enabled_providers: Annotated[tuple[str, ...], NoDecode] = (
        "warframe.cetus_night",
        "warframe.konzu_rotation",
        "warframe.ghoul_event",
    )
    delivery_max_attempts: int = Field(default=5, ge=1, le=20)
    delivery_default_lease_seconds: int = Field(default=60, ge=10, le=600)
    provider_default_timeout_seconds: float = Field(default=10, gt=0, le=60)
    provider_scheduler_tick_seconds: float = Field(default=5, ge=1, le=300)

    @field_validator("initial_admin_openids", "enabled_providers", mode="before")
    @classmethod
    def parse_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @field_validator("internal_api_token")
    @classmethod
    def reject_short_production_token(cls, value: str) -> str:
        if value and len(value) < 24:
            raise ValueError("INTERNAL_API_TOKEN must contain at least 24 characters")
        return value

    @property
    def database_url(self) -> str:
        password = quote_plus(self.mysql_password)
        auth = quote_plus(self.mysql_user)
        if password:
            auth = f"{auth}:{password}"
        return (
            f"mysql+pymysql://{auth}@{self.mysql_host}:{self.mysql_port}/"
            f"{quote_plus(self.mysql_database)}?charset={quote_plus(self.mysql_charset)}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
