"""공정거래위원회 소비자24 리콜정보 OpenAPI (XML, 개발가이드 V2.5).

서비스키가 메뉴(cntntsId)마다 달라 메뉴별로 수집기를 하나씩 만든다.
source는 consumer24_<cntntsId>이고, --source consumer24는 메뉴 전체를 고른다.
식품(0201)·축산물(0203)은 foodsafety_i0490과 겹쳐 받지 않는다.

실제 응답 (tests/fixtures/consumer24_*.xml, UTF-8):
  정상  <ns2:selectCntntsForOpenAPIResponse><channel><return> allCnt, code, codeMsg, content...
  에러  <ns2:selectCntntsForOpenAPIResponse><return> code, codeMsg
        (channel 없음. 30 데이터 없음도 이 형태)
값은 모두 CDATA이고 빈 값은 <![CDATA[]]>다. 자동차 결함 내용 등 일부 필드는 HTML 조각이다.
목록은 공표일이 아니라 recallSn 역순이다.
요청 변수 recallPublictBgnde는 "공표 시작일이 이 날짜 이후"로 걸러 준다.
해외리콜(0501)로 요청하면 항목의 cntntsId에 하위 분류 0502·0503·0504가 섞여 온다.
"""

import asyncio
import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.collectors.base import (
    KST,
    CollectError,
    Collector,
    FetchResult,
    ProbeResult,
    RecallRecord,
    clean_text,
    parse_image_urls,
)

log = logging.getLogger(__name__)

NAME = "consumer24"
BASE_URL = "https://www.consumer.go.kr/openapi/recall/contents/index.do"
PAGE_SIZE = 100  # 결과코드 41: 페이지당 최대 100건
REQUEST_INTERVAL_SECONDS = 0.3
CODE_OK = "00"
CODE_NO_DATA = "30"
DEFAULT_SOURCE_LABEL = "공정거래위원회 소비자24"
# 해외리콜은 10만 건이 넘어 SNAPSHOT_DAYS 대신 CONSUMER24_OVERSEAS_DAYS 범위만 받고 보여 준다.
OVERSEAS_MENU = "0501"
OVERSEAS_SOURCE = f"{NAME}_{OVERSEAS_MENU}"

# cntntsId → category. 식품(0201)·축산물(0203)은 일부러 넣지 않는다.
MENU_CATEGORIES: dict[str, str] = {
    "0101": "consumer_product",
    "0405": "radiation_product",
    "0204": "medicine",
    "0205": "quasi_drug",
    "0207": "medical_device",
    "0206": "cosmetic",
    "0401": "household_chemical",
    "0301": "vehicle",
    "0403": "drinking_water",
    "0208": "hygiene_product",
    "0501": "overseas",
}

# 실제 데이터에 나온 태그 위주의 허용목록. 속성이 "이름=값" 꼴일 때만 태그로 본다.
# 그래야 본문의 "<대상차량별 생산일자>", "<KC 마크 누락>", "<br (인증모델: …)>" 같은 글자가 남는다.
_HTML_TAGS = r"p|br|div|span|a|b|i|u|em|strong|font|input|img|ul|ol|li|table|thead|tbody|tr|td|th"
_ATTRS = r"""(?:\s+[a-zA-Z][\w:-]*(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'<>]+))?)*\s*/?>"""
_LINE_BREAK_RE = re.compile(rf"<br{_ATTRS}|</(?:p|div|li|tr)\s*>", re.IGNORECASE)
_TAG_RE = re.compile(rf"</?(?:{_HTML_TAGS}){_ATTRS}", re.IGNORECASE)
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_BARCODE_RE = re.compile(r"(?<![0-9])[0-9]{13}(?![0-9])")
_YYYYMMDD_RE = re.compile(r"[0-9]{8}")


def html_to_text(value: Any) -> str | None:
    """HTML 조각을 화면에 그대로 보여줄 텍스트로 바꾼다. 태그가 없는 값은 공백만 정리한다."""
    text = clean_text(value)
    if text is None:
        return None
    text = _LINE_BREAK_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = "\n".join(line.strip() for line in text.splitlines())
    return _BLANK_LINES_RE.sub("\n\n", text).strip() or None


def parse_barcode(value: Any) -> str | None:
    """처음 나오는 13자리 숫자. "a, b"처럼 여러 개면 첫 번째만 쓰고 원문은 raw에 남는다."""
    match = _BARCODE_RE.search(value or "")
    return match.group() if match else None


def parse_yyyymmdd(value: Any) -> datetime | None:
    """yyyyMMdd를 Asia/Seoul 자정으로 바꾼다. 해석 불가면 None."""
    text = clean_text(value)
    if text is None or not _YYYYMMDD_RE.fullmatch(text):
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").replace(tzinfo=KST)
    except ValueError:
        return None


def recall_period(begin: Any, end: Any) -> str | None:
    """리콜 시작~종료일 원문. 한쪽만 있으면 "20261014~"처럼 나머지를 비운다."""
    begin, end = clean_text(begin), clean_text(end)
    if begin is None and end is None:
        return None
    return f"{begin or ''}~{end or ''}"


