import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

from config import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD

DB_CONFIG = {
    "host": DB_HOST,
    "database": DB_NAME,
    "user": DB_USER,
    "password": DB_PASSWORD
}


def get_connection():
    return psycopg2.connect(
        **DB_CONFIG,
        cursor_factory=RealDictCursor
    )


# ─────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────

def create_db_schema():
    """Creates all tables if they don't exist. Run once on a fresh database."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    # user_persona — primary user table, same as Project 1
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_persona (
            user_id     TEXT PRIMARY KEY,
            name        TEXT,
            age         INTEGER,
            gender      TEXT,
            city        TEXT,
            personality_info TEXT[],
            total_tokens      INTEGER DEFAULT 0,
            prompt_tokens     INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            cost_inr          FLOAT   DEFAULT 0,
            created_at  TEXT,
            updated_at  TEXT
        );
    """)

    # messages — one row per question/answer exchange, same as Project 1
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            message_id   UUID    PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id      TEXT    NOT NULL REFERENCES user_persona(user_id) ON DELETE CASCADE,
            session_id   TEXT    NOT NULL,
            user_question TEXT   NOT NULL,
            answer        TEXT   NOT NULL,
            user_feedback INTEGER DEFAULT 0,
            latency       FLOAT,
            total_tokens  INTEGER,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            cost_inr      FLOAT,
            timestamp     TEXT
        );
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_personas_user_id
        ON user_persona(user_id);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_user_id_session_id
        ON messages(user_id, session_id);
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Database schema created successfully")


# ─────────────────────────────────────────
# MESSAGES
# ─────────────────────────────────────────

def add_message(user_id, session_id, question, answer, latency, total_tokens, prompt_tokens, completion_tokens, cost_inr):
    """Saves a question/answer exchange. Returns the new message_id (UUID)."""
    conn = get_connection()
    cur = conn.cursor()

    ist_time = datetime.now() + timedelta(hours=5, minutes=30)
    timestamp = ist_time.strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO messages
        (user_id, session_id, user_question, answer, latency,
         total_tokens, prompt_tokens, completion_tokens, cost_inr, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING message_id;
    """, (user_id, session_id, question, answer, latency,
          total_tokens, prompt_tokens, completion_tokens, cost_inr, timestamp))

    message_id = cur.fetchone()['message_id']
    conn.commit()
    cur.close()
    conn.close()
    return str(message_id)


def update_feedback(message_id, user_feedback):
    """Updates user_feedback on a specific message. Returns the updated row or None."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE messages
        SET user_feedback = %s
        WHERE message_id = %s
        RETURNING *;
    """, (user_feedback, message_id))

    updated = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return updated


def get_message_by_id(message_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM messages WHERE message_id = %s;", (message_id,))
    row = cur.fetchone()

    cur.close()
    conn.close()
    return row


def get_messages_by_user(user_id):
    """Returns messages grouped by session_id, same structure as Project 1."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id,
               session_id,
               json_agg(json_build_object(
                   'message_id',        message_id,
                   'user_question',     user_question,
                   'answer',            answer,
                   'user_feedback',     user_feedback,
                   'latency',           latency,
                   'total_tokens',      total_tokens,
                   'prompt_tokens',     prompt_tokens,
                   'completion_tokens', completion_tokens,
                   'cost_inr',          cost_inr,
                   'timestamp',         timestamp
               ) ORDER BY timestamp DESC) AS messages
        FROM messages
        WHERE user_id = %s
        GROUP BY user_id, session_id
        ORDER BY MAX(timestamp) DESC;
    """, (user_id,))

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_all_messages():
    """Returns all messages grouped by user_id and session_id."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id,
               session_id,
               json_agg(json_build_object(
                   'message_id',        message_id,
                   'user_question',     user_question,
                   'answer',            answer,
                   'user_feedback',     user_feedback,
                   'latency',           latency,
                   'total_tokens',      total_tokens,
                   'prompt_tokens',     prompt_tokens,
                   'completion_tokens', completion_tokens,
                   'cost_inr',          cost_inr,
                   'timestamp',         timestamp
               ) ORDER BY timestamp DESC) AS messages
        FROM messages
        GROUP BY user_id, session_id
        ORDER BY MAX(timestamp) DESC;
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_recent_messages(session_id, limit=20):
    """Returns recent (role, content) pairs for building the LLM prompt."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_question, answer
        FROM messages
        WHERE session_id = %s
        ORDER BY timestamp DESC
        LIMIT %s;
    """, (session_id, limit))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    # Reverse so oldest is first, then unpack into (role, content) pairs
    rows.reverse()
    history = []
    for row in rows:
        history.append(("user", row['user_question']))
        history.append(("assistant", row['answer']))
    return history


