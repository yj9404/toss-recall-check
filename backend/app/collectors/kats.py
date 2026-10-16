"""국가기술표준원 제품 안전인증 및 리콜 정보 (공산품·해외 리콜).

TODO(명세 대기): 엔드포인트, 인증 방식, 페이지네이션, 응답 필드가 확정되지 않았다.
URL이나 필드명을 추측해서 채우지 않는다. 샘플 응답은 tests/fixtures/kats_sample.* 에 둔다.
"""

from typing import Any

import httpx

from app.collectors.base import Collector, RecallRecord


def normalize_item(item: dict[str, Any]) -> RecallRecord | None:
    """응답 항목 하나를 RecallRecord로 바꾼다. category는 consumer_product 또는 overseas."""
    raise NotImplementedError("kats: 응답 필드 명세 대기")


class KatsCollector(Collector):
    source = "kats"
    categories = ("consumer_product", "overseas")

    def __init__(
        self, api_url: str, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._api_url = api_url  # KATS_API_URL
        self._api_key = api_key  # TODO: 어떤 키를 쓰는지 확인 (DATA_GO_KR_API_KEY 또는 별도 키)
        self._transport = transport

    async def fetch(self) -> list[RecallRecord]:
        raise NotImplementedError("kats: 엔드포인트 명세 대기")
