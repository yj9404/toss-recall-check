"""이미지 프록시. 원본이 http라 HTTPS 페이지에서 바로 쓸 수 없어 서버가 대신 받아 전달한다."""

import asyncio
from urllib.parse import quote, urlsplit

import httpx

TIMEOUT_SECONDS = 5.0
MAX_BYTES = 3 * 1024 * 1024
PROXY_PATH = "/api/v1/image"


# 원본(식약처)은 Content-Type 없이 응답하므로 헤더 대신 본문 시그니처로 형식을 정한다.
# 래스터 형식만 허용한다. SVG·HTML은 스크립트를 담을 수 있어 여기에 없다.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def sniff_image_type(body: bytes) -> str | None:
    for magic, content_type in _SIGNATURES:
        if body.startswith(magic):
            return content_type
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    return None


class ImageUrlError(ValueError):
    pass


class UpstreamError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(status_code)
        self.status_code = status_code


def is_allowed_url(url: str, allowed_hosts: frozenset[str]) -> bool:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme in ("http", "https")
        and parts.hostname is not None
        and parts.hostname.lower() in allowed_hosts
        and port is None
        and parts.username is None
        and parts.password is None
    )


def proxy_url(url: str) -> str:
    """API 기준 상대 경로. 프론트엔드가 API 베이스 URL을 앞에 붙인다."""
    return f"{PROXY_PATH}?u={quote(url, safe='')}"


async def fetch_image(client: httpx.AsyncClient, url: str) -> tuple[bytes, str]:
    """허용 호스트 검사가 끝난 URL만 넘긴다. 실패하면 UpstreamError(502/504)."""
    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            # 리다이렉트를 따라가면 허용목록 밖 호스트로 갈 수 있으므로 따라가지 않는다.
            async with client.stream("GET", url, follow_redirects=False) as resp:
                if resp.status_code != 200:
                    raise UpstreamError(502)
                length = resp.headers.get("content-length")
                if length and length.isdigit() and int(length) > MAX_BYTES:
                    raise UpstreamError(502)
                body = bytearray()
                async for chunk in resp.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise UpstreamError(502)
                data = bytes(body)
                content_type = sniff_image_type(data)
                if content_type is None:
                    raise UpstreamError(502)
                return data, content_type
    except (TimeoutError, httpx.TimeoutException):
        raise UpstreamError(504) from None
    except httpx.HTTPError:
        raise UpstreamError(502) from None
