import os
import sys
import json
import time
import requests
import random
from datetime import datetime

# Reconfigure stdout/stderr for Windows UTF-8 terminal
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
PRICES_DIR = os.path.join(DATA_DIR, "prices")
CACHE_DIR = os.path.join(DATA_DIR, "inst_cache")
TWSE_CACHE = os.path.join(CACHE_DIR, "twse")
TPEx_CACHE = os.path.join(CACHE_DIR, "tpex")

os.makedirs(TWSE_CACHE, exist_ok=True)
os.makedirs(TPEx_CACHE, exist_ok=True)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive"
    }

def clean_int(val_str):
    if not val_str:
        return 0
    try:
        # Remove commas and spaces
        val_str = val_str.replace(",", "").replace(" ", "").strip()
        return int(val_str)
    except Exception:
        return 0

def fetch_twse_date(date_str):
    """
    date_str: YYYY-MM-DD
    """
    formatted_date = date_str.replace("-", "")
    local_path = os.path.join(TWSE_CACHE, f"{formatted_date}.json")
    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={formatted_date}&selectType=ALL"
    print(f"Fetching TWSE for {date_str}...")
    
    for attempt in range(5):
        try:
            time.sleep(random.uniform(0.1, 0.4))  # Respect rate limit with slightly shorter delay
            resp = requests.get(url, headers=get_headers(), timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("stat") == "OK":
                    with open(local_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False)
                    return data
                elif "查詢無資料" in data.get("stat", "") or "No Data" in data.get("stat", ""):
                    # Cache empty results as well to prevent re-fetching non-trading days
                    empty_data = {"stat": "No Data", "fields": [], "data": []}
                    with open(local_path, "w", encoding="utf-8") as f:
                        json.dump(empty_data, f, ensure_ascii=False)
                    return empty_data
                else:
                    print(f"TWSE returned non-OK stat for {date_str}: {data.get('stat')}")
            elif resp.status_code == 429:
                sleep_time = 30 + attempt * 15
                print(f"TWSE returned 429 rate limit. Sleeping {sleep_time}s (attempt {attempt+1})...")
                time.sleep(sleep_time)
            else:
                print(f"TWSE returned HTTP {resp.status_code} for {date_str}")
        except Exception as e:
            print(f"Error fetching TWSE for {date_str}: {e}")
            time.sleep(5)
    return None

def fetch_tpex_date(date_str):
    """
    date_str: YYYY-MM-DD
    """
    parts = date_str.split("-")
    if len(parts) < 3:
        return None
    # Convert Gregorian year to Minguo year
    minguo_year = int(parts[0]) - 1911
    minguo_date = f"{minguo_year}/{parts[1]}/{parts[2]}"
    formatted_date = date_str.replace("-", "")
    
    local_path = os.path.join(TPEx_CACHE, f"{formatted_date}.json")
    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    url = f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={minguo_date}&s=0,asc"
    print(f"Fetching TPEx for {date_str}...")
    
    for attempt in range(5):
        try:
            time.sleep(random.uniform(0.1, 0.4))  # Respect rate limit with slightly shorter delay
            resp = requests.get(url, headers=get_headers(), timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("stat") == "OK" or "tables" in data:
                    with open(local_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False)
                    return data
                elif "查詢無資料" in data.get("stat", ""):
                    empty_data = {"stat": "No Data", "tables": []}
                    with open(local_path, "w", encoding="utf-8") as f:
                        json.dump(empty_data, f, ensure_ascii=False)
                    return empty_data
                else:
                    print(f"TPEx returned non-OK for {date_str}")
            elif resp.status_code == 429:
                sleep_time = 30 + attempt * 15
                print(f"TPEx returned 429 rate limit. Sleeping {sleep_time}s (attempt {attempt+1})...")
                time.sleep(sleep_time)
            else:
                print(f"TPEx returned HTTP {resp.status_code} for {date_str}")
        except Exception as e:
            print(f"Error fetching TPEx for {date_str}: {e}")
            time.sleep(5)
    return None

def parse_twse_data(twse_json, stock_codes):
    """
    Extracts foreign and trust net buying (in sheets) for our stock_codes.
    1 sheet (張) = 1000 shares (股).
    """
    results = {}
    if not twse_json or "data" not in twse_json or "fields" not in twse_json:
        return results

    fields = twse_json["fields"]
    data_rows = twse_json["data"]

    # Dynamically find column indexes
    code_idx = -1
    foreign_idx = -1
    trust_idx = -1

    for idx, field in enumerate(fields):
        # Clean clean string
        field_clean = field.replace(" ", "")
        if "證券代號" in field_clean or "代號" in field_clean:
            if code_idx == -1:
                code_idx = idx
        elif "外" in field_clean and "買賣超" in field_clean and "自營" not in field_clean:
            if foreign_idx == -1:
                foreign_idx = idx
        elif "投信" in field_clean and "買賣超" in field_clean:
            if trust_idx == -1:
                trust_idx = idx

    # Fallback to defaults if headers changed
    if code_idx == -1: code_idx = 0
    if foreign_idx == -1: foreign_idx = 4
    if trust_idx == -1: trust_idx = 10

    for row in data_rows:
        if len(row) > max(code_idx, foreign_idx, trust_idx):
            code = row[code_idx].strip()
            if code in stock_codes:
                foreign_shares = clean_int(row[foreign_idx])
                trust_shares = clean_int(row[trust_idx])
                # Convert to sheets (張)
                results[code] = {
                    "foreign_net": round(foreign_shares / 1000.0, 1),
                    "trust_net": round(trust_shares / 1000.0, 1)
                }
    return results

def parse_tpex_data(tpex_json, stock_codes):
    """
    Extracts foreign and trust net buying (in sheets) for our stock_codes.
    1 sheet (張) = 1000 shares (股).
    """
    results = {}
    if not tpex_json or "tables" not in tpex_json or len(tpex_json["tables"]) == 0:
        return results

    table = tpex_json["tables"][0]
    if "fields" not in table or "data" not in table:
        return results

    fields = table["fields"]
    data_rows = table["data"]

    # Dynamically find column indexes
    code_idx = -1
    foreign_idx = -1
    trust_idx = -1

    for idx, field in enumerate(fields):
        field_clean = field.replace(" ", "")
        if "代號" in field_clean or "證券代號" in field_clean:
            if code_idx == -1:
                code_idx = idx
        elif "外" in field_clean and "買賣超" in field_clean and "自營" not in field_clean:
            if foreign_idx == -1:
                foreign_idx = idx
        elif "投信" in field_clean and "買賣超" in field_clean:
            if trust_idx == -1:
                trust_idx = idx

    if code_idx == -1: code_idx = 0
    if foreign_idx == -1: foreign_idx = 4
    if trust_idx == -1: trust_idx = 10

    for row in data_rows:
        if len(row) > max(code_idx, foreign_idx, trust_idx):
            code = row[code_idx].strip()
            if code in stock_codes:
                foreign_shares = clean_int(row[foreign_idx])
                trust_shares = clean_int(row[trust_idx])
                results[code] = {
                    "foreign_net": round(foreign_shares / 1000.0, 1),
                    "trust_net": round(trust_shares / 1000.0, 1)
                }
    return results

def main():
    # Load unique stock codes
    parsed_bonds_path = os.path.join(DATA_DIR, "parsed_bonds.json")
    if not os.path.exists(parsed_bonds_path):
        print("parsed_bonds.json not found.")
        return

    with open(parsed_bonds_path, "r", encoding="utf-8") as f:
        bonds = json.load(f)

    stock_codes = set(bond["stock_code"] for bond in bonds if bond.get("stock_code"))
    print(f"Tracking {len(stock_codes)} unique stocks.")

    # Find all unique trading dates from price files
    all_dates = set()
    for code in stock_codes:
        price_file = os.path.join(PRICES_DIR, f"{code}.json")
        if os.path.exists(price_file):
            with open(price_file, "r", encoding="utf-8") as pf:
                prices = json.load(pf)
                for p in prices:
                    d = p["date"]
                    if "2024-11-01" <= d <= "2026-06-30":
                        all_dates.add(d)

    sorted_dates = sorted(list(all_dates))
    print(f"Compiled {len(sorted_dates)} trading dates from {sorted_dates[0]} to {sorted_dates[-1]}")

    # Load existing database
    db_path = os.path.join(DATA_DIR, "institutional_data.json")
    db = {}
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                db = json.load(f)
            print(f"Loaded {len(db)} existing dates from database.")
        except Exception:
            pass

    # Fetch and parse
    for idx, d in enumerate(sorted_dates):
        if d in db:
            continue

        print(f"[{idx+1}/{len(sorted_dates)}] Processing date {d}...")
        twse_json = fetch_twse_date(d)
        tpex_json = fetch_tpex_date(d)

        day_data = {}
        # Parse TWSE
        twse_res = parse_twse_data(twse_json, stock_codes)
        for c, v in twse_res.items():
            day_data[c] = v

        # Parse TPEx
        tpex_res = parse_tpex_data(tpex_json, stock_codes)
        for c, v in tpex_res.items():
            day_data[c] = v

        db[d] = day_data

        # Regularly save progress
        if (idx + 1) % 10 == 0:
            with open(db_path, "w", encoding="utf-8") as f:
                json.dump(db, f, ensure_ascii=False, indent=2)

    # Final save
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print(f"Successfully compiled and saved institutional data to {db_path}")

if __name__ == "__main__":
    main()
