-- Tracks whether an AI response has been generated for a given message,
-- keyed uniquely by message_id so the consumer's processing stays
-- idempotent under redelivery/retries.

CREATE TABLE IF NOT EXISTS message_responses (
    id         BIGSERIAL PRIMARY KEY,
    message_id BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    status     TEXT NOT NULL DEFAULT 'PROCESSING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_message_responses_message_id ON message_responses(message_id);
