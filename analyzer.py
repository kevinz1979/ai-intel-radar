import os
import json
import re
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

# 嘗試載入 google-genai SDK
try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

class IntelReportSchema(BaseModel):
    title: str = Field(description="簡明有力的繁中情報標題，包含核心技術或主角")
    urgency: str = Field(description="P0 (重大突破/突破性釋出), P1 (實用工具/評測), P2 (觀點爭辯/社群討論)")
    summary: str = Field(description="第一層：30 秒速讀摘要，客觀事實陳述")
    core_thesis: str = Field(description="第二層：核心技術架構或底層邏輯解析")
    pro_view: str = Field(description="第三層：社群支持/樂觀派觀點")
    con_view: str = Field(description="第三層：社群質疑/保守派/潛在缺陷觀點")
    has_time_gap: bool = Field(description="是否屬於 X 領先 Threads 的時間差情報")
    gap_hours: str = Field(description="預估時差（例如 '6 小時'，若無則填 '0 小時'）")
    threads_status: str = Field(description="Threads 繁中圈現況分析")
    links: list[dict] = Field(description="提取的關鍵連結，每項包含 name 與 url 與 type")
    actionable: str = Field(description="第四層：情報轉化建議，工程師或創作者的具體行動")

class AgenticAnalyzer:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.client = None
        if HAS_GENAI and self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[Analyzer] Gemini Client 初始化失敗: {e}")

    def system1_filter(self, content: str) -> bool:
        """
        System 1 脊髓反射：快速過濾日常閒聊、無實質情報價值的雜訊
        """
        if len(content.strip()) < 20:
            return False
            
        noise_patterns = [
            r"^(早安|晚安|吃飽沒|週末愉快)",
            r"抽獎.*轉發.*關注",
            r"^http\S+$", # 單純只有連結無文字
        ]
        for p in noise_patterns:
            if re.search(p, content, re.IGNORECASE):
                return False

        # 檢測是否有高價值信號詞
        tech_signals = [
            "ai", "llm", "model", "paper", "github", "release", "benchmark",
            "eval", "agent", "prompt", "code", "cursor", "claude", "gemini",
            "deepseek", "llama", "架構", "開源", "實測", "落地", "工作流"
        ]
        has_signal = any(s in content.lower() for s in tech_signals)
        return has_signal

    def system2_deep_extract(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """
        System 2 深度解構：透過 LLM 提煉 4 層情報結構
        """
        content = post["content"]
        author = post["author_handle"]
        platform = post["platform"]

        # 若有 Gemini API Key，呼叫 Gemini 進行結構化提煉
        if self.client:
            try:
                prompt = f"""
你是一名資深科技情報分析官。請針對以下來自 {platform} 的 AI KOL ({author}) 原始貼文進行「層層剝開重點」的深度解構：
---
原始內容：
{content}
---
請以繁體中文 (台灣習慣用語) 進行結構化提煉，並給出精闢客觀的分析。
"""
                response = self.client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=IntelReportSchema,
                        temperature=0.2
                    )
                )
                data = json.loads(response.text)
                return {
                    "raw_post_id": post["id"],
                    "title": data["title"],
                    "platform": platform,
                    "author": author,
                    "author_role": post.get("author_name") or "AI 領域專家",
                    "urgency": data["urgency"],
                    "timestamp_str": "剛剛",
                    "likes": post.get("likes", 0),
                    "summary": data["summary"],
                    "core_thesis": data["core_thesis"],
                    "links": data.get("links", []),
                    "community_views": {
                        "pro": data["pro_view"],
                        "con": data["con_view"]
                    },
                    "arbitrage": {
                        "hasTimeGap": data["has_time_gap"],
                        "gapHours": data["gap_hours"],
                        "threadsStatus": data["threads_status"]
                    },
                    "actionable": data["actionable"]
                }
            except Exception as e:
                print(f"[Analyzer] LLM 呼叫異常，切換至啟發式備援解構: {e}")

        # 啟發式規則備援 (無 API Key 或網路異常時的容錯處理)
        return self._heuristic_fallback_extract(post)

    def _heuristic_fallback_extract(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """啟發式智慧解析（確保任何環境下管線皆能端到端運作）"""
        clean_content = " ".join(content.split())
        first_line = clean_content[:55]
        links = []
        urls = re.findall(r"https?://[^\s]+", content)
        for u in urls:
            ltype = "github" if "github.com" in u else ("paper" if "arxiv.org" in u else "link")
            links.append({"name": "延伸連結", "url": u, "type": ltype})

        is_p0 = any(k in content.lower() for k in ["release", "breakthrough", "v2", "v3", "重磅", "開源"])
        urgency = "P0" if is_p0 else ("P1" if "實測" in content or "tool" in content.lower() else "P2")

        return {
            "raw_post_id": post["id"],
            "title": f"【社群熱議】{first_line}...",
            "platform": post["platform"],
            "author": post["author_handle"],
            "author_role": post.get("author_name", "AI 社群專家"),
            "urgency": urgency,
            "timestamp_str": "剛剛",
            "likes": post.get("likes", 0),
            "summary": f"作者分享關於：{clean_content[:140]}...",
            "core_thesis": "探討技術落地架構之效能瓶頸與社群實務最佳實踐。",
            "links": links if links else [{"name": "原始貼文", "url": "#", "type": "post"}],
            "community_views": {
                "pro": "大幅提升原型探索與日常編碼自動化生產力。",
                "con": "需留意邊緣情況下的潛在幻覺與維護負擔。"
            },
            "arbitrage": {
                "hasTimeGap": (post["platform"] == "X"),
                "gapHours": "4 小時" if post["platform"] == "X" else "0 小時",
                "threadsStatus": "X 領先釋出，Threads 繁中圈正逐步跟進中。" if post["platform"] == "X" else "繁中在地即時共鳴討論。"
            },
            "actionable": "建議密切追蹤相關 GitHub 專案或在沙盒環境進行驗證。"
        }
