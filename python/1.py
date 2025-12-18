import os
import json
import csv
import glob
import math
import re
from difflib import SequenceMatcher
from typing import Set, Dict, List, Any, Tuple

# Configuration
EKIDATA_PATH = os.path.join('public', 'ekidata', 'station20251211free.csv')
GEOJSON_SEARCH_ROOT = './public/'  # Root directory to search for GeoJSON files
GEOJSON_NAME_KEYS = ['name', 'station_name', 'stationName', 'title'] # Priority keys for station name
GEOJSON_LINE_KEYS = ['line_name', 'line', 'railway', 'company'] # Priority keys for line/company name

def normalize_name(name: str) -> str:
    """
    Normalizes string for basic comparison (strip whitespace).
    """
    if not name:
        return ""
    return str(name).strip()

def to_full_width(text: str) -> str:
    """
    Converts half-width ASCII (letters, numbers) to full-width characters.
    Also handles space.
    """
    if not text:
        return ""
    
    trans = {}
    trans[0x0020] = 0x3000
    for i in range(0x0021, 0x007F):
        trans[i] = i + 0xFEE0
        
    return text.translate(trans)

def normalize_advanced(name: str) -> str:
    """
    Applies advanced normalization for fallback matching:
    1. Convert ASCII to Full-width.
    2. Replace small 'ヶ' with large 'ケ'.
    """
    name = to_full_width(name)
    name = name.replace('ヶ', 'ケ')
    return name

def clean_for_fuzzy(name: str) -> str:
    """
    Cleans station name for fuzzy matching:
    1. Removes 'JR' (case insensitive).
    2. Removes content within parentheses (both half-width and full-width).
    """
    # Remove JR
    name = re.sub(r'JR', '', name, flags=re.IGNORECASE)
    # Remove content in brackets (greedy inside)
    # Pattern: ( or （ -> anything -> ) or ）
    name = re.sub(r'[\(（].*?[\)）]', '', name)
    return name.strip()

def get_lcs_length(s1: str, s2: str) -> int:
    """
    Calculates the length of the Longest Common Substring between two strings.
    """
    match = SequenceMatcher(None, s1, s2).find_longest_match(0, len(s1), 0, len(s2))
    return match.size

def calculate_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """
    Calculates the Haversine distance between two points (lon, lat) in kilometers.
    """
    if not coord1 or not coord2:
        return -1.0

    R = 6371.0
    lon1, lat1 = map(math.radians, coord1)
    lon2, lat2 = map(math.radians, coord2)

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

