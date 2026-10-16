"""식품의약품안전처 화장품 회수·판매중지 정보.

TODO(명세 대기): 엔드포인트, 응답 형식(JSON/XML), 응답 필드가 확정되지 않았다.
URL이나 필드명을 추측해서 채우지 않는다. 샘플 응답은 tests/fixtures/mfds_cosmetic_sample.* 에 둔다.
"""

from typing import Any

import httpx

from app.collectors.base import Collector, RecallRecord


def normalize_item(item: dict[str, Any]) -> RecallRecord | None:
    """응답 항목 하나를 RecallRecord로 바꾼다. category는 cosmetic."""
    raise NotImplementedError("mfds_cosmetic: 응답 필드 명세 대기")


class MfdsCosmeticCollector(Collector):
    source = "mfds_cosmetic"
    categories = ("cosmetic",)

    def __init__(
        self, api_url: str, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._api_url = api_url  # MFDS_COSMETIC_API_URL
        self._api_key = api_key  # DATA_GO_KR_API_KEY (TODO: 확인)
        self._transport = transport

    async def fetch(self) -> list[RecallRecord]:
        raise NotImplementedError("mfds_cosmetic: 엔드포인트 명세 대기")
