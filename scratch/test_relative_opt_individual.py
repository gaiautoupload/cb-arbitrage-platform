import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
PRICES_DIR = os.path.join(DATA_DIR, "prices")

def main():
    analysis = json.load(open(os.path.join(DATA_DIR, "analysis_results.json"), encoding="utf-8"))
    bonds = analysis["bonds_analysis"]
    shares_db = json.load(open(os.path.join(DATA_DIR, "shares_outstanding.json"), encoding="utf-8"))
    
    price_cache = {}
    for b in bonds:
        code = b["ticker"]
        p_path = os.path.join(PRICES_DIR, f"{code}.json")
        if os.path.exists(p_path):
            price_cache[code] = json.load(open(p_path, encoding="utf-8"))

    # Test separately
    for name, condition_fn in [
        ("Foreign > 2000 + 0.5% Cap", lambda f, t, cap: f > 2000 and (f * 1000) / cap * 100 > 0.5),
        ("Trust > 2000 + 0.5% Cap", lambda f, t, cap: t > 2000 and (t * 1000) / cap * 100 > 0.5),
        ("Foreign > 2000 + 2.0x Vol", lambda f, t, mv: f > 2000 and f > mv * 2.0),
        ("Trust > 2000 + 2.0x Vol", lambda f, t, mv: t > 2000 and t > mv * 2.0)
    ]:
        trades = []
        for b in bonds:
            code = b["ticker"]
            prices = price_cache.get(code)
            if not prices: continue
            
            shares_outstanding = shares_db.get(code, 100000000)
            iss_idx = next((i for i, p in enumerate(prices) if p["date"] >= b["issue_date"]), None)
            if iss_idx is None: continue
            
            buy_idx = iss_idx - 15
            sell_idx = iss_idx + 19
            if buy_idx < 0 or sell_idx >= len(prices): continue
            
            check_idx = buy_idx - 1
            ma_start_idx = max(0, check_idx - 20)
            prev_vols = [p.get("volume", 0) for p in prices[ma_start_idx:check_idx]]
            ma_vol_shares = sum(prev_vols) / len(prev_vols) if prev_vols else 1.0
            ma_vol_sheets = ma_vol_shares / 1000.0
            
            f = b.get("foreign_accum_10d", 0)
            t = b.get("trust_accum_10d", 0)
            
            if condition_fn(f, t, shares_outstanding) if "Cap" in name else condition_fn(f, t, ma_vol_sheets):
                buy_p = prices[buy_idx]["open"]
                sell_p = prices[sell_idx]["close"]
                ret = (sell_p - buy_p) / buy_p * 100
                trades.append(ret)
                
        win_rate = sum(1 for r in trades if r > 0) / len(trades) * 100 if trades else 0
        avg_ret = sum(trades) / len(trades) if trades else 0
        print(f"{name}: Trades={len(trades)} | WinRate={win_rate:.1f}% | AvgReturn={avg_ret:+.2f}%")

if __name__ == "__main__":
    main()
