import os
import sys
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
PRICES_DIR = os.path.join(DATA_DIR, "prices")

# Reconfigure stdout/stderr for Windows UTF-8 terminal
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def find_nearest_trading_day(prices, target_date_str):
    if not target_date_str:
        return None
    for idx, p in enumerate(prices):
        if p["date"] == target_date_str:
            return idx
    for idx, p in enumerate(prices):
        if p["date"] >= target_date_str:
            return idx
    return None

def main():
    linked_stages = load_json(os.path.join(DATA_DIR, "linked_bond_stages.json")) or []
    print(f"Loaded {len(linked_stages)} linked bonds for script-based backtesting.")
    
    price_cache = {}
    for lb in linked_stages:
        code = lb["stock_code"]
        if code not in price_cache:
            price_cache[code] = load_json(os.path.join(PRICES_DIR, f"{code}.json"))

    # Script: Buy at T_PRICING (Pricing Announcement Date)
    # Sell at T_LISTING + 1 (The day CBAS option is opened)
    # We test multiple conditional filters:
    filters = [
        {"name": "1. 無條件（基本盤）", "f_th": 0, "t_th": 0, "volume_breakout": False},
        {"name": "2. 投信定價前大買 > 1,500張", "f_th": 0, "t_th": 1500, "volume_breakout": False},
        {"name": "3. 外資定價前大買 > 2,000張", "f_th": 2000, "t_th": 0, "volume_breakout": False},
        {"name": "4. 雙法人定價前大買 (外資>1000且投信>1000)", "f_th": 1000, "t_th": 1000, "volume_breakout": False},
        {"name": "5. 定價日附近現貨出現爆量 (當日量 > 20日均量 2.0倍)", "f_th": 0, "t_th": 0, "volume_breakout": True},
        {"name": "6. 法人共振 + 現貨爆量 (外資或投信>1000 且 2.0倍爆量)", "f_th": 1000, "t_th": 1000, "volume_breakout": True, "either_inst": True}
    ]

    for f in filters:
        trades = []
        for lb in linked_stages:
            code = lb["stock_code"]
            prices = price_cache.get(code)
            if not prices:
                continue
                
            stages = lb.get("stages", {})
            pricing_stage = stages.get("PRICING")
            listing_stage = stages.get("LISTING")
            if not pricing_stage or not listing_stage:
                continue
                
            pricing_idx = find_nearest_trading_day(prices, pricing_stage["date"])
            listing_idx = find_nearest_trading_day(prices, listing_stage["date"])
            if pricing_idx is None or listing_idx is None or pricing_idx >= listing_idx:
                continue
                
            # Entry: 1 day after Pricing (T_PRICING + 1)
            buy_idx = pricing_idx + 1
            # Exit: 1 day after Listing (T_LISTING + 1, when CBAS splits)
            sell_idx = min(len(prices) - 1, listing_idx + 1)
            
            if buy_idx >= sell_idx:
                continue
                
            # Calculate institutional net buy before entry (T_PRICING)
            lookback_start = max(0, pricing_idx - 10)
            f_net = sum(p.get("foreign_net", 0.0) for p in prices[lookback_start:pricing_idx])
            t_net = sum(p.get("trust_net", 0.0) for p in prices[lookback_start:pricing_idx])
            
            # Check institutional thresholds
            if not f.get("either_inst", False):
                if f_net < f["f_th"] or t_net < f["t_th"]:
                    continue
            else:
                # Either must match threshold
                if f_net < f["f_th"] and t_net < f["t_th"]:
                    continue
                    
            # Check volume breakout condition:
            # Look at volume on the pricing announcement day compared to previous 20-day MA
            if f.get("volume_breakout", False):
                pricing_vol = prices[pricing_idx].get("volume", 0)
                # Calculate 20-day MA before pricing date
                ma_start = max(0, pricing_idx - 20)
                ma_volumes = [p.get("volume", 0) for p in prices[ma_start:pricing_idx]]
                if not ma_volumes:
                    continue
                ma_20 = sum(ma_volumes) / len(ma_volumes)
                if ma_20 == 0 or pricing_vol < ma_20 * 2.0:
                    continue
                    
            p1 = prices[buy_idx]["open"]
            p2 = prices[sell_idx]["close"]
            ret = (p2 - p1) / p1 * 100
            
            trades.append({
                "ticker": code,
                "company_name": lb["company_name"],
                "buy_date": prices[buy_idx]["date"],
                "sell_date": prices[sell_idx]["date"],
                "return_pct": ret
            })
            
        print(f"\n==================================================")
        print(f"🎬 {f['name']}")
        print(f"==================================================")
        if not trades:
            print("  沒有符合篩選條件的交易項目。")
            continue
            
        win_count = sum(1 for t in trades if t["return_pct"] > 0)
        win_rate = win_count / len(trades) * 100
        avg_ret = sum(t["return_pct"] for t in trades) / len(trades)
        
        print(f"  總交易筆數: {len(trades)} 筆")
        print(f"  歷史勝率: {win_rate:.1f}%")
        print(f"  平均報酬率: {avg_ret:+.2f}%")
        print("  每筆交易明細：")
        for t in trades:
            print(f"   - {t['company_name']} ({t['ticker']}) | 買入: {t['buy_date']} ➔ 賣出: {t['sell_date']} | 報酬率: {t['return_pct']:+.2f}%")

if __name__ == "__main__":
    main()
