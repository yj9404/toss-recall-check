from app.collectors.base import CollectError, Collector, RecallRecord
from app.collectors.foodsafety_i0490 import FoodSafetyI0490Collector
from app.collectors.ftc import FtcCollector
from app.collectors.kats import KatsCollector
from app.collectors.mfds_cosmetic import MfdsCosmeticCollector
from app.config import Settings
from app.labels import FTC_CATEGORIES

__all__ = ["Collector", "CollectError", "RecallRecord", "build_collectors", "select_collectors"]


def build_collectors(settings: Settings) -> list[Collector]:
    data_go_kr_key = settings.data_go_kr_api_key.get_secret_value()
    return [
        FoodSafetyI0490Collector(settings.foodsafety_api_key.get_secret_value()),
        KatsCollector(settings.kats_api_url, data_go_kr_key),
        *(FtcCollector(c, settings.ftc_api_url, data_go_kr_key) for c in FTC_CATEGORIES),
        MfdsCosmeticCollector(settings.mfds_cosmetic_api_url, data_go_kr_key),
    ]


def select_collectors(settings: Settings, source: str | None = None) -> list[Collector]:
    """source를 지정하면 그 수집기만, 아니면 노출 카테고리와 겹치는 수집기 전부."""
    collectors = build_collectors(settings)
    if source is not None:
        selected = [c for c in collectors if c.source == source]
        if not selected:
            raise ValueError(f"unknown source: {source}")
        return selected
    enabled = set(settings.enabled_category_list)
    return [c for c in collectors if enabled.intersection(c.categories)]