def load_ekidata_names(filepath: str) -> Set[str]:
    names = set()
    if not os.path.exists(filepath):
        print(f"Error: Ekidata file not found at {filepath}")
        return names

    try:
        with open(filepath, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if 'station_name' in row:
                    clean_name = normalize_name(row['station_name'])
                    if clean_name:
                        names.add(clean_name)
    except Exception as e:
        print(f"Error reading Ekidata CSV: {e}")
    
    print(f"Loaded {len(names)} unique stations from Ekidata.")
    return names

def extract_geojson_data(root_dir: str) -> Dict[str, List[Dict[str, Any]]]:
    station_map: Dict[str, List[Dict[str, Any]]] = {}
    
    search_pattern = os.path.join(root_dir, '**', '*.geojson')
    files = glob.glob(search_pattern, recursive=True)
    
    print(f"Found {len(files)} GeoJSON files. Scanning contents...")

    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                features = []
                if data.get('type') == 'FeatureCollection':
                    features = data.get('features', [])
                elif data.get('type') == 'Feature':
                    features = [data]
                
                has_valid_line_feature = False
                for feature in features:
                    props = feature.get('properties', {})
                    if props.get('type') == 'line':
                        has_valid_line_feature = True
                        break
                
                if not has_valid_line_feature:
                    continue

                company_name = os.path.splitext(os.path.basename(file_path))[0]

                for feature in features:
                    props = feature.get('properties', {})
                    geom = feature.get('geometry', {})
                    
                    if not props:
                        continue
                    
                    if props.get('type') != 'station':
                        continue

                    found_name = None
                    for key in GEOJSON_NAME_KEYS:
                        if key in props:
                            found_name = props[key]
                            break
                    
                    if not found_name:
                        continue

                    clean_name = normalize_name(found_name)
                    if not clean_name:
                        continue

                    line_name = company_name
                    for key in GEOJSON_LINE_KEYS:
                        if key in props and props[key]:
                            line_name = normalize_name(props[key])
                            break
                    
                    transfers_raw = props.get('transfers', [])
                    transfers_set = set()
                    if isinstance(transfers_raw, list):
                        for t in transfers_raw:
                            if isinstance(t, str):
                                transfers_set.add(normalize_name(t))
                    
                    coords = None
                    if geom and geom.get('type') == 'Point':
                        c = geom.get('coordinates')
                        if c and len(c) >= 2:
                            coords = (float(c[0]), float(c[1]))

                    entry = {
                        'company': company_name,
                        'file': file_path,
                        'line': line_name,
                        'transfers': transfers_set,
                        'coords': coords,
                        'original_name': clean_name
                    }

                    if clean_name not in station_map:
                        station_map[clean_name] = []
                    
                    is_existing = any(e['company'] == company_name for e in station_map[clean_name])
                    if not is_existing:
                        station_map[clean_name].append(entry)

        except Exception as e:
            print(f"Warning: Failed to parse {file_path}: {e}")

    print(f"Loaded {len(station_map)} unique station names from GeoJSONs.")
    return station_map

def check_inter_company_duplicates(station_map: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    duplicates_report = {}

    for name, entries in station_map.items():
        if len(entries) < 2:
            continue
            
        collisions = []
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                entry_a = entries[i]
                entry_b = entries[j]
                
                line_a = entry_a['line']
                line_b = entry_b['line']
                
                is_valid_transfer = (line_a in entry_b['transfers']) or (line_b in entry_a['transfers'])
                
                if not is_valid_transfer:
                    dist = calculate_distance(entry_a['coords'], entry_b['coords'])
                    collisions.append({
                        'company1': entry_a['company'],
                        'company2': entry_b['company'],
                        'distance': dist
                    })
        
        if collisions:
            duplicates_report[name] = collisions

    return duplicates_report

def write_diff_report(filename: str, title: str, dataset: Set[str], metadata: Dict[str, List[Dict]] = None, suggestions: Dict[str, Dict] = None):
    """
    Writes simple difference reports. 
    If suggestions provided, appends best match info.
    """
    sorted_data = sorted(list(dataset))
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"# {title}\n")
        f.write(f"# Total Count: {len(sorted_data)}\n")
        f.write("-" * 80 + "\n")
        for name in sorted_data:
            line = name
            
            # 1. Source Metadata
            if metadata and name in metadata:
                companies = sorted(list(set(e['company'] for e in metadata[name])))
                if companies:
                    line += f" \t[Found in: {', '.join(companies)}]"
            
            # 2. Fuzzy Suggestions
            if suggestions and name in suggestions:
                sugg = suggestions[name]
                line += f" \t>> Best Match: {sugg['match']} (LCS Len: {sugg['score']})"
                
            f.write(line + "\n")
    print(f"Generated report: {filename}")

def write_duplicate_report(filename: str, title: str, duplicate_map: Dict[str, List[Dict[str, Any]]]):
    sorted_names = sorted(duplicate_map.keys())
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"# {title}\n")
        f.write(f"# Total Stations with conflicts: {len(sorted_names)}\n")
        f.write(f"{'STATION NAME':<20} | {'PAIR (Company A <-> Company B)':<50} | {'DISTANCE (km)':<15}\n")
        f.write("-" * 90 + "\n")
        
        for name in sorted_names:
            collisions = duplicate_map[name]
            for c in collisions:
                pair_str = f"{c['company1']} <-> {c['company2']}"
                dist_str = f"{c['distance']:.3f} km" if c['distance'] >= 0 else "N/A"
                f.write(f"{name:<20} | {pair_str:<50} | {dist_str:<15}\n")
                
    print(f"Generated report: {filename}")

