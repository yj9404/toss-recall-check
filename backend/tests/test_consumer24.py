import asyncio
import json
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime

import httpx
import pytest

from app import collect
from app.collectors.base import KST, CollectError
from app.collectors.consumer24 import (
    DEFAULT_SOURCE_LABEL,
    Consumer24Collector,
    consumer_tips,
    html_to_text,
    normalize_item,
    parse_barcode,
    parse_response,
    recall_method,
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


TODAY = date(2026, 10, 20)


def _collector(menu: str, key: str, handler, **kwargs) -> Consumer24Collector:
    kwargs.setdefault("window_days", 1095)
    return Consumer24Collector(
        menu,
        key,
        transport=httpx.MockTransport(handler),
        request_interval=0,
        today=lambda: TODAY,
        **kwargs,
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
    record = normalize_item(item, "0101")
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
    assert record.recall_method is None  # "인증번호: CB067R2225-4001"은 회수 방법이 아니다
    assert record.raw["recallProcssInfo"] == "인증번호: CB067R2225-4001"
    assert record.address is None
    assert record.contact_text is None
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
    # 사전에 있는 문장이라 "ㅇ" 글머리 없이 사전 값으로 바뀐다. 원문은 raw에 그대로 있다.
    assert record.consumer_tips == (
        "해당 제품을 보유하고 있는 소비자는 즉시 사용을 중지할 것\n"
        "문의처에 연락·방문 등을 통하여 수리, 교환, 환불 등 조치를 받을 것"
    )
    assert record.raw["cnsmrGhvrTips"].startswith("ㅇ 해당 제품을 보유하고")
    assert record.recall_period_text is None
    assert record.raw == item
    assert record.raw["stdBrcd"] == "-"
    assert record.raw["etcInfo"] == "브랜드명: -, 연락처: 02-322-4110"


def test_normalize_vehicle_item_strips_html():
    item = _items("consumer24_0301.xml")[0]
    record = normalize_item(item, "0301")
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
    assert record.address is None
    assert record.contact_text == "현대자동차 대표번호 080-600-6000"
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
    record = normalize_item(item, "0101")
    assert record is not None
    assert record.company_name == "제조사"
    assert record.reason == "결함 내용"
    assert record.source_label == DEFAULT_SOURCE_LABEL
    assert record.source_url is None


@pytest.mark.parametrize(
    "override",
    [
        {"recallSn": ""},
        {"recallPublictBgnde": ""},
        {"recallPublictBgnde": "2026091"},
        {"recallPublictBgnde": "20261340"},
    ],
)
def test_normalize_skips_items_without_id_or_date(override):
    assert normalize_item({**_items("consumer24_0101.xml")[0], **override}, "0101") is None


def test_category_and_source_follow_requested_menu():
    # 해외리콜(0501)로 요청하면 하위 분류 cntntsId(0502·0503·0504)가 섞여 온다.
    item = {**_items("consumer24_0101.xml")[0], "cntntsId": "0502"}
    record = normalize_item(item, "0501")
    assert record is not None
    assert (record.source, record.category) == ("consumer24_0501", "overseas")
    assert record.raw["cntntsId"] == "0502"


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
    record = normalize_item(item, "0101")
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
    ("value", "expected"),
    [
        ("인증번호: CB067R2225-4001", None),
        ("인증번호: -", None),
        ("인증번호 : 공급자적합성", None),
        ("인증번호: CB064R3345-1003 <br (인증모델: 반짝반짝 달님이)>", None),
        ("<p>무상 수리 후 반환</p>", "무상 수리 후 반환"),
        ("사업자 홈페이지 주소 :\n\n이메일 :", "사업자 홈페이지 주소 :\n\n이메일 :"),
        ("", None),
    ],
)
def test_recall_method_drops_certification_numbers(value, expected):
    assert recall_method(value) == expected


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


TIP_STOP = "해당 제품을 보유하고 있는 소비자는 즉시 사용을 중지할 것"
TIP_REPAIR = "문의처에 연락·방문 등을 통하여 수리, 교환, 환불 등 조치를 받을 것"
TIP_NEW_PRODUCT = "문의처 또는 구입처 등에 연락·방문하여 새 제품으로 교환, 환불 등 조치를 받을 것"
TIP_REFUND = "문의처에 연락·방문 등을 통하여 환불 등 조치를 받을 것"
TIP_FIRE = "통상 사용 시 과도한 온도 상승으로 인한 화재의 위험성이 있음"
TIP_BURN = "통상 사용 시 신체에 접촉될 경우 화상의 위험이 있음"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 2026-10-20 운영 DB에서 띄어쓰기 없이 온 공산품(0101) 원문 8종 (건수 순)
        (
            "ㅇ해당제품을보유하고있는소비자는즉시사용을중지할것\n"
            "ㅇ문의처에연락·방문등을통하여수리교환환불등조치를받을것",
            f"{TIP_STOP}\n{TIP_REPAIR}",
        ),
        (
            "ㅇ해당제품을보유하고있는소비자는즉시사용을중지할것\r\n"
            "ㅇ문의처에연락·방문등을통하여수리,교환,환불등조치를받을것",
            f"{TIP_STOP}\n{TIP_REPAIR}",
        ),
        (
            "ㅇ해당제품을보유하고있는소비자는즉시사용을중지할것\n"
            "ㅇ문의처또는구입처등에연락·방문하여새제품으로교환환불등조치를받을것",
            f"{TIP_STOP}\n{TIP_NEW_PRODUCT}",
        ),
        (
            # 줄바꿈 없이 "ㅇ" 글머리로만 이어진 경우
            "ㅇ해당제품을보유하고있는소비자는즉시사용을중지할것"
            "ㅇ문의처에연락·방문등을통하여수리교환환불등조치를받을것",
            f"{TIP_STOP}\n{TIP_REPAIR}",
        ),
        (
            "ㅇ해당제품을보유하고있는소비자는즉시사용을중지할것\n"
            "ㅇ문의처에연락·방문등을통하여 환불등조치를받을것",
            f"{TIP_STOP}\n{TIP_REFUND}",
        ),
        ("ㅇ해당제품을보유하고있는소비자는즉시사용을중지할것", TIP_STOP),
        (
            "ㅇ통상사용시과도한온도상승으로인한화재의위험성이있음\n"
            "ㅇ통상사용시신체에접촉될경우화상의위험이있음",
            f"{TIP_FIRE}\n{TIP_BURN}",
        ),
        (
            # 일부만 띄어 쓴 원문
            "ㅇ해당제품을 보유하고 있는소비자는즉시사용을중지할것\n"
            "ㅇ문의처에연락·방문등을통하여수리교환환불등조치를받을것",
            f"{TIP_STOP}\n{TIP_REPAIR}",
        ),
    ],
)
def test_consumer_tips_respaces_known_sentences(raw, expected):
    assert consumer_tips(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        # 사전에 없는 문장이 하나라도 섞이면 보정하지 않는다
        "ㅇ해당제품을보유하고있는소비자는즉시사용을중지할것\nㅇ가까운서비스센터에방문할것",
        "ㅇ해당제품을보유하고있는소비자는즉시사용을중지할것ㅇ제조사홈페이지를확인할것",
        "스피커 사용을 즉시 중단하시고, 전원 플러그를 뽑아 주십시오.",
    ],
)
def test_consumer_tips_keeps_text_when_any_sentence_is_unknown(raw):
    assert consumer_tips(raw) == html_to_text(raw)


