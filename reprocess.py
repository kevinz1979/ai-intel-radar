import os
import sys
import json
import sqlite3

# 設定 Windows 控制台標準輸出為 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from storage import (
    get_connection,
    save_intel_report,
    get_all_intel_reports,
    get_roster_summary
)
from analyzer import AgenticAnalyzer
from runner import sync_to_dashboard

def reprocess_all_reports():
    print("🔄 開始重新解構既有貼文...")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM raw_posts ORDER BY id ASC")
    rows = cursor.fetchall()
    
    analyzer = AgenticAnalyzer()
    updated = 0
    filtered = 0
    
    for row in rows:
        post = dict(row)
        content = post.get("content", "")
        # System 1 快篩
        if not analyzer.system1_filter(content):
            filtered += 1
            continue
            
        report_data = analyzer.system2_deep_extract(post)
        report_id = save_intel_report(report_data)
        updated += 1
        print(f"✅ [重構完成 #{report_id}] {report_data['platform']} {report_data['author']}: {report_data['title'][:40]}...")

    conn.close()
    
    print(f"\n🎉 重新解構作業結束：共更新 {updated} 則情報卡片（過濾閒聊雜訊 {filtered} 則）")
    
    # 統計並同步寫入 index.html
    all_reports = get_all_intel_reports(limit=50)
    roster = get_roster_summary()
    sync_to_dashboard(all_reports, roster)
    print("🚀 Web App 儀控表已同步重新渲染完成！")

if __name__ == "__main__":
    reprocess_all_reports()
