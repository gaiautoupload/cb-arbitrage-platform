import os
import sys
import re
import json
import requests
from bs4 import BeautifulSoup

# Reconfigure stdout/stderr for Windows UTF-8 terminal
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
CACHE_DIR = os.path.join(DATA_DIR, "html_cache")

VLLM_API_BASE = "https://vllm-a5000.iii-ei-stack.com/v1"
VLLM_MODEL = "cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit"

def clean_text(text):
    if not text:
        return ""
    # Remove extra spaces and newlines
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def minguo_to_ad(minguo_str):
    """
    Convert Minguo date (e.g. '115年2月3日' or '115/01/28') to 'YYYY-MM-DD'
    """
    if not minguo_str:
        return None
    # Handle '115年2月3日'
    match = re.search(r'(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日', minguo_str)
    if match:
        year = int(match.group(1)) + 1911
        month = int(match.group(2))
        day = int(match.group(3))
        return f"{year}-{month:02d}-{day:02d}"
    
    # Handle '115/01/28'
    match = re.search(r'(\d+)/(\d+)/(\d+)', minguo_str)
    if match:
        year = int(match.group(1)) + 1911
        month = int(match.group(2))
        day = int(match.group(3))
        return f"{year}-{month:02d}-{day:02d}"
        
    return None

