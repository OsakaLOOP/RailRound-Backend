import logging
import json
import hashlib
import pandas as pd
import sqlite3
import shapely
import os
import re
import math
from difflib import SequenceMatcher
from shapely.geometry import Point, Polygon, LineString, MultiLineString, shape

logger = logging.getLogger()

# --- Normalization Helpers (Copied from python/1.py) ---
def normalize_name(name: str) -> str:
    """Normalizes string for basic comparison (strip whitespace)."""
    if not name:
        return ""
    return str(name).strip()

def to_full_width(text: str) -> str:
    """Converts half-width ASCII (letters, numbers) to full-width characters."""
    if not text:
        return ""
    trans = {}
    trans[0x0020] = 0x3000
    for i in range(0x0021, 0x007F):
        trans[i] = i + 0xFEE0
    return text.translate(trans)

def normalize_advanced(name: str) -> str:
    """Applies advanced normalization: Full-width + 'ヶ'->'ケ'."""
    name = to_full_width(name)
    name = name.replace('ヶ', 'ケ')
    return name

def clean_for_fuzzy(name: str) -> str:
    """Cleans station name for fuzzy matching (removes JR, parentheses)."""
    name = re.sub(r'JR', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[\(（].*?[\)）]', '', name)
    return name.strip()

def get_lcs_length(s1: str, s2: str) -> int:
    """Calculates the length of the Longest Common Substring."""
    match = SequenceMatcher(None, s1, s2).find_longest_match(0, len(s1), 0, len(s2))
    return match.size

def calculate_distance(coord1, coord2) -> float:
    """Calculates Haversine distance between two points (lon, lat) in km."""
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
# --------------------------------------------------------

# 基本文件读写方法
def load_json(path):
    '''读取 JSON 文件'''
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"Successfully read JSON file: {path}")
        return data
    except Exception as e:
        logger.error(f"Error reading JSON file: {e}")
        # print(e)
        return {}

def load_csv(path):
    '''读取 CSV 文件'''
    try:
        df = pd.read_csv(path, encoding='utf-8')
        logger.info(f"Successfully read CSV file: {path}")
        return df
        
        
    except Exception as e:
        logger.error(f"Error reading CSV file: {e}")
        return pd.DataFrame()
    
def clean_name(name):
    suffixes = ["株式会社", "（株）", "(株)", "一般社団法人"]
    for s in suffixes:
        name = name.replace(s, "")
    return name.strip()

# 核心数据类定义

class ekidata_company:
    def __init__(self, company_path, line_path, patch_path, station_path=None):
        self.company_df = load_csv(company_path)
        self.company_patch = load_csv(patch_path)
        self.df_merged = pd.concat([self.company_df, self.company_patch], ignore_index=True)
        
        self.line_df = load_csv(line_path)
        self.station_df = load_csv(station_path) if station_path else pd.DataFrame()

        self.companyDict = {} # Mapping by Company Name (Cleaned)
        self._id_to_name_map = {} # Mapping by Company CD -> Company Name
        self.ekidata_lines = {} # company_cd -> { line_cd -> {name, alias, data} }
        self.ekidata_stations = {} # line_cd -> [ {station_cd, station_g_cd, name, ...} ]

        # 1. Process Company Data
        for row in self.df_merged.itertuples():
            c_name = clean_name(getattr(row, 'company_name_h', ''))
            c_cd = getattr(row, 'company_cd', None)
            rr_cd = getattr(row, 'rr_cd', None)

            # Store mapping
            self.companyDict[c_name] = {
                "cd": c_cd,
                "rr_cd": rr_cd,
                "lines": {} 
            }
            if c_cd is not None:
                self._id_to_name_map[c_cd] = c_name
                if c_cd not in self.ekidata_lines:
                    self.ekidata_lines[c_cd] = {}

        # 2. Process Line Data
        for row in self.line_df.itertuples():
            l_comp_cd = getattr(row, 'company_cd', None)
            l_cd = getattr(row, 'line_cd', None)
            l_name_h = getattr(row, 'line_name_h', '')
            l_name_k = getattr(row, 'line_name_k', '')
            l_alias = getattr(row, 'line_name', '')
            
            if l_comp_cd and l_cd:
                # Add to lookup
                if l_comp_cd in self.ekidata_lines:
                    self.ekidata_lines[l_comp_cd][l_cd] = {
                        "line_cd": l_cd,
                        "name_h": l_name_h,
                        "name_k": l_name_k,
                        "alias": l_alias
                    }

                    # Update companyDict (legacy support)
                    c_name = self._id_to_name_map.get(l_comp_cd)
                    if c_name and c_name in self.companyDict:
                        self.companyDict[c_name]["lines"][l_cd] = [l_name_h, l_alias]

        # 3. Process Station Data
        if not self.station_df.empty:
            for row in self.station_df.itertuples():
                s_line_cd = getattr(row, 'line_cd', None)
                s_cd = getattr(row, 'station_cd', None)
                s_g_cd = getattr(row, 'station_g_cd', None)
                s_name = getattr(row, 'station_name', '')

                if s_line_cd and s_cd:
                    if s_line_cd not in self.ekidata_stations:
                        self.ekidata_stations[s_line_cd] = []

                    self.ekidata_stations[s_line_cd].append({
                        "station_cd": s_cd,
                        "station_g_cd": s_g_cd,
                        "name": s_name,
                        "row_data": row
                    })

        logger.info(f"Loaded Ekidata: {len(self.companyDict)} companies, {len(self.ekidata_lines)} companies with lines, {len(self.ekidata_stations)} lines with stations.")

    def match_company(self, name):
        """Matches company name to ID and raw line dictionary."""
        res = self.companyDict.get(name, {})
        return (res.get('cd'), res.get('rr_cd'), res.get('lines', {}))

    def match(self, name):
        # Legacy Wrapper
        return self.match_company(name)
            

