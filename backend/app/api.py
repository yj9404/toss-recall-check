import hmac
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel

from app import db, images
from app.collect import SourceResult, run_collection
from app.collectors import Collector, select_collectors
from app.collectors.base import KST
from app.config import Settings
from app.labels import EXCLUDED_FROM_ALL, category_label, source_label
from app.snapshot import Item, Snapshot, load_snapshot

log = logging.getLogger(__name__)

BARCODE_RE = re.compile(r"[0-9]{13}")

router = APIRouter()


@dataclass
class SourceStatus:
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_row_count: int | None = None
    skipped_count: int | None = None


class CategoryOut(BaseModel):
    code: str
    label: str
    count: int
    latest_registered_at: str


class Summary(BaseModel):
    id: int
    category: str
    category_label: str
    product_name: str | None
    company_name: str | None
    reason: str | None
    grade: int | None
    registered_at: str
    source_label: str
    thumbnail: str | None


class Detail(Summary):
    manufactured_text: str | None
    expiry_text: str | None
    package_unit: str | None
    recall_method: str | None
    address: str | None
    barcode: str | None
    images: list[str]
    source_url: str | None
    # 소비자24 항목에만 값이 있다.
    model_text: str | None
    consumer_tips: str | None
    recall_period_text: str | None
    contact_text: str | None
    last_seen_at: str


class RecallList(BaseModel):
    items: list[Summary]
    total: int


class BarcodeResult(BaseModel):
    # 회수 목록에 있는지만 알려준다. found=false가 안전하다는 뜻은 아니다.
    found: bool
    items: list[Summary]


def _iso(value: datetime) -> str:
    return value.astimezone(KST).isoformat(timespec="seconds")


def _image_links(item: Item, allowed_hosts: frozenset[str]) -> list[str]:
    return [images.proxy_url(u) for u in item.image_urls if images.is_allowed_url(u, allowed_hosts)]


def _summary(item: Item, settings: Settings) -> Summary:
    links = _image_links(item, settings.image_hosts)
    return Summary(
        id=item.id,
        category=item.category,
        category_label=category_label(item.category),
        product_name=item.product_name,
        company_name=item.company_name,
        reason=item.reason,
        grade=item.grade,
        registered_at=_iso(item.registered_at),
        source_label=item.source_label or source_label(item.source),
        thumbnail=links[0] if links else None,
    )


def _detail(item: Item, settings: Settings) -> Detail:
    return Detail(
        **_summary(item, settings).model_dump(),
        manufactured_text=item.manufactured_text,
        expiry_text=item.expiry_text,
        package_unit=item.package_unit,
        recall_method=item.recall_method,
        address=item.address,
        barcode=item.barcode,
        images=_image_links(item, settings.image_hosts),
        source_url=item.source_url,
        model_text=item.model_text,
        consumer_tips=item.consumer_tips,
        recall_period_text=item.recall_period_text,
        contact_text=item.contact_text,
        last_seen_at=_iso(item.last_seen_at),
    )


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _snapshot(request: Request) -> Snapshot:
    return request.app.state.snapshot


@router.get("/api/v1/categories", response_model=list[CategoryOut])
def list_categories(request: Request) -> list[CategoryOut]:
    settings = _settings(request)
    visible = _snapshot(request).visible_categories(
        settings.enabled_category_list, settings.hide_empty_days
    )
    return [
        CategoryOut(
            code=code,
            label=category_label(code),
            count=stat.count,
            latest_registered_at=_iso(stat.latest_registered_at),
        )
        for code, stat in visible
    ]


