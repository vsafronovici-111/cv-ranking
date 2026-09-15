-- Schema for persisted chat conversations.

CREATE TABLE IF NOT EXISTS conversations (
    id         BIGSERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL,
    name       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
