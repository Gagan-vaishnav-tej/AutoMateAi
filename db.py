import sqlite3
import os
from datetime import datetime

DB_PATH = "data.db"

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # Tokens
    c.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            platform TEXT PRIMARY KEY,
            access_token TEXT NOT NULL
        )
    """)

    # Campaigns (with hour + minute)
    c.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            days INTEGER NOT NULL,
            hour INTEGER DEFAULT 9,
            minute INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # Scheduled posts
    c.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER,
            topic_variant TEXT NOT NULL,
            run_time TEXT NOT NULL,
            status TEXT DEFAULT 'scheduled',
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        )
    """)

    conn.commit()
    conn.close()

# ---------- TOKEN OPS ----------
def save_token(platform, token):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO tokens (platform, access_token)
        VALUES (?, ?)
    """, (platform, token))
    conn.commit()
    conn.close()

def get_token(platform):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT access_token FROM tokens WHERE platform = ?", (platform,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

# ---------- CAMPAIGN OPS ----------
def save_campaign(topic, days, hour, minute):
    conn = get_conn()
    c = conn.cursor()
    created_at = datetime.now().isoformat()
    c.execute("""
        INSERT INTO campaigns (topic, days, hour, minute, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (topic, days, hour, minute, created_at))
    campaign_id = c.lastrowid
    conn.commit()
    conn.close()
    return campaign_id

def save_scheduled_post(campaign_id, topic_variant, run_time):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO scheduled_posts (campaign_id, topic_variant, run_time)
        VALUES (?, ?, ?)
    """, (campaign_id, topic_variant, run_time))
    conn.commit()
    conn.close()

def get_pending_posts():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, topic_variant, run_time FROM scheduled_posts
        WHERE status = 'scheduled'
    """)
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "topic_variant": r[1], "run_time": r[2]} for r in rows]

def mark_post_done(post_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE scheduled_posts SET status = 'done' WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()

def clear_all_data():
    conn = sqlite3.connect("social_ai.db")  # or your DB path
    cur = conn.cursor()
    try:
        # Adjust table names as per your schema
        cur.execute("DELETE FROM campaigns;")
        cur.execute("DELETE FROM scheduled_posts;")
        cur.execute("DELETE FROM posts;")
        conn.commit()
        print("🧹 All DB tables cleared.")
    except Exception as e:
        print("⚠️ Error clearing DB:", e)
    finally:
        conn.close()