class company:
    '''顶层对象'''
    def __init__(self, data:dict, service_instance=None):
        self.id = data["id"]
        self.region = data["region"]
        self.type = data["type"]
        self.logo = data["logo"]
        self.alias = data.get("ekidata_alias", None)
        self.cd = 0
        self.rr = 0
        
        self.rawFeatures = []
        self.ekidataLineDict = {}
        
        self.lineList = []
        self.stationList = []
        self.line_registry = {} # line.name -> list of station.name s 
        
        self.service = service_instance
        if self.service and self.service.company_ekidata:
             self.bind_ekidata(e=self.service.company_ekidata)
        
    def bind_ekidata(self, e:ekidata_company):
        if self.id in e.companyDict:
            self.cd, self.rr, self.ekidataLineDict = e.match(self.id)
        elif self.alias and self.alias in e.companyDict:
            self.cd, self.rr, self.ekidataLineDict = e.match(self.alias)
        elif not (self.type in ['cableline','disneyline']):
            # If not found, we still want to process it, possibly generating mock IDs later.
            # But the service tracks missing companies elsewhere.
            pass
        
    def get_category(self):
        '''格式化公司类别/地域'''
        return [0 if self.type == 'JR' else (1 if self.type =='私鉄' or self.type == '第三セクター' else 2), self.region if not('九州' in self.region or '沖縄' in self.region) else '九州・沖縄']
    
    def load_feature(self):
        '''加载 geojson 为 rawFeatures'''
        # Use configurable path if available, else default
        geojson_dir = "./public/geojson"
        if self.service and hasattr(self.service, 'geojson_dir'):
             geojson_dir = self.service.geojson_dir

        path = os.path.join(geojson_dir, f"{self.id}.geojson")
        geojson_data = load_json(path)
        
        if geojson_data.get('type')=="FeatureCollection" and "features" in geojson_data:
            self.rawFeatures=geojson_data["features"]
        else:
            logger.warning(f"Invalid GeoJSON file or no 'features' found in file: {path}")
    
    def load_meta(self):
        '''从raw加载line和station, 并同时实例化'''
        
        # Path for logging/error reporting
        geojson_dir = "./public/geojson"
        if self.service and hasattr(self.service, 'geojson_dir'):
             geojson_dir = self.service.geojson_dir
        path = os.path.join(geojson_dir, f"{self.id}.geojson")

        self.stations_feature_buffer = []

        # Helper to process line features
        def process_line_feature(i):
            geometry = i.get("geometry", {})
            properties = i.get("properties", {})
            geo_type = geometry.get('type')
            geo_coords = geometry.get('coordinates', [])
            
            try:
                if not(geo_type in ['LineString','MultiLineString'] and geo_coords):
                    raise ValueError(f"Invalid geometry type or empty coordinates: {geo_type if geo_type else 'None'}, {geo_coords if geo_coords else 'None'}")

                # Extract visual properties
                data = {
                    'name': properties.get('name'),
                    'uri': properties.get('uri'),
                    'geometry': geo_coords,
                    'type': properties.get('type'),
                    'stroke': properties.get('stroke'),
                    'stroke-width': properties.get('stroke-width')
                }
                lineInstance = line(data, self)
                self.lineList.append(lineInstance)
                self.line_registry[properties.get('name','')] = []

            except Exception as e:
                logger.error(f"Error processing line feature in GeoJSON file: {path} - {e}")

        # First pass: Regular lines
        for i in self.rawFeatures:
            properties = i.get("properties", {})
            pro_type = properties.get("type")

            if i['type'] == 'Feature':
                if pro_type == 'line':
                    process_line_feature(i)
                elif pro_type in ['cableline', 'disneyline']:
                    pass # Skip for second pass
                else:
                    self.stations_feature_buffer.append(i)
            else:
                 logger.error(f"Error processing feature in GeoJSON file: {path} - Invalid feature format")

        # Second pass: Special lines (cableline, disneyline)
        for i in self.rawFeatures:
             properties = i.get("properties", {})
             pro_type = properties.get("type")
             if i['type'] == 'Feature' and pro_type in ['cableline', 'disneyline']:
                 process_line_feature(i)

        
        # 建立与ekidata csv的联系
        if self.service and self.service.company_ekidata:
             self.bind_ekidata(self.service.company_ekidata)

        # 第二次循环
        for i in self.stations_feature_buffer:
            geometry = i.get("geometry", {})
            properties = i.get("properties", {})
            prop_type = properties.get('type')
            geo_type = geometry.get('type')
            geo_coords = geometry.get('coordinates', [])
            line_of_station = properties.get('line', None)
            
            if prop_type == 'station' and line_of_station:
                try:
                    if not(geo_type == 'Point' and geo_coords):
                        raise ValueError(f"Invalid geometry type or empty coordinate: {geo_type if geo_type else 'None'}, {geo_coords if geo_coords else 'None'}")
                    stationdata = {'location': geo_coords, 'name': properties.get('name'), 'transferLst': properties.get('transfers', [])}
                    stationInstance = station(stationdata, self)
                    self.stationList.append(stationInstance)
                    
                    if line_of_station in self.line_registry:
                        self.line_registry[line_of_station].append(stationInstance)
                    else: 
                        # logger.warning(f"line of station {properties.get('name')} not registered or mismatch.")
                        pass
                except Exception as e:
                    logger.error(f"Error processing station feature in GeoJSON file: {path} - {e}")
            else:
                pass # Already handled or unknown
            
        for i in self.lineList:
            i.load_stations()
            # print(i.stations)
        
    
    def load_lines(self, lineStr):
        '''加载线路数据'''
        pass
    
    def load_stations(self, path):
        '''加载车站数据'''
        pass
    
    def get_lines(self):
        return self.lineList
    
    def get_stations(self):
        return self.stationList
    
    def __str__(self):
        return f"Company(id='{self.id}', region='{self.region}', type='{self.type}',cd= {self.cd}, rr= {self.rr})"
    
    __repr__ = __str__

