from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row


class CVStoreError(RuntimeError):
    pass


@dataclass
class DBSettings:
    dsn: str  # e.g. "postgresql://user:pass@localhost:5432/cvranker"


# Project root: src/cv_ranker/db.py -> src/cv_ranker -> src -> <repo root>
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MIGRATIONS_DIR = _REPO_ROOT / "db" / "migrations"


def iter_migration_files(migrations_dir: Path = MIGRATIONS_DIR) -> list[Path]:
    """Return all `.sql` migration files in `migrations_dir`, sorted by filename.

    Sorting alphabetically relies on the `NNNN_description.sql` naming
    convention so migrations are always applied in the intended order.
    """
    return sorted(migrations_dir.glob("*.sql"))


PENDING = "PENDING"
PROCESSING = "PROCESSING"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"


class CVStore:
    """Postgres-backed durable queue for CV ingestion/scoring.

    Workflow:
      1. `ingest_file` inserts raw CV bytes as PENDING (dedup by content hash).
      2. `claim_next` atomically picks one PENDING/FAILED row and marks it
         PROCESSING (safe for multiple concurrent workers via SKIP LOCKED).
      3. Caller scores the CV and calls `mark_succeeded` or `mark_failed`.
      4. Re-running the processing loop automatically retries FAILED rows.
    """

    def __init__(self, settings: DBSettings, migrations_dir: Path = MIGRATIONS_DIR):
        self._dsn = settings.dsn
        self._migrations_dir = migrations_dir

    @contextmanager
    def _conn(self) -> Iterator[psycopg.Connection]:
        try:
            with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
                yield conn
        except psycopg.OperationalError as exc:
            raise CVStoreError(f"Cannot connect to database: {exc}") from exc

    def init_schema(self) -> None:
        """Apply every `.sql` migration file in `db/migrations/`, in order.

        Each migration is expected to be idempotent (`IF NOT EXISTS`, etc.)
        so this can safely run on every CLI startup and in tests.
        """
        migration_files = iter_migration_files(self._migrations_dir)
        if not migration_files:
            raise CVStoreError(f"No migration files found in {self._migrations_dir}")

        with self._conn() as conn:
            for migration_file in migration_files:
                conn.execute(migration_file.read_text(encoding="utf-8"))

    def ingest_file(self, filename: str, data: bytes) -> bool:
        """Insert a CV as PENDING. Returns False if it already exists (dedup by content)."""
        content_hash = hashlib.sha256(data).hexdigest()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO cvs (cv_file_name, data, content_hash, status)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (content_hash) DO NOTHING
                RETURNING id
                """,
                (filename, data, content_hash, PENDING),
            )
            return cur.fetchone() is not None

    def claim_next(self, statuses: tuple[str, ...] = (PENDING, FAILED)) -> dict[str, Any] | None:
        """Atomically pick one row to process and mark it PROCESSING.

        Uses SELECT ... FOR UPDATE SKIP LOCKED so multiple workers can run
        concurrently without double-processing the same row.
        """
        with self._conn() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    SELECT id, cv_file_name, data FROM cvs
                    WHERE status = ANY(%s)
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """,
                    (list(statuses),),
                ).fetchone()
                if row is None:
                    return None
                conn.execute(
                    """
                    UPDATE cvs SET status = %s, attempts = attempts + 1, updated_at = now()
                    WHERE id = %s
                    """,
                    (PROCESSING, row["id"]),
                )
                return row

    def mark_succeeded(self, cv_id: int, score: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE cvs SET status = %s, score_json = %s, error_message = NULL, updated_at = now()
                WHERE id = %s
                """,
                (SUCCEEDED, json.dumps(score), cv_id),
            )

    def mark_failed(self, cv_id: int, error: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE cvs SET status = %s, error_message = %s, updated_at = now()
                WHERE id = %s
                """,
                (FAILED, error, cv_id),
            )

    def fetch_by_status(self, status: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            return conn.execute(
                "SELECT id, cv_file_name, status, score_json, error_message, attempts "
                "FROM cvs WHERE status = %s ORDER BY id",
                (status,),
            ).fetchall()

    def fetch_all_succeeded(self) -> list[dict[str, Any]]:
        return self.fetch_by_status(SUCCEEDED)

    def counts_by_status(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute("SELECT status, count(*) AS count FROM cvs GROUP BY status").fetchall()
            return {row["status"]: row["count"] for row in rows}


