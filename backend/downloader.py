import os
import sys
import time
import base64
import json
import urllib.parse
import urllib.error
import urllib.request
import random
from datetime import datetime
import argparse

# Reconfigure stdout for UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
CACHE_DIR = os.path.join(DATA_DIR, "html_cache")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edge/122.0.0.0"
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
        "Referer": "https://www.tpex.org.tw/web/bond/announcement/announcement.php",
        "X-Requested-With": "XMLHttpRequest"
    }


class HttpResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = body.decode("utf-8-sig", errors="replace")

    def json(self):
        return json.loads(self.text)


def http_get(url, headers, timeout):
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return HttpResponse(response.getcode(), response.read())
    except urllib.error.HTTPError as exc:
        return HttpResponse(exc.code, exc.read())

def decode_base64(s):
    try:
        # Add padding if needed
        padding = len(s) % 4
        if padding:
            s += "=" * (4 - padding)
        return base64.b64decode(s).decode("utf-8")
    except Exception as e:
        print(f"Error decoding base64: {s}, error: {e}")
        return None

def fetch_monthly_announcements(date_str):
    """
    date_str format: 'YYYY/MM/DD', e.g., '2026/01/01'
    """
    url = f"https://www.tpex.org.tw/www/zh-tw/bond/announcement?date={urllib.parse.quote(date_str)}&id=&response=json"
    print(f"Fetching announcement list for {date_str}...")
    
    for attempt in range(5):
        try:
            headers = get_headers()
            time.sleep(random.uniform(1.5, 3.5))  # Randomized delay
            response = http_get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                sleep_time = (attempt + 1) * 10
                print(f"Rate limit 429 encountered for list. Sleeping {sleep_time}s...")
                time.sleep(sleep_time)
            else:
                print(f"Failed to fetch list: status code {response.status_code}. Retrying...")
                time.sleep(3)
        except Exception as e:
            print(f"Error fetching list for {date_str} (attempt {attempt+1}): {e}")
            time.sleep(5)
    return None

def download_detail_html(data_date, detail_param):
    """
    data_date format: '115/01/28' (Minguo date)
    detail_param: query string containing base64 file and id
    """
    # Parse query parameters
    params = urllib.parse.parse_qs(detail_param)
    file_b64 = params.get("file", [None])[0]
    id_b64 = params.get("id", [None])[0]
    
    if not file_b64 or not id_b64:
        return None
        
    filename = decode_base64(file_b64)
    doc_id = decode_base64(id_b64)
    
    if not filename or not doc_id:
        return None
        
    # Extract Minguo year and month from data_date (e.g. "115/01/28" -> "11501")
    parts = data_date.split("/")
    if len(parts) < 2:
        return None
    minguo_year_month = f"{parts[0]}{parts[1]}"
    
    local_path = os.path.join(CACHE_DIR, f"{doc_id}.html")
    if os.path.exists(local_path):
        return local_path
        
    # Construct the download URL
    download_url = f"https://www.tpex.org.tw/storage/eb_data/{minguo_year_month}/{filename}"
    print(f"Downloading: {download_url} -> {local_path}")
    
    for attempt in range(5):
        try:
            # Random sleep to prevent anti-scraping blocks
            time.sleep(random.uniform(1.0, 2.5))
            headers = get_headers()
            headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8"
            del headers["X-Requested-With"] # For regular file download
            
            resp = http_get(download_url, headers=headers, timeout=15)
            if resp.status_code == 200:
                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(resp.text)
                return local_path
            elif resp.status_code == 429:
                sleep_time = (attempt + 1) * 10
                print(f"Rate limit 429 encountered for detail {doc_id}. Sleeping {sleep_time}s...")
                time.sleep(sleep_time)
            else:
                print(f"Failed to download detail {doc_id}: HTTP {resp.status_code}. Retrying...")
                time.sleep(3)
        except Exception as e:
            print(f"Error downloading {download_url} (attempt {attempt+1}): {e}")
            time.sleep(5)
    return None

