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

def test_relative_days(linked_stages, price_cache, anchor_stage, entry_offset, exit_offset):
    trades = []
    for lb in linked_stages:
        code = lb["stock_code"]
        prices = price_cache.get(code)
        if not prices:
            continue
        
        stages = lb.get("stages", {})
        anchor = stages.get(anchor_stage)
        if not anchor:
            continue
            
        anchor_idx = find_nearest_trading_day(prices, anchor["date"])
        if anchor_idx is None:
            continue
            
        buy_idx = anchor_idx + entry_offset
        sell_idx = anchor_idx + exit_offset
        
        if buy_idx >= 0 and buy_idx < len(prices) and sell_idx >= 0 and sell_idx < len(prices) and buy_idx < sell_idx:
            p1 = prices[buy_idx]["close"]
            p2 = prices[sell_idx]["close"]
            ret = (p2 - p1) / p1 * 100
            trades.append(ret)
            
    if not trades:
        return {"win_rate": 0.0, "avg_return": 0.0, "total_trades": 0}
        
    win_count = sum(1 for r in trades if r > 0)
    return {
        "win_rate": round(win_count / len(trades) * 100, 1),
        "avg_return": round(sum(trades) / len(trades), 2),
        "total_trades": len(trades)
    }

def main():
    linked_stages = load_json(os.path.join(DATA_DIR, "linked_bond_stages.json")) or []
    price_cache = {}
    for lb in linked_stages:
        code = lb["stock_code"]
        if code not in price_cache:
            price_cache[code] = load_json(os.path.join(PRICES_DIR, f"{code}.json"))

    anchors = ["PRICING", "LISTING"]
    offsets = [
        (-15, 0, "前 15 天 ➔ 當天"),
        (-10, 0, "前 10 天 ➔ 當天"),
        (-5, 0, "前 5 天 ➔ 當天"),
        (0, 5, "當天 ➔ 後 5 天"),
        (0, 10, "當天 ➔ 後 10 天"),
        (0, 15, "當天 ➔ 後 15 天"),
        (-5, 5, "前 5 天 ➔ 後 5 天"),
        (-10, 10, "前 10 天 ➔ 後 10 天")
    ]

    for anchor in anchors:
        print(f"\n==================================================")
        print(f"基準日: {anchor} ({'定價公告日' if anchor == 'PRICING' else '正式掛牌日'})")
        print(f"==================================================")
        for entry, exit, label in offsets:
            res = test_relative_days(linked_stages, price_cache, anchor, entry, exit)
            print(f"✦ {label}:")
            print(f"  交易筆數: {res['total_trades']} | 勝率: {res['win_rate']}% | 平均報酬率: {res['avg_return']}%")

if __name__ == "__main__":
    main()
