import json
import os
import re
import sys
from html import unescape
from html.parser import HTMLParser

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
CACHE_DIR = os.path.join(DATA_DIR, "html_cache")


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.parts.append(text)

    def get_text(self):
        return "\n".join(self.parts)


def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def html_to_text(html_text):
    parser = TextExtractor()
    parser.feed(html_text)
    return unescape(parser.get_text())


def minguo_text_to_ad(text):
    if not text:
        return None
    match = re.search(r"(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if match:
        year = int(match.group(1)) + 1911
        month = int(match.group(2))
        day = int(match.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"
    match = re.search(r"(\d{2,3})/(\d{1,2})/(\d{1,2})", text)
    if match:
        year = int(match.group(1)) + 1911
        month = int(match.group(2))
        day = int(match.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def extract_field(text, label):
    match = re.search(rf"{re.escape(label)}\s*[:：]\s*([^\n。]+)", text)
    return match.group(1).strip() if match else None


def extract_announcement_date(text):
    match = re.search(r"發文日期[:：]?\s*中華民國\s*(\d{2,3}年\d{1,2}月\d{1,2}日)", text)
    return match.group(1) if match else None


def parse_html_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        html = file.read()

    text = clean_text(html_to_text(html))

    announcement_date_minguo = extract_announcement_date(text)
    company_name = extract_field(text, "發行公司名稱")
    bond_name = extract_field(text, "債券名稱")
    cb_code = extract_field(text, "代碼")
    short_name = extract_field(text, "簡稱")
    issue_amount = extract_field(text, "發行總面額")
    issue_date_minguo = extract_field(text, "發行日")
    maturity_date_minguo = extract_field(text, "到期日")

    if cb_code:
        code_match = re.search(r"\d+", cb_code)
        cb_code = code_match.group(0) if code_match else None

    stock_code = cb_code[:4] if cb_code and len(cb_code) >= 4 else None

    return {
        "file_id": os.path.splitext(os.path.basename(file_path))[0],
        "company_name": company_name,
        "bond_name": bond_name,
        "cb_code": cb_code,
        "stock_code": stock_code,
        "short_name": short_name,
        "announcement_date_minguo": announcement_date_minguo,
        "announcement_date": minguo_text_to_ad(announcement_date_minguo),
        "issue_date_minguo": issue_date_minguo,
        "issue_date": minguo_text_to_ad(issue_date_minguo),
        "maturity_date_minguo": maturity_date_minguo,
        "maturity_date": minguo_text_to_ad(maturity_date_minguo),
        "issue_amount": issue_amount,
    }


def main():
    parsed_bonds = []
    if not os.path.exists(CACHE_DIR):
        print("No cache directory found. Please run downloader.py first.")
        return

    files = sorted(f for f in os.listdir(CACHE_DIR) if f.endswith(".html"))
    print(f"Found {len(files)} cached HTML files to parse.")

    for idx, name in enumerate(files, start=1):
        file_path = os.path.join(CACHE_DIR, name)
        try:
            bond_info = parse_html_file(file_path)
            if bond_info["stock_code"] and bond_info["stock_code"].isdigit():
                parsed_bonds.append(bond_info)
                print(f"[{idx}/{len(files)}] Parsed: {bond_info['company_name']} ({bond_info['stock_code']})")
            else:
                print(f"[{idx}/{len(files)}] Skipped: {name}")
        except Exception as exc:
            print(f"Error parsing file {name}: {exc}")

    output_path = os.path.join(DATA_DIR, "parsed_bonds.json")
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(parsed_bonds, file, ensure_ascii=False, indent=2)

    print(f"Saved {len(parsed_bonds)} structured bond records to {output_path}")


if __name__ == "__main__":
    main()
