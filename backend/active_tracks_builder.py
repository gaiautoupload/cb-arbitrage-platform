import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
PRICES_DIR = os.path.join(DATA_DIR, "prices")

ACTIVE_TRACKS_PATH = os.path.join(DATA_DIR, "active_tracks.json")
ANALYSIS_PATH = os.path.join(DATA_DIR, "analysis_results.json")
LINKED_STAGES_PATH = os.path.join(DATA_DIR, "linked_bond_stages.json")
TWSA_BIDS_PATH = os.path.join(DATA_DIR, "twsa_bids.json")

INITIAL_CAPITAL = 1_000_000

STRATEGIES = [
    {
        "name": "策略 1: 外資定價前卡位",
        "foreign_min": 2000,
        "trust_min": 0,
        "win_rate": 100.0,
        "avg_return": 45.0,
    },
    {
        "name": "策略 2: 投信定價前卡位",
        "foreign_min": 0,
        "trust_min": 1500,
        "win_rate": 100.0,
        "avg_return": 42.9,
    },
    {
        "name": "策略 3: 雙法人共振",
        "foreign_min": 1000,
        "trust_min": 1000,
        "win_rate": 100.0,
        "avg_return": 43.6,
    },
    {
        "name": "策略 4: 法人卡位 + 股本佔比",
        "foreign_min": 0,
        "trust_min": 0,
        "share_cap_filter": True,
        "win_rate": 100.0,
        "avg_return": 43.6,
    },
]


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_seed_tracks():
    tracks = load_json(ACTIVE_TRACKS_PATH, [])

    try:
        completed = subprocess.run(
            ["git", "show", "HEAD:backend/data/active_tracks.json"],
            cwd=BASE_DIR,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=10,
        )
        if completed.returncode == 0:
            restored = json.loads(completed.stdout)
            if isinstance(restored, list):
                return [*(tracks or []), *restored]
    except Exception as exc:
        print(f"Unable to load active track seed from git: {exc}")

    return tracks or []


def parse_day(value):
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_twsa_day(value):
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y/%m/%d").date()
    except ValueError:
        return parse_day(value)


def day_str(value):
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value


def load_prices(stock_code):
    path = os.path.join(PRICES_DIR, f"{stock_code}.json")
    return load_json(path, [])


def nearest_index(prices, target_date):
    if not prices or not target_date:
        return None
    target = day_str(target_date)
    for idx, row in enumerate(prices):
        if row.get("date") >= target:
            return idx
    return None


def index_date(prices, idx, fallback):
    if prices and idx is not None and 0 <= idx < len(prices):
        return prices[idx].get("date")
    return day_str(fallback)


def latest_price(prices, max_day):
    if not prices:
        return None
    max_text = day_str(max_day)
    rows = [row for row in prices if row.get("date") <= max_text and row.get("close") is not None]
    return rows[-1] if rows else None


def has_price_through(prices, target_day):
    if not prices or not target_day:
        return False
    rows = [row for row in prices if row.get("date") and row.get("close") is not None]
    return bool(rows and parse_day(rows[-1].get("date")) and parse_day(rows[-1].get("date")) >= target_day)


def price_at(prices, idx, field):
    if not prices or idx is None or idx < 0 or idx >= len(prices):
        return None
    value = prices[idx].get(field)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def trading_or_calendar_indexes(prices, listing_day):
    listing_idx = nearest_index(prices, listing_day)
    if listing_idx is not None:
        buy_idx = listing_idx - 15
        check_idx = buy_idx - 1
        sell_idx = listing_idx + 19
        return listing_idx, buy_idx, check_idx, sell_idx

    buy_day = listing_day - timedelta(days=15)
    sell_day = listing_day + timedelta(days=27)
    buy_idx = nearest_index(prices, buy_day)
    check_idx = buy_idx - 1 if buy_idx is not None else None
    sell_idx = nearest_index(prices, sell_day)
    return None, buy_idx, check_idx, sell_idx


def calc_inst_window(prices, check_idx):
    if not prices or check_idx is None or check_idx < 0:
        return 0.0, 0.0
    start_idx = max(0, check_idx - 9)
    rows = prices[start_idx:check_idx + 1]
    foreign_net = sum(float(row.get("foreign_net") or 0.0) for row in rows)
    trust_net = sum(float(row.get("trust_net") or 0.0) for row in rows)
    return round(foreign_net, 1), round(trust_net, 1)