def _result_element(body: bytes) -> ET.Element:
    """정상 응답은 channel/return, 에러 응답은 루트 바로 아래 return에 결과가 온다."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise CollectError("response is not XML") from None
    result = root.find("channel/return")
    if result is None:
        result = root.find("return")
    if result is None:
        raise CollectError("missing return element")
    return result


def parse_response(body: bytes) -> tuple[int, list[dict[str, str]]]:
    """(allCnt, content 목록). 결과코드 30(데이터 없음)은 (0, []), 그 밖의 코드는 CollectError."""
    result = _result_element(body)
    code = (result.findtext("code") or "").strip()
    if code == CODE_NO_DATA:
        return 0, []
    if code != CODE_OK:
        msg = (result.findtext("codeMsg") or "").strip()
        raise CollectError(f"API result {code}: {msg}")
    try:
        total = int(result.findtext("allCnt") or "")
    except ValueError:
        raise CollectError("invalid allCnt") from None
    items = [
        {child.tag: "".join(child.itertext()).strip() for child in content}
        for content in result.iterfind("content")
    ]
    return total, items


def recall_method(value: Any) -> str | None:
    """recallProcssInfo. 공산품은 대부분 "인증번호: …"라 회수 방법이 아니므로 버린다.

    원문은 raw에 남는다.
    """
    text = html_to_text(value)
    if text is None or text.startswith("인증번호"):
        return None
    return text


def normalize_item(item: dict[str, str], menu_id: str) -> RecallRecord | None:
    """menu_id로 요청해 받은 content 하나를 RecallRecord로 바꾼다. recallSn·공표일이 없으면 None.

    category와 source는 항목의 cntntsId가 아니라 요청한 메뉴로 정한다. 해외리콜(0501)은
    하위 분류인 0502·0503·0504가 섞여 오기 때문이다. 항목의 cntntsId는 raw에 남는다.
    """
    category = MENU_CATEGORIES[menu_id]
    source_id = clean_text(item.get("recallSn"))
    registered_at = parse_yyyymmdd(item.get("recallPublictBgnde"))
    if source_id is None or registered_at is None:
        return None
    return RecallRecord(
        source=f"{NAME}_{menu_id}",
        source_id=source_id,
        category=category,
        product_name=html_to_text(item.get("productNm")),
        company_name=html_to_text(item.get("bsnmNm")) or html_to_text(item.get("makr")),
        reason=html_to_text(item.get("shrtcomCn")) or html_to_text(item.get("injryCauseResult")),
        grade=None,  # hrmflGrad는 형식이 정해지지 않아 raw에만 둔다.
        manufactured_text=html_to_text(item.get("mnfcturPd")),
        expiry_text=html_to_text(item.get("distbTmlmtDe")),
        recall_method=recall_method(item.get("recallProcssInfo")),
        # recallEntrpsInfo는 주소보다 전화번호·홈페이지가 많아 address가 아니라 contact_text에 둔다.
        address=None,
        contact_text=html_to_text(item.get("recallEntrpsInfo")),
        barcode=parse_barcode(item.get("stdBrcd")),
        image_urls=parse_image_urls(item.get("recallImgUrls")),
        # 문서의 infoOriginUrl은 실제 응답에서 infoOriginInsttUrl이다. 건별 링크가 아니라
        # 정보 출처 기관의 홈페이지 주소다.
        source_url=clean_text(item.get("infoOriginInsttUrl")),
        source_label=html_to_text(item.get("infoOriginInstt")) or DEFAULT_SOURCE_LABEL,
        model_text=html_to_text(item.get("modlNmInfo")),
        consumer_tips=html_to_text(item.get("cnsmrGhvrTips")),
        recall_period_text=recall_period(item.get("recallBgnde"), item.get("recallEndde")),
        registered_at=registered_at,
        raw=item,  # content 원문 전체 (stdBrcd 원문, hrmflGrad, etcInfo 등)
    )


def _kst_today() -> date:
    return datetime.now(KST).date()


class Consumer24Collector(Collector):
    def __init__(
        self,
        menu_id: str,
        api_key: str,
        *,
        window_days: int,
        lookback_days: int = 30,
        transport: httpx.AsyncBaseTransport | None = None,
        page_size: int = PAGE_SIZE,
        request_interval: float = REQUEST_INTERVAL_SECONDS,
        today: Callable[[], date] = _kst_today,
    ) -> None:
        """window_days: 받는 공표일 범위의 최대치.

        SNAPSHOT_DAYS, 0501(해외리콜)은 CONSUMER24_OVERSEAS_DAYS.
        """
        if menu_id not in MENU_CATEGORIES:
            raise ValueError(f"unsupported consumer24 menu: {menu_id}")
        self.menu_id = menu_id
        self.source = f"{NAME}_{menu_id}"
        self.categories = (MENU_CATEGORIES[menu_id],)
        self._api_key = api_key
        self._window_days = window_days
        self._lookback_days = lookback_days
        self._transport = transport
        self._page_size = page_size
        self._request_interval = request_interval
        self._today = today

    @property
    def group(self) -> str:
        return NAME

    def since(self, last_success_at: datetime | None) -> date:
        """요청할 공표 시작일 하한.

        성공 기록이 없으면 오늘 - window_days. 있으면 마지막 성공일 - lookback_days이되
        오늘 - window_days보다 이르지 않게 한다. 매시간 수집하면 "오늘 - lookback_days"와 같고,
        수집이 끊겼다가 다시 돌 때는 그 공백까지(최대 window_days) 거슬러 받는다.
        """
        floor = self._today() - timedelta(days=self._window_days)
        if last_success_at is None:
            return floor
        incremental = last_success_at.astimezone(KST).date() - timedelta(days=self._lookback_days)
        return max(floor, incremental)

    async def fetch(self, last_success_at: datetime | None = None) -> FetchResult:
        if not self._api_key:
            raise CollectError(f"CONSUMER24_KEY_{self.menu_id} is not set")
        since = self.since(last_success_at)

        items: list[dict[str, str]] = []
        async with httpx.AsyncClient(timeout=30.0, transport=self._transport) as client:
            page_no = 1
            while True:
                total, page = await self._fetch_page(client, page_no, since)
                items.extend(page)
                if not page or page_no * self._page_size >= total:
                    break
                page_no += 1
            undated = await self._count_undated(client)

        # 페이지를 넘기는 사이 새 항목이 끼면 같은 항목이 두 번 올 수 있어 recallSn으로 합친다.
        records: dict[str, RecallRecord] = {}
        invalid = 0
        for item in items:
            record = normalize_item(item, self.menu_id)
            if record is None:
                invalid += 1
            else:
                records[record.source_id] = record
        if undated or invalid:
            log.warning(
                "%s: skipped %d items without publication date, %d invalid items",
                self.source,
                undated,
                invalid,
            )
        return FetchResult(list(records.values()), skipped_count=undated + invalid)

    async def _count_undated(self, client: httpx.AsyncClient) -> int:
        """공표일이 없는 건수 (메뉴 전체). 날짜 조건을 걸면 API가 이런 항목을 아예 빼고 주므로
        조건 없는 allCnt에서 공표일이 있는 건수를 뺀다."""
        total, _ = await self._fetch_page(client, 1, None, page_size=1)
        dated, _ = await self._fetch_page(client, 1, date(1900, 1, 1), page_size=1)
        return max(total - dated, 0)

    async def probe(self) -> ProbeResult:
        params = {
            "serviceKey": self._api_key,
            "pageNo": 1,
            "cntPerPage": 1,
            "cntntsId": self.menu_id,
        }
        await asyncio.sleep(self._request_interval)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=30.0, transport=self._transport) as client:
                resp = await client.get(BASE_URL, params=params)
        except httpx.HTTPError as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            return ProbeResult(self.source, ok=False, elapsed_ms=elapsed, error=type(exc).__name__)
        elapsed = int((time.perf_counter() - started) * 1000)
        result = ProbeResult(
            self.source, ok=False, http_status=resp.status_code, elapsed_ms=elapsed
        )
        try:
            element = _result_element(resp.content)
        except CollectError as exc:
            result.error = str(exc)
            return result
        result.code = (element.findtext("code") or "").strip()
        result.ok = resp.status_code == 200 and result.code in (CODE_OK, CODE_NO_DATA)
        if result.code == CODE_OK:
            try:
                total, items = parse_response(resp.content)
            except CollectError as exc:
                result.ok, result.error = False, str(exc)
                return result
            result.total = total
            result.image_urls = [u for i in items for u in parse_image_urls(i.get("recallImgUrls"))]
        elif result.code == CODE_NO_DATA:
            result.total = 0
        else:
            result.error = (element.findtext("codeMsg") or "").strip()
        return result

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        page_no: int,
        since: date | None,
        page_size: int | None = None,
    ) -> tuple[int, list[dict[str, str]]]:
        params = {
            "serviceKey": self._api_key,
            "pageNo": page_no,
            "cntPerPage": page_size or self._page_size,
            "cntntsId": self.menu_id,
        }
        if since is not None:
            params["recallPublictBgnde"] = since.strftime("%Y%m%d")
        # 메뉴가 바뀔 때도 간격이 생기도록 첫 요청 전에도 쉰다.
        await asyncio.sleep(self._request_interval)
        try:
            resp = await client.get(BASE_URL, params=params)
        except httpx.HTTPError as exc:
            # httpx 예외 메시지에는 URL(=serviceKey)이 들어갈 수 있으므로 타입만 남긴다.
            raise CollectError(f"request failed: {type(exc).__name__}") from None
        if resp.status_code != 200:
            raise CollectError(f"HTTP {resp.status_code}")
        return parse_response(resp.content)
