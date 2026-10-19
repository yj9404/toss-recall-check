import asyncio
import json
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest

from app import collect
from app.collectors.base import KST, CollectError
from app.collectors.consumer24 import (
    DEFAULT_SOURCE_LABEL,
    Consumer24Collector,
    html_to_text,
    normalize_item,
    parse_barcode,
    parse_response,
    recall_period,
)
from tests.conftest import FIXTURES

KEY_0101 = "key-0101-secret"
KEY_0301 = "key-0301-secret"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _items(name: str) -> list[dict[str, str]]:
    return parse_response(_fixture(name))[1]


def _page(name: str, all_cnt: int, start: int, stop: int) -> bytes:
    """fixture에서 content[start:stop]만 남기고 allCnt를 바꾼 정상 응답."""
    root = ET.fromstring(_fixture(name))
    result = root.find("channel/return")
    result.find("allCnt").text = str(all_cnt)
    for i, content in enumerate(result.findall("content")):
        if not start <= i < stop:
            result.remove(content)
    return ET.tostring(root, encoding="utf-8")


def _xml(body: bytes) -> httpx.Response:
    return httpx.Response(200, content=body, headers={"content-type": "text/xml;charset=UTF-8"})


def _collector(menu: str, key: str, handler, **kwargs) -> Consumer24Collector:
    return Consumer24Collector(
        menu, key, transport=httpx.MockTransport(handler), request_interval=0, **kwargs
    )


# --- 응답 파싱 (실제 응답 fixture) ---


def test_parse_normal_response_under_channel_return():
    total, items = parse_response(_fixture("consumer24_0101.xml"))
    assert total == 4474
    assert [i["recallSn"] for i in items] == [
        "RCLL_000000000607750",
        "RCLL_000000000607751",
        "RCLL_000000000607650",
    ]
    assert items[0]["makr"] == ""  # 빈 값은 <![CDATA[]]>
    assert set(items[0]) >= {"cntntsId", "hrmflGrad", "infoOriginInsttUrl", "recallImgUrls"}


def test_parse_code_30_is_empty():
    assert parse_response(_fixture("consumer24_code30.xml")) == (0, [])


def test_parse_code_50_raises_with_message():
    with pytest.raises(CollectError, match="API result 50: 등록되지 않은 서비스키 에러"):
        parse_response(_fixture("consumer24_code50.xml"))


@pytest.mark.parametrize(
    "body",
    [
        b"<html>maintenance</html>",
        b"not xml",
        b"<root><channel><return><code>00</code></return></channel></root>",  # allCnt 없음
    ],
)
def test_parse_unexpected_body_raises(body):
    with pytest.raises(CollectError):
        parse_response(body)


# --- 매핑 ---


def test_normalize_consumer_product_item():
    item = _items("consumer24_0101.xml")[0]
    record = normalize_item(item)
    assert record is not None
    assert record.source == "consumer24_0101"
    assert record.source_id == "RCLL_000000000607750"
    assert record.category == "consumer_product"
    assert record.product_name == "기타완구(완구)"
    assert record.company_name == "핑크풋"
    # shrtcomCn이 비어 있어 injryCauseResult를 쓴다. 줄 끝 공백은 정리된다.
    assert record.reason is not None
    assert record.reason.startswith("ㅇ 방부제(MIT, CMIT, MIT+CMIT) 검출됨\n- 부위: 슬라임(하양)\n")
    assert record.reason.endswith("- 기준치: 300 mg/kg 이하")
    assert record.grade is None
    assert record.manufactured_text is None
    assert record.expiry_text is None
    assert record.recall_method == "인증번호: CB067R2225-4001"
    assert record.address is None
    assert record.barcode is None  # stdBrcd "-"
    assert record.image_urls == [
        "https://www.consumer.go.kr/openapi/recall/contents/recallApiImage.do?atchmnflId=10578512",
        "https://www.consumer.go.kr/openapi/recall/contents/recallApiImage.do?atchmnflId=10578511",
    ]
    assert record.registered_at == datetime(2026, 9, 16, tzinfo=KST)
    assert record.registered_at.isoformat() == "2026-09-16T00:00:00+09:00"
    assert record.source_url == "http://www.kats.go.kr"
    assert record.source_label == "국가기술표준원"
    assert record.model_text == "핑크풋 슬라임"
    assert record.consumer_tips == (
        "ㅇ 해당 제품을 보유하고 있는 소비자는 즉시 사용을 중지할 것\n"
        "ㅇ 문의처에 연락·방문 등을 통하여 수리, 교환, 환불 등 조치를 받을 것"
    )
    assert record.recall_period_text is None
    assert record.raw == item
    assert record.raw["stdBrcd"] == "-"
    assert record.raw["etcInfo"] == "브랜드명: -, 연락처: 02-322-4110"