@router.get("/api/v1/recalls", response_model=RecallList)
def list_recalls(
    request: Request,
    category: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RecallList:
    settings = _settings(request)
    if category is not None and category not in settings.enabled_category_list:
        raise HTTPException(400, "unknown category")
    # category 없이(전체·전체 검색) 조회하면 해외리콜을 뺀다. 바코드 조회는 해외도 포함한다.
    matched = _snapshot(request).search(category=category, q=q, exclude=EXCLUDED_FROM_ALL)
    return RecallList(
        items=[_summary(i, settings) for i in matched[offset : offset + limit]],
        total=len(matched),
    )


@router.get("/api/v1/recalls/barcode/{barcode}", response_model=BarcodeResult)
def find_by_barcode(request: Request, barcode: str) -> BarcodeResult:
    if not BARCODE_RE.fullmatch(barcode):
        raise HTTPException(400, "barcode must be 13 digits")
    settings = _settings(request)
    items = _snapshot(request).by_barcode.get(barcode, ())
    return BarcodeResult(found=bool(items), items=[_summary(i, settings) for i in items])


@router.get("/api/v1/recalls/{recall_id}", response_model=Detail)
def get_recall(request: Request, recall_id: int) -> Detail:
    item = _snapshot(request).by_id.get(recall_id)
    if item is None:
        raise HTTPException(404, "not found")
    return _detail(item, _settings(request))


@router.get("/api/v1/image")
async def proxy_image(request: Request, u: Annotated[str, Query(max_length=2048)]) -> Response:
    if not images.is_allowed_url(u, _settings(request).image_hosts):
        raise HTTPException(400, "image host not allowed")
    try:
        body, content_type = await images.fetch_image(request.app.state.image_client, u)
    except images.UpstreamError as exc:
        raise HTTPException(exc.status_code, "image unavailable") from None
    return Response(
        content=body,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/healthz")
async def healthz(request: Request) -> dict:
    """메모리만 본다. DB를 깨우지 않으므로 업타임 모니터가 자주 호출해도 된다."""
    snapshot = _snapshot(request)
    return {
        "status": "ok",
        "snapshot": {"count": len(snapshot), "loaded_at": _iso(snapshot.loaded_at)},
        "sources": [
            {
                "source": source,
                "last_success_at": _iso(s.last_success_at) if s.last_success_at else None,
                "last_error_at": _iso(s.last_error_at) if s.last_error_at else None,
                "last_row_count": s.last_row_count,
                # 공표일 등이 없어 받지 않은 건수. 0이 아니면 그만큼 화면에 나오지 않는다.
                "skipped_count": s.skipped_count,
            }
            for source, s in sorted(request.app.state.source_status.items())
        ],
    }


def _require_admin(request: Request, x_admin_token: Annotated[str | None, Header()] = None) -> None:
    expected = _settings(request).admin_token.get_secret_value()
    if (
        not expected
        or not x_admin_token
        or not hmac.compare_digest(x_admin_token.encode(), expected.encode())
    ):
        raise HTTPException(403, "forbidden")


@router.get("/internal/health/db", dependencies=[Depends(_require_admin)])
async def health_db(request: Request) -> dict:
    pool = request.app.state.pool
    if pool is None:
        raise HTTPException(503, "db unavailable")
    try:
        await db.ping(pool)
    except Exception as exc:
        log.warning("health/db: db unavailable: %s", type(exc).__name__)
        raise HTTPException(503, "db unavailable") from None
    return {"db": "ok"}


def record_source_status(app, results: list[SourceResult]) -> None:
    """수집 결과를 메모리에 반영한다. /healthz가 이 값을 그대로 돌려준다."""
    now = datetime.now(KST)
    for r in results:
        state = app.state.source_status.setdefault(r.source, SourceStatus())
        if r.status == "ok":
            state.last_success_at = now
            state.last_row_count = r.row_count
            state.skipped_count = r.skipped_count
        else:
            state.last_error_at = now


async def collect_and_reload(
    app, collectors: list[Collector], full: bool = False
) -> list[SourceResult] | None:
    """수집 후 스냅샷을 다시 읽어 통째로 교체한다. 다른 곳에서 수집 중이면 None."""
    settings: Settings = app.state.settings
    results = await run_collection(app.state.pool, collectors, settings.secret_values(), full)
    if results is not None:
        record_source_status(app, results)
        app.state.snapshot = await load_snapshot(app.state.pool, settings)
    return results


@router.post("/internal/collect", dependencies=[Depends(_require_admin)])
async def trigger_collect(
    request: Request,
    source: str | None = None,
    full: bool = False,
) -> dict:
    """full=true면 성공 기록을 무시하고 첫 수집 범위로 다시 받는다 (CLI의 --full)."""
    settings = _settings(request)
    try:
        collectors = select_collectors(settings, source)
    except ValueError:
        raise HTTPException(400, "unknown source") from None
    results = await collect_and_reload(request.app, collectors, full)
    if results is None:
        return {"ran": False, "results": []}
    return {
        "ran": True,
        "results": [
            {
                "source": r.source,
                "status": r.status,
                "row_count": r.row_count,
                "skipped_count": r.skipped_count,
            }
            for r in results
        ],
    }
