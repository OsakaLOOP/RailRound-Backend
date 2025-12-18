import logging
import json
import hashlib
import pandas as pd
import sqlite3
import shapely
from shapely.geometry import Point, Polygon, LineString, MultiLineString, shape

logger = logging.getLogger()

stationGroupList = []
companyList = []


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
        print(e)
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
    def __init__(self, path1, path2, patchpath):
        self.company_df = load_csv(path1)
        self.company_patch = load_csv(patchpath)
        self.df_merged = pd.concat([self.company_df, self.company_patch], ignore_index=True)
        
        self.line_df = load_csv(path2)
        self.companyDict = {}
        self._id_to_name_map = {}
        
        self.c1 = self.df_merged['company_name_h']
        self.c2 = self.df_merged['rr_cd']
        self.c3 = self.line_df['company_cd']
        
        for row in self.df_merged.itertuples():
            c_name = clean_name(getattr(row, 'company_name_h', ''))
            c_cd = getattr(row, 'company_cd', None)
            rr_cd = getattr(row, 'rr_cd', None)

            self.companyDict[c_name] = {
                "cd": c_cd,
                "rr_cd": rr_cd,
                "lines": {} 
            }
            
            if c_cd is not None:
                self._id_to_name_map[c_cd] = c_name

        for row in self.line_df.itertuples():
            l_comp_cd = getattr(row, 'company_cd', None)
            l_cd = getattr(row, 'line_cd', None)
            l_name = getattr(row, 'line_name_h', 'Unknown') 
            l_alias = getattr(row, 'line_name', 'Unknown') 
            target_company_name = self._id_to_name_map.get(l_comp_cd)

            if target_company_name and target_company_name in self.companyDict:
                self.companyDict[target_company_name]["lines"][l_cd] = [l_name, l_alias]
            

    def match(self, name):
        res = self.companyDict.get(name, {})
        return (res['cd'],res['rr_cd'],res['lines'])
            

class company:
    '''顶层对象'''
    def __init__(self, data:dict):
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
        
        companyList.append(self)
        self.bind_ekidata(e=company_ekidata)
        
    def bind_ekidata(self, e:ekidata_company):
        if self.id in company_ekidata.companyDict:
            self.cd, self.rr, self.ekidataLineDict = company_ekidata.match(self.id)
        elif self.alias and self.alias in company_ekidata.companyDict:
            self.cd, self.rr, self.ekidataLineDict = company_ekidata.match(self.alias)
        elif not (self.type in ['cableline','disneyline']):
            print('bind error')
        
    def get_category(self):
        '''格式化公司类别/地域'''
        
        return [0 if self.type == 'JR' else (1 if self.type =='私鉄' or self.type == '第三セクター' else 2), self.region if not('九州' in self.region or '沖縄' in self.region) else '九州・沖縄']
    
    def load_feature(self):
        '''加载 geojson 为 rawFeatures'''
        
        path = f"./public/geojson/{self.id}.geojson"
        geojson_data = load_json(path)
        
        if geojson_data.get('type')=="FeatureCollection" and "features" in geojson_data:
            self.rawFeatures=geojson_data["features"]
        else:
            logger.warning(f"Invalid GeoJSON file or no 'features' found in file: {path}")
        #print(self.rawFeatures)
    
    def load_meta(self):
        '''从raw加载line和station, 并同时实例化'''
        
        path= f"./public/geojson/{self.id}.geojson"
        self.stations_feature_buffer = []
        # 第一次循环
        for i in self.rawFeatures:
            geometry = i.get("geometry", {})
            properties = i.get("properties", {})
            pro_type = properties.get("type", {})
            geo_type = geometry.get('type')
            geo_coords = geometry.get('coordinates', [])
            
            if i['type'] == 'Feature' and geometry and properties:
                if pro_type == 'line':
                    try:
                        if not(geo_type in ['LineString','MultiLineString'] and geo_coords):
                            raise ValueError(f"Invalid geometry type or empty coordinates: {geo_type if geo_type else 'None'}, {geo_coords if geo_coords else 'None'}")
                        
                        data = {'name':properties.get('name'),'uri':properties.get('uri'),'geometry':geo_coords,'type':properties.get('type')}
                        lineInstance=line(data, self)
                        self.lineList.append(lineInstance)
                        self.line_registry[properties.get('name','')] = []
                        
                    except Exception as e:
                        logger.error(f"Error processing line feature in GeoJSON file: {path} - {e}")
                else:
                    self.stations_feature_buffer.append(i)
            else:
                logger.error(f"Error processing feature in GeoJSON file: {path} - Invalid feature format: {i[:30]}{'...' if len(i)>30 else ''}")
        
        # 建立与ekidata csv的联系        
        self.bind_ekidata(company_ekidata)
        # 第二次循环
        # return         
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
                    stationdata = {'location': geo_coords, 'name': properties['name'], 'transferLst': properties['transfers']}
                    stationInstance = station(stationdata, self)
                    self.stationList.append(stationInstance)
                    
                    if line_of_station in self.line_registry:
                        self.line_registry[line_of_station].append(stationInstance)
                    else: 
                        raise ValueError(f"line of station {properties.get('name')} not registered or mismatch.")
                except Exception as e:
                    logger.error(f"Error processing station feature in GeoJSON file: {path} - {e}")
            else:
                logger.warning(f"Unknown feature type in GeoJSON file: {path} - {properties}")
            
        for i in self.lineList:
            i.load_stations()
            print(i.stations)
        
    
    def load_lines(self, lineStr):
        '''加载线路数据'''
        
    
    def load_stations(self, path):
        '''加载车站数据'''
        pass
    
    def get_lines(self):
        return self.lineList
    
    def get_stations(self):
        return self.stationList
    
    def __str__(self):
        return f"Company(id='{self.id}', region='{self.region}', type='{self.type}',cd= {self.cd}, rr= {self.rr})"
    
    __repr__ = __str__#自定义对象的结构化print()输出,而在列表中则调用repr()

