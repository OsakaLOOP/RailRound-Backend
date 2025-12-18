import json
import glob
import os
import sys

# Configuration
GEOJSON_DIR = "./dist/geojson/"

class Color:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

def validate_file(filepath):
    """
    Validates a single GeoJSON file for line uniqueness and transfer referential integrity.
    Returns a list of error strings.
    """
    filename = os.path.basename(filepath)
    errors = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return [f"Fatal: Cannot read JSON - {str(e)}"]

    features = data.get("features", [])
    
    # 1. Collect all defined Lines
    defined_lines = set()
    line_duplicates = set()
    
    # 2. Collect all Station transfers to check
    stations_to_check = []

    for idx, feature in enumerate(features):
        props = feature.get("properties", {})
        f_type = props.get("type")
        name = props.get("name", "Unknown")
        
        if f_type == "line":
            if name in defined_lines:
                line_duplicates.add(name)
            else:
                defined_lines.add(name)
        
        elif f_type == "station":
            transfers = props.get("transfers", [])
            # Ensure transfers is a list
            if not isinstance(transfers, list):
                errors.append(f"Station '{name}' (idx {idx}): 'transfers' field is not a list.")
                continue
            
            if transfers:
                stations_to_check.append({
                    "name": name,
                    "transfers": transfers,
                    "index": idx
                })

    # Error Reporting: Duplicate Lines
    if line_duplicates:
        for dup in line_duplicates:
            errors.append(f"Duplicate Line Name detected: '{dup}'")

    # Error Reporting: Invalid Transfers
    for st in stations_to_check:
        for trans_line in st["transfers"]:
            if trans_line not in defined_lines:
                errors.append(
                    f"Invalid Transfer: Station '{st['name']}' refers to line '{trans_line}', "
                    f"but '{trans_line}' is not defined in this file."
                )

    return errors

def main():
    if not os.path.exists(GEOJSON_DIR):
        print(f"{Color.FAIL}Directory not found: {GEOJSON_DIR}{Color.ENDC}")
        return

    files = glob.glob(os.path.join(GEOJSON_DIR, "*.geojson"))
    if not files:
        print(f"{Color.WARNING}No .geojson files found in {GEOJSON_DIR}{Color.ENDC}")
        return

    print(f"{Color.HEADER}Starting validation on {len(files)} files in {GEOJSON_DIR}...{Color.ENDC}\n")
    
    total_errors = 0
    files_with_errors = 0

    for filepath in sorted(files):
        filename = os.path.basename(filepath)
        file_errors = validate_file(filepath)
        
        if file_errors:
            files_with_errors += 1
            total_errors += len(file_errors)
            print(f"{Color.FAIL}[FAIL] {filename}{Color.ENDC}")
            for err in file_errors:
                print(f"  - {err}")
            print("") 
        else:
            print(f"{Color.OKGREEN}[PASS] {filename}{Color.ENDC}")

    print("-" * 50)
    if total_errors > 0:
        print(f"{Color.FAIL}Validation Failed.{Color.ENDC}")
        print(f"Files with errors: {files_with_errors}")
        print(f"Total violations:  {total_errors}")
        sys.exit(1)
    else:
        print(f"{Color.OKBLUE}All checks passed. Data integrity verified.{Color.ENDC}")
        sys.exit(0)

if __name__ == "__main__":
    main()