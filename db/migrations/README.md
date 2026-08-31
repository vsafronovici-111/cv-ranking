# Database Migrations

Plain, ordered `.sql` files applied in filename order (`0001_...`, `0002_...`, ...).

- Applied automatically at runtime by `CVStore.init_schema()`
  (see `src/cv_ranker/db.py`), which runs every migration file in this
  folder inside a transaction, in order, each time the CLI starts.
  All statements use `CREATE TABLE IF NOT EXISTS` / `IF NOT EXISTS` so
  re-running them is always safe (idempotent).
- Reused by db-layer unit tests (`tests/test_db.py`) so the schema under
  test is always identical to the schema used in production/local.

To add a new migration, create a new file `NNNN_description.sql` with the
next number and keep statements idempotent (`IF NOT EXISTS`, etc.).

