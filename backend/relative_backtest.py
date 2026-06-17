import os
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

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

    # 1. Strategy A: Cumulative buy > 0.5% of share capital
    # 2. Strategy B: Cumulative buy > 2.0x of 20-day MA volume
    strategies = {
        "A_SHARE_CAPITAL": [],
        "B_VOLUME_MA": []
    }

    for b in bonds:
        code = b["ticker"]
        prices = price_cache.get(code)
        if not prices:
            continue
            
        shares_outstanding = shares_db.get(code, 100000000)
        
        # Find issue date index
        iss_idx = None
        for idx, p in enumerate(prices):
            if p["date"] >= b["issue_date"]:
                iss_idx = idx
                break
        if iss_idx is None:
            continue
            
        # Entry/Exit indices
        buy_idx = iss_idx - 15  # Buy at T-15 open (Check at T-16 close)
        sell_idx = iss_idx + 19  # Sell at T+19 close
        
        if buy_idx < 0 or sell_idx >= len(prices):
            continue
            
        # Calculate 20-day MA volume before check date (T-16)
        check_idx = buy_idx - 1 # T-16 index
        ma_start_idx = max(0, check_idx - 20)
        prev_vols = [p.get("volume", 0) for p in prices[ma_start_idx:check_idx]]
        ma_vol_shares = sum(prev_vols) / len(prev_vols) if prev_vols else 1.0
        ma_vol_sheets = ma_vol_shares / 1000.0
        
        # Cumulative net buys (T-25 to T-16, 10 days)
        # We look at the 10 days ending on check_idx (T-16)
        lookback_start = max(0, check_idx - 9)
        check_period = prices[lookback_start:check_idx + 1]
        
        f_net_10d = sum(p.get("foreign_net", 0.0) for p in check_period)
        t_net_10d = sum(p.get("trust_net", 0.0) for p in check_period)
        
        # Net buys as % of outstanding shares (1 sheet = 1000 shares)
        f_pct = (f_net_10d * 1000.0) / shares_outstanding * 100
        t_pct = (t_net_10d * 1000.0) / shares_outstanding * 100
        
        buy_p = prices[buy_idx]["open"]
        sell_p = prices[sell_idx]["close"]
        ret = (sell_p - buy_p) / buy_p * 100
        
        # Filter for A: either foreign or trust net buy > 0.5% of share capital
        if f_pct > 0.5 or t_pct > 0.5:
            strategies["A_SHARE_CAPITAL"].append({
                "ticker": code,
                "company_name": b["company_name"],
                "return_pct": ret,
                "f_pct": f_pct,
                "t_pct": t_pct,
                "buy_date": prices[buy_idx]["date"],
                "sell_date": prices[sell_idx]["date"]
            })
            
        # Filter for B: either foreign or trust net buy > 2.0x of 20-day MA volume
        if f_net_10d > ma_vol_sheets * 2.0 or t_net_10d > ma_vol_sheets * 2.0:
            strategies["B_VOLUME_MA"].append({
                "ticker": code,
                "company_name": b["company_name"],
                "return_pct": ret,
                "f_net": f_net_10d,
                "t_net": t_net_10d,
                "ma_vol_sheets": ma_vol_sheets,
                "buy_date": prices[buy_idx]["date"],
                "sell_date": prices[sell_idx]["date"]
            })

    for name, list_trades in strategies.items():
        win_count = sum(1 for t in list_trades if t["return_pct"] > 0)
        win_rate = win_count / len(list_trades) * 100 if list_trades else 0
        avg_ret = sum(t["return_pct"] for t in list_trades) / len(list_trades) if list_trades else 0
        print(f"\n======================================")
        print(f"🎬 {name}")
        print(f"======================================")
        print(f"Total trades: {len(list_trades)} | Win Rate: {win_rate:.1f}% | Avg Return: {avg_ret:+.2f}%")
        for t in list_trades[:5]:
            print(f" - {t['company_name']} ({t['ticker']}): {t['buy_date']} ➔ {t['sell_date']} | Return: {t['return_pct']:+.2f}%")

if __name__ == "__main__":
    main()
