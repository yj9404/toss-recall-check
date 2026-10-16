"""이미지 프록시. 원본이 http라 HTTPS 페이지에서 바로 쓸 수 없어 서버가 대신 받아 전달한다."""

import asyncio
from urllib.parse import quote, urlsplit

import httpx

TIMEOUT_SECONDS = 5.0
MAX_BYTES = 3 * 1024 * 1024
PROXY_PATH = "/api/v1/image"


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
                content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                # SVG는 스크립트를 담을 수 있어 제외한다.
                if not content_type.startswith("image/") or content_type == "image/svg+xml":
                    raise UpstreamError(502)
                length = resp.headers.get("content-length")
                if length and length.isdigit() and int(length) > MAX_BYTES:
                    raise UpstreamError(502)
                body = bytearray()
                async for chunk in resp.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise UpstreamError(502)
                return bytes(body), content_type
    except (TimeoutError, httpx.TimeoutException):
        raise UpstreamError(504) from None
    except httpx.HTTPError:
        raise UpstreamError(502) from None
