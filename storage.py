import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "intel_radar.db")
SEEDS_PATH = os.path.join(os.path.dirname(__file__), "seeds.json")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """初始化 SQLite 資料表結構與種子名單"""
    conn = get_connection()
    cursor = conn.cursor()

    # 種子名單表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS seeds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        handle TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        category TEXT,
        priority TEXT DEFAULT 'P1',
        tags TEXT,
        active INTEGER DEFAULT 1,
        last_polled_at TEXT,
        status TEXT DEFAULT '正常'
    )
    """)

    # 原始抓取貼文表（排重）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS raw_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        post_id TEXT NOT NULL,
        author_handle TEXT NOT NULL,
        author_name TEXT,
        content TEXT NOT NULL,
        created_at TEXT,
        likes INTEGER DEFAULT 0,
        reposts INTEGER DEFAULT 0,
        raw_metadata TEXT,
        processed INTEGER DEFAULT 0,
        scanned_at TEXT,
        UNIQUE(platform, post_id)
    )
    """)

    # 代理人萃取情報卡片表（四層解構）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS intel_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        raw_post_id INTEGER UNIQUE,
        title TEXT NOT NULL,
        platform TEXT NOT NULL,
        author TEXT NOT NULL,
        author_role TEXT,
        urgency TEXT DEFAULT 'P1',
        timestamp_str TEXT,
        likes INTEGER DEFAULT 0,
        summary TEXT NOT NULL,
        core_thesis TEXT NOT NULL,
        links_json TEXT,
        community_views_json TEXT,
        arbitrage_json TEXT,
        actionable TEXT,
        created_at TEXT,
        FOREIGN KEY (raw_post_id) REFERENCES raw_posts(id)
    )
    """)

    conn.commit()

    # 載入預設 seeds.json
    if os.path.exists(SEEDS_PATH):
        with open(SEEDS_PATH, "r", encoding="utf-8") as f:
            seeds = json.load(f)
            for s in seeds:
                cursor.execute("""
                INSERT INTO seeds (platform, handle, name, category, priority, tags, status)
                VALUES (?, ?, ?, ?, ?, ?, '正常')
                ON CONFLICT(handle) DO UPDATE SET
                    name=excluded.name,
                    category=excluded.category,
                    priority=excluded.priority,
                    tags=excluded.tags
                """, (
                    s["platform"],
                    s["handle"],
                    s["name"],
                    s.get("category", ""),
                    s.get("priority", "P1"),
                    json.dumps(s.get("tags", []), ensure_ascii=False)
                ))
            conn.commit()

    conn.close()

def save_raw_post(platform: str, post_id: str, author_handle: str, author_name: str, content: str, likes: int = 0, reposts: int = 0, metadata: dict = None) -> Optional[int]:
    """儲存原始貼文，若重複則返回 None"""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    try:
        cursor.execute("""
        INSERT INTO raw_posts (platform, post_id, author_handle, author_name, content, likes, reposts, raw_metadata, scanned_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (platform, post_id, author_handle, author_name, content, likes, reposts, json.dumps(metadata or {}), now))
        conn.commit()
        inserted_id = cursor.lastrowid
        conn.close()
        return inserted_id
    except sqlite3.IntegrityError:
        conn.close()
        return None

def get_unprocessed_posts(limit: int = 20) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM raw_posts WHERE processed = 0 ORDER BY id ASC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def mark_post_processed(raw_post_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE raw_posts SET processed = 1 WHERE id = ?", (raw_post_id,))
    conn.commit()
    conn.close()

def save_intel_report(report_data: dict) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO intel_reports (
        raw_post_id, title, platform, author, author_role, urgency,
        timestamp_str, likes, summary, core_thesis, links_json,
        community_views_json, arbitrage_json, actionable, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(raw_post_id) DO UPDATE SET
        title=excluded.title,
        urgency=excluded.urgency,
        summary=excluded.summary,
        core_thesis=excluded.core_thesis,
        links_json=excluded.links_json,
        community_views_json=excluded.community_views_json,
        arbitrage_json=excluded.arbitrage_json,
        actionable=excluded.actionable
    """, (
        report_data.get("raw_post_id"),
        report_data["title"],
        report_data["platform"],
        report_data["author"],
        report_data.get("author_role", "社群專家"),
        report_data.get("urgency", "P1"),
        report_data.get("timestamp_str", "剛剛"),
        report_data.get("likes", 0),
        report_data["summary"],
        report_data["core_thesis"],
        json.dumps(report_data.get("links", []), ensure_ascii=False),
        json.dumps(report_data.get("community_views", {}), ensure_ascii=False),
        json.dumps(report_data.get("arbitrage", {}), ensure_ascii=False),
        report_data.get("actionable", ""),
        now
    ))
    conn.commit()
    inserted_id = cursor.lastrowid
    conn.close()
    return inserted_id

def get_all_intel_reports(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM intel_reports ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        d = dict(r)
        d["links"] = json.loads(d["links_json"]) if d["links_json"] else []
        d["communityViews"] = json.loads(d["community_views_json"]) if d["community_views_json"] else {}
        d["arbitrage"] = json.loads(d["arbitrage_json"]) if d["arbitrage_json"] else {}
        results.append(d)
    return results

def get_roster_summary() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT s.*, COUNT(r.id) as post_count
    FROM seeds s
    LEFT JOIN raw_posts r ON s.handle = r.author_handle
    GROUP BY s.id
    ORDER BY s.priority ASC, post_count DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_seed_poll_time(handle: str):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("UPDATE seeds SET last_polled_at = ?, status = '正常' WHERE handle = ?", (now, handle))
    conn.commit()
    conn.close()
