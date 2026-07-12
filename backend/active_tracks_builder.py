import json
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta


sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
PRICES_DIR = os.path.join(DATA_DIR, "prices")
DB_PATH = os.path.join(DATA_DIR, "cb_event_master.sqlite")
OUTPUT_PATH = os.path.join(DATA_DIR, "active_tracks.json")
TWSA_BIDS_PATH = os.path.join(DATA_DIR, "twsa_bids.json")

INITIAL_CAPITAL = 1_000_000
STRATEGY_INFO = {
    "name": "候選：競拍前法人動能（模擬）",
    "win_rate": 80.0,
    "avg_return": 13.52,
    "raw_avg_return": 23.2,
    "status": "research_only",
}


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def parse_day(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def load_prices(stock_code):
    return load_json(os.path.join(PRICES_DIR, f"{stock_code}.json"), [])


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def nearest_index(prices, target_day):
    target = target_day.isoformat()
    for index, row in enumerate(prices):
        if row.get("date", "") >= target and number(row.get("close")) not in (None, 0):
            return index
    return None


def latest_index(prices, today):
    indexes = [index for index, row in enumerate(prices) if row.get("date", "") <= today.isoformat() and number(row.get("close")) is not None]
    return indexes[-1] if indexes else None


def station_status(station_day, today):
    if station_day < today:
        return "completed"
    if station_day == today:
        return "active"
    return "upcoming"


def company_names():
    return {
        str(row.get("ticker")): row.get("company_name") or row.get("full_company_name") or row.get("ticker")
        for row in load_json(TWSA_BIDS_PATH, [])
    }


def load_snapshots():
    if not os.path.exists(DB_PATH):
        return []
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    rows = [
        dict(row) for row in connection.execute(
            """SELECT * FROM event_feature_snapshots
               WHERE stage = 'AUCTION_BID_START' AND entry_offset = -5
               ORDER BY event_date, stock_code"""
        )
    ]
    connection.close()
    return rows


def passes_strategy(snapshot):
    reasons = []
    momentum = number(snapshot.get("momentum_10d"))
    foreign = number(snapshot.get("foreign_net_5d"))
    volume_ratio = number(snapshot.get("volume_ratio_5v20"))
    if momentum is None or momentum <= 0:
        reasons.append("買進前 10 日動能未轉正")
    if foreign is None or foreign <= 0:
        reasons.append("外資近 5 日未累計買超")
    if volume_ratio is None:
        reasons.append("缺少量能資料")
    elif volume_ratio >= 3:
        reasons.append("成交量過熱")
    return not reasons, reasons


def build_candidate(snapshot, today, names):
    stock_code = str(snapshot.get("stock_code") or "")
    event_day = parse_day(snapshot.get("event_date"))
    buy_day = parse_day(snapshot.get("buy_date"))
    prices = load_prices(stock_code)
    if not event_day or not buy_day:
        return None
    sell_idx = nearest_index(prices, event_day + timedelta(days=20))
    sell_day = parse_day(prices[sell_idx].get("date")) if sell_idx is not None else event_day + timedelta(days=20)
    buy_idx = nearest_index(prices, buy_day)
    passed, failure_reasons = passes_strategy(snapshot)

    stations = [
        {
            "name": "競拍時程已知",
            "date": event_day.isoformat(),
            "status": station_status(event_day, today),
            "description": "使用正式競拍時程，不使用事後推算的掛牌倒數日。",
        },
        {
            "name": "法人動能檢查",
            "date": buy_day.isoformat(),
            "status": "failed" if not passed and buy_day <= today else station_status(buy_day, today),
            "description": "10 日動能為正、外資 5 日買超且成交量未過熱。",
        },
        {
            "name": "模擬買進",
            "date": buy_day.isoformat(),
            "status": "failed" if not passed and buy_day <= today else station_status(buy_day, today),
            "description": "條件全部成立才以買進日收盤價建立模擬部位。",
        },
        {
            "name": "競拍開始",
            "date": event_day.isoformat(),
            "status": station_status(event_day, today),
            "description": "進入競拍事件觀察期。",
        },
        {
            "name": "第 20 天出場",
            "date": sell_day.isoformat(),
            "status": station_status(sell_day, today),
            "description": "暫定事件後第 20 天出場；單檔 -10% 先停損。",
        },
    ]
    performance = None
    if passed and buy_idx is not None and buy_day <= today:
        end_idx = sell_idx if sell_idx is not None and sell_day <= today else latest_index(prices, today)
        buy_price = number(prices[buy_idx].get("close"))
        current_price = number(prices[end_idx].get("close")) if end_idx is not None else None
        if buy_price and current_price:
            performance = {
                "buy_price": round(buy_price, 2),
                "current_price": round(current_price, 2),
                "return_pct": round((current_price - buy_price) / buy_price * 100, 2),
                "state": "closed" if sell_day <= today else "holding",
                "capital": INITIAL_CAPITAL,
            }

    if not passed and buy_day <= today:
        status_type = "failed"
        status_text = "條件未通過：" + "、".join(failure_reasons)
    elif buy_day > today:
        status_type = "pending"
        status_text = f"預計 {buy_day.isoformat()} 檢查並模擬買進"
    elif performance and performance["state"] == "holding":
        status_type = "success"
        status_text = f"模擬持有中，預計 {sell_day.isoformat()} 出場"
    elif performance and performance["state"] == "closed":
        status_type = "success"
        status_text = "模擬交易已完成"
    else:
        status_type = "pending"
        status_text = "資料不足，不建立部位"

    return {
        "stock_code": stock_code,
        "company_name": names.get(stock_code, stock_code),
        "bond_name": snapshot.get("cb_code") or f"{names.get(stock_code, stock_code)} 可轉債",
        "expected_listing_date": None,
        "event_date": event_day.isoformat(),
        "buy_date": buy_day.isoformat(),
        "sell_date": sell_day.isoformat(),
        "current_stage_index": sum(1 for station in stations if station["status"] in {"completed", "active"}) - 1,
        "status_text": status_text,
        "status_type": status_type,
        "strategy_mode": "paper_trade_only",
        "strategy_info": dict(STRATEGY_INFO),
        "signal": {
            "passed": passed,
            "momentum_10d": snapshot.get("momentum_10d"),
            "foreign_net_5d": snapshot.get("foreign_net_5d"),
            "trust_net_5d": snapshot.get("trust_net_5d"),
            "volume_ratio_5v20": snapshot.get("volume_ratio_5v20"),
            "failure_reasons": failure_reasons,
        },
        "stations": stations,
        "performance": performance,
    }


def apply_capital_allocation(tracks):
    qualified = [track for track in tracks if track.get("signal", {}).get("passed")]
    intervals = [(track, parse_day(track["buy_date"]), parse_day(track["sell_date"])) for track in qualified]
    for track, start, end in intervals:
        overlap = max(
            (sum(1 for _, other_start, other_end in intervals if other_start <= day <= other_end)
             for day in (start + timedelta(days=offset) for offset in range((end - start).days + 1))),
            default=1,
        )
        track["overlap_slots"] = overlap
        track["allocated_capital"] = round(INITIAL_CAPITAL / overlap, 2)
        if track.get("performance"):
            track["performance"]["capital"] = track["allocated_capital"]


def build_tracks(today=None):
    today = today or date.today()
    names = company_names()
    lower_bound = today - timedelta(days=90)
    upper_bound = today + timedelta(days=60)
    tracks = []
    for snapshot in load_snapshots():
        event_day = parse_day(snapshot.get("event_date"))
        if not event_day or not lower_bound <= event_day <= upper_bound:
            continue
        track = build_candidate(snapshot, today, names)
        if track:
            tracks.append(track)
    apply_capital_allocation(tracks)
    tracks.sort(key=lambda row: (row["status_type"] != "success", row.get("buy_date") or "9999-12-31"))
    return tracks


def main():
    tracks = build_tracks()
    save_json(tracks, OUTPUT_PATH)
    summary = {
        "output": OUTPUT_PATH,
        "tracks": len(tracks),
        "holding": sum((track.get("performance") or {}).get("state") == "holding" for track in tracks),
        "upcoming": sum(track.get("status_type") == "pending" and parse_day(track.get("buy_date")) > date.today() for track in tracks),
        "failed": sum(track.get("status_type") == "failed" for track in tracks),
        "mode": "paper_trade_only",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
