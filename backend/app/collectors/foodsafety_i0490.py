"""식품의약품안전처 식품안전나라 OpenAPI I0490 (회수·판매중지 정보)."""

import logging
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.collectors.base import (
    CollectError,
    Collector,
    FetchResult,
    ProbeResult,
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
# MNFDT·DISTBTMLMT 값 맨 앞에 붙어 오는 말머리. 화면에는 항목 이름이 따로 있어 뺀다.
MANUFACTURED_PREFIX_RE = re.compile(r"^\(제조일자\)\s*")
EXPIRY_PREFIX_RE = re.compile(r"^\(소비기한\)\s*")


def parse_grade(value: Any) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    match = GRADE_RE.search(text)
    return int(match.group(1)) if match else None


def strip_prefix(value: Any, prefix_re: re.Pattern[str]) -> str | None:
    """값 맨 앞의 말머리와 뒤따르는 공백을 지운다. 원문은 raw에 남는다."""
    text = clean_text(value)
    if text is None:
        return None
    return prefix_re.sub("", text, count=1) or None


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
        manufactured_text=strip_prefix(row.get("MNFDT"), MANUFACTURED_PREFIX_RE),
        expiry_text=strip_prefix(row.get("DISTBTMLMT"), EXPIRY_PREFIX_RE),
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

    async def fetch(self, last_success_at: datetime | None = None) -> FetchResult:
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
        return FetchResult(records, skipped_count=skipped)

    async def probe(self) -> ProbeResult:
        if not self._api_key:
            return ProbeResult(self.source, ok=False, error="FOODSAFETY_API_KEY is not set")
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=30.0, transport=self._transport) as client:
                resp = await client.get(self._url(1, 1))
        except httpx.HTTPError as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            return ProbeResult(self.source, ok=False, elapsed_ms=elapsed, error=type(exc).__name__)
        elapsed = int((time.perf_counter() - started) * 1000)
        result = ProbeResult(
            self.source, ok=False, http_status=resp.status_code, elapsed_ms=elapsed
        )
        try:
            data = resp.json()
        except ValueError:
            result.error = "response is not JSON"
            return result
        result.code, _ = _result_code(data)
        try:
            result.total, rows = parse_page(data)
        except CollectError as exc:
            result.error = str(exc)
            return result
        result.ok = resp.status_code == 200
        result.image_urls = [u for r in rows for u in parse_image_urls(r.get("IMG_FILE_PATH"))]
        return result

    def _url(self, start: int, end: int) -> str:
        return f"{BASE_URL}/{quote(self._api_key, safe='')}/{SERVICE}/json/{start}/{end}"

    async def _fetch_page(
        self, client: httpx.AsyncClient, start: int, end: int
    ) -> tuple[int, list[dict[str, Any]]]:
        try:
            resp = await client.get(self._url(start, end))
        except httpx.HTTPError as exc:
            # httpx 예외 메시지에는 URL(=키)이 들어갈 수 있으므로 타입만 남긴다.
            raise CollectError(f"request failed: {type(exc).__name__}") from None
        if resp.status_code != 200:
            raise CollectError(f"HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            raise CollectError("response is not JSON") from None
        return parse_page(data)


def _result_code(data: Any) -> tuple[str | None, str]:
    """(CODE, MSG). 인증키 오류 등은 서비스 키 없이 최상위 RESULT로 오는 경우가 있다."""
    body = data.get(SERVICE) if isinstance(data, dict) else None
    result = (body or {}).get("RESULT") or (data.get("RESULT") if isinstance(data, dict) else None)
    return (result or {}).get("CODE"), (result or {}).get("MSG", "")


def parse_page(data: Any) -> tuple[int, list[dict[str, Any]]]:
    """(total_count, row 목록). INFO-200(데이터 없음)은 (0, []), 그 밖의 코드는 CollectError."""
    code, msg = _result_code(data)
    if code == CODE_NO_DATA:
        return 0, []
    body = data.get(SERVICE) if isinstance(data, dict) else None
    if code != CODE_OK or not isinstance(body, dict):
        raise CollectError(f"API result {code}: {msg}")
    try:
        total = int(body.get("total_count") or 0)
    except (TypeError, ValueError):
        raise CollectError("invalid total_count") from None
    page = body.get("row") or []
    if not isinstance(page, list):
        raise CollectError("invalid row field")
    return total, page