def main():
    ekidata_names = load_ekidata_names(EKIDATA_PATH)
    geojson_data = extract_geojson_data(GEOJSON_SEARCH_ROOT)
    geojson_raw_names = set(geojson_data.keys())

    # --- Matching Process ---
    
    # Step 2a: Direct Match
    matched_names = geojson_raw_names & ekidata_names
    geojson_unmatched_1 = geojson_raw_names - ekidata_names
    
    # Step 2b: Advanced Match (Fullwidth, ヶ->ケ)
    extra_matches_original_names = set()
    for g_name in geojson_unmatched_1:
        adv_name = normalize_advanced(g_name)
        if adv_name in ekidata_names:
            extra_matches_original_names.add(g_name)
    
    final_matched_geojson_names = matched_names | extra_matches_original_names
    final_geojson_only = geojson_raw_names - final_matched_geojson_names
    
    # Reconstruct matched ekidata names to find what's TRULY unmatched in Ekidata
    ekidata_matched_names = matched_names.copy()
    for g_name in extra_matches_original_names:
        adv_name = normalize_advanced(g_name)
        if adv_name in ekidata_names:
            ekidata_matched_names.add(adv_name)
            
    final_ekidata_only = ekidata_names - ekidata_matched_names

    # --- Step 3: Fuzzy Suggestions for GeoJSON Unmatched ---
    # Goal: Find best match in final_ekidata_only for stations in final_geojson_only
    # Strategy: Clean name (remove JR/brackets) -> Find Longest Common Substring in unmatched ekidata
    
    fuzzy_suggestions = {}
    
    for g_name in final_geojson_only:
        # Clean the GeoJSON name
        cleaned_g = clean_for_fuzzy(g_name)
        if not cleaned_g:
            continue
            
        best_candidate = None
        best_score = 0
        
        for e_name in final_ekidata_only:
            # We compare cleaned GeoJSON name vs Raw Ekidata Unmatched Name
            # (assuming Ekidata names are already reasonably standard)
            score = get_lcs_length(cleaned_g, e_name)
            
            if score > best_score:
                best_score = score
                best_candidate = e_name
        
        # Threshold: At least 2 chars match to avoid noise
        if best_candidate and best_score >= 2:
            fuzzy_suggestions[g_name] = {
                'match': best_candidate, 
                'score': best_score,
                'cleaned': cleaned_g
            }

    # --- Check for Inter-Company Duplicates ---
    duplicate_map = check_inter_company_duplicates(geojson_data)
    
    # --- Output ---
    print("\n--- Comparison Results ---")
    print(f"Total GeoJSON Stations (Raw): {len(geojson_raw_names)}")
    print(f"Total Ekidata Stations: {len(ekidata_names)}")
    print("-" * 30)
    print(f"Exact Matches: {len(matched_names)}")
    print(f"Advanced Matches (Full-width/ケ): {len(extra_matches_original_names)}")
    print(f"Total Matches: {len(final_matched_geojson_names)}")
    print("-" * 30)
    print(f"Only in GeoJSON: {len(final_geojson_only)}")
    print(f"Only in Ekidata: {len(final_ekidata_only)}")
    print(f"Potential Duplicates (No Transfer Link): {len(duplicate_map)}")

    write_diff_report("diff_in_geojson_only.txt", 
                     "Stations found in GeoJSON but NOT in Ekidata (with Suggestions)", 
                     final_geojson_only, 
                     geojson_data, 
                     fuzzy_suggestions)
                     
    write_diff_report("diff_in_ekidata_only.txt", 
                     "Stations found in Ekidata but NOT in GeoJSON", 
                     final_ekidata_only)
    
    if duplicate_map:
        write_duplicate_report("duplicate_stations_across_companies.txt", 
                             "Stations with inter-company name collisions (No Transfer Link)", 
                             duplicate_map)

if __name__ == "__main__":
    main()