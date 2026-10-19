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
    admin_token: SecretStr = SecretStr("")
    app_name: str = "recall"
    env: str = "prod"
    enabled_categories: str = ",".join(DEFAULT_ENABLED_CATEGORIES)
    collect_interval_minutes: int = Field(default=60, ge=1)
    snapshot_days: int = Field(default=1095, ge=1)
    hide_empty_days: int = Field(default=180, ge=1)
    image_host_allowlist: str = "coop.foodsafetykorea.go.kr,www.consumer.go.kr"

    consumer24_lookback_days: int = Field(default=30, ge=1)
    # 소비자24 서비스키는 메뉴(cntntsId)마다 다르다. 비어 있는 메뉴는 수집하지 않는다.
    # 식품(0201)·축산물(0203)은 foodsafety_i0490과 겹쳐 받지 않으므로 항목이 없다.
    # 메뉴 목록은 app/collectors/consumer24.py의 MENU_CATEGORIES와 같아야 한다 (테스트로 확인).
    consumer24_key_0101: SecretStr = SecretStr("")  # 공산품
    consumer24_key_0405: SecretStr = SecretStr("")  # 생활방사선제품
    consumer24_key_0204: SecretStr = SecretStr("")  # 의약품
    consumer24_key_0205: SecretStr = SecretStr("")  # 의약외품
    consumer24_key_0207: SecretStr = SecretStr("")  # 의료기기
    consumer24_key_0206: SecretStr = SecretStr("")  # 화장품
    consumer24_key_0401: SecretStr = SecretStr("")  # 생활화학제품
    consumer24_key_0301: SecretStr = SecretStr("")  # 자동차
    consumer24_key_0403: SecretStr = SecretStr("")  # 먹는물
    consumer24_key_0208: SecretStr = SecretStr("")  # 위생용품
    consumer24_key_0501: SecretStr = SecretStr("")  # 해외리콜

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
    def consumer24_keys(self) -> dict[str, str]:
        """메뉴 ID → 서비스키. 키가 비어 있는 메뉴도 빈 문자열로 들어 있다."""
        prefix = "consumer24_key_"
        return {
            name.removeprefix(prefix): getattr(self, name).get_secret_value()
            for name in type(self).model_fields
            if name.startswith(prefix)
        }

    @property
    def image_hosts(self) -> frozenset[str]:
        return frozenset(h.lower() for h in _split_csv(self.image_host_allowlist))

    @property
    def is_dev(self) -> bool:
        return self.env.strip().lower() == "dev"

    @property
    def cors_origins(self) -> list[str]:
        # SDK 3.1.0+는 apps/private-apps, 3.0.x는 web/private-web. 롤백 대비 둘 다 허용한다.
        origins = [
            f"https://{self.app_name}.apps.tossmini.com",
            f"https://{self.app_name}.private-apps.tossmini.com",
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
            *self.consumer24_keys.values(),
            self.admin_token.get_secret_value(),
            self.database_url.get_secret_value(),
        ]
        return [v for v in values if v]


@cache
def get_settings() -> Settings:
    return Settings()
