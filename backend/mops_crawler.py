import os
import sys
import json
import csv
import io
import urllib.error
import urllib.request
import re
from datetime import datetime

# Reconfigure stdout/stderr for Windows UTF-8 terminal
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
RAW_PATH = os.path.join(DATA_DIR, "mops_raw_filtered.json")

os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

KEYWORDS = ["私募", "公司債", "庫藏股", "收購", "訂價", "生效", "買回", "公告"]

def parse_date(date_val):
    """
    Standardize date to YYYY-MM-DD.
    Handles '20260616', '1150616', '115/06/16', '2026-06-16'
    """
    if not date_val:
        return ""
    date_val = str(date_val).strip().replace("/", "").replace("-", "")
    
    # Check if Minguo (e.g., 1150616, length 7)
    if len(date_val) == 7 and date_val.isdigit():
        try:
            year = int(date_val[:3]) + 1911
            month = int(date_val[3:5])
            day = int(date_val[5:7])
            return f"{year}-{month:02d}-{day:02d}"
        except ValueError:
            pass
            
    # Check if Gregorian (e.g., 20260616, length 8)
    if len(date_val) == 8 and date_val.isdigit():
        try:
            year = int(date_val[:4])
            month = int(date_val[4:6])
            day = int(date_val[6:8])
            return f"{year}-{month:02d}-{day:02d}"
        except ValueError:
            pass
            
    return date_val

def save_raw_dataset(source_folder, filename, content):
    try:
        today_dir = os.path.join("D:\\dataset", source_folder, datetime.today().strftime("%Y%m%d"))
        os.makedirs(today_dir, exist_ok=True)
        file_path = os.path.join(today_dir, filename)
        mode = "w" if isinstance(content, str) else "wb"
        encoding = "utf-8" if isinstance(content, str) else None
        with open(file_path, mode, encoding=encoding) as f:
            f.write(content)
        print(f"Saved raw dataset to {file_path}")
    except Exception as e:
        print(f"Failed to save raw dataset to D:\\dataset: {e}")


def http_get_text(url):
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return resp.getcode(), raw.decode("utf-8-sig", errors="replace")

def fetch_listed_json():
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"
    print("Fetching Listed JSON from TWSE OpenAPI...")
    try:
        status, text = http_get_text(url)
        if status == 200:
            # Save original raw data
            save_raw_dataset("mops", "t187ap04_L.json", text)
            
            records = json.loads(text)
            standardized = []
            for r in records:
                standardized.append({
                    "stock_code": r.get("公司代號", "").strip(),
                    "company_name": r.get("公司名稱", "").strip(),
                    "date": parse_date(r.get("發言日期", "")),
                    "time": r.get("發言時間", "").strip(),
                    "subject": r.get("主旨", "").strip(),
                    "content": r.get("說明", "").strip()
                })
            return standardized
        else:
            print(f"Failed to fetch Listed JSON: HTTP {status}")
    except Exception as e:
        print(f"Error fetching Listed JSON: {e}")
    return []

def fetch_otc_csv():
    url = "https://mopsfin.twse.com.tw/opendata/t187ap04_O.csv"
    print("Fetching OTC CSV from MOPS...")
    try:
        status, text = http_get_text(url)
        if status == 200:
            # Save original raw data
            save_raw_dataset("mops", "t187ap04_O.csv", text)
            
            f = io.StringIO(text)
            reader = csv.DictReader(f)
            standardized = []
            for r in reader:
                standardized.append({
                    "stock_code": r.get("公司代號", "").strip(),
                    "company_name": r.get("公司名稱", "").strip(),
                    "date": parse_date(r.get("發言日期", "")),
                    "time": r.get("發言時間", "").strip(),
                    "subject": r.get("主旨", "").strip(),
                    "content": r.get("說明", "").strip()
                })
            return standardized
        else:
            print(f"Failed to fetch OTC CSV: HTTP {status}")
    except Exception as e:
        print(f"Error fetching OTC CSV: {e}")
    return []

def filter_records(records):
    filtered = []
    for r in records:
        subj = r["subject"]
        cont = r["content"]
        
        found = False
        for kw in KEYWORDS:
            if kw in subj or kw in cont:
                found = True
                break
        if found:
            filtered.append(r)
    return filtered

def main():
    listed = fetch_listed_json()
    print(f"Fetched {len(listed)} Listed records.")
    
    otc = fetch_otc_csv()
    print(f"Fetched {len(otc)} OTC records.")
    
    all_records = listed + otc
    print(f"Combined count: {len(all_records)} records.")
    
    filtered = filter_records(all_records)
    print(f"Filtered count (matching event keywords): {len(filtered)} records.")
    
    with open(RAW_PATH, "w", encoding="utf-8") as f:
        json.dump(filtered, f, ensure_ascii=False, indent=2)
        
    print(f"Saved filtered MOPS records to {RAW_PATH}")

if __name__ == "__main__":
    main()