# ─────────────────────────────────────────
# USER PERSONA
# ─────────────────────────────────────────

def upsert_user(user_id, name, age, gender, city):
    """Creates or updates a user persona. Same as Project 1's upsert_user_persona."""
    conn = get_connection()
    cur = conn.cursor()

    ist_time = datetime.now() + timedelta(hours=5, minutes=30)
    timestamp = ist_time.strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO user_persona (user_id, name, age, gender, city, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET
            name       = COALESCE(EXCLUDED.name,   user_persona.name),
            age        = COALESCE(EXCLUDED.age,    user_persona.age),
            gender     = COALESCE(EXCLUDED.gender, user_persona.gender),
            city       = COALESCE(EXCLUDED.city,   user_persona.city),
            updated_at = EXCLUDED.updated_at;
    """, (user_id, name, age, gender, city, timestamp, timestamp))

    conn.commit()
    cur.close()
    conn.close()


def get_user(user_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM user_persona WHERE user_id = %s;", (user_id,))
    row = cur.fetchone()

    cur.close()
    conn.close()
    return row


def get_all_users():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM user_persona ORDER BY updated_at DESC;")
    rows = cur.fetchall()

    cur.close()
    conn.close()
    return rows


def get_user_by_phone(phone_number):
    """Kept for the /login endpoint on the test frontend."""
    conn = get_connection()
    cur = conn.cursor()

    # user_persona doesn't have phone_number — return None gracefully
    cur.close()
    conn.close()
    return None


# ─────────────────────────────────────────
# HEALTH FACTS  (user_persona.personality_info)
# ─────────────────────────────────────────

def save_health_fact(user_id, fact_key, fact_value):
    """
    Upserts a single health fact into user_persona.personality_info (TEXT[]).
    Facts are stored as 'key: value' strings, matching Project 1's format.
    Existing entry for the same key is replaced; new keys are appended.
    """
    conn = get_connection()
    cur = conn.cursor()

    ist_time = datetime.now() + timedelta(hours=5, minutes=30)
    timestamp = ist_time.strftime("%Y-%m-%d %H:%M:%S")

    fact_string = f"{fact_key}: {fact_value}"

    # Ensure user row exists before updating personality_info
    cur.execute("""
        INSERT INTO user_persona (user_id, personality_info, created_at, updated_at)
        VALUES (%s, ARRAY[%s], %s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET
            personality_info = (
                -- Remove any existing entry with the same key, then append new one
                SELECT array_agg(elem)
                FROM unnest(
                    array_append(
                        ARRAY(
                            SELECT elem FROM unnest(
                                COALESCE(user_persona.personality_info, ARRAY[]::TEXT[])
                            ) AS elem
                            WHERE elem NOT LIKE %s
                        ),
                        %s
                    )
                ) AS elem
            ),
            updated_at = %s;
    """, (user_id, fact_string, timestamp, timestamp,
          f"{fact_key}:%", fact_string, timestamp))

    conn.commit()
    cur.close()
    conn.close()


def get_health_facts(user_id):
    """
    Returns personality_info as a list of (key, value) tuples,
    same format that agent.py and scheduler.py expect.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT personality_info FROM user_persona WHERE user_id = %s;",
        (user_id,)
    )

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row or not row['personality_info']:
        return []

    facts = []
    for entry in row['personality_info']:
        if ':' in entry:
            key, _, value = entry.partition(':')
            facts.append((key.strip(), value.strip()))
    return facts


# ─────────────────────────────────────────
# ANALYTICS
# ─────────────────────────────────────────

def get_analytics():
    """Exactly mirrors Project 1's analytics query."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        WITH user_session_stats AS (
            SELECT
                user_id,
                COUNT(DISTINCT session_id) AS sessions_per_user,
                COUNT(*) AS messages_per_user
            FROM messages
            GROUP BY user_id
        )
        SELECT
            COUNT(*)                                                        AS total_messages,
            COUNT(DISTINCT user_id)                                         AS total_users,
            COUNT(DISTINCT session_id)                                      AS total_sessions,

            ROUND(AVG(latency)::numeric, 3)                                 AS avg_latency,
            ROUND(AVG(total_tokens)::numeric, 2)                            AS avg_total_tokens,
            ROUND(AVG(prompt_tokens)::numeric, 2)                           AS avg_input_tokens,
            ROUND(AVG(completion_tokens)::numeric, 2)                       AS avg_output_tokens,
            ROUND(AVG(cost_inr)::numeric, 4)                                AS avg_cost_per_message,

            SUM(total_tokens)                                               AS total_tokens_used,
            SUM(prompt_tokens)                                              AS total_input_tokens,
            SUM(completion_tokens)                                          AS total_output_tokens,

            COUNT(CASE WHEN user_feedback = 1  THEN 1 END)                  AS positive_feedback,
            COUNT(CASE WHEN user_feedback = -1 THEN 1 END)                  AS negative_feedback,
            COUNT(CASE WHEN user_feedback = 0  THEN 1 END)                  AS no_feedback,

            ROUND(COUNT(DISTINCT session_id)::numeric /
                  NULLIF(COUNT(DISTINCT user_id), 0), 2)                    AS avg_sessions_per_user,
            ROUND(COUNT(*)::numeric /
                  NULLIF(COUNT(DISTINCT user_id), 0), 2)                    AS avg_messages_per_user,
            ROUND(COUNT(*)::numeric /
                  NULLIF(COUNT(DISTINCT session_id), 0), 2)                 AS avg_messages_per_session,

            ROUND(SUM(cost_inr)::numeric, 2)                                AS total_cost
        FROM messages;
    """)

    analytics = cur.fetchone()
    cur.close()
    conn.close()
    return analytics