class line:
    '''
    id: 对于普通线路是 Ekidata 编号(4-5位)，对于特殊线路是名称。
    type: 'line' | 'cableline' | 'disneyline'
    '''
    def __init__(self, data, company:company):
        self.name = data["name"]
        self.company = company
        self.type = data["type"]
        self.id = None
        self.rawGeometry = data['geometry']
        self.odptUri = data['uri']
        self.stations = []
    
    def load_stations(self):
        for i in self.company.line_registry[self.name]:
            self.stations.append(i)
            i.line = self     
           
    
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
        self.group = None
        self.transferLst = data.get("transferLst", [])
        
        self.id = None
        
            
    def find_group(self, stationGroupLst):
        '''查找所属stationGroup'''
        found=[]
        for sg in stationGroupLst:
            if sg.in_group(self):
                found.append((sg,sg.in_group(self)))
        if found:
            return sorted(found,key=lambda a:a[1])[-1][0]
        else:
            stationGroupLst.append(stationGroup([self,self.transferLst]))
        return None
        
    def __str__(self):
        return f"Station(id='{self.id}', name='{self.name}', line={self.line.name})'"
    
    __repr__ = __str__
    
class stationGroup:
    def __init__(self, lst):
        self.id = ""
        self.transferLst = lst
        
        
    def in_group(self, station):
        pass

def pprint(lst):
    print(*lst,sep='\n')

    

if __name__ == "__main__":
    company_json_path = "./public/company_data.json"
    geojson_folder = "./public/geojson/"
    ekidata_company_path = "./public/ekidata/company20251015.csv"
    ekidata_company_patch_path = "./public/ekidata/companypatch.csv"
    ekidata_line_path = "./public/ekidata/line20250604free.csv"

    company_data = load_json(company_json_path)
    company_ekidata = ekidata_company(ekidata_company_path, ekidata_line_path, ekidata_company_patch_path)

    for i in company_data.keys():
        company_data[i]["id"] = i
        company(company_data[i])
        
    pprint(companyList)

    for i in companyList:
        i.load_feature()
        #i.load_geometry()
    companyList[0].load_meta()