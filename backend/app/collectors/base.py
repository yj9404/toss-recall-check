from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
    # 문의처 원문 (전화번호·홈페이지·주소가 섞여 있다).
    contact_text: str | None = None
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


@dataclass
class FetchResult:
    records: list[RecallRecord]
    # 키·등록일(공표일)이 없어 받지 않은 건수. source_state와 /healthz에 남는다.
    skipped_count: int = 0


@dataclass
class ProbeResult:
    """출처 API를 1건만 호출해 본 결과 (python -m app.check_sources)."""

    source: str
    ok: bool
    http_status: int | None = None
    code: str | None = None
    total: int | None = None
    elapsed_ms: int = 0
    # 예외 타입 등. 요청 URL(=API 키)은 넣지 않는다.
    error: str | None = None
    image_urls: list[str] = field(default_factory=list)


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
    async def fetch(self, last_success_at: datetime | None = None) -> FetchResult:
        """last_success_at: 이 source의 마지막 성공 시각 (없으면 None). 증분 수집에 쓴다."""

    @abstractmethod
    async def probe(self) -> ProbeResult:
        """1건만 호출해 HTTP 상태·결과코드·응답 시간을 본다. 예외를 던지지 않는다."""


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
