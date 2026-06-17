import os
import json
import math
import sys

# Reconfigure stdout/stderr for Windows UTF-8 terminal
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")
PRICES_DIR = os.path.join(DATA_DIR, "prices")

def clean_value(val):
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
    return val

def clean_dict_or_list(obj):
    if isinstance(obj, dict):
        return {k: clean_dict_or_list(clean_value(v)) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_dict_or_list(clean_value(x)) for x in obj]
    else:
        return obj

def main():
    # 1. Clean individual price files
    if os.path.exists(PRICES_DIR):
        price_files = [f for f in os.listdir(PRICES_DIR) if f.endswith(".json")]
        cleaned_prices = 0
        for pf_name in price_files:
            pf_path = os.path.join(PRICES_DIR, pf_name)
            try:
                # Read raw file text to replace NaN before json parsing if it fails
                with open(pf_path, "r", encoding="utf-8") as f:
                    text = f.read()
                
                # Replace literal NaN/Infinity if any
                cleaned_text = text.replace(": NaN", ": null").replace(": -Infinity", ": null").replace(": Infinity", ": null")
                
                # Parse to ensure it is valid
                data = json.loads(cleaned_text)
                cleaned_data = clean_dict_or_list(data)
                
                with open(pf_path, "w", encoding="utf-8") as f:
                    json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
                cleaned_prices += 1
            except Exception as e:
                print(f"Error cleaning {pf_name}: {e}")
        print(f"Cleaned {cleaned_prices} price files.")

    # 2. Clean analysis results
    analysis_path = os.path.join(DATA_DIR, "analysis_results.json")
    if os.path.exists(analysis_path):
        try:
            with open(analysis_path, "r", encoding="utf-8") as f:
                text = f.read()
            cleaned_text = text.replace(": NaN", ": null").replace(": -Infinity", ": null").replace(": Infinity", ": null")
            data = json.loads(cleaned_text)
            cleaned_data = clean_dict_or_list(data)
            with open(analysis_path, "w", encoding="utf-8") as f:
                json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
            print("Successfully cleaned analysis_results.json.")
        except Exception as e:
            print(f"Error cleaning analysis_results.json: {e}")

if __name__ == "__main__":
    main()
