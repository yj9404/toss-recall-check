"""공정거래위원회 카테고리별 리콜정보 (XML, 카테고리 공통 스키마).

카테고리마다 FtcCollector를 하나씩 만든다. source는 ftc_<category>.

TODO(명세 대기): 엔드포인트, 카테고리 요청 파라미터 값, XML 요소명, 페이지네이션이
확정되지 않았다. URL이나 필드명을 추측해서 채우지 않는다.
샘플 응답은 tests/fixtures/ftc_<category>_sample.xml 에 둔다.
"""

import httpx

from app.collectors.base import Collector, RecallRecord
from app.labels import FTC_CATEGORIES


def parse_items(xml_text: str) -> list[dict[str, str]]:
    """XML 응답에서 항목 목록을 꺼낸다 (요소명 → 텍스트)."""
    raise NotImplementedError("ftc: XML 스키마 명세 대기")


def normalize_item(category: str, item: dict[str, str]) -> RecallRecord | None:
    """항목 하나를 RecallRecord로 바꾼다."""
    raise NotImplementedError("ftc: 응답 필드 명세 대기")


class FtcCollector(Collector):
    def __init__(
        self,
        category: str,
        api_url: str,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if category not in FTC_CATEGORIES:
            raise ValueError(f"unsupported ftc category: {category}")
        self.source = f"ftc_{category}"
        self.categories = (category,)
        self._category = category
        self._api_url = api_url  # FTC_API_URL
        self._api_key = api_key  # DATA_GO_KR_API_KEY (TODO: 확인)
        self._transport = transport

    async def fetch(self) -> list[RecallRecord]:
        raise NotImplementedError(f"{self.source}: 엔드포인트 명세 대기")