def test_normalize_vehicle_item_strips_html():
    item = _items("consumer24_0301.xml")[0]
    record = normalize_item(item)
    assert record is not None
    assert record.source == "consumer24_0301"
    assert record.category == "vehicle"
    assert record.product_name == "[현대] 아반떼 등 2차종 - 운전석 에어백 인플레이터 관련 리콜"
    assert record.company_name == "현대자동차(주)"
    assert record.reason == (
        "일부 차량에서 운전석 에어백 전개 시 인플레이터의 과도한 내부 압력 증가로 인해 "
        "인플레이터 용기가 파손될 수 있는 가능성이 확인됨에 따른리콜\n"
        "\n"
        "<대상차량별 생산일자>\n"
        "아반떼 (HD): 2010.06.23~2010.07.30 (문제 부품 장착 차량 한정)\n"
        "i30 (FD): 2010.06.23~2010.08.14 (문제 부품 장착 차량 한정)"
    )
    assert record.manufactured_text == "20100623~20100814"
    assert record.model_text == "아반떼 (HD), i30 (FD)"
    assert record.address == "현대자동차 대표번호 080-600-6000"
    assert record.recall_method is None
    assert record.recall_period_text == "20261014~"
    assert record.registered_at == datetime(2026, 10, 14, tzinfo=KST)
    assert record.image_urls == []
    assert record.source_label == "국토교통부"
    assert record.raw["etcInfo"].startswith("<p>")  # raw는 원문 그대로


def test_normalize_fallbacks():
    item = {
        **_items("consumer24_0101.xml")[0],
        "bsnmNm": "",
        "makr": "제조사",
        "shrtcomCn": "결함 내용",
        "infoOriginInstt": "",
        "infoOriginInsttUrl": "",
    }
    record = normalize_item(item)
    assert record is not None
    assert record.company_name == "제조사"
    assert record.reason == "결함 내용"
    assert record.source_label == DEFAULT_SOURCE_LABEL
    assert record.source_url is None


@pytest.mark.parametrize(
    "override",
    [
        {"recallSn": ""},
        {"cntntsId": "0201"},  # 식품은 받지 않는다
        {"cntntsId": "0203"},  # 축산물도
        {"recallPublictBgnde": ""},
        {"recallPublictBgnde": "2026091"},
        {"recallPublictBgnde": "20261340"},
    ],
)
def test_normalize_skips_items_without_id_menu_or_date(override):
    assert normalize_item({**_items("consumer24_0101.xml")[0], **override}) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("8809070000000", "8809070000000"),
        (" 8809070000000\n", "8809070000000"),
        ("8809184004260,8809184001214", "8809184004260"),
        ("2000000281049 / 2000000281070", "2000000281049"),
        ("T4961310152277, T4961310152307", "4961310152277"),
        ("-", None),
        ("없음", None),
        ("", None),
        (None, None),
        ("880952049148", None),  # 12자리
        ("88095204914833", None),  # 14자리
        ("８８０９５２０４９１４８３", None),  # 전각 숫자
    ],
)
def test_parse_barcode(value, expected):
    assert parse_barcode(value) == expected


