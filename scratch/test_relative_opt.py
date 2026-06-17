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

    # Test combination: Cumulative buy > 0.5% of share capital AND absolute net buy > 1,500 sheets
    # Compare Foreign vs Trust
    for min_absolute in [1000, 1500, 2000]:
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
            lookback_start = max(0, check_idx - 9)
            check_period = prices[lookback_start:check_idx + 1]
            
            f_net = sum(p.get("foreign_net", 0.0) for p in check_period)
            t_net = sum(p.get("trust_net", 0.0) for p in check_period)
            
            f_pct = (f_net * 1000.0) / shares_outstanding * 100
            t_pct = (t_net * 1000.0) / shares_outstanding * 100
            
            # Condition: (Foreign > min_absolute AND f_pct > 0.5%) OR (Trust > min_absolute AND t_pct > 0.5%)
            if (f_net > min_absolute and f_pct > 0.5) or (t_net > min_absolute and t_pct > 0.5):
                buy_p = prices[buy_idx]["open"]
                sell_p = prices[sell_idx]["close"]
                ret = (sell_p - buy_p) / buy_p * 100
                trades.append(ret)
                
        win_rate = sum(1 for r in trades if r > 0) / len(trades) * 100 if trades else 0
        avg_ret = sum(trades) / len(trades) if trades else 0
        print(f"Min Absolute: {min_absolute} sheets + 0.5% Capital: Trades={len(trades)} | WinRate={win_rate:.1f}% | AvgReturn={avg_ret:+.2f}%")

if __name__ == "__main__":
    main()
