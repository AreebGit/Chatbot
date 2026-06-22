import psycopg2
from datetime import datetime

DB_CONFIG = {
    "host": "localhost",
    "database": "chatbot_db",
    "user": "postgres",
    "password": "areeb"
}

def get_all_messages():

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM messages
        ORDER BY id DESC
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows


def get_messages_by_user(user_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM messages
        WHERE user_id = %s
        ORDER BY id DESC
        """,
        (user_id,)
    )

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows


def get_message_by_id(message_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM messages
        WHERE id = %s
        """,
        (message_id,)
    )

    row = cur.fetchone()

    cur.close()
    conn.close()

    return row


def get_analytics():

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*) FROM messages"
    )

    total_messages = cur.fetchone()[0]

    cur.execute(
        """
        SELECT COUNT(DISTINCT user_id)
        FROM messages
        """
    )

    total_users = cur.fetchone()[0]

    cur.execute(
        """
        SELECT COUNT(DISTINCT session_id)
        FROM messages
        """
    )

    total_sessions = cur.fetchone()[0]

    cur.close()
    conn.close()

    return {
        "total_messages": total_messages,
        "total_users": total_users,
        "total_sessions": total_sessions
    }


def get_connection():

    return psycopg2.connect(**DB_CONFIG)


def save_message(
    user_id,
    session_id,
    role,
    content,
    feedback=None
):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO messages
        (
            user_id,
            session_id,
            role,
            content,
            timestamp,
            feedback
        )
        VALUES
        (%s,%s,%s,%s,%s,%s)
        """,
        (
            user_id,
            session_id,
            role,
            content,
            datetime.now(),
            feedback
        )
    )

    conn.commit()

    cur.close()
    conn.close()


def get_recent_messages(
    session_id,
    limit=20
):

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


def upsert_user(
    user_id,
    name,
    email
):

    conn = get_connection()

    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO users (
            user_id,
            name,
            email
        )
        VALUES (
            %s,
            %s,
            %s
        )
        ON CONFLICT (user_id)
        DO UPDATE
        SET
            name = EXCLUDED.name,
            email = EXCLUDED.email
        """,
        (
            user_id,
            name,
            email
        )
    )

    conn.commit()

    cur.close()
    conn.close()


def get_all_users():

    conn = get_connection()

    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM users
        ORDER BY id
        """
    )

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows


def get_user(user_id):

    conn = get_connection()

    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM users
        WHERE user_id = %s
        """,
        (user_id,)
    )

    row = cur.fetchone()

    cur.close()
    conn.close()

    return row
def update_feedback(
    session_id,
    feedback
):

    conn = get_connection()

    cur = conn.cursor()

    cur.execute(
        """
        UPDATE messages
        SET feedback = %s
        WHERE id = (

            SELECT id
            FROM messages
            WHERE session_id = %s
            AND role = 'assistant'
            ORDER BY id DESC
            LIMIT 1

        )
        """,
        (
            feedback,
            session_id
        )
    )

    conn.commit()

    cur.close()
    conn.close()
    
def save_user_fact(
    user_id,
    fact_key,
    fact_value
):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO user_facts (
            user_id,
            fact_key,
            fact_value
        )
        VALUES (
            %s,
            %s,
            %s
        )

        ON CONFLICT (
            user_id,
            fact_key
        )

        DO UPDATE
        SET fact_value = EXCLUDED.fact_value
        """,
        (
            user_id,
            fact_key,
            fact_value
        )
    )

    conn.commit()

    cur.close()
    conn.close()


def get_user_facts(user_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT fact_key, fact_value
        FROM user_facts
        WHERE user_id = %s
        """,
        (user_id,)
    )

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows
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