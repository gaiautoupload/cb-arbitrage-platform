import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
PRICES_DIR = os.path.join(DATA_DIR, "prices")

def test_strategy():
    analysis = json.load(open(os.path.join(DATA_DIR, "analysis_results.json"), encoding="utf-8"))
    bonds = analysis["bonds_analysis"]
    
    price_cache = {}
    for b in bonds:
        code = b["ticker"]
        p_path = os.path.join(PRICES_DIR, f"{code}.json")
        if os.path.exists(p_path):
            price_cache[code] = json.load(open(p_path, encoding="utf-8"))
            
    for entry_offset in [-15, -14, -13]:
        trades = []
        for b in bonds:
            if b.get("foreign_accum_10d", 0) < 2000:
                continue
            if b.get("trust_accum_10d", 0) < 0:
                continue
            code = b["ticker"]
            prices = price_cache.get(code)
            if not prices:
                continue
                
            # Find issue date index
            iss_idx = None
            for idx, p in enumerate(prices):
                if p["date"] >= b["issue_date"]:
                    iss_idx = idx
                    break
            if iss_idx is None:
                continue
                
            buy_idx = iss_idx + entry_offset
            sell_idx = iss_idx + 19
            
            if buy_idx >= 0 and sell_idx < len(prices):
                buy_p = prices[buy_idx]["open"]
                sell_p = prices[sell_idx]["close"]
                trades.append((sell_p - buy_p) / buy_p * 100)
                
        win_rate = sum(1 for r in trades if r > 0) / len(trades) * 100 if trades else 0
        avg_ret = sum(trades) / len(trades) if trades else 0
        print(f"Buy at T{entry_offset} (Check at T{entry_offset-1}): Trades={len(trades)} | WinRate={win_rate:.1f}% | AvgReturn={avg_ret:+.2f}%")

if __name__ == "__main__":
    test_strategy()
