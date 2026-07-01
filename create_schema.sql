-- Run this once on a fresh database to set up all tables
-- psql -U postgres -d chatbot_db -f create_schema.sql

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS user_persona (
    user_id           TEXT PRIMARY KEY,
    name              TEXT,
    age               INTEGER,
    gender            TEXT,
    city              TEXT,
    personality_info  TEXT[],
    total_tokens      INTEGER DEFAULT 0,
    prompt_tokens     INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    cost_inr          FLOAT   DEFAULT 0,
    created_at        TEXT,
    updated_at        TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    message_id        UUID    PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id           TEXT    NOT NULL REFERENCES user_persona(user_id) ON DELETE CASCADE,
    session_id        TEXT    NOT NULL,
    user_question     TEXT    NOT NULL,
    answer            TEXT    NOT NULL,
    user_feedback     INTEGER DEFAULT 0,
    latency           FLOAT,
    total_tokens      INTEGER,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    cost_inr          FLOAT,
    timestamp         TEXT
);

CREATE INDEX IF NOT EXISTS idx_personas_user_id
    ON user_persona(user_id);

CREATE INDEX IF NOT EXISTS idx_messages_user_id_session_id
    ON messages(user_id, session_id);