"""배포 환경에서 출처 API와 이미지가 열리는지 확인한다 (해외 IP 차단 여부 등). DB는 쓰지 않는다.

실행: python -m app.check_sources

키가 설정된 소스마다 1건씩 호출해 HTTP 상태, 결과코드, 전체 건수, 응답 시간을 출력하고,
응답에서 나온 이미지 URL 중 허용목록 안의 1건을 이미지 프록시와 같은 코드(images.fetch_image)로
받아 본다. 서비스키는 출력하지 않는다. 모두 정상이면 종료 코드 0, 아니면 1.
"""

import asyncio
import sys
import time

import httpx

from app import images
from app.collect import redact
from app.collectors import Collector, build_collectors
from app.collectors.base import ProbeResult
from app.config import get_settings
from app.logging_setup import setup_logging


def format_probe(r: ProbeResult) -> str:
    return "\t".join(
        [
            r.source,
            "ok" if r.ok else "FAIL",
            f"http={r.http_status if r.http_status is not None else '-'}",
            f"code={r.code or '-'}",
            f"total={r.total if r.total is not None else '-'}",
            f"{r.elapsed_ms}ms",
            r.error or "",
        ]
    ).rstrip()


async def check_image(
    urls: list[str], allowed_hosts: frozenset[str], client: httpx.AsyncClient
) -> tuple[bool, str]:
    """허용목록 안의 첫 이미지 URL을 프록시와 같은 방식으로 받아 본다.

    확인할 URL이 없으면 실패가 아니라 SKIP이다 (이미지가 있는 메뉴의 키가 없을 때 등).
    """
    url = next((u for u in urls if images.is_allowed_url(u, allowed_hosts)), None)
    if url is None:
        hosts = sorted({httpx.URL(u).host for u in urls if u.startswith("http")})
        return True, f"image\tSKIP\t허용목록 안의 이미지 URL이 응답에 없음 (응답의 호스트: {hosts})"
    started = time.perf_counter()
    try:
        body, content_type = await images.fetch_image(client, url)
    except images.UpstreamError as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return False, f"image\tFAIL\tproxy={exc.status_code}\t{elapsed}ms\t{url}"
    elapsed = int((time.perf_counter() - started) * 1000)
    return True, f"image\tok\t{content_type}\t{len(body)}B\t{elapsed}ms\t{url}"


async def run_checks(
    collectors: list[Collector], allowed_hosts: frozenset[str], image_client: httpx.AsyncClient
) -> tuple[bool, list[str]]:
    lines = []
    all_ok = True
    image_urls: list[str] = []
    for collector in collectors:
        result = await collector.probe()
        all_ok &= result.ok
        image_urls += result.image_urls
        lines.append(format_probe(result))
    image_ok, line = await check_image(image_urls, allowed_hosts, image_client)
    lines.append(line)
    return all_ok and image_ok, lines


async def _main() -> int:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=images.TIMEOUT_SECONDS) as image_client:
        ok, lines = await run_checks(build_collectors(settings), settings.image_hosts, image_client)
    secrets = settings.secret_values()
    for line in lines:
        print(redact(line, secrets))
    return 0 if ok else 1


def main() -> int:
    setup_logging()
    return asyncio.run(_main())


if __name__ == "__main__":
    sys.exit(main())