def test_normalize_keeps_raw_barcode_text():
    item = {**_items("consumer24_0101.xml")[0], "stdBrcd": "8809184004260,8809184001214"}
    record = normalize_item(item)
    assert record is not None
    assert record.barcode == "8809184004260"
    assert record.raw["stdBrcd"] == "8809184004260,8809184001214"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("<p>소프트웨어 업데이트\xa0</p>", "소프트웨어 업데이트"),
        ("<p>리콜</p><div><br></div>", "리콜"),
        ("<P>대문자</P><BR>", "대문자"),
        ('<b><u><span style="font-size: 11pt;">주의</span></u></b>', "주의"),
        (
            '홈페이지(<a target="_blank" href="http://www.winiaaid.com/x">'
            '<font color="blue">www.winiaaid.com</font></a>)<br/> 또는',
            "홈페이지(www.winiaaid.com)\n또는",
        ),
        # 꺾쇠로 감싼 본문은 태그가 아니다.
        (
            "램프홀더 <br> <br><KC 마크 및 안전확인 신고번호 누락> <br>",
            "램프홀더\n\n<KC 마크 및 안전확인 신고번호 누락>",
        ),
        (
            "인증번호: CB064R3345-1003 <br (인증모델: 반짝반짝 달님이)>",
            "인증번호: CB064R3345-1003 <br (인증모델: 반짝반짝 달님이)>",
        ),
        ("CB017R908-2002<bt>(인증모델: GB78)", "CB017R908-2002<bt>(인증모델: GB78)"),
        ("A &lt;B&gt; &middot; C", "A <B> · C"),
        ("줄1\n\n\n\n줄2", "줄1\n\n줄2"),
        ("<p> </p>", None),
        ("", None),
        (None, None),
    ],
)
def test_html_to_text(value, expected):
    assert html_to_text(value) == expected


@pytest.mark.parametrize(
    ("begin", "end", "expected"),
    [
        ("20261001", "20271231", "20261001~20271231"),
        ("20261014", "", "20261014~"),
        ("", "20271231", "~20271231"),
        ("", "", None),
    ],
)
def test_recall_period(begin, end, expected):
    assert recall_period(begin, end) == expected


def test_record_is_json_serializable():
    record = normalize_item(_items("consumer24_0301.xml")[0])
    assert record is not None
    json.dumps(record.model_dump(mode="json"), ensure_ascii=False)


# --- 수집 (httpx 모킹) ---


def test_first_fetch_gets_everything_with_required_params():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return _xml(_page("consumer24_0101.xml", 3, 0, 3))

    records = asyncio.run(_collector("0101", KEY_0101, handler).fetch(None))
    assert [r.source_id for r in records] == [
        "RCLL_000000000607750",
        "RCLL_000000000607751",
        "RCLL_000000000607650",
    ]
    assert seen == [
        {"serviceKey": KEY_0101, "pageNo": "1", "cntPerPage": "100", "cntntsId": "0101"}
    ]


def test_fetch_paginates_by_all_cnt():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        page_no = int(request.url.params["pageNo"])
        seen.append((page_no, request.url.params["cntPerPage"]))
        start = (page_no - 1) * 2
        return _xml(_page("consumer24_0101.xml", 3, start, start + 2))

    records = asyncio.run(_collector("0101", KEY_0101, handler, page_size=2).fetch(None))
    assert len(records) == 3
    assert seen == [(1, "2"), (2, "2")]


def test_fetch_stops_on_empty_page_even_if_all_cnt_is_larger():
    pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        page_no = int(request.url.params["pageNo"])
        pages.append(page_no)
        if page_no == 1:
            return _xml(_page("consumer24_0101.xml", 10, 0, 2))
        return _xml(_page("consumer24_0101.xml", 10, 0, 0))

    records = asyncio.run(_collector("0101", KEY_0101, handler, page_size=2).fetch(None))
    assert len(records) == 2
    assert pages == [1, 2]


def test_fetch_merges_duplicates_across_pages():
    def handler(request: httpx.Request) -> httpx.Response:
        # 페이지 사이에 새 항목이 끼어 1페이지 마지막 항목이 2페이지에 다시 나온 경우
        page_no = int(request.url.params["pageNo"])
        start = 0 if page_no == 1 else 1
        return _xml(_page("consumer24_0101.xml", 4, start, start + 2))

    records = asyncio.run(_collector("0101", KEY_0101, handler, page_size=2).fetch(None))
    assert sorted(r.source_id for r in records) == [
        "RCLL_000000000607650",
        "RCLL_000000000607750",
        "RCLL_000000000607751",
    ]


@pytest.mark.parametrize(
    ("last_success_at", "lookback_days", "expected"),
    [
        (datetime(2026, 10, 19, 9, 0, tzinfo=KST), 30, "20260919"),
        (datetime(2026, 10, 19, 9, 0, tzinfo=KST), 7, "20261012"),
        # UTC 10-18 16:00은 KST 10-19 01:00이다.
        (datetime(2026, 10, 18, 16, 0, tzinfo=UTC), 30, "20260919"),
        # 수집이 오래 끊겼으면 마지막 성공일부터 거슬러 받는다.
        (datetime(2026, 8, 1, 12, 0, tzinfo=KST), 30, "20260702"),
    ],
)
def test_incremental_fetch_sends_publication_start_date(last_success_at, lookback_days, expected):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return _xml(_page("consumer24_0301.xml", 3, 0, 3))

    collector = _collector("0301", KEY_0301, handler, lookback_days=lookback_days)
    records = asyncio.run(collector.fetch(last_success_at))
    assert len(records) == 3
    [params] = seen
    assert params["recallPublictBgnde"] == expected
    assert params["cntntsId"] == "0301"
    assert "recallPublictEndde" not in params