class line:
    '''
    id: 对于普通线路是 Ekidata 编号(4-5位)，对于特殊线路是名称。
    type: 'line' | 'cableline' | 'disneyline'
    '''
    def __init__(self, data, company:company):
        self.name = data["name"]
        self.company = company
        self.type = data["type"]
        self.id = None # line_cd
        self.is_mock = False
        self.rawGeometry = data['geometry']
        self.odptUri = data['uri']
        self.stations = []

        # Visual properties
        self.stroke = data.get('stroke')
        self.stroke_width = data.get('stroke-width')

        # Match with Ekidata
        if self.company.service and self.company.service.company_ekidata:
             self.match_ekidata(self.company.service.company_ekidata)
    
    def match_ekidata(self, ekidata: ekidata_company):
        """Matches this line to an Ekidata line_cd."""
        company_cd = self.company.cd

        # 1. Prepare candidate list from company
        if not company_cd or company_cd not in ekidata.ekidata_lines:
             self.assign_mock_id(ekidata)
             return

        candidates = ekidata.ekidata_lines[company_cd]

        # 2. Try Exact & Normalized Match
        norm_name = normalize_name(self.name)
        norm_adv = normalize_advanced(self.name)

        best_match_cd = None

        for l_cd, l_data in candidates.items():
            e_name = normalize_name(l_data['name_h'])
            e_alias = normalize_name(l_data['alias'])

            # Exact/Normalized Checks
            if norm_name == e_name or norm_name == e_alias:
                best_match_cd = l_cd
                break

            if norm_adv == normalize_advanced(l_data['name_h']) or norm_adv == normalize_advanced(l_data['alias']):
                 best_match_cd = l_cd
                 break

        if best_match_cd:
            self.id = best_match_cd
            self.is_mock = False
        else:
            self.assign_mock_id(ekidata)

    def assign_mock_id(self, ekidata):
        """Generates a deterministic mock ID."""
        self.is_mock = True
        # Hash based on Company + Line Name to ensure consistency
        unique_str = f"{self.company.id}_{self.name}"
        hash_val = int(hashlib.md5(unique_str.encode('utf-8')).hexdigest(), 16)
        # Mock Range: 800000 + (hash % 100000)
        self.id = 800000 + (hash_val % 100000)

    def load_stations(self):
        for i in self.company.line_registry[self.name]:
            self.stations.append(i)
            i.line = self     
            # Attempt to match station to Ekidata now that Line is known
            if self.company.service and self.company.service.company_ekidata:
                 i.match_ekidata(self.company.service.company_ekidata)
           
    
    def load_geometry(self):
        pass
    
    def clean_geometry(self):
        pass
    
    def severed_geometry(self, fromto):
        pass
    
    def full_geometry(self):
        pass
    
    def __str__(self):
        return f"Line(id='{self.name}', type='{self.type}'"
    
    __repr__ = __str__
