from functools import cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.labels import CATEGORIES, DEFAULT_ENABLED_CATEGORIES


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: SecretStr = SecretStr("")
    foodsafety_api_key: SecretStr = SecretStr("")
    data_go_kr_api_key: SecretStr = SecretStr("")
    admin_token: SecretStr = SecretStr("")
    app_name: str = "recall-check"
    env: str = "prod"
    enabled_categories: str = ",".join(DEFAULT_ENABLED_CATEGORIES)
    collect_interval_minutes: int = Field(default=60, ge=1)
    snapshot_days: int = Field(default=1095, ge=1)
    hide_empty_days: int = Field(default=180, ge=1)
    image_host_allowlist: str = "coop.foodsafetykorea.go.kr"

    # TODO: 아래 수집기의 엔드포인트는 명세 확정 후 채운다. 비어 있으면 fetch()가 동작하지 않는다.
    kats_api_url: str = ""
    ftc_api_url: str = ""
    mfds_cosmetic_api_url: str = ""

    @field_validator("enabled_categories")
    @classmethod
    def _check_categories(cls, value: str) -> str:
        unknown = [c for c in _split_csv(value) if c not in CATEGORIES]
        if unknown:
            raise ValueError(f"unknown categories: {unknown}")
        return value

    @property
    def enabled_category_list(self) -> list[str]:
        enabled = set(_split_csv(self.enabled_categories))
        return [c for c in CATEGORIES if c in enabled]

    @property
    def image_hosts(self) -> frozenset[str]:
        return frozenset(h.lower() for h in _split_csv(self.image_host_allowlist))

    @property
    def is_dev(self) -> bool:
        return self.env.strip().lower() == "dev"

    @property
    def cors_origins(self) -> list[str]:
        origins = [
            f"https://{self.app_name}.web.tossmini.com",
            f"https://{self.app_name}.private-web.tossmini.com",
        ]
        if self.is_dev:
            origins.append("http://localhost:5173")
        return origins

    def secret_values(self) -> list[str]:
        """로그·에러 메시지에서 가릴 값들."""
        values = [
            self.foodsafety_api_key.get_secret_value(),
            self.data_go_kr_api_key.get_secret_value(),
            self.admin_token.get_secret_value(),
            self.database_url.get_secret_value(),
        ]
        return [v for v in values if v]


@cache
def get_settings() -> Settings:
    return Settings()
