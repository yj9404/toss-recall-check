import asyncio

import httpx

from app.check_sources import check_image, format_probe, run_checks
from app.collectors.base import ProbeResult
from app.collectors.consumer24 import Consumer24Collector
from app.collectors.foodsafety_i0490 import FoodSafetyI0490Collector
from tests.conftest import FIXTURES, load_fixture

C24_KEY = "c24-secret-key"
FS_KEY = "fs-secret-key"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"0" * 100
ALLOWED = frozenset({"www.consumer.go.kr"})


def _c24(handler) -> Consumer24Collector:
    return Consumer24Collector(
        "0101",
        C24_KEY,
        window_days=1095,
        transport=httpx.MockTransport(handler),
        request_interval=0,
    )


def _fs(handler) -> FoodSafetyI0490Collector:
    return FoodSafetyI0490Collector(FS_KEY, transport=httpx.MockTransport(handler))


def _image_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _c24_ok(request):
    return httpx.Response(200, content=(FIXTURES / "consumer24_0101.xml").read_bytes())


def _fs_ok(request):
    return httpx.Response(200, json=load_fixture("i0490_sample.json"))


async def _run(collectors, image_handler):
    async with _image_client(image_handler) as client:
        return await run_checks(collectors, ALLOWED, client)


def test_all_sources_and_image_ok():
    images = []

    def image(request):
        images.append(str(request.url))
        return httpx.Response(200, content=JPEG)

    ok, lines = asyncio.run(_run([_fs(_fs_ok), _c24(_c24_ok)], image))
    assert ok
    assert lines[0].startswith("foodsafety_i0490\tok\thttp=200\tcode=INFO-000\ttotal=381\t")
    assert lines[1].startswith("consumer24_0101\tok\thttp=200\tcode=00\ttotal=4474\t")
    # 식품안전나라 이미지는 허용목록 밖이라 건너뛰고 소비자24 이미지를 프록시 방식으로 받는다.
    assert images == [
        "https://www.consumer.go.kr/openapi/recall/contents/recallApiImage.do?atchmnflId=10578512"
    ]
    assert lines[2].startswith("image\tok\timage/jpeg\t")
    assert not any(C24_KEY in line or FS_KEY in line for line in lines)


def test_blocked_source_fails_without_leaking_key():
    def blocked(request):
        raise httpx.ConnectTimeout(f"timed out connecting to {request.url}")

    ok, lines = asyncio.run(_run([_c24(blocked)], lambda r: httpx.Response(200, content=JPEG)))
    assert not ok
    fields = lines[0].split("\t")
    assert fields[:5] == ["consumer24_0101", "FAIL", "http=-", "code=-", "total=-"]
    assert fields[-1] == "ConnectTimeout"
    assert lines[1].startswith("image\tSKIP\t")
    assert not any(C24_KEY in line for line in lines)


def test_image_redirect_to_login_fails():
    def login(request):
        return httpx.Response(302, headers={"location": "https://www.consumer.go.kr/login"})

    ok, lines = asyncio.run(_run([_c24(_c24_ok)], login))
    assert not ok
    assert lines[-1].startswith("image\tFAIL\tproxy=502\t")


def test_no_allowed_image_is_skip():
    async def run():
        async with _image_client(lambda r: httpx.Response(200, content=JPEG)) as client:
            return await check_image(
                ["http://coop.foodsafetykorea.go.kr/open/minfo_image.do?fSeq=1"], ALLOWED, client
            )

    ok, line = asyncio.run(run())
    assert ok
    assert line.startswith("image\tSKIP\t")
    assert "coop.foodsafetykorea.go.kr" in line


def test_format_probe_shows_api_error_message():
    line = format_probe(
        ProbeResult("consumer24_0101", ok=False, http_status=200, code="50", error="미등록 키")
    )
    assert line == "consumer24_0101\tFAIL\thttp=200\tcode=50\ttotal=-\t0ms\t미등록 키"