def extract_with_llm(html_text):
    """
    Use the user-provided Qwen vLLM to extract JSON structure if regex fails or is incomplete.
    """
    # Keep only first 4000 chars of text to avoid context bloat
    text_snippet = html_text[:6000]
    
    prompt = f"""
Analyze the following corporate bond announcement from the Taiwan Taipei Exchange (TPEx) and extract the structured details.
Return ONLY a valid JSON object. Do not include markdown formatting, backticks, or explanation.

Text:
{text_snippet}

JSON format to return:
{{
  "company_name": "公司完整名稱, e.g. 騰輝電子國際集團股份有限公司",
  "bond_name": "債券完整名稱, e.g. 騰輝電子國際集團股份有限公司中華民國境內第二次無擔保轉換公司債",
  "cb_code": "5位數代碼, e.g. 66722",
  "short_name": "簡稱, e.g. 騰輝電子二KY",
  "announcement_date_minguo": "發文日期 Minguo format, e.g. 115年1月28日 or 115/01/28",
  "issue_date_minguo": "發行日/開始買賣日 Minguo format, e.g. 115年2月3日",
  "maturity_date_minguo": "到期日 Minguo format, e.g. 120年2月3日",
  "issue_amount": "發行總額, e.g. 新台幣5億元整"
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
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            # Clean possible markdown wrap
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            content = content.strip()
            return json.loads(content)
    except Exception as e:
        print(f"vLLM extraction failed: {e}")
    return None

def parse_html_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        html = f.read()
        
    soup = BeautifulSoup(html, "lxml")
    full_text = soup.get_text()
    
    # Try regex parsing first
    company_name = None
    bond_name = None
    cb_code = None
    short_name = None
    issue_date_minguo = None
    maturity_date_minguo = None
    issue_amount = None
    announcement_date_minguo = None
    
    # Extract announcement date
    date_div = soup.find(id="發文日期")
    if date_div:
        announcement_date_minguo = clean_text(date_div.get_text().replace("發文日期：", ""))
    else:
        # Fallback regex
        date_match = re.search(r"發文日期：中華民國([\d]+年[\d]+月[\d]+日)", full_text)
        if date_match:
            announcement_date_minguo = date_match.group(1)
            
    # Extract from list items
    full_text_clean = clean_text(full_text)
    
    comp_match = re.search(r"發行公司名稱\s*[:：]\s*(.*?)[。，\n;\s]", full_text_clean)
    if comp_match:
        company_name = comp_match.group(1).strip()
        
    bond_match = re.search(r"債券名稱\s*[:：]\s*(.*?)[。，\n;\s]", full_text_clean)
    if bond_match:
        bond_name = bond_match.group(1).strip()
        
    code_match = re.search(r"代碼\s*[:：]\s*(\d+)", full_text_clean)
    if code_match:
        cb_code = code_match.group(1).strip()
        
    short_match = re.search(r"簡稱\s*[:：]\s*(.*?)[。，\n;\s]", full_text_clean)
    if short_match:
        short_name = short_match.group(1).strip()
        
    issue_match = re.search(r"發行日\s*[:：]\s*(.*?)[。，\n;\s]", full_text_clean)
    if issue_match:
        issue_date_minguo = issue_match.group(1).strip()
        
    maturity_match = re.search(r"到期日\s*[:：]\s*(.*?)[。，\n;\s]", full_text_clean)
    if maturity_match:
        maturity_date_minguo = maturity_match.group(1).strip()
        
    amount_match = re.search(r"發行總面額\s*[:：]\s*(.*?)[。，\n;\s]", full_text_clean)
    if amount_match:
        issue_amount = amount_match.group(1).strip()

    # If any crucial field (company_name, cb_code, issue_date_minguo) is missing, fall back to LLM
    if not (company_name and cb_code and issue_date_minguo):
        print(f"Regex missing details for {os.path.basename(file_path)}. Trying vLLM...")
        llm_data = extract_with_llm(full_text)
        if llm_data:
            company_name = company_name or llm_data.get("company_name")
            bond_name = bond_name or llm_data.get("bond_name")
            cb_code = cb_code or llm_data.get("cb_code")
            short_name = short_name or llm_data.get("short_name")
            announcement_date_minguo = announcement_date_minguo or llm_data.get("announcement_date_minguo")
            issue_date_minguo = issue_date_minguo or llm_data.get("issue_date_minguo")
            maturity_date_minguo = maturity_date_minguo or llm_data.get("maturity_date_minguo")
            issue_amount = issue_amount or llm_data.get("issue_amount")
            
    # Clean stock code (first 4 digits of CB code)
    stock_code = None
    if cb_code and len(cb_code) >= 4:
        # Taiwan convertible bonds have codes like 35872 (閎康二), underlying is 3587
        stock_code = cb_code[:4]
        
    return {
        "file_id": os.path.splitext(os.path.basename(file_path))[0],
        "company_name": company_name,
        "bond_name": bond_name,
        "cb_code": cb_code,
        "stock_code": stock_code,
        "short_name": short_name,
        "announcement_date_minguo": announcement_date_minguo,
        "announcement_date": minguo_to_ad(announcement_date_minguo),
        "issue_date_minguo": issue_date_minguo,
        "issue_date": minguo_to_ad(issue_date_minguo),
        "maturity_date_minguo": maturity_date_minguo,
        "maturity_date": minguo_to_ad(maturity_date_minguo),
        "issue_amount": issue_amount
    }

def main():
    parsed_bonds = []
    
    if not os.path.exists(CACHE_DIR):
        print("No cache directory found. Please run downloader.py first.")
        return
        
    files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".html")]
    print(f"Found {len(files)} cached HTML files to parse.")
    
    for idx, f in enumerate(files):
        file_path = os.path.join(CACHE_DIR, f)
        try:
            bond_info = parse_html_file(file_path)
            # We only keep files that have a valid stock code
            if bond_info["stock_code"] and bond_info["stock_code"].isdigit():
                parsed_bonds.append(bond_info)
                print(f"[{idx+1}/{len(files)}] Parsed successfully: {bond_info['company_name']} ({bond_info['stock_code']})")
            else:
                print(f"[{idx+1}/{len(files)}] Skipped: {bond_info.get('company_name') or f} (No valid stock ticker)")
        except Exception as e:
            print(f"Error parsing file {f}: {e}")
            
    # Save parsed data to JSON
    output_path = os.path.join(DATA_DIR, "parsed_bonds.json")
    with open(output_path, "w", encoding="utf-8") as out_f:
        json.dump(parsed_bonds, out_f, ensure_ascii=False, indent=2)
        
    print(f"Saved {len(parsed_bonds)} structured bond records to {output_path}")

if __name__ == "__main__":
    main()
