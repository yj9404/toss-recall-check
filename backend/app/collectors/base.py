from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

from app.labels import CATEGORIES

KST = ZoneInfo("Asia/Seoul")


class CollectError(Exception):
    """수집 실패. 메시지에 API 키나 요청 URL을 넣지 않는다."""


class RecallRecord(BaseModel):
    source: str
    source_id: str
    category: str
    product_name: str | None = None
    company_name: str | None = None
    reason: str | None = None
    grade: int | None = Field(default=None, ge=1, le=3)
    manufactured_text: str | None = None
    expiry_text: str | None = None
    package_unit: str | None = None
    recall_method: str | None = None
    address: str | None = None
    company_phone: str | None = None
    barcode: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    source_url: str | None = None
    registered_at: datetime
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError(f"unknown category: {value}")
        return value

    @field_validator("registered_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("registered_at must be timezone-aware")
        return value


class Collector(ABC):
    source: str
    # 이 수집기가 채우는 카테고리. 기본 수집 대상은 ENABLED_CATEGORIES와 겹치는 수집기다.
    categories: tuple[str, ...]

    @abstractmethod
    async def fetch(self) -> list[RecallRecord]: ...


def clean_text(value: Any) -> str | None:
    """앞뒤 공백을 지우고 빈 문자열은 None으로 바꾼다. "데이터없음" 같은 값은 그대로 둔다."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_kst_datetime(value: Any) -> datetime | None:
    """소스 시각 문자열을 Asia/Seoul 기준 aware datetime으로 바꾼다. 해석 불가면 None."""
    text = clean_text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)
