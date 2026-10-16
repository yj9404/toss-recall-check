import asyncio

import pytest

from app import collect, db
from app.collectors import CollectError, Collector, select_collectors
from app.collectors.ftc import FtcCollector
from app.collectors.kats import KatsCollector
from app.collectors.mfds_cosmetic import MfdsCosmeticCollector
from tests.conftest import make_settings


class FakeCollector(Collector):
    source = "fake"
    categories = ("food",)

    def __init__(self, exc: Exception | None = None, records=()):
        self._exc = exc
        self._records = list(records)

    async def fetch(self):
        if self._exc:
            raise self._exc
        return self._records


@pytest.fixture
def state(monkeypatch):
    calls = {"upsert": [], "success": [], "error": []}

    async def upsert(conn, records):
        calls["upsert"].append(records)

    async def success(conn, source, n):
        calls["success"].append((source, n))

    async def error(conn, source, message):
        calls["error"].append((source, message))

    monkeypatch.setattr(db, "upsert_records", upsert)
    monkeypatch.setattr(db, "record_success", success)
    monkeypatch.setattr(db, "record_error", error)
    return calls


def test_run_one_success(state):
    result = asyncio.run(collect._run_one(None, FakeCollector(), []))
    assert result.status == "ok"
    assert state["success"] == [("fake", 0)]
    assert state["error"] == []


def test_run_one_failure_records_redacted_error_and_skips_upsert(state):
    exc = CollectError("failed at https://host/api/SECRETKEY/I0490")
    result = asyncio.run(collect._run_one(None, FakeCollector(exc), ["SECRETKEY"]))
    assert result.status == "error"
    assert state["upsert"] == []
    assert state["success"] == []
    [(source, message)] = state["error"]
    assert source == "fake"
    assert "SECRETKEY" not in message
    assert "***" in message


def test_run_one_not_implemented_is_skipped_without_state(state):
    result = asyncio.run(collect._run_one(None, FakeCollector(NotImplementedError()), []))
    assert result.status == "not_implemented"
    assert state == {"upsert": [], "success": [], "error": []}


def test_redact_handles_url_encoded_secret():
    assert collect.redact("key=a%2Bb/c", ["a+b"]) == "key=***/c"


def test_default_collectors_follow_enabled_categories():
    sources = [c.source for c in select_collectors(make_settings())]
    assert "foodsafety_i0490" in sources
    assert "ftc_medicine" in sources
    assert "ftc_vehicle" not in sources  # vehicle은 기본 비노출

    sources = [c.source for c in select_collectors(make_settings(enabled_categories="food"))]
    assert sources == ["foodsafety_i0490"]


def test_select_explicit_source():
    assert [c.source for c in select_collectors(make_settings(), "ftc_vehicle")] == ["ftc_vehicle"]
    with pytest.raises(ValueError):
        select_collectors(make_settings(), "nope")


def test_unknown_enabled_category_is_rejected():
    with pytest.raises(ValueError):
        make_settings(enabled_categories="food,unknown")


@pytest.mark.parametrize(
    "collector",
    [
        KatsCollector("", ""),
        FtcCollector("medicine", "", ""),
        MfdsCosmeticCollector("", ""),
    ],
)
def test_pending_collectors_are_not_implemented(collector):
    with pytest.raises(NotImplementedError):
        asyncio.run(collector.fetch())
