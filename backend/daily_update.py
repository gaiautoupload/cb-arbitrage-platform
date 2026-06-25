import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
STATUS_PATH = os.path.join(DATA_DIR, "update_status.json")


def script_path(name):
    return os.path.join(BASE_DIR, "backend", name)


def recent_month_window(months_back=2):
    today = datetime.today()
    month_index = today.year * 12 + today.month - 1 - months_back
    year = month_index // 12
    month = month_index % 12 + 1
    return year, month


def build_pipeline():
    start_year, start_month = recent_month_window()
    return [
        {
            "name": "TPEx 可轉債公告下載",
            "cmd": [
                sys.executable,
                script_path("downloader.py"),
                "--start-year",
                str(start_year),
                "--start-month",
                str(start_month),
            ],
            "required": True,
        },
        {"name": "MOPS 重大訊息爬蟲", "cmd": [sys.executable, script_path("mops_crawler.py")], "required": True},
        {"name": "承銷競拍時程爬蟲", "cmd": [sys.executable, script_path("twsa_crawler.py")], "required": True},
        {"name": "可轉債公告解析", "cmd": [sys.executable, script_path("parser.py")], "required": True},
        {"name": "股價更新", "cmd": [sys.executable, script_path("stock_fetcher.py")], "required": True},
        {"name": "三大法人更新", "cmd": [sys.executable, script_path("inst_fetcher.py")], "required": True},
        {"name": "法人資料合併至價格", "cmd": [sys.executable, script_path("merge_inst_to_prices.py")], "required": True},
        {"name": "價格資料清理", "cmd": [sys.executable, script_path("clean_nan_prices.py")], "required": True},
        {"name": "股本資料更新", "cmd": [sys.executable, script_path("fetch_shares_outstanding.py")], "required": False, "timeout": 180},
        {"name": "事件階段連結", "cmd": [sys.executable, script_path("bond_stage_linker.py")], "required": True},
        {"name": "策略回測與統計更新", "cmd": [sys.executable, script_path("analyzer.py")], "required": True},
        {"name": "前台執行中事件更新", "cmd": [sys.executable, script_path("active_tracks_builder.py")], "required": True},
        {"name": "LINE 策略提醒", "cmd": [sys.executable, script_path("line_notifier.py")], "required": False},
    ]


def run_command(command, cwd=BASE_DIR, timeout=None):
    return subprocess.run(command, cwd=cwd, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def run_step(step, retries, retry_delay):
    started = datetime.now()
    result = {
        "name": step["name"],
        "required": step.get("required", True),
        "started_at": started.isoformat(timespec="seconds"),
        "attempts": 0,
        "returncode": None,
        "status": "pending",
    }

    for attempt in range(1, retries + 1):
        result["attempts"] = attempt
        print(f"\n=== {step['name']} (attempt {attempt}/{retries}) ===")
        try:
            completed = run_command(step["cmd"], timeout=step.get("timeout"))
            result["returncode"] = completed.returncode
        except subprocess.TimeoutExpired:
            result["returncode"] = 124
            print(f"Step timed out after {step.get('timeout')} seconds: {step['name']}")
            if not step.get("required", True):
                break
            completed = None

        if completed is None:
            print(f"Step failed with exit code {result['returncode']}: {step['name']}")
            if attempt < retries:
                time.sleep(retry_delay)
            continue
        elif completed.returncode == 0:
            result["status"] = "ok"
            break

        print(f"Step failed with exit code {completed.returncode}: {step['name']}")
        if attempt < retries:
            time.sleep(retry_delay)

    finished = datetime.now()
    result["finished_at"] = finished.isoformat(timespec="seconds")
    result["duration_sec"] = round((finished - started).total_seconds(), 1)
    if result["status"] != "ok":
        result["status"] = "failed"
    return result


def write_status(status):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def git_has_data_changes():
    completed = subprocess.run(
        ["git", "status", "--short", "backend/data"],
        cwd=BASE_DIR,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    return bool(completed.stdout.strip()), completed.stdout.strip()


def commit_and_push():
    has_changes, status_text = git_has_data_changes()
    if not has_changes:
        print("No backend/data changes to commit.")
        return {"status": "skipped", "reason": "no_data_changes"}

    print("Data changes detected:")
    print(status_text)

    run_command(["git", "add", "backend/data"])
    message = f"Auto update strategy data {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    commit = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=BASE_DIR,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if commit.returncode != 0:
        print(commit.stdout)
        print(commit.stderr)
        return {"status": "failed", "stage": "commit", "returncode": commit.returncode}

    push = subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=BASE_DIR,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if push.returncode != 0:
        print(push.stdout)
        print(push.stderr)
        return {"status": "failed", "stage": "push", "returncode": push.returncode}

    print(push.stdout)
    return {"status": "ok", "commit_message": message}


def parse_args():
    parser = argparse.ArgumentParser(description="Run the daily CB strategy update pipeline.")
    parser.add_argument("--push", action="store_true", help="Commit backend/data changes and push origin/main.")
    parser.add_argument("--no-notify", action="store_true", help="Skip LINE notification step.")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-delay", type=int, default=20)
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(LOG_DIR, exist_ok=True)

    steps = build_pipeline()
    if args.no_notify:
        steps = [step for step in steps if step["name"] != "LINE 策略提醒"]

    status = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": None,
        "ok": False,
        "steps": [],
        "git": None,
    }
    write_status(status)

    for step in steps:
        result = run_step(step, args.retries, args.retry_delay)
        status["steps"].append(result)
        write_status(status)

        if result["status"] != "ok" and result["required"]:
            status["finished_at"] = datetime.now().isoformat(timespec="seconds")
            status["ok"] = False
            write_status(status)
            print(f"Required step failed: {step['name']}")
            return 1

    if args.push:
        status["git"] = commit_and_push()
        write_status(status)
        if status["git"].get("status") == "failed":
            return 1

    status["finished_at"] = datetime.now().isoformat(timespec="seconds")
    status["ok"] = True
    write_status(status)
    print("\nDaily update pipeline complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
