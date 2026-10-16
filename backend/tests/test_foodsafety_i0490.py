import asyncio
import json
from datetime import datetime

import httpx
import pytest

from app.collectors.base import KST, CollectError
from app.collectors.foodsafety_i0490 import FoodSafetyI0490Collector, normalize_row
from tests.conftest import load_fixture

API_KEY = "test-key-123"


def _rows():
    return load_fixture("i0490_sample.json")["I0490"]["row"]


def _collector(handler, **kwargs) -> FoodSafetyI0490Collector:
    return FoodSafetyI0490Collector(API_KEY, transport=httpx.MockTransport(handler), **kwargs)


def test_normalize_valid_barcode_row():
    record = normalize_row(_rows()[0])
    assert record is not None
    assert record.source == "foodsafety_i0490"
    assert record.source_id == "3000235717"
    assert record.category == "food"
    assert record.product_name == "그릭요거트 카페라떼"
    assert record.company_name == "(주)요즘"
    assert record.reason == "대장균군 기준 규격 부적합"
    assert record.grade == 3
    assert record.manufactured_text == "(제조일자) 2026-10-05"
    assert record.expiry_text == "(소비기한) 2026-10-19"
    assert record.package_unit == "100g"
    assert record.recall_method is None
    assert record.company_phone is None
    assert record.barcode == "8809520491483"
    assert record.image_urls == [
        "http://coop.foodsafetykorea.go.kr/open/minfo_image.do?fSeq=2681127",
        "http://coop.foodsafetykorea.go.kr/open/minfo_image.do?fSeq=2681128",
        "http://coop.foodsafetykorea.go.kr/open/minfo_image.do?fSeq=2678245",
    ]
    assert record.registered_at == datetime(2026, 10, 14, 15, 21, 26, 956787, tzinfo=KST)
    assert record.registered_at.isoformat().endswith("+09:00")
    assert record.raw["PRDLST_TYPE"] == "축산물"


def test_normalize_empty_barcode_and_images():
    record = normalize_row(_rows()[1])
    assert record is not None
    assert record.barcode is None
    assert record.image_urls == []
    assert record.grade == 1
    assert record.category == "food"  # 가공식품도 food
    assert record.package_unit == "-"


def test_normalize_nonstandard_barcode_keeps_raw_text_values():
    record = normalize_row(_rows()[2])
    assert record is not None
    assert record.barcode is None
    assert record.raw["BRCDNO"] == "R229632780001"
    assert record.manufactured_text == "데이터없음"
    assert record.grade == 2
    assert record.category == "food"  # 농산물도 food


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("880952049148", None),
        ("88095204914833", None),
        ("８８０９５２０４９１４８３", None),  # 전각 숫자
        (" 8809520491483\n", "8809520491483"),  # 앞뒤 공백은 정리
    ],
)
def test_normalize_barcode_requires_13_ascii_digits(value, expected):
    record = normalize_row({**_rows()[0], "BRCDNO": value})
    assert record is not None
    assert record.barcode == expected


def test_normalize_skips_rows_without_id_or_date():
    assert normalize_row({**_rows()[0], "RTRVLDSUSE_SEQ": ""}) is None
    assert normalize_row({**_rows()[0], "CRET_DTM": "not a date"}) is None


def test_fetch_parses_fixture_and_builds_url():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json=load_fixture("i0490_sample.json"))

    records = asyncio.run(_collector(handler).fetch())
    assert [r.source_id for r in records] == ["3000235717", "3000235627", "3000235620"]
    assert seen == [f"/api/{API_KEY}/I0490/json/1/1000"]


def test_fetch_paginates_until_total():
    data = load_fixture("i0490_sample.json")
    all_rows = data["I0490"]["row"]
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        start, end = (int(x) for x in request.url.path.rsplit("/", 2)[-2:])
        seen.append((start, end))
        body = {"I0490": {**data["I0490"], "total_count": "3", "row": all_rows[start - 1 : end]}}
        return httpx.Response(200, json=body)

    records = asyncio.run(_collector(handler, page_size=2).fetch())
    assert len(records) == 3
    assert seen == [(1, 2), (3, 4)]


def test_fetch_no_data_returns_empty():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "I0490": {
                    "total_count": "0",
                    "RESULT": {"CODE": "INFO-200", "MSG": "해당하는 데이터가 없습니다."},
                }
            },
        )

    assert asyncio.run(_collector(handler).fetch()) == []


@pytest.mark.parametrize(
    "body",
    [
        {"RESULT": {"CODE": "INFO-100", "MSG": "인증키가 유효하지 않습니다."}},
        {
            "I0490": {
                "RESULT": {
                    "CODE": "ERROR-336",
                    "MSG": "데이터요청은 한번에 최대 1000건을 넘을 수 없습니다.",
                }
            }
        },
        {"unexpected": True},
    ],
)
def test_fetch_error_codes_raise(body):
    def handler(request):
        return httpx.Response(200, json=body)

    with pytest.raises(CollectError):
        asyncio.run(_collector(handler).fetch())


def test_fetch_http_error_does_not_leak_key():
    def handler(request):
        return httpx.Response(500, text="oops")

    with pytest.raises(CollectError) as info:
        asyncio.run(_collector(handler).fetch())
    assert API_KEY not in str(info.value)


def test_fetch_transport_error_does_not_leak_key():
    def handler(request):
        raise httpx.ConnectError(f"cannot connect to {request.url}")

    with pytest.raises(CollectError) as info:
        asyncio.run(_collector(handler).fetch())
    assert API_KEY not in str(info.value)


def test_fetch_non_json():
    def handler(request):
        return httpx.Response(200, text="<html>maintenance</html>")

    with pytest.raises(CollectError):
        asyncio.run(_collector(handler).fetch())


def test_fetch_requires_key():
    with pytest.raises(CollectError):
        asyncio.run(FoodSafetyI0490Collector("").fetch())


def test_record_is_json_serializable():
    record = normalize_row(_rows()[0])
    json.dumps(record.model_dump(mode="json"), ensure_ascii=False)