def choose_strategy(bond, prices, check_idx):
    foreign_net, trust_net = calc_inst_window(prices, check_idx)
    share_signal = max(abs(float(bond.get("foreign_accum_10d") or 0)), abs(float(bond.get("trust_accum_10d") or 0))) >= 0

    for strategy in STRATEGIES:
        if strategy.get("share_cap_filter"):
            if share_signal and (foreign_net > 0 or trust_net > 0):
                return strategy
            continue
        if foreign_net >= strategy["foreign_min"] and trust_net >= strategy["trust_min"]:
            return strategy

    return bond.get("seed_strategy") or STRATEGIES[-1]


def strategy_from_seed(seed):
    info = seed.get("strategy_info") or {}
    if not info:
        return None
    return {
        "name": info.get("name") or STRATEGIES[-1]["name"],
        "foreign_min": 0,
        "trust_min": 0,
        "win_rate": float(info.get("win_rate") or 100.0),
        "avg_return": float(info.get("avg_return") or 43.6),
    }


def station_status(station_day, today, required_price_available=True):
    if station_day > today:
        return "upcoming"
    if station_day == today:
        return "active"
    return "completed" if required_price_available else "stale"


def build_stations(bond, prices, today):
    seed_stations = bond.get("seed_stations") or []
    if seed_stations:
        normalized = []
        for station in seed_stations:
            station_day = parse_day(station.get("date"))
            if not station_day:
                continue
            status = station_status(station_day, today, has_price_through(prices, station_day))
            if station.get("status") == "failed":
                status = "failed"
            normalized.append({
                **station,
                "status": status,
            })
        normalized.sort(key=lambda item: item.get("date") or "9999-12-31")

        listing_day = parse_day(bond.get("issue_date"))
        listing_idx, buy_idx, check_idx, sell_idx = trading_or_calendar_indexes(prices, listing_day)
        buy_station_day = next(
            (parse_day(item.get("date")) for item in normalized if "買進" in item.get("name", "")),
            None,
        )
        check_station_day = next(
            (parse_day(item.get("date")) for item in normalized if "審查" in item.get("name", "") or "複審" in item.get("name", "")),
            None,
        )
        sell_station_day = next(
            (parse_day(item.get("date")) for item in normalized if "出場" in item.get("name", "") or "結算" in item.get("name", "")),
            None,
        )
        if buy_station_day:
            buy_idx = nearest_index(prices, buy_station_day)
        if check_station_day:
            check_idx = nearest_index(prices, check_station_day)
        elif buy_idx is not None:
            check_idx = buy_idx - 1
        if sell_station_day:
            sell_idx = nearest_index(prices, sell_station_day)
        return normalized, {"listing_idx": listing_idx, "buy_idx": buy_idx, "check_idx": check_idx, "sell_idx": sell_idx}

    listing_day = parse_day(bond.get("issue_date"))
    pricing_day = parse_day(bond.get("announcement_date"))
    bid_start = parse_day(bond.get("bid_start"))
    bid_end = parse_day(bond.get("bid_end"))
    if not listing_day:
        return [], None

    listing_idx, buy_idx, check_idx, sell_idx = trading_or_calendar_indexes(prices, listing_day)
    check_day = parse_day(index_date(prices, check_idx, listing_day - timedelta(days=16)))
    buy_day = parse_day(index_date(prices, buy_idx, listing_day - timedelta(days=15)))
    sell_day = parse_day(index_date(prices, sell_idx, listing_day + timedelta(days=27)))
    pricing_day = pricing_day or bid_start or listing_day - timedelta(days=18)
    result_day = bid_end + timedelta(days=2) if bid_end else pricing_day + timedelta(days=6)

    latest = latest_price(prices, today)
    latest_day = parse_day(latest.get("date")) if latest else None

    def has_data_for(day_value):
        return latest_day is not None and latest_day >= day_value

    stations = [
        {
            "name": "競拍公告與定價",
            "date": day_str(pricing_day),
            "status": station_status(pricing_day, today, has_data_for(pricing_day)),
            "description": "確認可轉債競拍公告、發行條件與掛牌時程。",
        },
        {
            "name": "T-16 籌碼檢查",
            "date": day_str(check_day),
            "status": station_status(check_day, today, has_data_for(check_day)),
            "description": "檢查外資與投信累積買超是否符合策略門檻。",
        },
        {
            "name": "T-15 策略買進",
            "date": day_str(buy_day),
            "status": station_status(buy_day, today, has_data_for(buy_day)),
            "description": "符合策略條件時，以隔日開盤價模擬買進。",
        },
        {
            "name": "競拍開標與結果",
            "date": day_str(result_day),
            "status": station_status(result_day, today, has_data_for(result_day)),
            "description": "確認競拍是否完成、承銷價格與後續掛牌節點。",
        },
        {
            "name": "T日 掛牌上市",
            "date": day_str(listing_day),
            "status": station_status(listing_day, today, has_data_for(listing_day)),
            "description": "可轉債掛牌日，持續追蹤標的股表現。",
        },
        {
            "name": "T+1~18 持有觀察",
            "date": day_str(listing_day + timedelta(days=1)),
            "status": station_status(listing_day + timedelta(days=1), today, has_data_for(listing_day + timedelta(days=1))),
            "description": "持有期間監控價格與法人籌碼變化。",
        },
        {
            "name": "T+19 結算出場",
            "date": day_str(sell_day),
            "status": station_status(sell_day, today, has_data_for(sell_day)),
            "description": "以 T+19 收盤價模擬賣出並更新策略報酬。",
        },
    ]
    stations.sort(key=lambda item: item.get("date") or "9999-12-31")
    return stations, {"listing_idx": listing_idx, "buy_idx": buy_idx, "check_idx": check_idx, "sell_idx": sell_idx}


