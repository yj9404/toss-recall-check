import httpx
import pytest

from app.images import MAX_BYTES

ALLOWED = "http://coop.foodsafetykorea.go.kr/open/minfo_image.do?fSeq=2681127"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


@pytest.fixture
def proxy_client(make_client):
    def factory(handler):
        client = make_client()
        calls = []

        def recording(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return handler(request)

        client.app.state.image_client = httpx.AsyncClient(transport=httpx.MockTransport(recording))
        return client, calls

    return factory


def test_proxy_passes_image(proxy_client):
    client, calls = proxy_client(
        lambda r: httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
    )
    resp = client.get("/api/v1/image", params={"u": ALLOWED})
    assert resp.status_code == 200
    assert resp.content == PNG
    assert resp.headers["content-type"] == "image/png"
    assert resp.headers["cache-control"] == "public, max-age=86400"
    assert calls == [ALLOWED]


@pytest.mark.parametrize(
    "url",
    [
        "http://evil.example/a.png",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost/a.png",
        "http://coop.foodsafetykorea.go.kr.evil.example/a.png",
        "http://coop.foodsafetykorea.go.kr:8080/a.png",
        "http://user@coop.foodsafetykorea.go.kr/a.png",
        "file:///etc/passwd",
        "ftp://coop.foodsafetykorea.go.kr/a.png",
        "not a url",
    ],
)
def test_proxy_rejects_hosts_outside_allowlist(proxy_client, url):
    client, calls = proxy_client(lambda r: httpx.Response(200, content=PNG))
    resp = client.get("/api/v1/image", params={"u": url})
    assert resp.status_code == 400
    assert calls == []


def test_proxy_sniffs_jpeg_without_content_type(proxy_client):
    # 식약처 이미지 서버는 Content-Type 헤더 없이 JPEG를 보낸다.
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"0" * 100
    client, _ = proxy_client(lambda r: httpx.Response(200, content=jpeg))
    resp = client.get("/api/v1/image", params={"u": ALLOWED})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"


def test_proxy_ignores_spoofed_content_type(proxy_client):
    client, _ = proxy_client(
        lambda r: httpx.Response(200, content=b"<html>", headers={"content-type": "image/png"})
    )
    assert client.get("/api/v1/image", params={"u": ALLOWED}).status_code == 502


def test_proxy_rejects_non_image(proxy_client):
    client, _ = proxy_client(
        lambda r: httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})
    )
    assert client.get("/api/v1/image", params={"u": ALLOWED}).status_code == 502


def test_proxy_rejects_svg(proxy_client):
    client, _ = proxy_client(
        lambda r: httpx.Response(200, content=b"<svg/>", headers={"content-type": "image/svg+xml"})
    )
    assert client.get("/api/v1/image", params={"u": ALLOWED}).status_code == 502


def test_proxy_rejects_oversized_body(proxy_client):
    async def chunks():
        for _ in range(4):
            yield b"0" * (MAX_BYTES // 3)

    def handler(request):
        # content-length 없이 스트리밍되는 경우도 본문 크기로 막는다.
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=chunks())

    client, _ = proxy_client(handler)
    assert client.get("/api/v1/image", params={"u": ALLOWED}).status_code == 502


def test_proxy_does_not_follow_redirects(proxy_client):
    client, calls = proxy_client(
        lambda r: httpx.Response(302, headers={"location": "http://evil.example/a.png"})
    )
    assert client.get("/api/v1/image", params={"u": ALLOWED}).status_code == 502
    assert calls == [ALLOWED]


def test_proxy_rejects_declared_oversized_length(proxy_client):
    client, _ = proxy_client(
        lambda r: httpx.Response(
            200, headers={"content-type": "image/jpeg"}, content=b"0" * (MAX_BYTES + 1)
        )
    )
    assert client.get("/api/v1/image", params={"u": ALLOWED}).status_code == 502


def test_proxy_upstream_error(proxy_client):
    client, _ = proxy_client(lambda r: httpx.Response(404))
    assert client.get("/api/v1/image", params={"u": ALLOWED}).status_code == 502


def test_proxy_timeout(proxy_client):
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    client, _ = proxy_client(handler)
    assert client.get("/api/v1/image", params={"u": ALLOWED}).status_code == 504


def test_proxy_custom_allowlist(make_client):
    client = make_client(image_host_allowlist="img.example.com, other.example.com")
    client.app.state.image_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
        )
    )
    assert (
        client.get("/api/v1/image", params={"u": "https://other.example.com/x.png"}).status_code
        == 200
    )
    assert client.get("/api/v1/image", params={"u": ALLOWED}).status_code == 400
