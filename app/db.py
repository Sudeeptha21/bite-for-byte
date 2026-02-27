import pathlib
import psycopg2
from app.config import settings


def get_conn():
    return psycopg2.connect(
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        host=settings.DB_HOST,
        port=settings.DB_PORT,
    )


def execute(sql: str, params: tuple | None = None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        cur.close()
    finally:
        conn.close()


def fetchone(sql: str, params: tuple | None = None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        row = cur.fetchone()
        cur.close()
        return row
    finally:
        conn.close()


def init_schema():
    schema_path = pathlib.Path(__file__).parent / "models" / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")
    execute(sql)


def log_request(
    endpoint: str,
    status_code: int,
    latency_ms: int,
    provider: str | None = None,
    token_usage: int | None = None,
    estimated_cost_usd: float | None = None,
):
    execute(
        """
        INSERT INTO requests_log (endpoint, status_code, latency_ms, provider, token_usage, estimated_cost_usd)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (endpoint, status_code, latency_ms, provider, token_usage, estimated_cost_usd),
    )
