import os
import sys
import json
import requests
from datetime import datetime

# Reconfigure stdout/stderr for Windows UTF-8 terminal
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
CONFIG_PATH = os.path.join(BASE_DIR, "backend", "config.json")

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception as e:
                print(f"Error loading {path}: {e}")
    return {}

def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def send_line_notify(token, message):
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"message": message}
    try:
        res = requests.post(url, headers=headers, data=payload, timeout=10)
        if res.status_code == 200:
            print("Line Notify sent successfully!")
        else:
            print(f"Failed to send Line Notify: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Error sending Line Notify: {e}")

def send_line_messaging_api(channel_access_token, to_id, message):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {channel_access_token}"
    }
    payload = {
        "to": to_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            print("Line Messaging API push sent successfully!")
        else:
            print(f"Failed to send Line Messaging API: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Error sending Line Messaging API: {e}")

def main():
    # 1. Initialize or load config
    config = load_json(CONFIG_PATH)
    if not config:
        # Create a default template config.json if not exists
        config = {
            "line_notify_token": "",
            "line_channel_access_token": "",
            "line_user_id": "",
            "line_group_id": "",
            "website_url": "https://gaiautoupload.github.io/cb-arbitrage-platform/"
        }
        save_json(config, CONFIG_PATH)
        print(f"Created template configuration at {CONFIG_PATH}. Please configure your Line tokens/IDs.")
        
        # Also ensure config.json is in .gitignore
        gitignore_path = os.path.join(BASE_DIR, ".gitignore")
        has_config = False
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r", encoding="utf-8") as f:
                if "backend/config.json" in f.read():
                    has_config = True
        if not has_config:
            with open(gitignore_path, "a", encoding="utf-8") as f:
                f.write("\nbackend/config.json\n")
            print("Added backend/config.json to .gitignore to prevent leaking tokens.")

    # 2. Check tokens
    notify_token = config.get("line_notify_token")
    channel_access_token = config.get("line_channel_access_token")
    user_id = config.get("line_user_id") or config.get("line_group_id")
    web_url = config.get("website_url", "https://gaiautoupload.github.io/cb-arbitrage-platform/")

    if not notify_token and not (channel_access_token and user_id):
        print("Line notifications are not configured. Skipping active push.")
        return

    # 3. Load active tracks
    tracks_path = os.path.join(DATA_DIR, "active_tracks.json")
    if not os.path.exists(tracks_path):
        print("active_tracks.json not found. Skipping notifications.")
        return

    tracks = load_json(tracks_path)
    if not isinstance(tracks, list):
        print("Invalid format in active_tracks.json. Skipping.")
        return

    today_str = datetime.today().strftime("%Y-%m-%d")
    print(f"Checking for strategy triggers on {today_str}...")

    alerts = []

    for track in tracks:
        stock_code = track.get("stock_code")
        company_name = track.get("company_name")
        bond_name = track.get("bond_name")
        strategy_info = track.get("strategy_info", {})
        strat_name = strategy_info.get("name", "未定義策略")
        win_rate = strategy_info.get("win_rate", 0)
        avg_return = strategy_info.get("avg_return", 0)
        status_type = track.get("status_type", "") # "success", "failed", "pending"

        stations = track.get("stations", [])
        for station in stations:
            s_name = station.get("name")
            s_date = station.get("date")
            s_status = station.get("status")

            if s_date == today_str:
                # Event 1: Buy Signal (T-15 or T-16 or T-14 depending on matching today's date)
                if "T-15" in s_name or "T-16" in s_name or "T-14" in s_name:
                    # Only alert if the status check succeeded (not failed)
                    if status_type != "failed" and s_status != "failed":
                        msg = (
                            f"\n📢 【買入訊號】可轉債策略通知\n"
                            f"📌 標的：{company_name} ({stock_code})\n"
                            f"🏷️ 債券：{bond_name}\n"
                            f"🎯 策略：{strat_name}\n"
                            f"📊 勝率：{win_rate}% | 平均報酬：{avg_return}%\n"
                            f"💡 動作：符合籌碼卡位條件，建議今日開盤佈局現貨！\n"
                            f"🔗 詳情請見系統網站：{web_url}"
                        )
                        alerts.append(msg)
                
                # Event 2: Sell Signal (T+19 結算出場)
                elif "結算出場" in s_name or "T+19" in s_name:
                    msg = (
                        f"\n⚠️ 【賣出訊號】可轉債策略通知\n"
                        f"📌 標的：{company_name} ({stock_code})\n"
                        f"🏷️ 債券：{bond_name}\n"
                        f"🎯 策略：{strat_name}\n"
                        f"💡 動作：本日為 T+19 結算出場日，請於今日收盤無條件賣出結算！\n"
                        f"🔗 詳情請見系統網站：{web_url}"
                    )
                    alerts.append(msg)

    # 4. Push Alerts
    if alerts:
        combined_message = "\n====================".join(alerts)
        print(f"Triggered alerts:\n{combined_message}")
        
        if notify_token:
            send_line_notify(notify_token, combined_message)
        if channel_access_token and user_id:
            send_line_messaging_api(channel_access_token, user_id, combined_message)
    else:
        print("No buy or sell signals triggered today.")

if __name__ == "__main__":
    main()
