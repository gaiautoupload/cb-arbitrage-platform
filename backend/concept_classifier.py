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
CONCEPTS_PATH = os.path.join(DATA_DIR, "concepts_metadata.json")

VLLM_API_BASE = "https://vllm-a5000.iii-ei-stack.com/v1"
VLLM_MODEL = "cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit"

def get_concept_from_llm(stock_code, company_name):
    prompt = f"""
請分析台灣上市/上櫃公司：{company_name} (代號: {stock_code})。
回傳其所屬的「產業族群」與「概念股題材」（例如：AI伺服器, 半導體, 記憶體, 生技, 綠能, 網通, 車用電子, 營建等）。
請嚴格以 JSON 格式回傳，不要包含任何 markdown 格式的 ``` 或額外說明。

JSON 格式要求：
{{
  "sector": "單一主要產業族群名稱 (例如: 記憶體/半導體/生技醫療/電腦週邊)",
  "concepts": ["概念標籤1", "概念標籤2", "概念標籤3"],
  "description": "一兩句描述公司主營業務或題材"
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
        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code == 200:
            resp.encoding = 'utf-8'
            resp_json = resp.json()
            content = resp_json["choices"][0]["message"]["content"]
            # Clean possible markdown wrap
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            content = content.strip()
            # Escape invalid backslashes
            content_clean = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', content)
            return json.loads(content_clean)
    except Exception as e:
        print(f"Error fetching concepts for {stock_code}: {e}")
    return None

def main():
    parsed_bonds_path = os.path.join(DATA_DIR, "parsed_bonds.json")
    if not os.path.exists(parsed_bonds_path):
        print("parsed_bonds.json not found. Please run parser.py first.")
        return

    with open(parsed_bonds_path, "r", encoding="utf-8") as f:
        bonds = json.load(f)

    # Get unique stocks
    unique_stocks = {}
    for bond in bonds:
        code = bond["stock_code"]
        name = bond["company_name"]
        if code and code not in unique_stocks:
            unique_stocks[code] = name

    # Load existing concepts if exists
    concepts = {}
    if os.path.exists(CONCEPTS_PATH):
        try:
            with open(CONCEPTS_PATH, "r", encoding="utf-8") as f:
                concepts = json.load(f)
            print(f"Loaded {len(concepts)} existing concepts from cache.")
        except Exception as e:
            print(f"Error reading {CONCEPTS_PATH}: {e}")

    updated = False
    for idx, (code, name) in enumerate(unique_stocks.items()):
        # Query again if the sector is missing, or is default "其他"
        if code in concepts and concepts[code].get("sector") and concepts[code].get("sector") != "其他":
            continue

        print(f"[{idx+1}/{len(unique_stocks)}] Querying concepts for {name} ({code})...")
        res = get_concept_from_llm(code, name)
        if res:
            concepts[code] = res
            updated = True
            print(f"  Result: Sector={res['sector']}, Concepts={res['concepts']}")
        else:
            # Fallback
            concepts[code] = {
                "sector": "其他",
                "concepts": ["概念股"],
                "description": "台灣上市櫃公司"
            }
            updated = True
        time.sleep(0.5)

    if updated or not os.path.exists(CONCEPTS_PATH):
        with open(CONCEPTS_PATH, "w", encoding="utf-8") as f:
            json.dump(concepts, f, ensure_ascii=False, indent=2)
        print(f"Saved concepts metadata to {CONCEPTS_PATH}")
    else:
        print("Concepts cache is up-to-date.")

if __name__ == "__main__":
    main()
