import psycopg2
from datetime import datetime

DB_CONFIG = {
    "host": "localhost",
    "database": "chatbot_db",
    "user": "postgres",
    "password": "areeb"
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


# ─────────────────────────────────────────
# MESSAGES
# ─────────────────────────────────────────

def save_message(
    user_id,
    session_id,
    role,
    content,
    feedback=None,
    input_tokens=None,
    output_tokens=None,
    latency_ms=None
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO messages
        (user_id, session_id, role, content, timestamp, feedback,
         input_tokens, output_tokens, latency_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user_id, session_id, role, content,
            datetime.now(), feedback,
            input_tokens, output_tokens, latency_ms
        )
    )

    conn.commit()
    cur.close()
    conn.close()


def get_recent_messages(session_id, limit=20):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT role, content
        FROM messages
        WHERE session_id = %s
        ORDER BY id DESC
        LIMIT %s
        """,
        (session_id, limit)
    )

    rows = cur.fetchall()
    cur.close()
    conn.close()

    rows.reverse()
    return rows


def get_all_messages():

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM messages ORDER BY id DESC")
    rows = cur.fetchall()

    cur.close()
    conn.close()
    return rows


def get_messages_by_user(user_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM messages WHERE user_id = %s ORDER BY id DESC",
        (user_id,)
    )

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_message_by_id(message_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM messages WHERE id = %s", (message_id,))
    row = cur.fetchone()

    cur.close()
    conn.close()
    return row


def update_feedback(session_id, feedback):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE messages
        SET feedback = %s
        WHERE id = (
            SELECT id FROM messages
            WHERE session_id = %s
            AND role = 'assistant'
            ORDER BY id DESC
            LIMIT 1
        )
        """,
        (feedback, session_id)
    )

    conn.commit()
    cur.close()
    conn.close()


# ─────────────────────────────────────────
# USERS
# ─────────────────────────────────────────

def upsert_user(user_id, name, email, phone_number, city=None):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO users (user_id, name, email, phone_number, city)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET
            name = EXCLUDED.name,
            email = EXCLUDED.email,
            phone_number = EXCLUDED.phone_number,
            city = EXCLUDED.city
        """,
        (user_id, name, email, phone_number, city)
    )

    conn.commit()
    cur.close()
    conn.close()


def get_all_users():

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users ORDER BY id")
    rows = cur.fetchall()

    cur.close()
    conn.close()
    return rows


def get_user(user_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    row = cur.fetchone()

    cur.close()
    conn.close()
    return row


def get_user_by_phone(phone_number):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM users WHERE phone_number = %s",
        (phone_number,)
    )

    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


# ─────────────────────────────────────────
# HEALTH FACTS
# ─────────────────────────────────────────

def save_health_fact(user_id, fact_key, fact_value):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO user_facts (user_id, fact_key, fact_value)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, fact_key)
        DO UPDATE SET fact_value = EXCLUDED.fact_value
        """,
        (user_id, fact_key, fact_value)
    )

    conn.commit()
    cur.close()
    conn.close()


def get_sessions(user_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT DISTINCT session_id
        FROM messages
        WHERE user_id = %s
        ORDER BY session_id
        """,
        (user_id,)
    )

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_health_facts(user_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT fact_key, fact_value FROM user_facts WHERE user_id = %s",
        (user_id,)
    )

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


# ─────────────────────────────────────────
# ANALYTICS
# ─────────────────────────────────────────

def get_analytics():

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM messages WHERE role = 'user'")
    total_messages = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT user_id) FROM messages")
    total_users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT session_id) FROM messages")
    total_sessions = cur.fetchone()[0]

    cur.execute("""
        SELECT COALESCE(AVG(input_tokens), 0)
        FROM messages
        WHERE role = 'user' AND input_tokens IS NOT NULL
    """)
    avg_input_tokens = round(float(cur.fetchone()[0]), 2)

    cur.execute("""
        SELECT COALESCE(AVG(output_tokens), 0)
        FROM messages
        WHERE role = 'assistant' AND output_tokens IS NOT NULL
    """)
    avg_output_tokens = round(float(cur.fetchone()[0]), 2)

    avg_tokens_per_msg = round(avg_input_tokens + avg_output_tokens, 2)

    cur.execute("""
        SELECT COALESCE(AVG(latency_ms), 0)
        FROM messages
        WHERE role = 'assistant' AND latency_ms IS NOT NULL
    """)
    avg_latency_s = round(float(cur.fetchone()[0]) / 1000, 2)

    sessions_per_user = round(
        total_sessions / total_users, 2
    ) if total_users > 0 else 0

    messages_per_user = round(
        total_messages / total_users, 2
    ) if total_users > 0 else 0

    cur.execute("""
        SELECT feedback, COUNT(*)
        FROM messages
        WHERE feedback IS NOT NULL
        GROUP BY feedback
    """)
    feedback_rows = cur.fetchall()
    feedback = {row[0]: row[1] for row in feedback_rows}

    cur.execute("""
        SELECT timestamp, latency_ms
        FROM messages
        WHERE role = 'assistant' AND latency_ms IS NOT NULL
        ORDER BY id DESC
        LIMIT 30
    """)
    latency_rows = cur.fetchall()
    latency_chart = [
        {
            "time": str(row[0]),
            "latency_s": round(row[1] / 1000, 2)
        }
        for row in reversed(latency_rows)
    ]

    cur.close()
    conn.close()

    return {
        "total_messages": total_messages,
        "total_users": total_users,
        "total_sessions": total_sessions,
        "avg_input_tokens": avg_input_tokens,
        "avg_output_tokens": avg_output_tokens,
        "avg_tokens_per_msg": avg_tokens_per_msg,
        "avg_latency_s": avg_latency_s,
        "sessions_per_user": sessions_per_user,
        "messages_per_user": messages_per_user,
        "feedback": feedback,
        "latency_chart": latency_chart
    }