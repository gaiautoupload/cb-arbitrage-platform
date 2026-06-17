import os
import json
import time
import yfinance as yf
import sys

# Reconfigure stdout/stderr for Windows UTF-8 terminal
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
METADATA_PATH = os.path.join(DATA_DIR, "stock_metadata.json")
SHARES_PATH = os.path.join(DATA_DIR, "shares_outstanding.json")

def main():
    if not os.path.exists(METADATA_PATH):
        print("stock_metadata.json not found.")
        return

    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # Load existing shares database if any to prevent redundant API calls
    shares_db = {}
    if os.path.exists(SHARES_PATH):
        try:
            with open(SHARES_PATH, "r", encoding="utf-8") as f:
                shares_db = json.load(f)
            print(f"Loaded {len(shares_db)} existing shares records.")
        except Exception:
            pass

    print(f"Total tickers to fetch: {len(meta)}")
    
    updated = False
    for code, info in meta.items():
        if code in shares_db and shares_db[code] > 0:
            continue
            
        ticker = info["ticker"]
        print(f"Fetching shares outstanding for {ticker} ({code})...")
        try:
            ticker_obj = yf.Ticker(ticker)
            # Retrieve shares outstanding
            shares = ticker_obj.info.get("sharesOutstanding")
            if shares:
                shares_db[code] = shares
                updated = True
                print(f" -> {shares} shares.")
            else:
                # Fallback estimate (e.g. average for mid-cap)
                shares_db[code] = 100000000 # 100M shares / 10M NTD capital proxy
                print(f" -> Not found. Using 100M shares default.")
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            shares_db[code] = 100000000
            
        time.sleep(0.5)

    with open(SHARES_PATH, "w", encoding="utf-8") as f:
        json.dump(shares_db, f, ensure_ascii=False, indent=2)
    print(f"Successfully saved shares outstanding to {SHARES_PATH}")

if __name__ == "__main__":
    main()
