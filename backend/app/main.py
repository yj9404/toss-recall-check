"""실행: uvicorn --factory app.main:create_app"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import db
from app.api import collect_and_reload, router
from app.collectors import select_collectors
from app.collectors.base import KST
from app.config import Settings, get_settings
from app.images import TIMEOUT_SECONDS
from app.logging_setup import setup_logging
from app.snapshot import Snapshot, load_snapshot

log = logging.getLogger(__name__)


async def _scheduled_collect(app: FastAPI) -> None:
    try:
        await collect_and_reload(app, select_collectors(app.state.settings))
    except Exception as exc:
        log.error("scheduled collection failed: %s", type(exc).__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    pool = db.make_pool(settings)
    await pool.open()
    app.state.pool = pool
    await db.apply_schema(pool)
    app.state.snapshot = await load_snapshot(pool, settings)
    log.info("snapshot loaded: %d items", len(app.state.snapshot))

    scheduler = AsyncIOScheduler(timezone=KST)
    scheduler.add_job(
        _scheduled_collect,
        "interval",
        minutes=settings.collect_interval_minutes,
        args=[app],
        next_run_time=datetime.now(KST),  # 기동 직후 1회
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await app.state.image_client.aclose()
        await pool.close()


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled error on %s: %s", request.url.path, type(exc).__name__)
    return JSONResponse({"detail": "internal error"}, status_code=500)


def create_app(settings: Settings | None = None) -> FastAPI:
    setup_logging()
    settings = settings or get_settings()
    app = FastAPI(
        title="RecallCheck API",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_dev else None,
    )
    app.state.settings = settings
    app.state.pool = None
    app.state.snapshot = Snapshot()
    app.state.image_client = httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_credentials=False,
    )
    app.add_exception_handler(Exception, _unhandled)
    app.include_router(router)
    return app
