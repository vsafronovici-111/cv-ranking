-- Initial schema for the CV processing queue.
-- Applied automatically by CVStore.init_schema() and reused by db-layer unit
-- tests to keep the test schema and the runtime schema in sync.

CREATE TABLE IF NOT EXISTS cvs (
    id             BIGSERIAL PRIMARY KEY,
    cv_file_name   TEXT NOT NULL,
    data           BYTEA NOT NULL,
    content_hash   TEXT NOT NULL UNIQUE,
    status         TEXT NOT NULL DEFAULT 'PENDING',
    score_json     JSONB,
    error_message  TEXT,
    attempts       INT NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cvs_status ON cvs(status);

