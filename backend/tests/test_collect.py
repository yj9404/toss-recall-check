import asyncio
import logging
from datetime import datetime

import pytest

from app import collect
from app.collectors import CollectError, Collector, log_skipped_sources, select_collectors
from app.collectors.base import KST, FetchResult, ProbeResult
from app.collectors.consumer24 import MENU_CATEGORIES
from tests.conftest import make_settings


class FakeCollector(Collector):
    source = "fake"
    categories = ("food",)

    def __init__(self, exc: Exception | None = None, records=(), skipped: int = 0):
        self._exc = exc
        self._records = list(records)
        self._skipped = skipped
        self.seen_last_success_at = "not called"

    async def fetch(self, last_success_at=None):
        self.seen_last_success_at = last_success_at
        if self._exc:
            raise self._exc
        return FetchResult(self._records, self._skipped)

    async def probe(self):
        return ProbeResult(self.source, ok=True)


def test_run_one_success_records_skipped_count(fake_db, caplog):
    with caplog.at_level(logging.INFO):
        result = asyncio.run(collect._run_one(None, FakeCollector(skipped=7), []))
    assert (result.status, result.row_count, result.skipped_count) == ("ok", 0, 7)
    assert fake_db["success"] == [("fake", 0, 7)]
    assert fake_db["error"] == []
    assert any("fake: upserted 0 rows, skipped 7" in r.getMessage() for r in caplog.records)


def test_run_one_passes_last_success_to_fetch(fake_db):
    last = datetime(2026, 10, 19, 9, 0, tzinfo=KST)
    fake_db["last_success"]["fake"] = last
    collector = FakeCollector()
    asyncio.run(collect._run_one(None, collector, []))
    assert collector.seen_last_success_at == last


def test_run_one_full_ignores_last_success(fake_db):
    fake_db["last_success"]["fake"] = datetime(2026, 10, 19, 9, 0, tzinfo=KST)
    collector = FakeCollector()
    asyncio.run(collect._run_one(None, collector, [], full=True))
    assert collector.seen_last_success_at is None


def test_run_one_failure_records_redacted_error_and_skips_upsert(fake_db):
    exc = CollectError("failed at https://host/api/SECRETKEY/I0490")
    result = asyncio.run(collect._run_one(None, FakeCollector(exc), ["SECRETKEY"]))
    assert result.status == "error"
    assert fake_db["upsert"] == []
    assert fake_db["success"] == []
    [(source, message)] = fake_db["error"]
    assert source == "fake"
    assert "SECRETKEY" not in message
    assert "***" in message


def test_redact_handles_url_encoded_secret():
    assert collect.redact("key=a%2Bb/c", ["a+b"]) == "key=***/c"


def test_default_collectors_follow_enabled_categories():
    settings = make_settings(consumer24_key_0101="k1", consumer24_key_0301="k3")
    sources = [c.source for c in select_collectors(settings)]
    assert sources == ["foodsafety_i0490", "consumer24_0101", "consumer24_0301"]

    settings = make_settings(
        consumer24_key_0101="k1", consumer24_key_0301="k3", enabled_categories="food,vehicle"
    )
    assert [c.source for c in select_collectors(settings)] == [
        "foodsafety_i0490",
        "consumer24_0301",
    ]


def test_overseas_menu_uses_its_own_window():
    settings = make_settings(
        consumer24_key_0101="k1",
        consumer24_key_0501="k5",
        snapshot_days=1095,
        consumer24_overseas_days=180,
    )
    today = datetime.now(KST).date()
    windows = {
        c.source: (today - c.since(None)).days for c in select_collectors(settings, "consumer24")
    }
    assert windows == {"consumer24_0101": 1095, "consumer24_0501": 180}


def test_consumer24_menus_without_key_are_not_built():
    assert [c.source for c in select_collectors(make_settings())] == ["foodsafety_i0490"]


def test_select_explicit_source_and_group():
    settings = make_settings(consumer24_key_0101="k1", consumer24_key_0301="k3")
    assert [c.source for c in select_collectors(settings, "consumer24")] == [
        "consumer24_0101",
        "consumer24_0301",
    ]
    assert [c.source for c in select_collectors(settings, "consumer24_0301")] == ["consumer24_0301"]
    # 키가 없는 메뉴는 이름으로 골라도 없다.
    with pytest.raises(ValueError):
        select_collectors(settings, "consumer24_0204")
    with pytest.raises(ValueError):
        select_collectors(settings, "nope")


def test_food_and_livestock_menus_are_never_collected(monkeypatch):
    monkeypatch.setenv("CONSUMER24_KEY_0201", "food-key")
    monkeypatch.setenv("CONSUMER24_KEY_0203", "livestock-key")
    settings = make_settings()
    assert "0201" not in settings.consumer24_keys
    assert "0203" not in settings.consumer24_keys
    assert [c.source for c in select_collectors(settings)] == ["foodsafety_i0490"]


def test_consumer24_key_settings_match_menu_list():
    assert list(make_settings().consumer24_keys) == list(MENU_CATEGORIES)


def test_consumer24_keys_are_redacted_secrets():
    settings = make_settings(consumer24_key_0101="menu-key-1")
    assert "menu-key-1" in settings.secret_values()
    assert "menu-key-1" not in repr(settings)


def test_log_skipped_sources_lists_menus_without_key(caplog):
    with caplog.at_level(logging.INFO):
        log_skipped_sources(make_settings(consumer24_key_0101="k1"))
    [message] = [r.getMessage() for r in caplog.records if "consumer24" in r.getMessage()]
    assert "0101" not in message
    assert "0301" in message and "0501" in message
    assert "k1" not in message


def test_unknown_enabled_category_is_rejected():
    with pytest.raises(ValueError):
        make_settings(enabled_categories="food,unknown")
