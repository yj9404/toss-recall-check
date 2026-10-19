"""메모리 스냅샷. 사용자 요청(검색·집계·바코드)은 모두 여기서 처리하고 DB는 건드리지 않는다."""

import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from psycopg_pool import AsyncConnectionPool

from app import db
from app.collectors.base import KST
from app.config import Settings


def normalize_text(text: str) -> str:
    """NFC 정규화, 대소문자 무시, 공백 제거."""
    folded = unicodedata.normalize("NFC", text).casefold()
    return "".join(unicodedata.normalize("NFC", folded).split())


@dataclass(frozen=True, slots=True)
class Item:
    id: int
    source: str
    category: str
    product_name: str | None
    company_name: str | None
    reason: str | None
    grade: int | None
    manufactured_text: str | None
    expiry_text: str | None
    package_unit: str | None
    recall_method: str | None
    address: str | None
    barcode: str | None
    image_urls: tuple[str, ...]
    source_url: str | None
    source_label: str | None
    model_text: str | None
    consumer_tips: str | None
    recall_period_text: str | None
    registered_at: datetime
    last_seen_at: datetime
    search_key: str = field(repr=False)


def _to_item(row: Mapping[str, Any]) -> Item:
    product = row.get("product_name")
    company = row.get("company_name")
    # 제품명과 업체명 사이에 공백이 아닌 구분자를 넣어 검색어가 두 필드에 걸쳐 맞지 않게 한다.
    search_key = normalize_text(product or "") + "\n" + normalize_text(company or "")
    return Item(
        id=row["id"],
        source=row["source"],
        category=row["category"],
        product_name=product,
        company_name=company,
        reason=row.get("reason"),
        grade=row.get("grade"),
        manufactured_text=row.get("manufactured_text"),
        expiry_text=row.get("expiry_text"),
        package_unit=row.get("package_unit"),
        recall_method=row.get("recall_method"),
        address=row.get("address"),
        barcode=row.get("barcode"),
        image_urls=tuple(row.get("image_urls") or ()),
        source_url=row.get("source_url"),
        source_label=row.get("source_label"),
        model_text=row.get("model_text"),
        consumer_tips=row.get("consumer_tips"),
        recall_period_text=row.get("recall_period_text"),
        registered_at=row["registered_at"].astimezone(KST),
        last_seen_at=row["last_seen_at"].astimezone(KST),
        search_key=search_key,
    )


@dataclass(frozen=True)
class CategoryStat:
    count: int
    latest_registered_at: datetime


class Snapshot:
    """불변 스냅샷. 갱신할 때는 새로 만들어 통째로 교체한다."""

    def __init__(self, rows: Iterable[Mapping[str, Any]] = (), loaded_at: datetime | None = None):
        items = sorted(
            (_to_item(r) for r in rows), key=lambda i: (i.registered_at, i.id), reverse=True
        )
        self.items: tuple[Item, ...] = tuple(items)
        self.by_id: dict[int, Item] = {i.id: i for i in items}
        by_barcode: dict[str, list[Item]] = defaultdict(list)
        stats: dict[str, CategoryStat] = {}
        for item in items:
            if item.barcode:
                by_barcode[item.barcode].append(item)
            stat = stats.get(item.category)
            # items가 최신순이므로 처음 본 항목이 그 카테고리의 최신 등록일이다.
            latest = stat.latest_registered_at if stat else item.registered_at
            stats[item.category] = CategoryStat((stat.count if stat else 0) + 1, latest)
        self.by_barcode: dict[str, tuple[Item, ...]] = {k: tuple(v) for k, v in by_barcode.items()}
        self.category_stats: dict[str, CategoryStat] = stats
        self.loaded_at = loaded_at or datetime.now(KST)

    def __len__(self) -> int:
        return len(self.items)

    def search(self, category: str | None = None, q: str | None = None) -> list[Item]:
        terms = [normalize_text(t) for t in unicodedata.normalize("NFC", q or "").split()]
        terms = [t for t in terms if t]
        return [
            item
            for item in self.items
            if (category is None or item.category == category)
            and all(t in item.search_key for t in terms)
        ]

    def visible_categories(
        self, enabled: list[str], hide_empty_days: int, now: datetime | None = None
    ) -> list[tuple[str, CategoryStat]]:
        """최근 hide_empty_days일 안에 등록 건이 있는 노출 카테고리만 (코드 정의 순서)."""
        cutoff = (now or datetime.now(KST)) - timedelta(days=hide_empty_days)
        result = []
        for code in enabled:
            stat = self.category_stats.get(code)
            if stat and stat.latest_registered_at >= cutoff:
                result.append((code, stat))
        return result


async def load_snapshot(pool: AsyncConnectionPool, settings: Settings) -> Snapshot:
    rows = await db.fetch_snapshot_rows(
        pool, settings.snapshot_days, settings.enabled_category_list
    )
    return Snapshot(rows)
