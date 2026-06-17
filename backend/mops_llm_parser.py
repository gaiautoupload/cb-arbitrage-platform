import os
import sys
import json
import re
import requests
import time

# Reconfigure stdout/stderr for Windows UTF-8 terminal
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
RAW_PATH = os.path.join(DATA_DIR, "mops_raw_filtered.json")
WIKI_PATH = os.path.join(DATA_DIR, "mops_wiki_db.json")

VLLM_API_BASE = "https://vllm-a5000.iii-ei-stack.com/v1"
VLLM_MODEL = "cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit"

def parse_announcement_with_llm(subj, content):
    prompt = f"""
分析以下台灣股市重大訊息公告，將其結構化並提取關鍵策略特徵。
回傳必須嚴格為單一 JSON 物件，請勿包含 markdown ``` 格式或任何額外字元。
請不要在 JSON 內部使用任何未轉義的反斜線 (\\)。如果必須提到 DRAM 或其他術語，直接寫單字，不要在前面加反斜線。

主旨：{subj}
說明內容：{content[:4000]}

JSON 結構要求：
{{
  "event_type": "CB_ISSUANCE (可轉債) | PRIVATE_PLACEMENT (私募) | BUYBACK (庫藏股) | TENDER_OFFER (公開收購) | OTHER (其他)",
  "stage": "BOARD_RESOLUTION (董事會決議) | EFFECTIVE (申報生效/核准) | PRICING (訂價公告) | LISTING (掛牌/買賣開始) | N/A (不適用)",
  "wiki_details": {{
    "amount": "募集金額或股數或張數 (例如: 新台幣10億元 / 20,000張 / 5,000,000股，若無則為 null)",
    "price": "轉換價或認購價或收購價 (例如: 120.5元，必須為純數字或可轉化為數字的字串，若無則為 null)",
    "partners": ["如果是私募，引進的戰略股東、認購對象，例如: ['聯發科', '台積電']，若無或非私募則為空陣列 []"],
    "buyback_range": ["如果是庫藏股，買回價格區間，格式為 [下限, 上限]，例如: [50.0, 80.0]，若無則為空陣列 []"]
  }},
  "sentiment": "BULLISH (偏多) | NEUTRAL (中性) | BEARISH (偏空)",
  "summary": "一句話說明本事件之交易策略含意 (例如: 聯發科私募入股利多、護盤動機強、有拉抬訂價動機)"
}}
"""
    try:
        url = f"{VLLM_API_BASE}/chat/completions"
        payload = {
            "model": VLLM_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        resp = requests.post(url, json=payload, timeout=25)
        if resp.status_code == 200:
            resp.encoding = 'utf-8'
            content_str = resp.json()["choices"][0]["message"]["content"]
            content_str = re.sub(r'^```json\s*', '', content_str)
            content_str = re.sub(r'\s*```$', '', content_str)
            content_str = content_str.strip()
            # Escape invalid backslashes
            content_clean = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', content_str)
            return json.loads(content_clean)
    except Exception as e:
        print(f"Error parsing announcement '{subj[:20]}...': {e}")
    return None

def main():
    if not os.path.exists(RAW_PATH):
        print("mops_raw_filtered.json not found. Run mops_crawler.py first.")
        return
        
    with open(RAW_PATH, "r", encoding="utf-8") as f:
        raw_items = json.load(f)
        
    wiki_db = []
    if os.path.exists(WIKI_PATH):
        try:
            with open(WIKI_PATH, "r", encoding="utf-8") as f:
                wiki_db = json.load(f)
            print(f"Loaded {len(wiki_db)} parsed Wiki items from cache.")
        except Exception:
            pass

    # Create a unique key using code + date + subject to avoid duplicate parses
    parsed_keys = set(f"{x['stock_code']}_{x['date']}_{x['event_title']}" for x in wiki_db)
    
    updated = False
    newly_parsed = 0
    
    # We only process up to 80 records per run to respect time and vLLM capacity, 
    # but since the task runs in background we can process all.
    for idx, item in enumerate(raw_items):
        key = f"{item['stock_code']}_{item['date']}_{item['subject']}"
        if key in parsed_keys:
            continue
            
        print(f"[{idx+1}/{len(raw_items)}] Querying Qwen for {item['company_name']} ({item['stock_code']}): {item['subject'][:30]}...")
        res = parse_announcement_with_llm(item['subject'], item['content'])
        if res:
            wiki_item = {
                "date": item["date"],
                "time": item["time"],
                "stock_code": item["stock_code"],
                "company_name": item["company_name"],
                "event_title": item["subject"],
                "event_type": res.get("event_type", "OTHER"),
                "stage": res.get("stage", "N/A"),
                "wiki_details": res.get("wiki_details", {}),
                "sentiment": res.get("sentiment", "NEUTRAL"),
                "summary": res.get("summary", "")
            }
            wiki_db.append(wiki_item)
            parsed_keys.add(key)
            updated = True
            newly_parsed += 1
            print(f"  Result: EventType={wiki_item['event_type']}, Stage={wiki_item['stage']}, Sentiment={wiki_item['sentiment']}")
        else:
            print(f"  Skipped (LLM parsing failed)")
            
        time.sleep(0.5)
        # Regularly save progress
        if newly_parsed % 5 == 0 and updated:
            with open(WIKI_PATH, "w", encoding="utf-8") as f:
                json.dump(wiki_db, f, ensure_ascii=False, indent=2)

    if updated or not os.path.exists(WIKI_PATH):
        with open(WIKI_PATH, "w", encoding="utf-8") as f:
            json.dump(wiki_db, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(wiki_db)} structured Wiki items to {WIKI_PATH}")
    else:
        print("Wiki database is already up-to-date.")

if __name__ == "__main__":
    main()
