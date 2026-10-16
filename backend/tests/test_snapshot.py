import unicodedata
from datetime import UTC, datetime, timedelta

from app.collectors.base import KST
from app.snapshot import Snapshot, normalize_text
from tests.conftest import make_row


def test_normalize_text_nfc_case_and_spaces():
    nfd = unicodedata.normalize("NFD", "카페 라떼")
    assert normalize_text(nfd) == "카페라떼"
    assert normalize_text("  Greek  YOGURT ") == "greekyogurt"


def test_search_is_and_over_product_and_company():
    snap = Snapshot(
        [
            make_row(1, product_name="그릭요거트 카페라떼", company_name="(주)요즘"),
            make_row(2, product_name="카페라떼", company_name="다른회사"),
        ]
    )
    assert [i.id for i in snap.search(q="카페라떼 요즘")] == [1]
    assert sorted(i.id for i in snap.search(q="카페 라떼")) == [1, 2]
    # 공백을 무시하므로 띄어 쓴 원문도 붙여 쓴 검색어로 찾는다.
    assert [i.id for i in snap.search(q="그릭요거트카페")] == [1]
    # NFD 입력도 찾는다.
    assert [i.id for i in snap.search(q=unicodedata.normalize("NFD", "요즘"))] == [1]
    assert snap.search(q="없는단어") == []


def test_search_term_does_not_span_product_and_company():
    snap = Snapshot([make_row(1, product_name="라떼", company_name="요즘")])
    assert snap.search(q="라떼요즘") == []


def test_items_sorted_by_registered_at_desc():
    now = datetime.now(KST)
    snap = Snapshot(
        [
            make_row(1, registered_at=now - timedelta(days=2)),
            make_row(2, registered_at=now),
            make_row(3, registered_at=now - timedelta(days=1)),
        ]
    )
    assert [i.id for i in snap.items] == [2, 3, 1]


def test_registered_at_is_converted_to_kst():
    snap = Snapshot([make_row(1, registered_at=datetime(2026, 10, 14, 6, 0, tzinfo=UTC))])
    assert snap.items[0].registered_at.isoformat() == "2026-10-14T15:00:00+09:00"