@pytest.mark.parametrize("raw", [None, "", "  "])
def test_consumer_tips_empty(raw):
    assert consumer_tips(raw) is None


def test_normalize_respaces_tips_but_keeps_raw():
    item = _items("consumer24_0101.xml")[0]
    no_space = (
        "ㅇ해당제품을보유하고있는소비자는즉시사용을중지할것\n"
        "ㅇ문의처에연락·방문등을통하여수리교환환불등조치를받을것"
    )
    record = normalize_item({**item, "cnsmrGhvrTips": no_space}, "0101")
    assert record is not None
    assert record.consumer_tips == f"{TIP_STOP}\n{TIP_REPAIR}"
    assert record.raw["cnsmrGhvrTips"] == no_space


def test_record_is_json_serializable():
    record = normalize_item(_items("consumer24_0301.xml")[0], "0301")
    assert record is not None
    json.dumps(record.model_dump(mode="json"), ensure_ascii=False)


# --- 수집 (httpx 모킹) ---


def _api(page_handler=None, *, total: int = 3, dated: int = 3, seen: list | None = None):
    """목록 요청은 page_handler로 답하고, 공표일 없는 건수를 세는 1건짜리 요청(cntPerPage=1)은
    날짜 조건이 없으면 total, recallPublictBgnde=19000101이면 dated를 allCnt로 답한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params["cntPerPage"] == "1":
            all_cnt = dated if params.get("recallPublictBgnde") == "19000101" else total
            return _xml(_page("consumer24_0101.xml", all_cnt, 0, 1))
        if seen is not None:
            seen.append(params)
        return page_handler(request)

    return handler


def test_first_fetch_gets_snapshot_window_with_required_params():
    seen = []
    handler = _api(lambda r: _xml(_page("consumer24_0101.xml", 3, 0, 3)), seen=seen)
    result = asyncio.run(_collector("0101", KEY_0101, handler).fetch(None))
    assert [r.source_id for r in result.records] == [
        "RCLL_000000000607750",
        "RCLL_000000000607751",
        "RCLL_000000000607650",
    ]
    # 성공 기록이 없으면 전량이 아니라 오늘(2026-10-20) - window_days(1095)부터
    assert seen == [
        {
            "serviceKey": KEY_0101,
            "pageNo": "1",
            "cntPerPage": "100",
            "cntntsId": "0101",
            "recallPublictBgnde": "20231021",
        }
    ]


def test_overseas_first_fetch_uses_short_window():
    seen = []
    handler = _api(lambda r: _xml(_fixture("consumer24_code30.xml")), seen=seen)
    collector = _collector("0501", "key-0501", handler, window_days=180)
    asyncio.run(collector.fetch(None))
    assert [p["recallPublictBgnde"] for p in seen] == ["20260423"]


def test_fetch_paginates_by_all_cnt():
    seen = []

    def pages(request: httpx.Request) -> httpx.Response:
        page_no = int(request.url.params["pageNo"])
        start = (page_no - 1) * 2
        return _xml(_page("consumer24_0101.xml", 3, start, start + 2))

    handler = _api(pages, seen=seen)
    result = asyncio.run(_collector("0101", KEY_0101, handler, page_size=2).fetch(None))
    assert len(result.records) == 3
    assert [(p["pageNo"], p["cntPerPage"]) for p in seen] == [("1", "2"), ("2", "2")]


def test_fetch_stops_on_empty_page_even_if_all_cnt_is_larger():
    seen = []

    def pages(request: httpx.Request) -> httpx.Response:
        if request.url.params["pageNo"] == "1":
            return _xml(_page("consumer24_0101.xml", 10, 0, 2))
        return _xml(_page("consumer24_0101.xml", 10, 0, 0))

    handler = _api(pages, seen=seen)
    result = asyncio.run(_collector("0101", KEY_0101, handler, page_size=2).fetch(None))
    assert len(result.records) == 2
    assert [p["pageNo"] for p in seen] == ["1", "2"]


def test_fetch_merges_duplicates_across_pages():
    def pages(request: httpx.Request) -> httpx.Response:
        # 페이지 사이에 새 항목이 끼어 1페이지 마지막 항목이 2페이지에 다시 나온 경우
        start = 0 if request.url.params["pageNo"] == "1" else 1
        return _xml(_page("consumer24_0101.xml", 4, start, start + 2))

    collector = _collector("0101", KEY_0101, _api(pages), page_size=2)
    result = asyncio.run(collector.fetch(None))
    assert sorted(r.source_id for r in result.records) == [
        "RCLL_000000000607650",
        "RCLL_000000000607750",
        "RCLL_000000000607751",
    ]


@pytest.mark.parametrize(
    ("last_success_at", "lookback_days", "window_days", "expected"),
    [
        (datetime(2026, 10, 19, 9, 0, tzinfo=KST), 30, 1095, "20260919"),
        (datetime(2026, 10, 19, 9, 0, tzinfo=KST), 7, 1095, "20261012"),
        # UTC 10-18 16:00은 KST 10-19 01:00이다.
        (datetime(2026, 10, 18, 16, 0, tzinfo=UTC), 30, 1095, "20260919"),
        # 수집이 끊겼으면 마지막 성공일부터 거슬러 받는다.
        (datetime(2026, 8, 1, 12, 0, tzinfo=KST), 30, 1095, "20260702"),
        # 다만 오늘 - window_days보다 이르게는 가지 않는다.
        (datetime(2022, 1, 1, 12, 0, tzinfo=KST), 30, 1095, "20231021"),
        (datetime(2026, 3, 1, 12, 0, tzinfo=KST), 30, 180, "20260423"),
    ],
)
def test_incremental_fetch_sends_publication_start_date(
    last_success_at, lookback_days, window_days, expected
):
    seen = []
    handler = _api(lambda r: _xml(_page("consumer24_0301.xml", 3, 0, 3)), seen=seen)
    collector = _collector(
        "0301", KEY_0301, handler, lookback_days=lookback_days, window_days=window_days
    )
    result = asyncio.run(collector.fetch(last_success_at))
    assert len(result.records) == 3
    [params] = seen
    assert params["recallPublictBgnde"] == expected
    assert params["cntntsId"] == "0301"
    assert "recallPublictEndde" not in params


def test_overseas_sub_menu_items_are_kept():
    root = ET.fromstring(_page("consumer24_0101.xml", 3, 0, 3))
    for content, sub in zip(
        root.iterfind("channel/return/content"), ("0502", "0503", "0504"), strict=True
    ):
        content.find("cntntsId").text = sub
    body = ET.tostring(root, encoding="utf-8")
    handler = _api(lambda r: _xml(body), total=3, dated=3)
    result = asyncio.run(_collector("0501", "key-0501", handler, window_days=180).fetch(None))
    assert len(result.records) == 3
    assert result.skipped_count == 0
    assert {(r.source, r.category) for r in result.records} == {("consumer24_0501", "overseas")}


def test_undated_items_are_counted_as_skipped():
    # 날짜 조건을 걸면 API가 공표일 없는 항목을 빼고 주므로 allCnt 차이로 센다.
    # 0207(의료기기)은 전부 공표일이 없다.
    handler = _api(lambda r: _xml(_fixture("consumer24_code30.xml")), total=113, dated=0)
    result = asyncio.run(_collector("0207", "key-0207", handler).fetch(None))
    assert result.records == []
    assert result.skipped_count == 113


def test_invalid_items_are_added_to_skipped():
    root = ET.fromstring(_page("consumer24_0101.xml", 2, 0, 2))
    root.find("channel/return/content/recallPublictBgnde").text = "2026-09-16"
    body = ET.tostring(root, encoding="utf-8")
    handler = _api(lambda r: _xml(body), total=5, dated=4)
    result = asyncio.run(_collector("0101", KEY_0101, handler).fetch(None))
    assert len(result.records) == 1
    assert result.skipped_count == 1 + 1  # 공표일 없음 1 + 형식 오류 1


def test_fetch_code_30_returns_empty():
    handler = _api(lambda r: _xml(_fixture("consumer24_code30.xml")), total=0, dated=0)
    collector = _collector("0301", KEY_0301, handler)
    result = asyncio.run(collector.fetch(datetime(2026, 10, 19, tzinfo=KST)))
    assert (result.records, result.skipped_count) == ([], 0)


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
        asyncio.run(Consumer24Collector("0101", "", window_days=1095).fetch(None))


def test_unsupported_menu_is_rejected():
    for menu in ("0201", "0203", "9999"):
        with pytest.raises(ValueError):
            Consumer24Collector(menu, "key", window_days=1095)


# --- probe (python -m app.check_sources) ---


def test_probe_reports_status_code_total_and_images():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return _xml(_page("consumer24_0101.xml", 4474, 0, 1))

    result = asyncio.run(_collector("0101", KEY_0101, handler).probe())
    assert seen == [{"serviceKey": KEY_0101, "pageNo": "1", "cntPerPage": "1", "cntntsId": "0101"}]
    assert result.ok
    assert (result.source, result.http_status, result.code, result.total) == (
        "consumer24_0101",
        200,
        "00",
        4474,
    )
    assert len(result.image_urls) == 2
    assert result.elapsed_ms >= 0


def test_probe_code_30_is_ok():
    handler = lambda r: _xml(_fixture("consumer24_code30.xml"))  # noqa: E731
    result = asyncio.run(_collector("0403", "key", handler).probe())
    assert (result.ok, result.code, result.total) == (True, "30", 0)


def test_probe_code_50_is_failure():
    handler = lambda r: _xml(_fixture("consumer24_code50.xml"))  # noqa: E731
    result = asyncio.run(_collector("0101", KEY_0101, handler).probe())
    assert not result.ok
    assert result.code == "50"
    assert result.error == "등록되지 않은 서비스키 에러"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403, text="<html>blocked</html>"),
        httpx.Response(200, text="<html>maintenance</html>"),
    ],
)
def test_probe_non_api_response_is_failure(response):
    result = asyncio.run(_collector("0101", KEY_0101, lambda r: response).probe())
    assert not result.ok
    assert result.http_status == response.status_code


def test_probe_transport_error_does_not_leak_key():
    def handler(request):
        raise httpx.ConnectTimeout(f"timed out connecting to {request.url}")

    result = asyncio.run(_collector("0101", KEY_0101, handler).probe())
    assert not result.ok
    assert result.http_status is None
    assert result.error == "ConnectTimeout"


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

    ok = _api(lambda r: _xml(_page("consumer24_0301.xml", 3, 0, 3)), total=5, dated=3)
    collectors = [_collector("0101", KEY_0101, failing), _collector("0301", KEY_0301, ok)]
    results = asyncio.run(collect.run_collection(_FakePool(), collectors, [KEY_0101, KEY_0301]))

    assert [(r.source, r.status, r.row_count, r.skipped_count) for r in results] == [
        ("consumer24_0101", "error", 0, 0),
        ("consumer24_0301", "ok", 3, 2),
    ]
    # 실패한 메뉴는 upsert하지 않으므로 기존 데이터가 그대로 남는다.
    [upserted] = fake_db["upsert"]
    assert {r.source for r in upserted} == {"consumer24_0301"}
    assert fake_db["success"] == [("consumer24_0301", 3, 2)]
    [(source, message)] = fake_db["error"]
    assert source == "consumer24_0101"
    assert "API result 50" in message
    assert KEY_0101 not in message


def test_source_state_is_per_menu(fake_db):
    seen = {}

    def pages(request):
        seen[request.url.params["cntntsId"]] = request.url.params.get("recallPublictBgnde")
        return _xml(_fixture("consumer24_code30.xml"))

    handler = _api(pages, total=0, dated=0)
    fake_db["last_success"]["consumer24_0301"] = datetime(2026, 10, 19, 9, 0, tzinfo=KST)
    collectors = [_collector("0101", KEY_0101, handler), _collector("0301", KEY_0301, handler)]
    asyncio.run(collect.run_collection(_FakePool(), collectors, []))
    # 0101은 성공 기록이 없어 첫 수집 범위, 0301은 증분
    assert seen == {"0101": "20231021", "0301": "20260919"}
    assert fake_db["success"] == [("consumer24_0101", 0, 0), ("consumer24_0301", 0, 0)]


def test_full_run_ignores_success_records(fake_db):
    seen = {}

    def pages(request):
        seen[request.url.params["cntntsId"]] = request.url.params.get("recallPublictBgnde")
        return _xml(_fixture("consumer24_code30.xml"))

    fake_db["last_success"]["consumer24_0301"] = datetime(2026, 10, 19, 9, 0, tzinfo=KST)
    collectors = [_collector("0301", KEY_0301, _api(pages, total=0, dated=0))]
    asyncio.run(collect.run_collection(_FakePool(), collectors, [], full=True))
    assert seen == {"0301": "20231021"}
