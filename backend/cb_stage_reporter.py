import os
import sys
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
PRICES_DIR = os.path.join(DATA_DIR, "prices")

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

def run_stage_backtest(linked_stages, price_cache, start_stage, end_stage, f_th=0, t_th=0):
    trades = []
    for lb in linked_stages:
        code = lb["stock_code"]
        prices = price_cache.get(code)
        if not prices:
            continue
        
        stages = lb.get("stages", {})
        s1 = stages.get(start_stage)
        s2 = stages.get(end_stage)
        if not s1 or not s2:
            continue

        idx_start = find_nearest_trading_day(prices, s1["date"])
        idx_end = find_nearest_trading_day(prices, s2["date"])
        if idx_start is None or idx_end is None or idx_start >= idx_end:
            continue

        # Lookback institutional buy before the start stage
        lookback_start = max(0, idx_start - 10)
        f_net = sum(p.get("foreign_net", 0.0) for p in prices[lookback_start:idx_start])
        t_net = sum(p.get("trust_net", 0.0) for p in prices[lookback_start:idx_start])

        if f_net < f_th or t_net < t_th:
            continue

        p1 = prices[idx_start]["close"]
        p2 = prices[idx_end]["close"]
        ret = (p2 - p1) / p1 * 100
        trades.append(ret)
        
    if not trades:
        return {"win_rate": 0.0, "avg_return": 0.0, "total_trades": 0, "all_returns": []}
        
    win_count = sum(1 for r in trades if r > 0)
    return {
        "win_rate": round(win_count / len(trades) * 100, 1),
        "avg_return": round(sum(trades) / len(trades), 2),
        "total_trades": len(trades),
        "all_returns": [round(x, 2) for x in trades]
    }

# Reconfigure stdout/stderr for Windows UTF-8 terminal
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

def main():
    linked_stages = load_json(os.path.join(DATA_DIR, "linked_bond_stages.json")) or []
    print(f"Loaded {len(linked_stages)} linked bonds.")

    price_cache = {}
    for lb in linked_stages:
        code = lb["stock_code"]
        if code not in price_cache:
            price_cache[code] = load_json(os.path.join(PRICES_DIR, f"{code}.json"))

    # Define stage relations to test
    relations = [
        ("BOARD_RESOLUTION", "EFFECTIVE", "BOARD_RESOLUTION -> EFFECTIVE (董事會 ➔ 申報生效)"),
        ("BOARD_RESOLUTION", "PRICING", "BOARD_RESOLUTION -> PRICING (董事會 ➔ 訂價公告)"),
        ("BOARD_RESOLUTION", "LISTING", "BOARD_RESOLUTION -> LISTING (董事會 ➔ 正式掛牌)"),
        ("EFFECTIVE", "PRICING", "EFFECTIVE -> PRICING (申報生效 ➔ 訂價公告)"),
        ("EFFECTIVE", "LISTING", "EFFECTIVE -> LISTING (申報生效 ➔ 正式掛牌)"),
        ("PRICING", "LISTING", "PRICING -> LISTING (訂價公告 ➔ 正式掛牌)")
    ]

    # Threshold settings to test
    # (Label, ForeignTh, TrustTh)
    thresholds = [
        ("No Filter (Basic)", 0, 0),
        ("Foreign Accum 10d > 1000", 1000, 0),
        ("Trust Accum 10d > 1000", 0, 1000),
        ("Foreign > 1000 AND Trust > 1000", 1000, 1000),
        ("Trust Accum 10d > 2000", 0, 2000),
        ("Foreign Accum 10d > 3000", 3000, 0)
    ]

    results = []

    for start, end, label in relations:
        print(f"\n==================================================")
        print(f"STAGE: {label}")
        print(f"==================================================")
        for th_label, f_th, t_th in thresholds:
            res = run_stage_backtest(linked_stages, price_cache, start, end, f_th, t_th)
            if res["total_trades"] > 0:
                print(f" - {th_label}:")
                print(f"   Trades: {res['total_trades']} | Win Rate: {res['win_rate']}% | Avg Return: {res['avg_return']}%")
                if len(res["all_returns"]) <= 10:
                    print(f"   Returns: {res['all_returns']}")
                else:
                    print(f"   Returns (First 10): {res['all_returns'][:10]}...")

if __name__ == "__main__":
    main()