def iter_month_starts(start_year, start_month, end_year, end_month):
    year = start_year
    month = start_month
    while (year, month) <= (end_year, end_month):
        yield f"{year}/{month:02d}/01"
        month += 1
        if month == 13:
            year += 1
            month = 1


def parse_args():
    today = datetime.today()
    parser = argparse.ArgumentParser(description="Download TPEx convertible bond announcements.")
    parser.add_argument("--start-year", type=int, default=2020)
    parser.add_argument("--start-month", type=int, default=1)
    parser.add_argument("--end-year", type=int, default=today.year)
    parser.add_argument("--end-month", type=int, default=today.month)
    return parser.parse_args()


def main():
    args = parse_args()
    months = list(iter_month_starts(args.start_year, args.start_month, args.end_year, args.end_month))
    
    print(f"Crawling months: {months}")
    
    # Load existing announcements list if available to avoid full recrawl of months
    list_path = os.path.join(DATA_DIR, "announcement_list.json")
    all_items = []
    existing_ids = set()
    if os.path.exists(list_path):
        try:
            with open(list_path, "r", encoding="utf-8") as f:
                all_items = json.load(f)
            # Find unique identifiers to avoid duplicates
            for item in all_items:
                params = urllib.parse.parse_qs(item["detail_param"])
                id_b64 = params.get("id", [None])[0]
                if id_b64:
                    doc_id = decode_base64(id_b64)
                    if doc_id:
                        existing_ids.add(doc_id)
            print(f"Loaded {len(all_items)} existing items from {list_path}")
        except Exception as e:
            print(f"Failed to load existing announcement list: {e}")
            all_items = []
    
    new_items_added = 0
    for m in months:
        data = fetch_monthly_announcements(m)
        if not data or "tables" not in data or len(data["tables"]) == 0:
            continue
            
        table = data["tables"][0]
        rows = table.get("data", [])
        print(f"Found {len(rows)} announcements for {m}")
        
        for row in rows:
            # row structure: [項次, 資料日期, 發文字號, 主旨, 詳細資料]
            if len(row) < 5:
                continue
            
            # Check if already in our existing items list
            detail_param = row[4]
            params = urllib.parse.parse_qs(detail_param)
            id_b64 = params.get("id", [None])[0]
            if id_b64:
                doc_id = decode_base64(id_b64)
                if doc_id and doc_id in existing_ids:
                    continue # Skip duplicate
            
            item = {
                "idx": row[0],
                "date": row[1],
                "doc_no": row[2],
                "subject": row[3],
                "detail_param": row[4]
            }
            all_items.append(item)
            if id_b64 and doc_id:
                existing_ids.add(doc_id)
            new_items_added += 1
            
    # Save the updated list to a JSON file
    with open(list_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print(f"Saved/Updated {len(all_items)} total announcement metadata to {list_path} (added {new_items_added} new items)")
    
    # Download detailed HTML pages
    success_count = 0
    for idx, item in enumerate(all_items):
        subject = item["subject"]
        # Filter for convertible bonds (轉換公司債 or 轉換債 or 轉換 or 交換)
        if "轉換" in subject or "交換" in subject:
            # Check if already downloaded
            params = urllib.parse.parse_qs(item["detail_param"])
            id_b64 = params.get("id", [None])[0]
            doc_id = decode_base64(id_b64) if id_b64 else None
            if doc_id and os.path.exists(os.path.join(CACHE_DIR, f"{doc_id}.html")):
                success_count += 1
                continue
                
            print(f"[{idx+1}/{len(all_items)}] Processing CB: {subject}")
            local_file = download_detail_html(item["date"], item["detail_param"])
            if local_file:
                success_count += 1
                
    print(f"Finished downloading {success_count} detailed HTML files.")

if __name__ == "__main__":
    main()
