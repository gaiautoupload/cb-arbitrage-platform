import argparse
import json
import os
import sys
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
CONFIG_PATH = os.path.join(BASE_DIR, "backend", "config.json")
DEFAULT_WEB_URL = "https://gaiautoupload.github.io/cb-arbitrage-platform/"


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"Failed to load {path}: {exc}")
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ensure_config():
    config = load_json(CONFIG_PATH, {})
    if config:
        return config

    config = {
        "line_notify_token": "",
        "line_channel_access_token": "",
        "line_user_id": "",
        "line_group_id": "",
        "website_url": DEFAULT_WEB_URL,
    }
    save_json(CONFIG_PATH, config)
    print(f"Created template configuration at {CONFIG_PATH}.")

    gitignore_path = os.path.join(BASE_DIR, ".gitignore")
    existing = ""
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            existing = f.read()
    if "backend/config.json" not in existing:
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write("\nbackend/config.json\n")
        print("Added backend/config.json to .gitignore.")

    return config


def send_line_notify(token, message):
    import requests

    res = requests.post(
        "https://notify-api.line.me/api/notify",
        headers={"Authorization": f"Bearer {token}"},
        data={"message": message},
        timeout=15,
    )
    if res.status_code != 200:
        raise RuntimeError(f"Line Notify failed: {res.status_code} {res.text[:300]}")
    print("Line Notify sent successfully.")


def send_line_messaging_api(channel_access_token, to_id, message):
    import requests

    res = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {channel_access_token}",
        },
        json={"to": to_id, "messages": [{"type": "text", "text": message}]},
        timeout=15,
    )
    if res.status_code != 200:
        raise RuntimeError(f"Line Messaging API failed: {res.status_code} {res.text[:300]}")
    print("Line Messaging API push sent successfully.")


def station_hits_on(track, day):
    return [s for s in track.get("stations", []) if s.get("date") == day]


def is_buy_station(name):
    return any(marker in (name or "") for marker in ("T-16", "T-15", "T-14", "策略買進", "模擬買進", "籌碼檢查"))


def is_sell_station(name):
    return any(marker in (name or "") for marker in ("T+19", "結算出場", "出清"))


def track_title(track):
    code = track.get("stock_code") or track.get("stock_id") or "----"
    company = track.get("company_name") or "未知公司"
    bond = track.get("bond_name") or "未知公司債"
    return f"{company} ({code}) - {bond}"


def format_strategy(track):
    info = track.get("strategy_info") or {}
    name = info.get("name") or "未命名策略"
    win_rate = info.get("win_rate")
    avg_return = info.get("avg_return")
    parts = [name]
    if win_rate is not None:
        parts.append(f"勝率 {win_rate}%")
    if avg_return is not None:
        parts.append(f"均報酬 {avg_return}%")
    return " / ".join(parts)


def summarize_counts(tracks, today):
    today_dt = datetime.strptime(today, "%Y-%m-%d").date()
    soon_end = today_dt + timedelta(days=2)
    counts = {
        "today_events": 0,
        "today_buy": 0,
        "today_sell": 0,
        "holding": 0,
        "pending": 0,
        "failed": 0,
        "exit_within_2d": 0,
    }

    for track in tracks:
        status_type = track.get("status_type")
        if status_type == "pending":
            counts["pending"] += 1
        elif status_type == "failed":
            counts["failed"] += 1
        elif status_type not in ("success", "failed"):
            counts["holding"] += 1

        for station in station_hits_on(track, today):
            counts["today_events"] += 1
            name = station.get("name") or ""
            if is_buy_station(name) and status_type != "failed" and station.get("status") != "failed":
                counts["today_buy"] += 1
            if is_sell_station(name):
                counts["today_sell"] += 1

        for station in track.get("stations", []):
            if not is_sell_station(station.get("name")):
                continue
            s_date = station.get("date")
            try:
                s_dt = datetime.strptime(s_date, "%Y-%m-%d").date()
            except Exception:
                continue
            if today_dt <= s_dt <= soon_end:
                counts["exit_within_2d"] += 1

    return counts


