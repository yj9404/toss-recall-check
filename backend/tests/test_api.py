from datetime import datetime, timedelta
from urllib.parse import quote

import pytest

from app import db
from app.api import record_source_status
from app.collect import SourceResult
from app.collectors.base import KST
from app.collectors.foodsafety_i0490 import normalize_row
from tests.conftest import load_fixture, make_row, record_to_row


@pytest.fixture
def fixture_rows():
    rows = load_fixture("i0490_sample.json")["I0490"]["row"]
    return [record_to_row(i + 1, normalize_row(r)) for i, r in enumerate(rows)]


def test_recalls_list_from_fixture(make_client, fixture_rows):
    client = make_client(fixture_rows)
    resp = client.get("/api/v1/recalls")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    # registered_at 내림차순: 10-14, 10-08 19:14, 10-08 17:52
    assert [i["id"] for i in body["items"]] == [1, 3, 2]
    first = body["items"][0]
    assert first["registered_at"] == "2026-10-14T15:21:26+09:00"
    assert first["source_label"] == "식품의약품안전처 식품안전나라"
    assert first["category_label"] == "식품"
    assert first["grade"] == 3
    assert first["thumbnail"] == "/api/v1/image?u=" + quote(
        "http://coop.foodsafetykorea.go.kr/open/minfo_image.do?fSeq=2681127", safe=""
    )
    no_image = next(i for i in body["items"] if i["id"] == 2)
    assert no_image["thumbnail"] is None


