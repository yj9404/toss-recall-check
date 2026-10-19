"""DB 접근. 수집기 upsert, 기동 시 스냅샷 로드, /internal/health/db 확인에서만 쓴다."""

from pathlib import Path
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from app.collectors.base import RecallRecord
from app.config import Settings

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


def make_pool(settings: Settings) -> AsyncConnectionPool:
    # min_size=0, 짧은 max_idle: 유휴 연결을 남겨 두지 않아 Neon 컴퓨트가 절전할 수 있게 한다.
    return AsyncConnectionPool(
        settings.database_url.get_secret_value(),
        min_size=0,
        max_size=3,
        max_idle=60,
        timeout=30,
        kwargs={"autocommit": True, "prepare_threshold": None},
        check=AsyncConnectionPool.check_connection,
        open=False,
    )


async def apply_schema(pool: AsyncConnectionPool) -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    async with pool.connection() as conn:
        await conn.execute(sql)


_UPSERT_COLUMNS = (
    "source",
    "source_id",
    "category",
    "product_name",
    "company_name",
    "reason",
    "grade",
    "manufactured_text",
    "expiry_text",
    "package_unit",
    "recall_method",
    "address",
    "company_phone",
    "barcode",
    "image_urls",
    "source_url",
    "registered_at",
    "raw",
)
_UPDATE_COLUMNS = [c for c in _UPSERT_COLUMNS if c not in ("source", "source_id")]

UPSERT_SQL = f"""
INSERT INTO recalls ({", ".join(_UPSERT_COLUMNS)})
VALUES ({", ".join(f"%({c})s" for c in _UPSERT_COLUMNS)})
ON CONFLICT (source, source_id) DO UPDATE SET
    {", ".join(f"{c} = EXCLUDED.{c}" for c in _UPDATE_COLUMNS)},
    last_seen_at = now()
"""


def _record_params(record: RecallRecord) -> dict[str, Any]:
    params = record.model_dump()
    params["image_urls"] = Jsonb(params["image_urls"])
    params["raw"] = Jsonb(params["raw"])
    return params


async def upsert_records(conn: AsyncConnection, records: list[RecallRecord]) -> None:
    """한 트랜잭션으로 upsert. 실패하면 롤백되어 기존 데이터는 그대로 남는다.

    수집에서 빠진 항목은 지우지 않는다 (last_seen_at이 갱신되지 않을 뿐).
    """
    if not records:
        return
    async with conn.transaction(), conn.cursor() as cur:
        await cur.executemany(UPSERT_SQL, [_record_params(r) for r in records])


async def record_success(conn: AsyncConnection, source: str, row_count: int) -> None:
    await conn.execute(
        """
        INSERT INTO source_state (source, last_success_at, last_row_count)
        VALUES (%s, now(), %s)
        ON CONFLICT (source) DO UPDATE SET
            last_success_at = EXCLUDED.last_success_at,
            last_row_count = EXCLUDED.last_row_count
        """,
        (source, row_count),
    )


async def record_error(conn: AsyncConnection, source: str, message: str) -> None:
    await conn.execute(
        """
        INSERT INTO source_state (source, last_error_at, last_error)
        VALUES (%s, now(), %s)
        ON CONFLICT (source) DO UPDATE SET
            last_error_at = EXCLUDED.last_error_at,
            last_error = EXCLUDED.last_error
        """,
        (source, message[:1000]),
    )


async def ping(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as conn:
        await conn.execute("SELECT 1")


async def fetch_snapshot_rows(
    pool: AsyncConnectionPool, days: int, categories: list[str]
) -> list[dict[str, Any]]:
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, source, category, product_name, company_name, reason, grade,
                   manufactured_text, expiry_text, package_unit, recall_method, address,
                   barcode, image_urls, source_url, registered_at, last_seen_at
            FROM recalls
            WHERE registered_at >= now() - make_interval(days => %s)
              AND category = ANY(%s)
            """,
            (days, categories),
        )
        return await cur.fetchall()
