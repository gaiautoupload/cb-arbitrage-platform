import argparse
import json
import os
from datetime import date, datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
PRICES_DIR = os.path.join(DATA_DIR, "prices")
TWSA_BIDS_PATH = os.path.join(DATA_DIR, "twsa_bids.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "recent_strategy_backtest.json")


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_day(value):
    if not value:
        return None
    text = str(value)[:10].replace("/", "-")
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def day_str(value):
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value


def nearest_trading_index(prices, target_day):
    target_text = day_str(target_day)
    for idx, row in enumerate(prices):
        if row.get("date", "") >= target_text and row.get("close") not in (None, 0):
            return idx
    return None


def parse_bidding_period(period):
    if not period:
        return None, None
    if "~" in period:
        start_text, end_text = period.split("~", 1)
    else:
        start_text, end_text = period, ""
    return parse_day(start_text), parse_day(end_text)


def build_events(start_day, end_day):
    rows = load_json(TWSA_BIDS_PATH, [])
    events = []
    for row in rows:
        bid_start, bid_end = parse_bidding_period(row.get("bidding_period", ""))
        if not bid_start or not (start_day <= bid_start <= end_day):
            continue
        listing_day = (bid_end or bid_start) + timedelta(days=14)
        events.append({
            "stock_code": row.get("ticker"),
            "company_name": row.get("company_name") or row.get("full_company_name") or row.get("ticker"),
            "serial": row.get("serial"),
            "bid_start": day_str(bid_start),
            "bid_end": day_str(bid_end),
            "estimated_listing_date": day_str(listing_day),
            "listing_day": listing_day,
        })
    return events


def precompute_trades(events, end_day, entry_offsets, exit_offsets, lookbacks):
    trades = []
    for event in events:
        code = event.get("stock_code")
        prices = load_json(os.path.join(PRICES_DIR, f"{code}.json"), [])
        if not prices:
            continue

        for entry_offset in entry_offsets:
            buy_idx = nearest_trading_index(prices, event["listing_day"] + timedelta(days=entry_offset))
            if buy_idx is None:
                continue
            buy_price = prices[buy_idx].get("open") or prices[buy_idx].get("close")
            if not buy_price:
                continue

            inst_windows = {}
            for lookback in lookbacks:
                window = prices[max(0, buy_idx - lookback):buy_idx]
                inst_windows[str(lookback)] = {
                    "foreign_net": round(sum(float(row.get("foreign_net") or 0) for row in window), 1),
                    "trust_net": round(sum(float(row.get("trust_net") or 0) for row in window), 1),
                }

            for exit_offset in exit_offsets:
                sell_idx = nearest_trading_index(prices, event["listing_day"] + timedelta(days=exit_offset))
                if sell_idx is None or sell_idx <= buy_idx:
                    continue
                if parse_day(prices[sell_idx].get("date")) > end_day:
                    continue
                sell_price = prices[sell_idx].get("close")
                if not sell_price:
                    continue

                return_pct = (float(sell_price) - float(buy_price)) / float(buy_price) * 100
                trades.append({
                    "stock_code": code,
                    "company_name": event.get("company_name"),
                    "serial": event.get("serial"),
                    "bid_start": event.get("bid_start"),
                    "bid_end": event.get("bid_end"),
                    "estimated_listing_date": event.get("estimated_listing_date"),
                    "entry_offset": entry_offset,
                    "exit_offset": exit_offset,
                    "buy_date": prices[buy_idx].get("date"),
                    "buy_price": round(float(buy_price), 2),
                    "sell_date": prices[sell_idx].get("date"),
                    "sell_price": round(float(sell_price), 2),
                    "return_pct": round(return_pct, 2),
                    "institutional_windows": inst_windows,
                })
    return trades


def passes_filter(foreign_net, trust_net, mode, foreign_threshold, trust_threshold):
    if mode == "foreign":
        return foreign_net >= foreign_threshold
    if mode == "trust":
        return trust_net >= trust_threshold
    if mode == "and":
        return foreign_net >= foreign_threshold and trust_net >= trust_threshold
    if mode == "or":
        return foreign_net >= foreign_threshold or trust_net >= trust_threshold
    return False


def evaluate_strategies(base_trades, args):
    matches = []
    for entry_offset in args.entry_offsets:
        for exit_offset in args.exit_offsets:
            pool = [
                trade for trade in base_trades
                if trade["entry_offset"] == entry_offset and trade["exit_offset"] == exit_offset
            ]
            if len(pool) < args.min_trades:
                continue

            for lookback in args.lookbacks:
                lookback_key = str(lookback)
                for mode in args.modes:
                    for foreign_threshold in args.foreign_thresholds:
                        for trust_threshold in args.trust_thresholds:
                            trades = []
                            for trade in pool:
                                inst = trade["institutional_windows"][lookback_key]
                                if passes_filter(
                                    inst["foreign_net"],
                                    inst["trust_net"],
                                    mode,
                                    foreign_threshold,
                                    trust_threshold,
                                ):
                                    item = dict(trade)
                                    item["foreign_net"] = inst["foreign_net"]
                                    item["trust_net"] = inst["trust_net"]
                                    item.pop("institutional_windows", None)
                                    trades.append(item)

                            if len(trades) < args.min_trades:
                                continue

                            win_rate = sum(1 for trade in trades if trade["return_pct"] > 0) / len(trades) * 100
                            avg_return = sum(trade["return_pct"] for trade in trades) / len(trades)
                            win_rate_passes = win_rate >= args.min_win_rate
                            avg_return_passes = avg_return >= args.min_avg_return
                            if args.match_logic == "and":
                                strategy_passes = win_rate_passes and avg_return_passes
                            else:
                                strategy_passes = win_rate_passes or avg_return_passes

                            if strategy_passes:
                                matches.append({
                                    "name": strategy_name(entry_offset, exit_offset, lookback, mode, foreign_threshold, trust_threshold),
                                    "entry_offset": entry_offset,
                                    "exit_offset": exit_offset,
                                    "lookback_days": lookback,
                                    "filter_mode": mode,
                                    "foreign_threshold": foreign_threshold,
                                    "trust_threshold": trust_threshold,
                                    "num_trades": len(trades),
                                    "win_rate": round(win_rate, 1),
                                    "avg_return": round(avg_return, 2),
                                    "best_return": max(trade["return_pct"] for trade in trades),
                                    "worst_return": min(trade["return_pct"] for trade in trades),
                                    "trades": sorted(trades, key=lambda trade: trade["buy_date"]),
                                })
    return sorted(matches, key=lambda row: (row["win_rate"], row["avg_return"], row["num_trades"]), reverse=True)


def trade_signature(strategy):
    return tuple(
        (trade["stock_code"], trade["buy_date"], trade["sell_date"], trade["return_pct"])
        for trade in strategy["trades"]
    )


def threshold_complexity(strategy):
    return (
        abs(strategy["foreign_threshold"]) + abs(strategy["trust_threshold"]),
        strategy["filter_mode"] != "foreign",
        strategy["filter_mode"] != "trust",
        strategy["lookback_days"],
    )


def representative_strategies(matches, limit):
    by_signature = {}
    for strategy in matches:
        signature = trade_signature(strategy)
        current = by_signature.get(signature)
        if current is None or threshold_complexity(strategy) < threshold_complexity(current):
            by_signature[signature] = strategy
    rows = list(by_signature.values())
    rows.sort(key=lambda row: (row["win_rate"], row["avg_return"], row["num_trades"]), reverse=True)
    return rows[:limit]


def strategy_name(entry_offset, exit_offset, lookback, mode, foreign_threshold, trust_threshold):
    mode_text = {
        "foreign": f"外資 {lookback} 日 >= {foreign_threshold}",
        "trust": f"投信 {lookback} 日 >= {trust_threshold}",
        "and": f"外資 >= {foreign_threshold} 且投信 >= {trust_threshold}",
        "or": f"外資 >= {foreign_threshold} 或投信 >= {trust_threshold}",
    }[mode]
    return f"T{entry_offset:+d} 買進 / T{exit_offset:+d} 出場 / {mode_text}"


def parse_args():
    parser = argparse.ArgumentParser(description="Search recent CB auction strategies.")
    parser.add_argument("--as-of", default="2026-06-25")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--min-trades", type=int, default=3)
    parser.add_argument("--min-win-rate", type=float, default=80.0)
    parser.add_argument("--min-avg-return", type=float, default=50.0)
    parser.add_argument("--match-logic", choices=["and", "or"], default="or")
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--output", default=OUTPUT_PATH)
    parser.set_defaults(
        entry_offsets=[-25, -20, -16, -15, -12, -10, -7, -5, 0],
        exit_offsets=[0, 3, 5, 10, 15, 19, 25, 30, 40, 60],
        lookbacks=[5, 10, 20],
        modes=["foreign", "trust", "and", "or"],
        foreign_thresholds=[-5000, -3000, -1000, 0, 500, 1000, 2000, 3000, 5000],
        trust_thresholds=[-5000, -3000, -1000, 0, 500, 1000, 1500, 2000, 3000, 5000],
    )
    return parser.parse_args()


def main():
    args = parse_args()
    end_day = parse_day(args.as_of)
    start_day = end_day - timedelta(days=args.days)
    events = build_events(start_day, end_day)
    base_trades = precompute_trades(events, end_day, args.entry_offsets, args.exit_offsets, args.lookbacks)
    matches = evaluate_strategies(base_trades, args)

    output = {
        "as_of": day_str(end_day),
        "window_start": day_str(start_day),
        "window_days": args.days,
        "source": "backend/data/twsa_bids.json + backend/data/prices/*.json",
        "criteria": {
            "min_trades": args.min_trades,
            "min_win_rate": args.min_win_rate,
            "min_avg_return": args.min_avg_return,
            "match_logic": f"win_rate >= min_win_rate {args.match_logic.upper()} avg_return >= min_avg_return",
        },
        "sample": {
            "events": len(events),
            "precomputed_completed_trades": len(base_trades),
            "tradable_codes": len({trade["stock_code"] for trade in base_trades}),
        },
        "matches_count": len(matches),
        "avg_return_50_plus_count": sum(1 for row in matches if row["avg_return"] >= args.min_avg_return),
        "high_avg_return_strategies": representative_strategies(
            sorted(
                [row for row in matches if row["avg_return"] >= args.min_avg_return],
                key=lambda item: (item["avg_return"], item["win_rate"], item["num_trades"]),
                reverse=True,
            ),
            args.top,
        ),
        "representative_strategies": representative_strategies(matches, args.top),
        "top_strategies": matches[:args.top],
    }
    save_json(output, args.output)

    print(f"Saved {len(matches)} matching strategies to {args.output}")
    print(f"Sample: {len(events)} events, {len(base_trades)} completed candidate trades")
    for idx, row in enumerate(matches[:10], 1):
        print(
            f"{idx:02d}. {row['name']} | trades={row['num_trades']} "
            f"win={row['win_rate']}% avg={row['avg_return']}%"
        )


if __name__ == "__main__":
    main()
