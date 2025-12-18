import json
import csv
import os

COMPANY_DATA = "./public/company_data.json"
EKIDATA_CSV = "./public/ekidata/company20251015.csv"

def clean_name(name):
    """移除法人后缀以标准化名称"""
    suffixes = ["株式会社", "（株）", "(株)", "一般社団法人"]
    for s in suffixes:
        name = name.replace(s, "")
    return name.strip()

def main():
    if not os.path.exists(COMPANY_DATA) or not os.path.exists(EKIDATA_CSV):
        print("Error: Missing data files.")
        return

    # 1. Load Local Company Names (Keys)
    with open(COMPANY_DATA, 'r', encoding='utf-8') as f:
        local_comps = set(json.load(f).keys())

    # 2. Load and Clean Ekidata Company Names
    eki_map = {} # Cleaned -> Original
    with open(EKIDATA_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = row.get("company_name_h", "")
            if raw:
                cleaned = clean_name(raw)
                eki_map[cleaned] = raw

    # 3. Compare
    eki_cleaned_set = set(eki_map.keys())
    matched = local_comps & eki_cleaned_set
    missing = local_comps - eki_cleaned_set

    # 4. Report
    print(f"Total Local Companies: {len(local_comps)}")
    print(f"Total Ekidata Entries: {len(eki_map)}")
    print(f"Matches: {len(matched)}")

    if missing:
        print(f"\n[MISMATCH] Found {len(missing)} missing companies:")
        for m in sorted(missing):
            print(f"  - {m}")
            # Simple suggestion lookup
            candidates = [raw for raw in eki_map.values() if m in raw or raw in m]
            if candidates:
                print(f"    (Did you mean: {candidates}?)")
    else:
        print("\n[SUCCESS] All companies matched successfully.")

if __name__ == "__main__":
    main()