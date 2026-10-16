import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.collectors.base import KST, RecallRecord
from app.config import Settings
from app.main import create_app
from app.snapshot import Snapshot

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


def make_row(id: int, **overrides: Any) -> dict[str, Any]:
    """DB에서 읽은 스냅샷 행 형태."""
    row: dict[str, Any] = {
        "id": id,
        "source": "foodsafety_i0490",
        "category": "food",
        "product_name": f"제품{id}",
        "company_name": f"업체{id}",
        "reason": None,
        "grade": None,
        "manufactured_text": None,
        "expiry_text": None,
        "package_unit": None,
        "recall_method": None,
        "address": None,
        "barcode": None,
        "image_urls": [],
        "source_url": None,
        "registered_at": datetime.now(KST),
        "last_seen_at": datetime.now(KST),
    }
    row.update(overrides)
    return row


def record_to_row(id: int, record: RecallRecord) -> dict[str, Any]:
    data = record.model_dump()
    data.pop("raw")
    data.pop("source_id")
    data.pop("company_phone")
    return {**data, "id": id, "last_seen_at": datetime.now(KST)}


@pytest.fixture
def make_client():
    def factory(rows=(), **settings_overrides: Any) -> TestClient:
        app = create_app(make_settings(**settings_overrides))
        app.state.snapshot = Snapshot(rows)
        # 컨텍스트 매니저로 쓰지 않으므로 lifespan(DB 연결·스케줄러)은 실행되지 않는다.
        return TestClient(app, raise_server_exceptions=False)

    return factory
