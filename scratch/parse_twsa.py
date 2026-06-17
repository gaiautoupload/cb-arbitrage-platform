import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8')

def test_fetch():
    url = "https://web.twsa.org.tw/Edoc2/Default.aspx?Year=2026"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": url,
    }
    
    session = requests.Session()
    get_res = session.get(url, headers=headers, timeout=15)
    
    soup = BeautifulSoup(get_res.text, "html.parser")
    viewstate = soup.find("input", {"name": "__VIEWSTATE"})["value"]
    generator = soup.find("input", {"name": "__VIEWSTATEGENERATOR"})["value"]
    validation = soup.find("input", {"name": "__EVENTVALIDATION"})["value"]
    
    payload = {
        "__EVENTTARGET": "ctl00$cphMain$rblReportType$1",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
        "__VIEWSTATE": viewstate,
        "__VIEWSTATEGENERATOR": generator,
        "__EVENTVALIDATION": validation,
        "ctl00$cphMain$ddlYear": "2026",
        "ctl00$cphMain$rblReportType": "Auction"
    }
    
    post_res = session.post(url, data=payload, headers=headers, timeout=15)
    post_soup = BeautifulSoup(post_res.text, "html.parser")
    tables = post_soup.find_all("table")
    
    if len(tables) > 4:
        table = tables[4]
        rows = table.find_all("tr")
        print(f"Total rows in Auction Table: {len(rows)}")
        
        start_idx = max(0, len(rows) - 20)
        for idx in range(start_idx, len(rows)):
            cells = [td.get_text(strip=True) for td in rows[idx].find_all(["th", "td"])]
            print(f"Row {idx}: {cells}")

if __name__ == "__main__":
    test_fetch()
