import os
import json
import sys

# Reconfigure stdout/stderr for Windows UTF-8 terminal
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
PRICES_DIR = os.path.join(DATA_DIR, "prices")

def main():
    inst_path = os.path.join(DATA_DIR, "institutional_data.json")
    if not os.path.exists(inst_path):
        print(f"Error: {inst_path} does not exist. Run inst_fetcher.py first.")
        return

    print("Loading institutional data...")
    with open(inst_path, "r", encoding="utf-8") as f:
        inst_db = json.load(f)
    print(f"Loaded institutional data for {len(inst_db)} dates.")

    if not os.path.exists(PRICES_DIR):
        print(f"Error: Prices directory {PRICES_DIR} does not exist.")
        return

    price_files = [f for f in os.listdir(PRICES_DIR) if f.endswith(".json")]
    print(f"Found {len(price_files)} stock price files to update.")

    updated_count = 0
    for pf_name in price_files:
        code = pf_name.replace(".json", "")
        pf_path = os.path.join(PRICES_DIR, pf_name)
        
        with open(pf_path, "r", encoding="utf-8") as f:
            prices = json.load(f)
            
        modified = False
        for p in prices:
            date_str = p.get("date")
            # Default to 0.0 if not found
            foreign_net = 0.0
            trust_net = 0.0
            
            if date_str in inst_db:
                day_data = inst_db[date_str]
                if code in day_data:
                    foreign_net = day_data[code].get("foreign_net", 0.0)
                    trust_net = day_data[code].get("trust_net", 0.0)
            
            # Update fields
            p["foreign_net"] = foreign_net
            p["trust_net"] = trust_net
            modified = True
            
        if modified:
            with open(pf_path, "w", encoding="utf-8") as f:
                json.dump(prices, f, ensure_ascii=False, indent=2)
            updated_count += 1

    print(f"Successfully merged institutional data into {updated_count} price files.")

if __name__ == "__main__":
    main()
