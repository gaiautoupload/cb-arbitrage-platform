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

def main():
    linked_stages = load_json(os.path.join(DATA_DIR, "linked_bond_stages.json")) or []
    analysis_results = load_json(os.path.join(DATA_DIR, "analysis_results.json")) or {}
    bonds_analysis = {b["ticker"]: b for b in analysis_results.get("bonds_analysis", [])}

    print(f"Loaded {len(linked_stages)} linked bond lifecycle stages.")
    
    price_cache = {}
    for lb in linked_stages:
        code = lb["stock_code"]
        if code not in price_cache:
            price_cache[code] = load_json(os.path.join(PRICES_DIR, f"{code}.json"))

    print("\n--- Running Multi-Stage CB Lifecycle Backtest Parameter Search ---")
    print("Goal: Locate strategy conditions reaching 100% win rate and >50% average returns.")

    # We backtest different stage-to-stage strategies:
    # 1. BOARD_RESOLUTION -> EFFECTIVE
    # 2. BOARD_RESOLUTION -> PRICING
    # 3. EFFECTIVE -> PRICING
    # 4. PRICING -> LISTING
    # We will search over:
    # - Start Stage: BOARD_RESOLUTION, EFFECTIVE, PRICING
    # - End Stage: EFFECTIVE, PRICING, LISTING
    # - Institutional filters: Foreign/Trust 10-day net accumulation before the START stage date.

    stage_options = ["BOARD_RESOLUTION", "EFFECTIVE", "PRICING", "LISTING"]
    best_combos = []

    for idx1, start_stage in enumerate(stage_options[:-1]):
        for idx2, end_stage in enumerate(stage_options[idx1+1:]):
            for f_th in [0, 500, 1000, 2000, 3000, 5000]:
                for t_th in [0, 500, 1000, 2000, 3000, 5000]:
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

                        # Calculate institutional net buy before the s1 (start stage) date
                        idx_start = find_nearest_trading_day(prices, s1["date"])
                        idx_end = find_nearest_trading_day(prices, s2["date"])
                        if idx_start is None or idx_end is None or idx_start >= idx_end:
                            continue

                        # 10 days before start stage
                        lookback_start = max(0, idx_start - 10)
                        f_net = sum(p.get("foreign_net", 0.0) for p in prices[lookback_start:idx_start])
                        t_net = sum(p.get("trust_net", 0.0) for p in prices[lookback_start:idx_start])

                        if f_net < f_th or t_net < t_th:
                            continue

                        p1 = prices[idx_start]["close"]
                        p2 = prices[idx_end]["close"]
                        ret = (p2 - p1) / p1 * 100
                        trades.append(ret)

                    if len(trades) >= 3:
                        win_rate = sum(1 for r in trades if r > 0) / len(trades) * 100
                        avg_return = sum(trades) / len(trades)
                        
                        if win_rate >= 80.0 and avg_return >= 15.0:
                            best_combos.append({
                                "start_stage": start_stage,
                                "end_stage": end_stage,
                                "foreign_threshold": f_th,
                                "trust_threshold": t_th,
                                "num_trades": len(trades),
                                "win_rate": win_rate,
                                "avg_return": avg_return,
                                "all_returns": [round(x, 2) for x in trades]
                            })

    # Sort by win_rate descending, then avg_return descending
    best_combos.sort(key=lambda x: (x["win_rate"], x["avg_return"]), reverse=True)

    print(f"\nFound {len(best_combos)} multi-stage combinations matching relaxed constraints (Win Rate >= 80%, Avg Return >= 15%):")
    for i, s in enumerate(best_combos[:15]):
        print(f"Top {i+1}: {s['start_stage']} -> {s['end_stage']} | ForeignTh={s['foreign_threshold']}, TrustTh={s['trust_threshold']}")
        print(f"       Trades count: {s['num_trades']} | Win Rate: {s['win_rate']}% | Avg Return: {s['avg_return']:.2f}%")
        print(f"       Returns: {s['all_returns']}")

if __name__ == "__main__":
    main()
