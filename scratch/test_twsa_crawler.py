import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8')

def test_fetch():
    url = "https://web.twsa.org.tw/Edoc2/Default.aspx?Year=2026"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    session = requests.Session()
    response = session.get(url, headers=headers, timeout=15)
    print("Apparent Encoding:", response.apparent_encoding)
    
    # Try different encodings
    encodings_to_try = [response.apparent_encoding, 'utf-8', 'big5', 'gbk', 'gb18030', 'cp950']
    for enc in encodings_to_try:
        try:
            print(f"\n--- Trying {enc} ---")
            text = response.content.decode(enc)
            soup = BeautifulSoup(text, "html.parser")
            tables = soup.find_all("table")
            if len(tables) > 4:
                table = tables[4]
                rows = table.find_all("tr")
                if len(rows) > 6:
                    cells = [td.get_text(strip=True) for td in rows[6].find_all(["th", "td"])]
                    print(f"Row 6 preview: {cells}")
                    # If we see legible Chinese, this encoding is correct!
                    if any("申報" in c or "公司" in c or "承銷" in c or "公告" in c or "申購" in c for c in cells):
                        print(f"===> Success! {enc} is the correct encoding!")
                        break
        except Exception as e:
            print(f"Failed decoding with {enc}: {e}")

if __name__ == "__main__":
    test_fetch()
