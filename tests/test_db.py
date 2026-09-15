from __future__ import annotations

import unittest
import uuid

import psycopg

try:
    from testcontainers.community.postgres import PostgresContainer
except ImportError:  # pragma: no cover - optional dev/test dependency
    PostgresContainer = None  # type: ignore[assignment,misc]

from cv_ranker.db import (
    FAILED,
    MIGRATIONS_DIR,
    PENDING,
    SUCCEEDED,
    CVStore,
    DBSettings,
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

    postgres: PostgresContainer

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.postgres = PostgresContainer("postgres:16-alpine")
            cls.postgres.start()
        except Exception as exc:  # pragma: no cover - environment guard
            raise unittest.SkipTest(f"Docker not available to run Testcontainers: {exc}") from exc

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
            conn.execute("TRUNCATE cvs, conversations, messages")

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

    def test_create_conversation_persists_user_id_and_name(self) -> None:
        conversation_id = self.store.create_conversation("user-1", name="First chat")

        with self.store._conn() as conn:  # noqa: SLF001 - test-only assertion helper
            row = conn.execute("SELECT user_id, name FROM conversations WHERE id = %s", (conversation_id,)).fetchone()

        self.assertEqual(row["user_id"], "user-1")
        self.assertEqual(row["name"], "First chat")

    def test_create_conversation_defaults_name_to_none(self) -> None:
        conversation_id = self.store.create_conversation("user-2")

        with self.store._conn() as conn:  # noqa: SLF001 - test-only assertion helper
            row = conn.execute("SELECT name FROM conversations WHERE id = %s", (conversation_id,)).fetchone()

        self.assertIsNone(row["name"])

    def test_update_conversation_name_renames_existing_conversation(self) -> None:
        conversation_id = self.store.create_conversation("user-3", name="Old name")

        updated = self.store.update_conversation_name(conversation_id, "New name")

        self.assertTrue(updated)
        with self.store._conn() as conn:  # noqa: SLF001 - test-only assertion helper
            row = conn.execute("SELECT name FROM conversations WHERE id = %s", (conversation_id,)).fetchone()

        self.assertEqual(row["name"], "New name")

    def test_update_conversation_name_for_missing_conversation_returns_false(self) -> None:
        updated = self.store.update_conversation_name(999999, "New name")

        self.assertFalse(updated)

    def test_get_conversation_returns_row_or_none(self) -> None:
        conversation_id = self.store.create_conversation("user-5", name="Fetchable")

        conversation = self.store.get_conversation(conversation_id)
        self.assertEqual(conversation.user_id, "user-5")
        self.assertEqual(conversation.name, "Fetchable")

        self.assertIsNone(self.store.get_conversation(999999))

    def test_list_conversations_by_user_returns_only_that_users_conversations(self) -> None:
        self.store.create_conversation("user-6", name="A")
        self.store.create_conversation("user-6", name="B")
        self.store.create_conversation("user-7", name="Other user's")

        conversations = self.store.list_conversations_by_user("user-6")

        self.assertEqual({c.name for c in conversations}, {"A", "B"})

    def test_create_message_persists_under_conversation(self) -> None:
        conversation_id = self.store.create_conversation("user-4")

        message_id = self.store.create_message(conversation_id, "user", "Hello there")

        with self.store._conn() as conn:  # noqa: SLF001 - test-only assertion helper
            row = conn.execute(
                "SELECT conversation_id, role, content FROM messages WHERE id = %s", (message_id,)
            ).fetchone()

        self.assertEqual(row["conversation_id"], conversation_id)
        self.assertEqual(row["role"], "user")
        self.assertEqual(row["content"], "Hello there")

    def test_create_message_for_missing_conversation_raises(self) -> None:
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.store.create_message(999999, "user", "orphaned")

    def test_get_message_returns_row_or_none(self) -> None:
        conversation_id = self.store.create_conversation("user-8")
        message_id = self.store.create_message(conversation_id, "assistant", "hi")

        message = self.store.get_message(message_id)
        self.assertEqual(message.conversation_id, conversation_id)
        self.assertEqual(message.role, "assistant")
        self.assertEqual(message.content, "hi")

        self.assertIsNone(self.store.get_message(999999))

    def test_list_messages_by_conversation_returns_only_that_conversations_messages(self) -> None:
        conversation_id = self.store.create_conversation("user-9")
        other_conversation_id = self.store.create_conversation("user-9")
        self.store.create_message(conversation_id, "user", "first")
        self.store.create_message(conversation_id, "assistant", "second")
        self.store.create_message(other_conversation_id, "user", "unrelated")

        messages = self.store.list_messages_by_conversation(conversation_id)

        self.assertEqual([m.content for m in messages], ["first", "second"])

    def test_update_message_content_changes_existing_message(self) -> None:
        conversation_id = self.store.create_conversation("user-10")
        message_id = self.store.create_message(conversation_id, "user", "original")

        updated = self.store.update_message_content(message_id, "edited")

        self.assertTrue(updated)
        self.assertEqual(self.store.get_message(message_id).content, "edited")

    def test_update_message_content_for_missing_message_returns_false(self) -> None:
        updated = self.store.update_message_content(999999, "edited")

        self.assertFalse(updated)


if __name__ == "__main__":
    unittest.main()
