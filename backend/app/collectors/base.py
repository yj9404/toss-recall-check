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
    # 건별 출처 기관명. 없으면 API가 labels.SOURCE_LABELS[source]를 쓴다.
    source_label: str | None = None
    model_text: str | None = None
    consumer_tips: str | None = None
    recall_period_text: str | None = None
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
    # source_state의 키. 수집 결과(성공·실패)는 source 단위로 기록된다.
    source: str
    # 이 수집기가 채우는 카테고리. 기본 수집 대상은 ENABLED_CATEGORIES와 겹치는 수집기다.
    categories: tuple[str, ...]

    @property
    def group(self) -> str:
        """--source로 고를 때 쓰는 묶음 이름. 여러 source로 나뉜 출처만 따로 정한다."""
        return self.source

    @abstractmethod
    async def fetch(self, last_success_at: datetime | None = None) -> list[RecallRecord]:
        """last_success_at: 이 source의 마지막 성공 시각 (없으면 None). 증분 수집에 쓴다."""


def clean_text(value: Any) -> str | None:
    """앞뒤 공백을 지우고 빈 문자열은 None으로 바꾼다. "데이터없음" 같은 값은 그대로 둔다."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_image_urls(value: Any) -> list[str]:
    """쉼표로 이어진 이미지 URL 목록을 나눈다."""
    text = clean_text(value)
    if text is None:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


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