class station:
    def __init__(self, data, company:company):
        self.name = data["name"]
        self.company = company
        self.line = None
            
        self.location = Point(data["location"])
        self.group = None # stationGroup Object
        self.transferLst = data.get("transferLst", [])
        
        self.id = None # station_cd
        self.gid = None # station_g_cd
        self.is_mock = False

    def match_ekidata(self, ekidata: ekidata_company):
        """Matches this station to an Ekidata station_cd, or mocks it."""
        if not self.line:
             self.assign_mock_id()
             return

        # 1. If Line is Mocked, Station MUST be Mocked
        if self.line.is_mock:
            self.assign_mock_id()
            return

        # 2. Search in Ekidata Line
        line_cd = self.line.id
        candidates = ekidata.ekidata_stations.get(line_cd, [])

        norm_name = normalize_name(self.name)
        norm_adv = normalize_advanced(self.name)
        cleaned_fuzzy = clean_for_fuzzy(self.name)
        
        best_match = None

        # Priority 1: Exact / Advanced Match
        for s_data in candidates:
            e_name = normalize_name(s_data['name'])
            e_adv = normalize_advanced(s_data['name'])

            if norm_name == e_name or norm_adv == e_adv:
                best_match = s_data
                break

        # Priority 2: Fuzzy LCS (Only if no exact match)
        if not best_match:
             best_score = 0
             for s_data in candidates:
                 score = get_lcs_length(cleaned_fuzzy, s_data['name'])
                 # Threshold: > 2 chars and reasonable coverage
                 if score > best_score and score >= 2:
                     best_score = score
                     best_match = s_data

             # If score is too low, don't guess
             if best_score < 2:
                 best_match = None

        if best_match:
            self.id = best_match['station_cd']
            self.gid = best_match['station_g_cd']
            self.is_mock = False
        else:
            self.assign_mock_id()

    def assign_mock_id(self):
        """Generates a deterministic mock ID."""
        self.is_mock = True
        line_id = self.line.id if self.line else 0
        unique_str = f"{line_id}_{self.name}"
        hash_val = int(hashlib.md5(unique_str.encode('utf-8')).hexdigest(), 16)
        # Mock Range: 8000000 + (hash % 1000000)
        self.id = 8000000 + (hash_val % 1000000)
        # Default gid to id initially, will be merged later
        self.gid = self.id

    def find_group(self, stationGroupLst, stationGroupNameMap=None):
        '''查找所属stationGroup. Modified to handle Mock Merging with optimization.'''

        norm_name = normalize_name(self.name)

        # Helper to register group in map
        def register_group(sg):
             for s in sg.stations:
                 n = normalize_name(s.name)
                 if n not in stationGroupNameMap:
                     stationGroupNameMap[n] = []
                 if sg not in stationGroupNameMap[n]:
                     stationGroupNameMap[n].append(sg)

        # 1. If we have a Real GID, we just look for that Group or create one
        if not self.is_mock and self.gid:
            # Optimization: Can we lookup by GID?
            # Current structure is List, so we still iterate?
            # Or we trust that if we built it, it's there.
            # For now, linear scan for GID is "okay" if we assume GID uniqueness prevents too many dupes,
            # but ideally we'd map GID->Group too.
            # BUT, let's stick to the map optimization for Name first.

            # Legacy linear search for GID (safe but maybe slow if many groups)
            # To optimize: stationGroupNameMap could help if we search by name?
            # But GID is authoritative.

            # Let's try to find by Name first (likely shares name) to narrow search?
            candidates = []
            if stationGroupNameMap is not None and norm_name in stationGroupNameMap:
                candidates = stationGroupNameMap[norm_name]

            found_sg = None
            for sg in candidates:
                if sg.id == self.gid:
                    found_sg = sg
                    break

            # Fallback to full list if not in candidates (unlikely if name matches)
            if not found_sg:
                for sg in stationGroupLst:
                    if sg.id == self.gid:
                        found_sg = sg
                        break

            if found_sg:
                 found_sg.add_station(self)
                 if stationGroupNameMap is not None: register_group(found_sg)
                 return found_sg
            
            # Create new group with this Real GID
            new_sg = stationGroup([self, self.transferLst], id_override=self.gid)
            stationGroupLst.append(new_sg)
            if stationGroupNameMap is not None: register_group(new_sg)
            return new_sg

        # 2. If Mock, we need to be smart.
        # Logic: Check existing groups (Real or Mock).
        # Match if: Name is similar AND Distance < 500m

        best_sg = None
        min_dist = float('inf')

        # Optimization: Only look at groups that have a station with the same name!
        candidates = []
        if stationGroupNameMap is not None:
             # Trust the map! If not in map, no such group exists yet.
             if norm_name in stationGroupNameMap:
                 candidates = stationGroupNameMap[norm_name]
             else:
                 candidates = []
        else:
            # Fallback: if map not provided (legacy test), iterate all
            candidates = stationGroupLst
        
        for sg in candidates:
            # Check proximity to any station in the group
            dist = sg.distance_to(self.location)

            if dist < 0.5: # 500m
                 # Name match is guaranteed if we came from the map
                 # But if we are iterating full list (fallback), we check name
                 if stationGroupNameMap is None:
                     name_match = False
                     for s in sg.stations:
                         if normalize_name(s.name) == norm_name:
                             name_match = True
                             break
                     if not name_match:
                         continue

                 if dist < min_dist:
                     min_dist = dist
                     best_sg = sg

        if best_sg:
            best_sg.add_station(self)
            self.gid = best_sg.id # Inherit the group's ID
            if stationGroupNameMap is not None: register_group(best_sg)
            return best_sg
        else:
            # Create new Mock Group
            # Use station's Mock ID as Group ID
            new_sg = stationGroup([self, self.transferLst], id_override=self.gid)
            stationGroupLst.append(new_sg)
            if stationGroupNameMap is not None: register_group(new_sg)
            return new_sg

    def __str__(self):
        return f"Station(id='{self.id}', name='{self.name}', line={self.line.name if self.line else 'None'})'"
    
    __repr__ = __str__
    
