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
    # Fallback to closest if exact not found
    for idx, p in enumerate(prices):
        if p["date"] >= target_date_str:
            return idx
    return None

def main():
    analysis_results = load_json(os.path.join(DATA_DIR, "analysis_results.json"))
    if not analysis_results:
        print("analysis_results.json not found.")
        return

    bonds = analysis_results.get("bonds_analysis", [])
    print(f"Total analyzed bonds: {len(bonds)}")

    # Let's search parameter space for:
    # 1. Entry offset (relative to issue date): -20 to -1
    # 2. Exit offset (relative to issue date): 1 to 20
    # 3. Foreign net buy threshold (10 days before announcement): 0 to 10000 (step 500)
    # 4. Trust net buy threshold (10 days before announcement): 0 to 10000 (step 500)

    best_strategies = []

    # Preload prices to make it fast
    price_cache = {}
    for b in bonds:
        ticker = b["ticker"]
        if ticker not in price_cache:
            price_cache[ticker] = load_json(os.path.join(PRICES_DIR, f"{ticker}.json"))

    print("Running parameter grid search for 100% win rate and maximum return...")

    # We do a nested loop of parameters
    for entry in range(-15, 0, 2):
        for exit in range(1, 25, 2):
            for f_th in [-5000, -2000, 0, 500, 1000, 2000, 3000, 5000]:
                for t_th in [-5000, -2000, 0, 500, 1000, 2000, 3000, 5000]:
                    trades = []
                    for b in bonds:
                        # Check threshold filters
                        if b["foreign_accum_10d"] < f_th:
                            continue
                        if b["trust_accum_10d"] < t_th:
                            continue

                        prices = price_cache.get(b["ticker"])
                        if not prices:
                            continue

                        iss_idx = find_nearest_trading_day(prices, b["issue_date"])
                        if iss_idx is None:
                            continue

                        buy_idx = iss_idx + entry
                        sell_idx = iss_idx + exit

                        if buy_idx >= 0 and buy_idx < len(prices) and sell_idx >= 0 and sell_idx < len(prices) and buy_idx < sell_idx:
                            buy_p = prices[buy_idx]["open"]
                            sell_p = prices[sell_idx]["close"]
                            ret = (sell_p - buy_p) / buy_p * 100
                            trades.append(ret)

                    if len(trades) >= 3:  # Min trades to avoid sample bias
                        win_rate = sum(1 for r in trades if r > 0) / len(trades) * 100
                        avg_return = sum(trades) / len(trades)
                        
                        best_strategies.append({
                            "entry_offset": entry,
                            "exit_offset": exit,
                            "foreign_threshold": f_th,
                            "trust_threshold": t_th,
                            "num_trades": len(trades),
                            "win_rate": win_rate,
                            "avg_return": avg_return,
                            "all_returns": [round(x, 2) for x in trades]
                        })

    # Sort by win_rate descending, then avg_return descending
    best_strategies.sort(key=lambda x: (x["win_rate"], x["avg_return"]), reverse=True)

    print(f"\nFound {len(best_strategies)} total strategies in parameter space.")
    print("Top 10 highest performing strategies matching constraints:")
    printed = 0
    for s in best_strategies:
        if printed >= 10:
            break
        # Filter for high performance
        if s["win_rate"] == 100.0 and s["num_trades"] >= 5:
            print(f"Top {printed+1}: Buy (T{s['entry_offset']}), Sell (T+{s['exit_offset']}) | ForeignTh={s['foreign_threshold']}, TrustTh={s['trust_threshold']}")
            print(f"       Trades count: {s['num_trades']} | Win Rate: {s['win_rate']}% | Avg Return: {s['avg_return']:.2f}%")
            print(f"       Returns: {s['all_returns']}")
            printed += 1

if __name__ == "__main__":
    main()
