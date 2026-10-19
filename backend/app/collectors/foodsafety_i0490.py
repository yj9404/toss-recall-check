"""식품의약품안전처 식품안전나라 OpenAPI I0490 (회수·판매중지 정보)."""

import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.collectors.base import (
    CollectError,
    Collector,
    RecallRecord,
    clean_text,
    parse_image_urls,
    parse_kst_datetime,
)

log = logging.getLogger(__name__)

BASE_URL = "https://openapi.foodsafetykorea.go.kr/api"
SERVICE = "I0490"
# ERROR-336: 데이터요청은 한번에 최대 1000건을 넘을 수 없다.
PAGE_SIZE = 1000
CODE_OK = "INFO-000"
CODE_NO_DATA = "INFO-200"  # 해당하는 데이터가 없습니다.

BARCODE_RE = re.compile(r"[0-9]{13}")
GRADE_RE = re.compile(r"([1-3])\s*등급")


def parse_grade(value: Any) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    match = GRADE_RE.search(text)
    return int(match.group(1)) if match else None


def parse_barcode(value: Any) -> str | None:
    text = clean_text(value)
    if text is not None and BARCODE_RE.fullmatch(text):
        return text
    return None


def normalize_row(row: dict[str, Any]) -> RecallRecord | None:
    """I0490 row 하나를 RecallRecord로 바꾼다. 키나 등록일이 없으면 None."""
    source_id = clean_text(row.get("RTRVLDSUSE_SEQ"))
    registered_at = parse_kst_datetime(row.get("CRET_DTM"))
    if source_id is None or registered_at is None:
        return None
    return RecallRecord(
        source=FoodSafetyI0490Collector.source,
        source_id=source_id,
        # PRDLST_TYPE(축산물·가공식품·농산물)과 무관하게 모두 food로 분류한다.
        category="food",
        product_name=clean_text(row.get("PRDTNM")),
        company_name=clean_text(row.get("BSSHNM")),
        reason=clean_text(row.get("RTRVLPRVNS")),
        grade=parse_grade(row.get("RTRVL_GRDCD_NM")),
        manufactured_text=clean_text(row.get("MNFDT")),
        expiry_text=clean_text(row.get("DISTBTMLMT")),
        package_unit=clean_text(row.get("FRMLCUNIT")),
        recall_method=clean_text(row.get("RTRVLPLANDOC_RTRVLMTHD")),
        address=clean_text(row.get("ADDR")),
        company_phone=clean_text(row.get("TELNO")),
        barcode=parse_barcode(row.get("BRCDNO")),
        image_urls=parse_image_urls(row.get("IMG_FILE_PATH")),
        source_url=None,  # I0490에는 건별 상세 페이지 링크 필드가 없다.
        registered_at=registered_at,
        raw=row,  # 원문 row 전체 (비표준 바코드 등 원본 값 보존)
    )


class FoodSafetyI0490Collector(Collector):
    source = "foodsafety_i0490"
    categories = ("food",)

    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        page_size: int = PAGE_SIZE,
    ) -> None:
        self._api_key = api_key
        self._transport = transport
        self._page_size = page_size

    async def fetch(self, last_success_at: datetime | None = None) -> list[RecallRecord]:
        # I0490은 날짜 조건 없이 매번 전량을 받으므로 last_success_at을 쓰지 않는다.
        if not self._api_key:
            raise CollectError("FOODSAFETY_API_KEY is not set")

        rows: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30.0, transport=self._transport) as client:
            start = 1
            while True:
                end = start + self._page_size - 1
                total, page = await self._fetch_page(client, start, end)
                rows.extend(page)
                if not page or end >= total:
                    break
                start = end + 1

        records = []
        skipped = 0
        for row in rows:
            record = normalize_row(row)
            if record is None:
                skipped += 1
            else:
                records.append(record)
        if skipped:
            log.warning("%s: skipped %d rows without id or registered_at", self.source, skipped)
        return records

    async def _fetch_page(
        self, client: httpx.AsyncClient, start: int, end: int
    ) -> tuple[int, list[dict[str, Any]]]:
        url = f"{BASE_URL}/{quote(self._api_key, safe='')}/{SERVICE}/json/{start}/{end}"
        try:
            resp = await client.get(url)
        except httpx.HTTPError as exc:
            # httpx 예외 메시지에는 URL(=키)이 들어갈 수 있으므로 타입만 남긴다.
            raise CollectError(f"request failed: {type(exc).__name__}") from None
        if resp.status_code != 200:
            raise CollectError(f"HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            raise CollectError("response is not JSON") from None

        body = data.get(SERVICE) if isinstance(data, dict) else None
        # 인증키 오류 등은 서비스 키 없이 최상위 RESULT로 오는 경우가 있다.
        result = (body or {}).get("RESULT") or (
            data.get("RESULT") if isinstance(data, dict) else None
        )
        code = (result or {}).get("CODE")
        if code == CODE_NO_DATA:
            return 0, []
        if code != CODE_OK or not isinstance(body, dict):
            msg = (result or {}).get("MSG", "")
            raise CollectError(f"API result {code}: {msg}")

        try:
            total = int(body.get("total_count") or 0)
        except (TypeError, ValueError):
            raise CollectError("invalid total_count") from None
        page = body.get("row") or []
        if not isinstance(page, list):
            raise CollectError("invalid row field")
        return total, page