def build_performance(prices, indexes, today):
    if not prices or not indexes:
        return None
    buy_idx = indexes.get("buy_idx")
    sell_idx = indexes.get("sell_idx")
    buy_date = parse_day(index_date(prices, buy_idx, None))
    if not buy_date or buy_date > today:
        return None
    buy_price = price_at(prices, buy_idx, "open")
    if buy_price is None or buy_price <= 0:
        buy_price = price_at(prices, buy_idx, "close")
    if buy_price is None or buy_price <= 0:
        return None

    sell_date = parse_day(index_date(prices, sell_idx, None))
    if sell_idx is not None and sell_idx < len(prices) and sell_date and sell_date <= today:
        current_idx = sell_idx
        label = "closed"
    else:
        latest = latest_price(prices, today)
        if not latest:
            return None
        current_idx = prices.index(latest)
        label = "holding"

    current_price = price_at(prices, current_idx, "close")
    if current_price is None:
        return None

    return {
        "buy_price": round(buy_price, 2),
        "current_price": round(current_price, 2),
        "return_pct": round((current_price - buy_price) / buy_price * 100, 2),
        "state": label,
        "capital": INITIAL_CAPITAL,
    }


def summarize_track(stations, performance, today):
    if any(s["status"] == "failed" for s in stations):
        return "\u7c4c\u78bc\u5224\u5b9a\u5931\u6557\uff0c\u653e\u68c4\u4ea4\u6613", "failed"
    if performance and performance.get("state") == "closed":
        return "\u4ea4\u6613\u5df2\u5b8c\u6210\uff0c\u7e3e\u6548\u5df2\u66f4\u65b0", "success"
    if performance and performance.get("state") == "holding":
        return "\u6301\u6709\u4e2d\uff0c\u958b\u59cb\u8a08\u7b97\u5831\u916c", "success"

    stale_count = sum(1 for s in stations if s["status"] == "stale")
    if stale_count:
        return f"{stale_count} \u500b\u7bc0\u9ede\u5f85\u5f8c\u53f0\u8cc7\u6599\u78ba\u8a8d", "pending"

    future = [s for s in stations if parse_day(s["date"]) and parse_day(s["date"]) >= today]
    if future:
        return f"\u4e0b\u4e00\u6b65 {future[0]['date']}\uff1a{future[0]['name']}", "pending"
    return "\u5f85\u51fa\u5834\u6216\u5f85\u88dc\u8cc7\u6599", "pending"


def buy_station_has_passed(stations, today):
    return any(
        "\u8cb7\u9032" in station.get("name", "") and parse_day(station.get("date")) and parse_day(station.get("date")) <= today
        for station in stations
    )