# ─────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────

def get_last_3_days_user_queries():
    """
    Returns conversations from the last 3 days grouped by user_id,
    same structure as Project 1's get_last_3_days_user_queries.
    """
    conn = get_connection()
    cur = conn.cursor()

    three_days_ago = datetime.now() - timedelta(days=3, hours=1)
    three_days_ago_str = three_days_ago.strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        SELECT
            user_id,
            json_agg(json_build_object(
                'user_question', user_question,
                'answer',        answer,
                'timestamp',     timestamp
            ) ORDER BY timestamp ASC) AS conversations
        FROM messages
        WHERE timestamp >= %s
        GROUP BY user_id
        ORDER BY user_id;
    """, (three_days_ago_str,))

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def update_persona_traits(user_id, new_traits, cost_inr, total_tokens, prompt_tokens, completion_tokens):
    """
    Merges new personality traits into user_persona.personality_info
    and accumulates token/cost totals. Matches Project 1's update_persona logic.
    """
    conn = get_connection()
    cur = conn.cursor()

    ist_time = datetime.now() + timedelta(hours=5, minutes=30)
    timestamp = ist_time.strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        SELECT personality_info, total_tokens, prompt_tokens, completion_tokens, cost_inr
        FROM user_persona
        WHERE user_id = %s;
    """, (user_id,))

    existing = cur.fetchone()
    if not existing:
        cur.close()
        conn.close()
        return

    existing_traits = existing['personality_info'] or []
    merged = list(set(existing_traits + new_traits))

    cur.execute("""
        UPDATE user_persona
        SET personality_info  = %s,
            total_tokens      = total_tokens      + %s,
            prompt_tokens     = prompt_tokens     + %s,
            completion_tokens = completion_tokens + %s,
            cost_inr          = cost_inr          + %s,
            updated_at        = %s
        WHERE user_id = %s;
    """, (merged, total_tokens, prompt_tokens, completion_tokens,
          cost_inr, timestamp, user_id))

    conn.commit()
    cur.close()
    conn.close()