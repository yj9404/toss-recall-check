"""수집 실행. 스케줄러, POST /internal/collect, CLI가 함께 쓴다.

수동 실행: python -m app.collect [--source <source>] [--full]
"""

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from app import db
from app.collectors import Collector, log_skipped_sources, select_collectors
from app.config import Settings, get_settings
from app.logging_setup import setup_logging

log = logging.getLogger(__name__)

# 수집 동시 실행 방지용 Postgres advisory lock 키 (임의의 고정값).
ADVISORY_LOCK_KEY = 7_224_190_001


@dataclass
class SourceResult:
    source: str
    status: Literal["ok", "error"]
    row_count: int = 0
    skipped_count: int = 0


def redact(message: str, secrets: list[str]) -> str:
    for secret in secrets:
        for variant in {secret, quote(secret, safe="")}:
            message = message.replace(variant, "***")
    return message


async def _run_one(
    conn: AsyncConnection, collector: Collector, secrets: list[str], full: bool = False
) -> SourceResult:
    try:
        # full이면 성공 기록을 무시하고 첫 수집 범위로 다시 받는다 (매핑을 바꾼 뒤 기존 행 갱신용).
        last_success_at = None if full else await db.get_last_success_at(conn, collector.source)
        result = await collector.fetch(last_success_at)
        await db.upsert_records(conn, result.records)
        await db.record_success(conn, collector.source, len(result.records), result.skipped_count)
    except Exception as exc:
        message = redact(f"{type(exc).__name__}: {exc}", secrets)
        log.error("%s: collect failed: %s", collector.source, message)
        try:
            await db.record_error(conn, collector.source, message)
        except Exception as state_exc:
            log.error(
                "%s: failed to record error state: %s", collector.source, type(state_exc).__name__
            )
        return SourceResult(collector.source, "error")
    log.info(
        "%s: upserted %d rows, skipped %d",
        collector.source,
        len(result.records),
        result.skipped_count,
    )
    return SourceResult(collector.source, "ok", len(result.records), result.skipped_count)


async def run_collection(
    pool: AsyncConnectionPool, collectors: list[Collector], secrets: list[str], full: bool = False
) -> list[SourceResult] | None:
    """수집기를 차례로 실행한다. 다른 곳에서 이미 실행 중이면 None."""
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT pg_try_advisory_lock(%s)", (ADVISORY_LOCK_KEY,))
        row = await cur.fetchone()
        if not row or not row[0]:
            log.info("collection already running elsewhere, skipped")
            return None
        try:
            return [await _run_one(conn, c, secrets, full) for c in collectors]
        finally:
            await conn.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))


async def _main(settings: Settings, source: str | None, full: bool) -> int:
    collectors = select_collectors(settings, source)
    pool = db.make_pool(settings)
    await pool.open()
    try:
        await db.apply_schema(pool)
        results = await run_collection(pool, collectors, settings.secret_values(), full)
    finally:
        await pool.close()
    if results is None:
        print("another collection is running; skipped")
        return 2
    for r in results:
        print(f"{r.source}\t{r.status}\t{r.row_count}\t{r.skipped_count}")
    return 1 if any(r.status != "ok" for r in results) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.collect")
    parser.add_argument(
        "--source",
        help="이 source만 수집 (예: foodsafety_i0490, consumer24, consumer24_0301)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="성공 기록을 무시하고 첫 수집 범위로 다시 받는다 (매핑을 바꾼 뒤 기존 행 갱신용)",
    )
    args = parser.parse_args(argv)
    setup_logging()
    settings = get_settings()
    try:
        select_collectors(settings, args.source)
    except ValueError as exc:
        parser.error(str(exc))
    log_skipped_sources(settings)
    # psycopg 비동기 모드는 Windows 기본 ProactorEventLoop에서 동작하지 않는다.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    return asyncio.run(_main(settings, args.source, args.full), loop_factory=loop_factory)


if __name__ == "__main__":
    sys.exit(main())