def test_fetch_code_30_returns_empty():
    def handler(request):
        return _xml(_fixture("consumer24_code30.xml"))

    collector = _collector("0301", KEY_0301, handler)
    assert asyncio.run(collector.fetch(datetime(2026, 10, 19, tzinfo=KST))) == []


def test_fetch_code_50_raises_without_key():
    def handler(request):
        return _xml(_fixture("consumer24_code50.xml"))

    with pytest.raises(CollectError) as info:
        asyncio.run(_collector("0101", KEY_0101, handler).fetch(None))
    assert "50" in str(info.value)
    assert KEY_0101 not in str(info.value)


def test_fetch_http_error_does_not_leak_key():
    def handler(request):
        return httpx.Response(500, text=f"error for {request.url}")

    with pytest.raises(CollectError) as info:
        asyncio.run(_collector("0101", KEY_0101, handler).fetch(None))
    assert KEY_0101 not in str(info.value)


def test_fetch_transport_error_does_not_leak_key():
    def handler(request):
        raise httpx.ConnectError(f"cannot connect to {request.url}")

    with pytest.raises(CollectError) as info:
        asyncio.run(_collector("0101", KEY_0101, handler).fetch(None))
    assert KEY_0101 not in str(info.value)


def test_fetch_requires_key():
    with pytest.raises(CollectError, match="CONSUMER24_KEY_0101"):
        asyncio.run(Consumer24Collector("0101", "").fetch(None))


def test_unsupported_menu_is_rejected():
    for menu in ("0201", "0203", "9999"):
        with pytest.raises(ValueError):
            Consumer24Collector(menu, "key")


# --- 메뉴 하나가 실패해도 나머지는 진행 ---


class _FakeCursor:
    async def fetchone(self):
        return (True,)  # advisory lock 획득


class _FakeConn:
    async def execute(self, sql, params=None):
        return _FakeCursor()


class _FakePool:
    @asynccontextmanager
    async def connection(self):
        yield _FakeConn()


def test_one_menu_failure_does_not_stop_others(fake_db):
    def failing(request):
        return _xml(_fixture("consumer24_code50.xml"))

    def ok(request):
        return _xml(_page("consumer24_0301.xml", 3, 0, 3))

    collectors = [_collector("0101", KEY_0101, failing), _collector("0301", KEY_0301, ok)]
    results = asyncio.run(collect.run_collection(_FakePool(), collectors, [KEY_0101, KEY_0301]))

    assert [(r.source, r.status, r.row_count) for r in results] == [
        ("consumer24_0101", "error", 0),
        ("consumer24_0301", "ok", 3),
    ]
    # 실패한 메뉴는 upsert하지 않으므로 기존 데이터가 그대로 남는다.
    [upserted] = fake_db["upsert"]
    assert {r.source for r in upserted} == {"consumer24_0301"}
    assert fake_db["success"] == [("consumer24_0301", 3)]
    [(source, message)] = fake_db["error"]
    assert source == "consumer24_0101"
    assert "API result 50" in message
    assert KEY_0101 not in message


def test_source_state_is_per_menu(fake_db):
    seen = {}

    def handler(request):
        seen[request.url.params["cntntsId"]] = request.url.params.get("recallPublictBgnde")
        return _xml(_fixture("consumer24_code30.xml"))

    fake_db["last_success"]["consumer24_0301"] = datetime(2026, 10, 19, 9, 0, tzinfo=KST)
    collectors = [_collector("0101", KEY_0101, handler), _collector("0301", KEY_0301, handler)]
    asyncio.run(collect.run_collection(_FakePool(), collectors, []))
    # 0101은 성공 기록이 없어 전량, 0301은 증분
    assert seen == {"0101": None, "0301": "20260919"}
    assert fake_db["success"] == [("consumer24_0101", 0), ("consumer24_0301", 0)]
