import os
import json
import time
import yfinance as yf
import pandas as pd

# Base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
PRICES_DIR = os.path.join(DATA_DIR, "prices")

os.makedirs(PRICES_DIR, exist_ok=True)

def fetch_stock_prices(stock_code, start_date="2024-01-01", end_date="2026-07-01"):
    """
    Fetch historical prices for a Taiwan stock ticker.
    We try .TWO first (OTC/TPEx), and if that yields no data, we try .TW (TWSE).
    """
    suffixes = [".TWO", ".TW"]
    df = None
    successful_suffix = None
    
    for suffix in suffixes:
        ticker = f"{stock_code}{suffix}"
        print(f"Trying ticker {ticker}...")
        try:
            # We fetch daily data
            ticker_obj = yf.Ticker(ticker)
            data = ticker_obj.history(start=start_date, end=end_date)
            if not data.empty and len(data) > 5:
                df = data
                successful_suffix = suffix
                break
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            
    if df is not None:
        # Convert index (Datetime) to string YYYY-MM-DD
        df.index = df.index.strftime('%Y-%m-%d')
        # Format the dataframe into a dict/JSON list
        records = []
        for date, row in df.iterrows():
            records.append({
                "date": date,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"])
            })
        return records, successful_suffix
    else:
        print(f"Failed to fetch data for stock code {stock_code}")
        return None, None

def main():
    parsed_bonds_path = os.path.join(DATA_DIR, "parsed_bonds.json")
    if not os.path.exists(parsed_bonds_path):
        print("parsed_bonds.json not found. Run parser.py first.")
        return
        
    with open(parsed_bonds_path, "r", encoding="utf-8") as f:
        bonds = json.load(f)
        
    # Get unique stock codes to avoid redundant fetches
    stock_codes = sorted(list(set(bond["stock_code"] for bond in bonds if bond.get("stock_code"))))
    print(f"Unique stock codes to fetch: {stock_codes}")
    
    stock_meta = {}
    
    for idx, code in enumerate(stock_codes):
        print(f"[{idx+1}/{len(stock_codes)}] Fetching prices for {code}...")
        prices, suffix = fetch_stock_prices(code)
        if prices:
            # Save prices to a separate JSON
            price_file = os.path.join(PRICES_DIR, f"{code}.json")
            with open(price_file, "w", encoding="utf-8") as pf:
                json.dump(prices, pf, ensure_ascii=False, indent=2)
            print(f"Successfully saved {len(prices)} price bars to {price_file}")
            stock_meta[code] = {
                "ticker": f"{code}{suffix}",
                "data_points": len(prices)
            }
            # Short sleep to respect API rate limits
            time.sleep(1.0)
        else:
            print(f"Could not retrieve prices for {code}")
            
    # Save stock metadata
    meta_path = os.path.join(DATA_DIR, "stock_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as mf:
        json.dump(stock_meta, mf, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
