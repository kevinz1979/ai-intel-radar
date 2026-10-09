import os
import sys
import time
import json
from datetime import datetime

# 設定 Windows 控制台標準輸出為 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from storage import (
    init_db,
    get_unprocessed_posts,
    mark_post_processed,
    save_intel_report,
    get_all_intel_reports,
    get_roster_summary
)
from analyzer import AgenticAnalyzer
from poller import RealSocialPoller

DASHBOARD_HTML_PATH = r"C:\Users\kevinz\.gemini\antigravity\brain\e4c2ce29-1de8-411a-9781-e6565c3f5626\intel_dashboard.html"

def sync_to_dashboard(reports, roster):
    """將 SQLite 最新提煉的情報同步寫入 Web App 儀控表 HTML"""
    if not os.path.exists(DASHBOARD_HTML_PATH):
        print(f"[Runner] 找不到儀控表文件: {DASHBOARD_HTML_PATH}")
        return

    with open(DASHBOARD_HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # 清洗 reports 內的所有字串，確保不含任何換行符號
    clean_reports = []
    for r in reports:
        cr = dict(r)
        for k in ["title", "summary", "core_thesis", "actionable", "author", "author_role"]:
            if k in cr and isinstance(cr[k], str):
                cr[k] = " ".join(cr[k].split())
        clean_reports.append(cr)

    intel_json = json.dumps(clean_reports, ensure_ascii=False, indent=2)
    import re
    # 使用 lambda 避免 re.sub 解析 backslash 造成字串中斷
    html = re.sub(r"const INTEL_DATA = \[.*?\];", lambda _: f"const INTEL_DATA = {intel_json};", html, flags=re.DOTALL)

    # 替換 ROSTER_DATA
    roster_clean = []
    for r in roster[:15]:
        roster_clean.append({
            "platform": r["platform"],
            "handle": r["handle"],
            "name": r["name"],
            "role": r.get("category", "AI 領域專家"),
            "lastCheck": r.get("last_polled_at") or "剛剛",
            "count": r.get("post_count", 0),
            "status": r.get("status", "正常")
        })
    roster_json = json.dumps(roster_clean, ensure_ascii=False, indent=2)
    html = re.sub(r"const ROSTER_DATA = \[.*?\];", lambda _: f"const ROSTER_DATA = {roster_json};", html, flags=re.DOTALL)

    with open(DASHBOARD_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[Runner] 儀控表已成功同步更新！共寫入 {len(clean_reports)} 則乾淨格式情報卡片。")

def run_patrol_cycle():
    """執行一次完整的巡邏與雙核解構循環"""
    print("=" * 60)
    print(f"🚀 [AI 情報雷達] 啟動巡邏作業 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 初始化資料庫
    init_db()

    # 2. 執行真實雙軌巡邏
    poller = RealSocialPoller()
    print("📡 [Poller] 開始對 X 與 Threads 種子進行真實即時掃描...", flush=True)
    # 巡邏 X 核心 KOL
    for handle in ["@karpathy", "@swyx", "@simonw"]:
        poller.poll_x_user(handle)
        time.sleep(1)
    # 巡邏 Threads 核心 KOL
    for handle in ["@ihower"]:
        poller.poll_threads_user(handle)
        time.sleep(1)

    # 3. 讀取未處理貼文
    unprocessed = get_unprocessed_posts(limit=20)
    print(f"🔍 [Queue] 待解構貼文隊列：{len(unprocessed)} 則")

    analyzer = AgenticAnalyzer()
    processed_count = 0
    noise_count = 0

    for post in unprocessed:
        print(f"\n--- 檢視貼文: {post['platform']} {post['author_handle']} ---")
        print(f"內文: {post['content'][:60]}...")

        # System 1 脊髓快篩
        if not analyzer.system1_filter(post["content"]):
            print("🛑 [System 1] 判定為無情報價值之閒聊/雜訊，已過濾。")
            mark_post_processed(post["id"])
            noise_count += 1
            continue

        print("⚡ [System 1] 偵測到高價值技術信號！啟動 System 2 深度解構...")
        # System 2 深度解構
        report_data = analyzer.system2_deep_extract(post)
        report_id = save_intel_report(report_data)
        mark_post_processed(post["id"])
        processed_count += 1
        print(f"✅ [System 2] 成功產出情報卡片 #{report_id}: {report_data['title']} ({report_data['urgency']})")

    # 4. 統計與同步至 Dashboard
    all_reports = get_all_intel_reports(limit=50)
    roster = get_roster_summary()
    sync_to_dashboard(all_reports, roster)

    print("\n" + "=" * 60)
    print(f"🎉 巡邏作業圓滿完成！")
    print(f"• 雜訊過濾: {noise_count} 則")
    print(f"• 新增情報卡片: {processed_count} 則")
    print(f"• 目前資料庫累計有效情報: {len(all_reports)} 則")
    print("=" * 60)

if __name__ == "__main__":
    run_patrol_cycle()
