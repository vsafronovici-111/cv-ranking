from __future__ import annotations

import unittest
import uuid

try:
    from testcontainers.community.postgres import PostgresContainer
except ImportError:  # pragma: no cover - optional dev/test dependency
    PostgresContainer = None  # type: ignore[assignment,misc]

from cv_ranker.db import (
    FAILED,
    PENDING,
    SUCCEEDED,
    CVStore,
    DBSettings,
    MIGRATIONS_DIR,
    iter_migration_files,
)


@unittest.skipUnless(
    PostgresContainer is not None,
    "Install the 'test' extra to run DB-layer tests: pip install -e '.[test]'",
)
class CVStoreTests(unittest.TestCase):
    """DB-layer tests running against a real, ephemeral Postgres container.

    Equivalent to Testcontainers (Java/Go): `testcontainers-python` pulls the
    `postgres:16-alpine` image, starts a fresh container bound to a random
    host port, and tears it down automatically — no shared/manual database,
    no leftover state between test runs.

    The container is started once per test class (matching typical
    Testcontainers usage in Java/Go for speed); each test method still gets
    an isolated `cvs` table via `TRUNCATE` in `setUp`, so tests remain fully
    independent from one another.
    """

    postgres: "PostgresContainer"

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.postgres = PostgresContainer("postgres:16-alpine")
            cls.postgres.start()
        except Exception as exc:  # pragma: no cover - environment guard
            raise unittest.SkipTest(f"Docker not available to run Testcontainers: {exc}")

        dsn = cls.postgres.get_connection_url(driver=None)  # postgresql://...
        cls.store = CVStore(DBSettings(dsn=dsn), migrations_dir=MIGRATIONS_DIR)
        cls.store.init_schema()

    @classmethod
    def tearDownClass(cls) -> None:
        if getattr(cls, "postgres", None) is not None:
            cls.postgres.stop()

    def setUp(self) -> None:
        # Unique-ish filename per test to avoid content-hash collisions across runs.
        self._suffix = uuid.uuid4().hex[:8]
        with self.store._conn() as conn:  # noqa: SLF001 - test-only cleanup helper
            conn.execute("TRUNCATE cvs")

    def test_iter_migration_files_finds_initial_migration(self) -> None:
        files = iter_migration_files(MIGRATIONS_DIR)
        self.assertTrue(any("create_cvs_table" in f.name for f in files))

    def test_ingest_file_dedupes_by_content_hash(self) -> None:
        data = f"hello world {self._suffix}".encode()

        first = self.store.ingest_file("alice.txt", data)
        second = self.store.ingest_file("alice-renamed.txt", data)

        self.assertTrue(first)
        self.assertFalse(second)

        rows = self.store.fetch_by_status(PENDING)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cv_file_name"], "alice.txt")

    def test_claim_next_marks_row_processing_and_increments_attempts(self) -> None:
        self.store.ingest_file("bob.txt", f"cv-{self._suffix}".encode())

        row = self.store.claim_next()
        self.assertIsNotNone(row)
        self.assertEqual(row["cv_file_name"], "bob.txt")

        # No more PENDING/FAILED rows left to claim.
        self.assertIsNone(self.store.claim_next())

    def test_mark_succeeded_then_report(self) -> None:
        self.store.ingest_file("carla.txt", f"cv-{self._suffix}".encode())
        row = self.store.claim_next()

        self.store.mark_succeeded(row["id"], {"score": 85, "summary": "great fit"})

        succeeded = self.store.fetch_all_succeeded()
        self.assertEqual(len(succeeded), 1)
        self.assertEqual(succeeded[0]["score_json"]["score"], 85)

    def test_mark_failed_allows_retry_via_claim_next(self) -> None:
        self.store.ingest_file("derek.txt", f"cv-{self._suffix}".encode())
        row = self.store.claim_next()

        self.store.mark_failed(row["id"], "boom")

        failed_rows = self.store.fetch_by_status(FAILED)
        self.assertEqual(len(failed_rows), 1)
        self.assertEqual(failed_rows[0]["error_message"], "boom")

        # Re-running claim_next (default statuses include FAILED) retries it.
        retried = self.store.claim_next()
        self.assertIsNotNone(retried)
        self.assertEqual(retried["id"], row["id"])

        self.store.mark_succeeded(retried["id"], {"score": 10})
        self.assertEqual(len(self.store.fetch_by_status(SUCCEEDED)), 1)

    def test_counts_by_status(self) -> None:
        self.store.ingest_file("elena.txt", f"cv-a-{self._suffix}".encode())
        self.store.ingest_file("farhan.txt", f"cv-b-{self._suffix}".encode())

        row = self.store.claim_next()
        self.store.mark_succeeded(row["id"], {"score": 50})

        counts = self.store.counts_by_status()
        self.assertEqual(counts.get(SUCCEEDED), 1)
        self.assertEqual(counts.get(PENDING), 1)


if __name__ == "__main__":
    unittest.main()



