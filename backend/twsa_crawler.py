import os
import sys
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Reconfigure stdout/stderr for Windows UTF-8 terminal
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def clean_company_name(name):
    if not name:
        return ""
    import re
    # Normalize character variants (e.g. 晧 -> 皓, 台 -> 臺)
    name = name.replace("晧", "皓").replace("台", "臺")
    # Extract content inside parentheses if it contains Chinese characters
    match = re.search(r'\(([\u4e00-\u9fa5a-zA-Z0-9\-–]+)\)', name)
    if match:
        name = match.group(1)
    for suffix in ["股份有限公司", "股份公司", "-KY", "科技", "工業", "建設", "電機", "電子", "製造", "化學", "開發", "國際", "集團", "投資控股", "投控", "實業"]:
        name = name.replace(suffix, "")
    return name.strip()

def save_raw_dataset(source_folder, filename, content):
    try:
        today_dir = os.path.join("D:\\dataset", source_folder, datetime.today().strftime("%Y%m%d"))
        os.makedirs(today_dir, exist_ok=True)
        file_path = os.path.join(today_dir, filename)
        mode = "w" if isinstance(content, str) else "wb"
        encoding = "utf-8" if isinstance(content, str) else None
        with open(file_path, mode, encoding=encoding) as f:
            f.write(content)
        print(f"Saved raw dataset to {file_path}")
    except Exception as e:
        print(f"Failed to save raw dataset to D:\\dataset: {e}")

def main():
    url = "https://web.twsa.org.tw/Edoc2/Default.aspx?Year=2026"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": url,
    }
    
    # Load metadata for ticker lookup
    metadata = load_json(os.path.join(DATA_DIR, "stock_metadata.json"))
    
    # Build a comprehensive name mapping dictionary
    name_to_ticker = {}
    
    # 1. From parsed_bonds.json
    parsed_bonds = load_json(os.path.join(DATA_DIR, "parsed_bonds.json"))
    if isinstance(parsed_bonds, list):
        for item in parsed_bonds:
            cname = item.get("company_name")
            scode = item.get("stock_code")
            if cname and scode:
                name_to_ticker[cname] = scode
                name_to_ticker[clean_company_name(cname)] = scode
                
    # 2. From linked_bond_stages.json
    stages = load_json(os.path.join(DATA_DIR, "linked_bond_stages.json"))
    if isinstance(stages, list):
        for item in stages:
            cname = item.get("company_name")
            scode = item.get("stock_code")
            if cname and scode:
                name_to_ticker[cname] = scode
                name_to_ticker[clean_company_name(cname)] = scode

    # 3. From D:\ai-theme-map-site\ticker_registry_tw.json
    registry_path = "D:\\ai-theme-map-site\\ticker_registry_tw.json"
    if os.path.exists(registry_path):
        registry = load_json(registry_path)
        if isinstance(registry, dict):
            for scode, item in registry.items():
                # Index both main name and aliases
                names = [item.get("name")] + item.get("aliases", [])
                for cname in names:
                    if cname and scode:
                        name_to_ticker[cname] = scode
                        name_to_ticker[clean_company_name(cname)] = scode

    def find_ticker(full_name):
        if not full_name:
            return None
        # 1. Try exact full name
        if full_name in name_to_ticker:
            return name_to_ticker[full_name]
            
        # 2. Try cleaned name
        cname = clean_company_name(full_name)
        if cname in name_to_ticker:
            return name_to_ticker[cname]
            
        # 3. Fuzzy matching: check if any key in name_to_ticker (length >= 2) is a substring, or vice-versa
        for name_key, scode in name_to_ticker.items():
            if len(name_key) < 2:
                continue
            c_key = clean_company_name(name_key)
            if len(c_key) < 2:
                continue
            if c_key in cname or cname in c_key:
                return scode
        return None

    print("Fetching TWSA Edoc2 initial page...")
    session = requests.Session()
    try:
        get_res = session.get(url, headers=headers, timeout=15)
        if get_res.status_code != 200:
            print("Failed to GET TWSA page")
            return
            
        soup = BeautifulSoup(get_res.text, "html.parser")
        viewstate = soup.find("input", {"name": "__VIEWSTATE"})["value"]
        generator = soup.find("input", {"name": "__VIEWSTATEGENERATOR"})["value"]
        validation = soup.find("input", {"name": "__EVENTVALIDATION"})["value"]
        
        payload = {
            "__EVENTTARGET": "ctl00$cphMain$rblReportType$1", # Switch to Auction Tab
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "__VIEWSTATE": viewstate,
            "__VIEWSTATEGENERATOR": generator,
            "__EVENTVALIDATION": validation,
            "ctl00$cphMain$ddlYear": "2026",
            "ctl00$cphMain$rblReportType": "Auction"
        }
        
        print("Sending PostBack POST to switch to Auction Announcements...")
        post_res = session.post(url, data=payload, headers=headers, timeout=15)
        if post_res.status_code != 200:
            print("Failed to POST TWSA page")
            return
            
        # Save original raw data
        save_raw_dataset("twsa", "twsa_auction.html", post_res.text)
            
        post_soup = BeautifulSoup(post_res.text, "html.parser")
        tables = post_soup.find_all("table")
        if len(tables) <= 4:
            print("No auction table found in response")
            return
            
        table = tables[4]
        rows = table.find_all("tr")
        print(f"Successfully fetched {len(rows)} rows from TWSA Auction Table.")
        
        bids = []
        # Header is row 6
        for idx in range(7, len(rows)):
            cells = [td.get_text(strip=True) for td in rows[idx].find_all(["th", "td"])]
            if len(cells) < 8 or not cells[0]:
                continue
                
            serial = cells[0]
            company_name = cells[1]
            underwriter = cells[2]
            issue_type = cells[3]
            shares_thousand = cells[4]
            bidding_shares_thousand = cells[5]
            period = cells[6]
            min_price = cells[7]
            
            # Filter only convertible bonds (轉換公司債)
            if "轉換公司債" not in issue_type:
                continue
                
            # Find stock ticker using mapping
            ticker = find_ticker(company_name)
            
            bids.append({
                "serial": serial,
                "company_name": clean_company_name(company_name),
                "full_company_name": company_name,
                "ticker": ticker,
                "underwriter": underwriter,
                "bond_type": issue_type,
                "shares_thousand": shares_thousand,
                "bidding_shares_thousand": bidding_shares_thousand,
                "bidding_period": period,
                "min_price": min_price
            })
            
        out_path = os.path.join(DATA_DIR, "twsa_bids.json")
        save_json(bids, out_path)
        print(f"Parsed {len(bids)} convertible bond bidding events and saved to {out_path}")
        
    except Exception as e:
        print("Error crawling TWSA:", e)

if __name__ == "__main__":
    main()