def build_tracks(today=None):
    today = today or date.today()
    analysis = load_json(ANALYSIS_PATH, {})
    bonds = analysis.get("bonds_analysis", [])
    linked = load_json(LINKED_STAGES_PATH, [])
    twsa_bids = load_json(TWSA_BIDS_PATH, [])
    seed_tracks = load_seed_tracks()
    linked_by_code = {row.get("stock_code"): row for row in linked}
    candidates = {}

    for bond in bonds:
        code = bond.get("ticker") or bond.get("stock_code")
        if code:
            candidates[code] = dict(bond)

    for item in twsa_bids:
        code = item.get("ticker")
        if not code:
            continue
        period = item.get("bidding_period", "")
        start_text, end_text = (period.split("~", 1) + [""])[:2] if "~" in period else (period, "")
        bid_start = parse_twsa_day(start_text)
        bid_end = parse_twsa_day(end_text)
        inferred_listing = bid_end + timedelta(days=14) if bid_end else None
        candidates[code] = {
            **candidates.get(code, {}),
            "ticker": code,
            "company_name": item.get("company_name") or item.get("full_company_name") or code,
            "bond_name": f"{item.get('company_name') or code} 可轉債",
            "announcement_date": day_str(bid_start),
            "issue_date": day_str(inferred_listing),
            "bid_start": day_str(bid_start),
            "bid_end": day_str(bid_end),
        }

    for seed in seed_tracks if isinstance(seed_tracks, list) else []:
        code = seed.get("stock_code")
        if not code:
            continue
        first_station = (seed.get("stations") or [{}])[0]
        candidates[code] = {
            **candidates.get(code, {}),
            "ticker": code,
            "company_name": seed.get("company_name") or code,
            "bond_name": seed.get("bond_name") or "",
            "announcement_date": first_station.get("date") or candidates.get(code, {}).get("announcement_date"),
            "issue_date": seed.get("expected_listing_date") or candidates.get(code, {}).get("issue_date"),
            "seed_strategy": strategy_from_seed(seed),
            "seed_stations": seed.get("stations") or [],
            "seed_performance": seed.get("performance"),
        }

    tracks = []
    for bond in candidates.values():
        stock_code = bond.get("ticker") or bond.get("stock_code")
        listing_day = parse_day(bond.get("issue_date"))
        if not stock_code or not listing_day:
            continue
        if listing_day < today - timedelta(days=45) or listing_day > today + timedelta(days=75):
            continue

        prices = load_prices(stock_code)
        stations, indexes = build_stations(bond, prices, today)
        if not stations:
            continue

        strategy = choose_strategy(bond, prices, indexes.get("check_idx") if indexes else None)

        has_failed_station = any(station.get("status") == "failed" for station in stations)
        performance = None if has_failed_station else (build_performance(prices, indexes, today) or bond.get("seed_performance"))
        if performance and not performance.get("state"):
            performance["state"] = "holding"
        status_text, status_type = summarize_track(stations, performance, today)
        if not prices and buy_station_has_passed(stations, today) and status_type != "failed":
            status_text, status_type = "\u5df2\u9054\u8cb7\u9032\u65e5\uff0c\u4f46\u7f3a\u5c11\u50f9\u683c\u8cc7\u6599\uff0c\u5f85\u88dc\u50f9\u5f8c\u8f49\u6301\u6709", "pending"
        completed = sum(1 for s in stations if s["status"] in {"completed", "active", "stale"})

        linked_row = linked_by_code.get(stock_code, {})
        tracks.append({
            "stock_code": stock_code,
            "company_name": bond.get("company_name") or linked_row.get("company_name") or stock_code,
            "bond_name": bond.get("bond_name") or linked_row.get("short_name") or "",
            "expected_listing_date": day_str(listing_day),
            "current_stage_index": max(0, completed - 1),
            "status_text": status_text,
            "status_type": status_type,
            "strategy_info": {
                "name": strategy["name"],
                "win_rate": strategy["win_rate"],
                "avg_return": strategy["avg_return"],
            },
            "stations": stations,
            "performance": performance,
        })

    tracks.sort(key=lambda t: (
        0 if t.get("performance") else 1,
        t.get("expected_listing_date") or "9999-12-31",
        t.get("stock_code") or "",
    ))
    return tracks


def main():
    today_arg = sys.argv[1] if len(sys.argv) > 1 else None
    today = parse_day(today_arg) if today_arg else date.today()
    tracks = build_tracks(today)
    save_json(tracks, ACTIVE_TRACKS_PATH)
    print(f"Saved {len(tracks)} active tracks to {ACTIVE_TRACKS_PATH}")


if __name__ == "__main__":
    main()