def build_message(tracks, today, web_url, alerts_only=False):
    paper_trade_only = bool(tracks) and all(track.get("strategy_mode") == "paper_trade_only" for track in tracks)
    mode_label = "[模擬] " if paper_trade_only else ""
    alerts = []
    daily_events = []

    for track in tracks:
        status_type = track.get("status_type", "")
        for station in station_hits_on(track, today):
            name = station.get("name") or ""
            line = f"{track_title(track)} | {name} | {format_strategy(track)}"
            daily_events.append(line)

            if is_buy_station(name) and status_type != "failed" and station.get("status") != "failed":
                alerts.append(f"模擬買進/檢查提醒：{line}" if paper_trade_only else f"買進/檢查提醒：{line}")
            elif is_sell_station(name):
                alerts.append(f"出清提醒：{line}")

    if alerts:
        body = [f"{mode_label}公司債策略提醒", f"日期：{today}", ""]
        body.extend(alerts[:12])
        if len(alerts) > 12:
            body.append(f"...另有 {len(alerts) - 12} 筆提醒")
    elif alerts_only:
        return ""
    else:
        counts = summarize_counts(tracks, today)
        body = [
            f"{mode_label}公司債每日策略摘要",
            f"日期：{today}",
            "",
            "今日沒有買進或出清觸發。",
            f"今日節點：{counts['today_events']} 筆",
            f"買進/檢查：{counts['today_buy']} 筆，出清：{counts['today_sell']} 筆",
            f"待買/待確認：{counts['pending']} 筆，籌碼失敗：{counts['failed']} 筆",
            f"兩日內出清：{counts['exit_within_2d']} 筆",
        ]
        if daily_events:
            body.append("")
            body.append("今日時程：")
            body.extend(daily_events[:8])
            if len(daily_events) > 8:
                body.append(f"...另有 {len(daily_events) - 8} 筆")

    body.extend(["", f"網站：{web_url}"])
    return "\n".join(body)


def parse_args():
    parser = argparse.ArgumentParser(description="Send daily CB strategy LINE notifications.")
    parser.add_argument("--date", default=datetime.today().strftime("%Y-%m-%d"), help="Notification date, YYYY-MM-DD.")
    parser.add_argument("--dry-run", action="store_true", help="Print the message without sending it.")
    parser.add_argument("--alerts-only", action="store_true", help="Only send on buy/sell trigger days.")
    return parser.parse_args()


def main():
    args = parse_args()
    config = ensure_config()
    notify_token = (config.get("line_notify_token") or "").strip()
    channel_access_token = (config.get("line_channel_access_token") or "").strip()
    to_ids = [v.strip() for v in [config.get("line_user_id"), config.get("line_group_id")] if (v or "").strip()]
    web_url = config.get("website_url") or DEFAULT_WEB_URL

    tracks_path = os.path.join(DATA_DIR, "active_tracks.json")
    tracks = load_json(tracks_path, [])
    if not isinstance(tracks, list):
        print("Invalid active_tracks.json format.")
        return 1

    message = build_message(tracks, args.date, web_url, alerts_only=args.alerts_only)
    if not message:
        print(f"No buy or sell signals triggered on {args.date}. alerts-only mode skipped.")
        return 0

    print("Prepared LINE message:")
    print(message)

    if args.dry_run:
        print("Dry run enabled; message was not sent.")
        return 0

    if not notify_token and not (channel_access_token and to_ids):
        print("Line notifications are not configured. Skipping active push.")
        return 0

    failures = []
    if notify_token:
        try:
            send_line_notify(notify_token, message)
        except Exception as exc:
            failures.append(str(exc))

    if channel_access_token and to_ids:
        for to_id in to_ids:
            try:
                send_line_messaging_api(channel_access_token, to_id, message)
            except Exception as exc:
                failures.append(str(exc))

    if failures:
        for failure in failures:
            print(failure)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