def test_recalls_search_and_pagination(make_client):
    rows = [make_row(i, product_name=f"우유 {i}", company_name="회사") for i in range(1, 6)]
    rows.append(make_row(6, product_name="두부", company_name="회사"))
    client = make_client(rows)

    body = client.get("/api/v1/recalls", params={"q": "우유 회사", "limit": 2, "offset": 1}).json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert client.get("/api/v1/recalls", params={"q": "회사"}).json()["total"] == 6
    assert client.get("/api/v1/recalls", params={"q": "  "}).json()["total"] == 6
    assert client.get("/api/v1/recalls", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/recalls", params={"limit": 101}).status_code == 422


def test_recalls_category_filter(make_client):
    rows = [make_row(1, category="food"), make_row(2, category="cosmetic")]
    client = make_client(rows)
    body = client.get("/api/v1/recalls", params={"category": "cosmetic"}).json()
    assert [i["id"] for i in body["items"]] == [2]
    assert client.get("/api/v1/recalls", params={"category": "nope"}).status_code == 400
    # 기본 설정에서 vehicle은 노출하지 않는다.
    assert client.get("/api/v1/recalls", params={"category": "vehicle"}).status_code == 400


def test_categories_hides_empty_and_disabled(make_client):
    now = datetime.now(KST)
    rows = [
        make_row(1, category="food", registered_at=now - timedelta(days=1)),
        make_row(2, category="food", registered_at=now - timedelta(days=400)),
        make_row(3, category="cosmetic", registered_at=now - timedelta(days=181)),
        make_row(4, category="vehicle", registered_at=now),
    ]
    client = make_client(rows)
    body = client.get("/api/v1/categories").json()
    assert [c["code"] for c in body] == ["food"]
    assert body[0]["label"] == "식품"
    assert body[0]["count"] == 2
    assert body[0]["latest_registered_at"] == (now - timedelta(days=1)).isoformat(
        timespec="seconds"
    )

    client = make_client(rows, hide_empty_days=365)
    assert [c["code"] for c in client.get("/api/v1/categories").json()] == ["food", "cosmetic"]

    client = make_client(rows, enabled_categories="food,vehicle")
    assert [c["code"] for c in client.get("/api/v1/categories").json()] == ["food", "vehicle"]


def test_recall_detail(make_client, fixture_rows):
    client = make_client(fixture_rows)
    resp = client.get("/api/v1/recalls/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["barcode"] == "8809520491483"
    assert body["manufactured_text"] == "(제조일자) 2026-10-05"
    assert body["expiry_text"] == "(소비기한) 2026-10-19"
    assert len(body["images"]) == 3
    assert all(u.startswith("/api/v1/image?u=") for u in body["images"])
    assert body["source_label"] == "식품의약품안전처 식품안전나라"
    assert body["last_seen_at"].endswith("+09:00")
    assert "raw" not in body

    assert client.get("/api/v1/recalls/999").status_code == 404
    assert client.get("/api/v1/recalls/abc").status_code == 422


def test_images_outside_allowlist_are_not_linked(make_client):
    client = make_client([make_row(1, image_urls=["http://evil.example/a.png"])])
    body = client.get("/api/v1/recalls/1").json()
    assert body["images"] == []
    assert body["thumbnail"] is None


def test_barcode_lookup(make_client, fixture_rows):
    client = make_client(fixture_rows)
    found = client.get("/api/v1/recalls/barcode/8809520491483").json()
    assert found["found"] is True
    assert [i["id"] for i in found["items"]] == [1]
    assert found["items"][0]["source_label"] == "식품의약품안전처 식품안전나라"

    missing = client.get("/api/v1/recalls/barcode/8800000000000").json()
    assert missing == {"found": False, "items": []}


@pytest.mark.parametrize(
    "bad", ["880952049148", "88095204914830", "R229632780001", "８８０９５２０４９１４８３"]
)
def test_barcode_must_be_13_digits(make_client, bad):
    client = make_client()
    assert client.get(f"/api/v1/recalls/barcode/{quote(bad)}").status_code == 400


def test_internal_errors_are_not_exposed(make_client, monkeypatch):
    client = make_client()

    def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(client.app.state.snapshot, "search", boom)
    resp = client.get("/api/v1/recalls")
    assert resp.status_code == 500
    assert resp.json() == {"detail": "internal error"}
    assert "secret" not in resp.text


def test_internal_collect_requires_admin_token(make_client):
    client = make_client(admin_token="right-token")
    assert client.post("/internal/collect").status_code == 403
    assert client.post("/internal/collect", headers={"X-Admin-Token": "wrong"}).status_code == 403
    resp = client.post(
        "/internal/collect", params={"source": "nope"}, headers={"X-Admin-Token": "right-token"}
    )
    assert resp.status_code == 400


def test_internal_collect_disabled_without_admin_token(make_client):
    client = make_client()
    assert client.post("/internal/collect", headers={"X-Admin-Token": ""}).status_code == 403


def test_healthz_reads_memory_only(make_client, fixture_rows):
    client = make_client(fixture_rows)
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["snapshot"]["count"] == 3
    assert "db" not in body
    assert body["sources"] == []


def test_healthz_reports_last_collection_results(make_client):
    client = make_client()
    record_source_status(client.app, [SourceResult("foodsafety_i0490", "ok", 7)])
    record_source_status(
        client.app,
        [SourceResult("foodsafety_i0490", "error"), SourceResult("kats", "not_implemented")],
    )
    [src] = client.get("/healthz").json()["sources"]
    assert src["source"] == "foodsafety_i0490"
    assert src["last_success_at"] and src["last_error_at"]
    assert src["last_row_count"] == 7  # 실패해도 마지막 성공 건수는 유지


def test_health_db_requires_admin_token(make_client):
    client = make_client(admin_token="right-token")
    assert client.get("/internal/health/db").status_code == 403
    assert client.get("/internal/health/db", headers={"X-Admin-Token": "x"}).status_code == 403
    # 토큰이 맞아도 풀이 없으면 503
    resp = client.get("/internal/health/db", headers={"X-Admin-Token": "right-token"})
    assert resp.status_code == 503


def test_health_db_ok_and_failure(make_client, monkeypatch):
    client = make_client(admin_token="t")
    client.app.state.pool = object()
    headers = {"X-Admin-Token": "t"}

    async def ok(pool):
        return None

    async def boom(pool):
        raise RuntimeError("secret")

    monkeypatch.setattr(db, "ping", ok)
    assert client.get("/internal/health/db", headers=headers).json() == {"db": "ok"}
    monkeypatch.setattr(db, "ping", boom)
    resp = client.get("/internal/health/db", headers=headers)
    assert resp.status_code == 503
    assert "secret" not in resp.text