class stationGroup:
    def __init__(self, lst, id_override=None):
        self.stations = []
        if isinstance(lst[0], station):
             self.stations.append(lst[0])
             lst[0].group = self
        
        self.transferLst = lst[1] # Keep raw transfer list
        self.id = id_override if id_override else self.stations[0].id
        self.center = self.stations[0].location
        
    def add_station(self, s: station):
        self.stations.append(s)
        s.group = self
        # Update center?
        # Keep simple for now

    def distance_to(self, point: Point):
        return calculate_distance((self.center.x, self.center.y), (point.x, point.y))

    def in_group(self, station):
        # Legacy stub
        pass

def pprint(lst):
    print(*lst,sep='\n')


class RailwayDataService:
    def __init__(self, db_path="railway.db", data_dir="./public"):
        self.db_path = db_path
        self.data_dir = data_dir
        self.geojson_dir = os.path.join(data_dir, "geojson")
        self.ekidata_dir = os.path.join(data_dir, "ekidata")

        self.companyList = []
        self.stationGroupList = []
        self.company_ekidata = None

    def build(self):
        """Builds the in-memory object graph and persists to SQLite."""
        logger.info("Starting RailwayDataService build...")

        company_json_path = os.path.join(self.data_dir, "company_data.json")

        # NOTE: For now hardcoding the names relative to ekidata_dir as they were in the original script
        ekidata_company_path = os.path.join(self.ekidata_dir, "company20251015.csv")
        ekidata_company_patch_path = os.path.join(self.ekidata_dir, "companypatch.csv")
        ekidata_line_path = os.path.join(self.ekidata_dir, "line20250604free.csv")
        ekidata_station_path = os.path.join(self.ekidata_dir, "station20251211free.csv")

        try:
            company_data = load_json(company_json_path)
            # Only load ekidata if files exist (allows for partial mocks)
            if os.path.exists(ekidata_company_path):
                 self.company_ekidata = ekidata_company(
                     ekidata_company_path,
                     ekidata_line_path,
                     ekidata_company_patch_path,
                     ekidata_station_path
                 )
            else:
                 logger.warning(f"Ekidata files not found at {ekidata_company_path}, skipping ekidata linkage.")
                 self.company_ekidata = None

        except Exception as e:
            logger.error(f"Failed to load base data: {e}")
            return

        temp_company_list = [] # Use local list for thread safety

        for i in company_data.keys():
            company_data[i]["id"] = i
            c = company(company_data[i], service_instance=self)
            temp_company_list.append(c)

        # Load features and meta
        for i in temp_company_list:
            i.load_feature()
            i.load_meta()

        # Build Station Groups (Consolidate)
        self.stationGroupList = []
        self.stationGroupNameMap = {} # Optimization: name -> [group, ...]

        for c in temp_company_list:
            for line in c.lineList:
                for st in line.stations:
                     # This will link stations to existing groups or create new ones
                     st.find_group(self.stationGroupList, self.stationGroupNameMap)

        # Atomic swap
        self.companyList = temp_company_list
        logger.info(f"Built {len(self.companyList)} companies.")
        logger.info(f"Built {len(self.stationGroupList)} station groups.")

        self.save_to_db()

    def save_to_db(self):
        """Saves the current state to SQLite."""
        logger.info(f"Saving to SQLite: {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Drop tables to ensure schema update
        cursor.execute("DROP TABLE IF EXISTS stations")
        cursor.execute("DROP TABLE IF EXISTS lines")
        cursor.execute("DROP TABLE IF EXISTS companies")

        # Create Tables
        cursor.execute('''
            CREATE TABLE companies (
                id TEXT PRIMARY KEY,
                region TEXT,
                type TEXT,
                cd INTEGER,
                rr INTEGER
            )
        ''')

        cursor.execute('''
            CREATE TABLE lines (
                company_id TEXT,
                name TEXT,
                type TEXT,
                line_cd INTEGER,
                stroke TEXT,
                stroke_width REAL,
                FOREIGN KEY(company_id) REFERENCES companies(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE stations (
                company_id TEXT,
                line_name TEXT,
                name TEXT,
                station_cd INTEGER,
                station_g_cd INTEGER,
                location_x REAL,
                location_y REAL,
                transfers TEXT,
                FOREIGN KEY(company_id) REFERENCES companies(id)
            )
        ''')

        for c in self.companyList:
            cursor.execute("INSERT INTO companies (id, region, type, cd, rr) VALUES (?, ?, ?, ?, ?)",
                           (c.id, c.region, c.type, c.cd, c.rr))

            for l in c.lineList:
                cursor.execute("INSERT INTO lines (company_id, name, type, line_cd, stroke, stroke_width) VALUES (?, ?, ?, ?, ?, ?)",
                               (c.id, l.name, l.type, l.id, l.stroke, l.stroke_width))

                for s in l.stations:
                     # Serialize transfers list to JSON string
                     transfers_json = json.dumps(s.transferLst, ensure_ascii=False)
                     cursor.execute("INSERT INTO stations (company_id, line_name, name, station_cd, station_g_cd, location_x, location_y, transfers) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                               (c.id, l.name, s.name, s.id, s.gid, s.location.x, s.location.y, transfers_json))

        conn.commit()
        conn.close()
        logger.info("Database save complete.")

if __name__ == "__main__":
    service = RailwayDataService()
    service.build()
    pprint(service.companyList)
