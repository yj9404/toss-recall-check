import logging

from app.collectors.base import CollectError, Collector, RecallRecord
from app.collectors.consumer24 import OVERSEAS_MENU, Consumer24Collector
from app.collectors.foodsafety_i0490 import FoodSafetyI0490Collector
from app.config import Settings

__all__ = [
    "Collector",
    "CollectError",
    "RecallRecord",
    "build_collectors",
    "log_skipped_sources",
    "select_collectors",
]

log = logging.getLogger(__name__)


def build_collectors(settings: Settings) -> list[Collector]:
    return [
        FoodSafetyI0490Collector(settings.foodsafety_api_key.get_secret_value()),
        # 서비스키가 있는 소비자24 메뉴만 만든다.
        *(
            Consumer24Collector(
                menu,
                key,
                window_days=(
                    settings.consumer24_overseas_days
                    if menu == OVERSEAS_MENU
                    else settings.snapshot_days
                ),
                lookback_days=settings.consumer24_lookback_days,
            )
            for menu, key in settings.consumer24_keys.items()
            if key
        ),
    ]


def log_skipped_sources(settings: Settings) -> None:
    """기동 시 한 번 호출한다. 서비스키가 없어 수집하지 않는 소비자24 메뉴를 남긴다."""
    missing = [menu for menu, key in settings.consumer24_keys.items() if not key]
    if missing:
        log.info("consumer24: no service key, skipping menus %s", ", ".join(missing))


def select_collectors(settings: Settings, source: str | None = None) -> list[Collector]:
    """source(또는 consumer24 같은 묶음 이름)를 지정하면 그 수집기만, 아니면 노출 카테고리와
    겹치는 수집기 전부."""
    collectors = build_collectors(settings)
    if source is not None:
        selected = [c for c in collectors if source in (c.source, c.group)]
        if not selected:
            raise ValueError(f"unknown source: {source}")
        return selected
    enabled = set(settings.enabled_category_list)
    return [c for c in collectors if enabled.intersection(c.categories)]
