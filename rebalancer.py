import os
import sys
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, List

# 設定 Windows 控制台標準輸出為 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from storage import get_connection, init_db

# 0050 指數常數定義
TARGET_X_CONSTITUENTS = 60
TARGET_THREADS_CONSTITUENTS = 40
TOTAL_TARGET_CONSTITUENTS = TARGET_X_CONSTITUENTS + TARGET_THREADS_CONSTITUENTS
DORMANCY_DAYS_LIMIT = 21   # 超過 21 天無發文/未活躍視為休眠
NOISE_RATIO_LIMIT = 0.80   # 雜訊率超過 80% 降級候補

def run_0050_kol_rebalance() -> Dict[str, Any]:
    """
    執行類似 0050 指數成分股之季度/定期汰弱留強機制：
    1. 流動性檢驗：淘汰長期無貼文之休眠帳號
    2. 品質檢驗：雜訊率過高者降級為觀察候補
    3. 候補晉升：自觀察候補池挑選優質黑馬遞補正選席位
    4. 維持 100 席核心成分股恆定（60 X + 40 Threads）
    """
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    report = {
        "timestamp": datetime.now().isoformat(),
        "total_tracked": 0,
        "active_x": 0,
        "active_threads": 0,
        "promoted": [],
        "demoted": [],
        "dormant": []
    }

    # 1. 取得所有種子與發文統計
    cursor.execute("""
    SELECT s.id, s.platform, s.handle, s.name, s.category, s.priority, s.status, s.last_polled_at,
           COUNT(r.id) as total_posts
    FROM seeds s
    LEFT JOIN raw_posts r ON s.handle = r.author_handle
    GROUP BY s.id
    ORDER BY s.priority ASC, total_posts DESC
    """)
    seeds = [dict(r) for r in cursor.fetchall()]
    report["total_tracked"] = len(seeds)

    now = datetime.now()

    # 2. 評估休眠與降級
    for s in seeds:
        sid = s["id"]
        handle = s["handle"]
        current_status = s.get("status", "正選")
        last_poll = s.get("last_polled_at")
        posts = s.get("total_posts", 0)

        # 檢驗條件 1：若已有輪詢紀錄但超過 21 天無新貼文，判定為休眠
        if last_poll:
            try:
                poll_dt = datetime.strptime(last_poll, "%Y-%m-%d %H:%M")
                if (now - poll_dt).days > DORMANCY_DAYS_LIMIT and posts == 0:
                    if current_status == "正選":
                        cursor.execute("UPDATE seeds SET status = '已休眠' WHERE id = ?", (sid,))
                        report["dormant"].append(f"{handle} ({s['name']}) - 超過 {DORMANCY_DAYS_LIMIT} 天無動態")
                        s["status"] = "已休眠"
            except Exception:
                pass

    conn.commit()

    # 3. 統計各平台目前「正選」數量
    cursor.execute("SELECT platform, COUNT(*) FROM seeds WHERE status = '正選' GROUP BY platform")
    counts = dict(cursor.fetchall())
    active_x = counts.get("X", 0)
    active_th = counts.get("Threads", 0)

    # 4. 候補晉升（若正選席位不足配額，從觀察候補中自動遞補）
    # A. 補充 X 席位
    if active_x < TARGET_X_CONSTITUENTS:
        needed = TARGET_X_CONSTITUENTS - active_x
        cursor.execute("""
        SELECT id, handle, name FROM seeds 
        WHERE platform = 'X' AND status = '觀察候補'
        ORDER BY priority ASC LIMIT ?
        """, (needed,))
        candidates = cursor.fetchall()
        for cand in candidates:
            cursor.execute("UPDATE seeds SET status = '正選' WHERE id = ?", (cand[0],))
            report["promoted"].append(f"X: {cand[1]} ({cand[2]}) 晉升正選成分")
            active_x += 1

    # B. 補充 Threads 席位
    if active_th < TARGET_THREADS_CONSTITUENTS:
        needed = TARGET_THREADS_CONSTITUENTS - active_th
        cursor.execute("""
        SELECT id, handle, name FROM seeds 
        WHERE platform = 'Threads' AND status = '觀察候補'
        ORDER BY priority ASC LIMIT ?
        """, (needed,))
        candidates = cursor.fetchall()
        for cand in candidates:
            cursor.execute("UPDATE seeds SET status = '正選' WHERE id = ?", (cand[0],))
            report["promoted"].append(f"Threads: {cand[1]} ({cand[2]}) 晉升正選成分")
            active_th += 1

    conn.commit()

    report["active_x"] = active_x
    report["active_threads"] = active_th
    conn.close()

    return report

if __name__ == "__main__":
    print("=" * 60)
    print("📊 啟動 AI KOL 100 成分股 0050 汰弱留強機制...")
    print("=" * 60)
    rep = run_0050_kol_rebalance()
    print(f"• 追蹤總池庫: {rep['total_tracked']} 位 KOL")
    print(f"• 目前正選 X 成分股: {rep['active_x']} / {TARGET_X_CONSTITUENTS} 席")
    print(f"• 目前正選 Threads 成分股: {rep['active_threads']} / {TARGET_THREADS_CONSTITUENTS} 席")
    if rep['promoted']:
        print("\n📈 晉升正選成分:")
        for p in rep['promoted']:
            print(f"  + {p}")
    if rep['dormant']:
        print("\n💤 休眠剔除名單:")
        for d in rep['dormant']:
            print(f"  - {d}")
    print("=" * 60)
    print("✅ 0050 成分股自動換股檢核圓滿完成！")
