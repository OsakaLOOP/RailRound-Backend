import time
import os
import json
import urllib.parse
import logging
import re
import requests
from abc import ABC, abstractmethod
from rdflib import Graph, Namespace

import threading
import time
from typing import Dict, Any

# 简单的进度查询器父类
class ProgressTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self.total = 0
        self.current = 0
        self.start_time = 0
        self.error = None
        self._errors = []

    def start(self, total: int):
        '''开始任务'''
        with self._lock:
            self.total = total
            self.current = 0
            self.start_time = time.time()

    def update(self, current: int):
        '''更新进度'''
        with self._lock:
            self.current = current

    def get_snapshot(self):
        '''获取展示数据'''
        with self._lock:
            # 1. 耗时计算
            elapsed = time.time() - self.start_time
            
            # 2. 进度计算
            if self.total == 0:
                percent = 0
            else:
                percent = int((self.current / self.total) * 100)
            
            # 3. ETA 计算 (核心)
            eta_seconds = 0
            speed = 0
            if self.current > 0:
                # 平均处理速度 (秒/个)
                avg_time_per_item = elapsed / self.current
                remaining_items = self.total - self.current
                eta_seconds = int(avg_time_per_item * remaining_items)
                speed = round(self.current / elapsed, 2) # 个/秒

            # 4. 格式化输出 (给人类看的)
            return {
                "progress": f"{self.current}/{self.total}",
                "percent": f"{percent}%",
                "elapsed": f"{int(elapsed)}s",
                "eta": f"{eta_seconds}s",  # 剩余秒数
                "speed": f"{speed}/s"      # 速度
            }
    
    def get_view_model(self):
        '''为前端生成数据字典'''
        with self._lock:
            elapsed = time.time() - self.start_time
            
            # 基础计算
            percent = 0
            if self.total > 0:
                percent = round((self.current / self.total) * 100, 1)
            
            # ETA 计算
            eta = 0
            speed = 0.0
            if self.current > 0 and self.total > 0:
                avg_time = elapsed / self.current
                eta = int(avg_time * (self.total - self.current))
                speed = round(self.current / elapsed, 2)

            return {
                "current": self.current,
                "total": self.total,
                "percent": percent,
                "eta_seconds": eta,
                "speed": speed,
                "error": self.error,
                # 如果 current < total 且 total > 0，认为 active
                "is_active": (self.current < self.total) and (self.total > 0)
            }

    def increment(self, item= None):
        '''进度+1'''
        with self._lock:
            self._current += 1
            if item is not None:
                self._item = item

    def recErr(self,err:str):
        with self._lock:
            self._errors.append(err)

# 父类
class WorkerProcess(ABC):
    def __init__(self, name: str, period: int, type_str: str, max_retry=3):
        self.name = name
        self.period = period if period>=3600 else 3600 # 部分任务耗时, 周期太短干扰调度
        self.type = type_str
        self.log_dir = './static' + self.name + '_logs'
        self.max_retry = max_retry
        
        self.logger = self._setup_logger()
        self.tracker = ProgressTracker()
        
        # 初始化状态字典
        self.status = {
            'starttime': time.time(),
            'nextrun': time.time(),
            'uptime': 0,
            'lastrun': 0,
            'lastreturn': None,
            'statcode': 0,  # 0: Idle, 1: Running, 200: Success, 500: Error
            'retry':0
        }
    
    def _setup_logger(self):
        '''配置独立 Logger'''
        # 1. 创建 Logger 对象 (使用唯一名称)
        logger = logging.getLogger(f"Worker.{self.name}")
        logger.setLevel(logging.INFO)

        # 2. 防止重复添加 Handler (关键：避免多重打印)
        if logger.hasHandlers():
            return logger

        # 3. 确保日志目录存在
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        # 4. 定义格式
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 5. Handler A: 文件输出 (logs/WorkerName.log)
        file_handler = logging.FileHandler(
            os.path.join(self.log_dir, f"{self.name}.log"), 
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # 6. Handler B: 控制台输出
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        return logger
    
    def _pre_run(self):
        '''运行前更新状态'''
        self.status['lastrun'] = time.time()
        self.status['statcode'] = 1
    
    def _post_run(self, result, error=None):
        '''运行后更新状态'''
        current_time = time.time()
        self.status['uptime'] = current_time - self.status['starttime']
        
        if error:
            self.status['statcode'] = 500
            self.status['lastreturn'] = str(error)
            self.status['retry'] += 1
        else:
            self.status['statcode'] = 200
            self.status['lastreturn'] = result
            self.status['nextrun'] = current_time + worker.period

    def get_dashboard_view(self):
        """前端展示的状态"""
        # 获取进度快照
        prog_data = self.tracker.get_view_model()
        
        return {
            "id": self.name,# React key
            "display_name": self.name,
            "type": self.type,
            "status_code": self.status['statcode'], # 0, 1, 200, 500
            "status_text": self._get_status_text(self.status['statcode']), 
            "progress": prog_data,
            "last_update_ts": time.time(),

            "log_preview": str(self.status.get('lastreturn') or "Ready")[:50]
        }
        
    def _get_status_text(self, code):
        mapping = {0: "Idle", 1: "Running", 200: "Done", 500: "Error"}
        return mapping.get(code, "Unknown")
    
    def run(self):
        # 抽象统一流程
        self._pre_run()
        
        # 子类一定要调用tracker.start()!!!
        
        try:
            result_msg = self.trigger() 
            self._post_run(result_msg)
            
        except Exception as e:
            # 统一的错误兜底
            self.logger.exception("Critical Failure")
            self.tracker.recErr(str(e))
            self._post_run(None, error=e)
    
    # 抽象子类定义
    @abstractmethod
    def trigger(self):
        pass

# 以下为 WorkerProcess 具体子类
class GeoJsonWorker(WorkerProcess):
    # 静态常量配置
    HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
    BASE_URL = "https://uedayou.net/jrslod/"
    
    # RDF Namespaces
    GEO = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
    WDT = Namespace("http://www.wikidata.org/prop/direct/")
    GEOSPARQL = Namespace("http://www.opengis.net/ont/geosparql#")
    ODPT = Namespace("http://vocab.odpt.org/ODPT/") 
    SCHEMA = Namespace("http://schema.org/")

    def __init__(self, name, period, config_file=r'D:\PROJ\GIT\RailRound\dist\company_data.json'):
        # 传递类型为 "geojson_process"
        super().__init__(name, period, "geojson_process")
        self.config_file = config_file
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def run(self):
        '''执行爬虫与生成逻辑'''
        self._pre_run()
        try:
            # 1. 加载配置
            if not os.path.exists(self.config_file):
                raise FileNotFoundError(f"Config file {self.config_file} not found")
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                companies = json.load(f)
            
            processed_count = 0
            skipped_count = 0
            
            # 2. 遍历处理
            for company_name in companies.keys():
                filename = f"{company_name}.geojson"
                
                if os.path.exists(filename):
                    skipped_count += 1
                    continue
                
                # 执行生成逻辑
                self._generate_for_company(company_name)
                processed_count += 1
                time.sleep(2) # 礼貌延迟

            result_msg = f"Completed. Processed: {processed_count}, Skipped: {skipped_count}"
            self._post_run(result=result_msg)

        except Exception as e:
            print(f"[Worker Error] {e}")
            self._post_run(result=None, error=e)

    # --- 内部核心逻辑 (封装原脚本函数) ---

    def _generate_for_company(self, company_name):
        filename = f"{company_name}.geojson"
        all_features = []
        feature_map = {}

        # 获取线路
        lines = self._get_company_lines(company_name)
        
        for line_uri in lines:
            line_name = urllib.parse.unquote(line_uri.split('/')[-1])
            
            # 1. 处理线路轨迹
            if line_uri not in feature_map:
                line_feats, _ = self._get_line_data(line_uri)
                if line_feats:
                    all_features.extend(line_feats)
                    feature_map[line_uri] = line_feats[0]

            # 2. 处理车站
            g_line = self._fetch_graph(line_uri)
            if not g_line: continue
            
            station_uris = [str(o) for s, p, o in g_line.triples((None, self.WDT.P527, None))]
            
            for st_uri in station_uris:
                existing = feature_map.get(st_uri)
                feat, updated = self._update_or_create_station(st_uri, line_name, existing)
                if updated:
                    if not existing:
                        all_features.append(feat)
                        feature_map[st_uri] = feat

        # 保存文件
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({ "type": "FeatureCollection", "features": all_features }, f, ensure_ascii=False, indent=2)

    def _fetch_graph(self, url):
        safe_url = self._get_encoded_uri(url)
        try:
            resp = self.session.get(safe_url, timeout=10)
            resp.raise_for_status()
            
            # 清洗非法字符
            raw_text = resp.text
            def encode_match(match):
                return f"<{urllib.parse.quote(match.group(1), safe=':/?#[]@!$&*+,;=%')}>"
            clean_text = re.sub(r'<(https?://[^>]+)>', encode_match, raw_text)

            g = Graph()
            g.parse(data=clean_text, format="turtle", publicID=safe_url)
            return g
        except Exception:
            return None

    def _get_company_lines(self, company_name):
        url = f"{self.BASE_URL}{company_name}"
        g = self._fetch_graph(url)
        if not g: return []
        return [str(o) for s, p, o in g.triples((None, self.WDT.P527, None))]

    def _get_line_data(self, line_uri):
        g = self._fetch_graph(line_uri)
        if not g: return [], []

        features = []
        line_name = urllib.parse.unquote(line_uri.split('/')[-1])

        for s, p, o in g.triples((None, self.GEOSPARQL.asWKT, None)):
            geom_type, coords = self._parse_wkt(str(o))
            if geom_type and coords:
                feature = {
                    "type": "Feature",
                    "properties": {
                        "name": line_name,
                        "type": "line",
                        "uri": line_uri,
                        "stroke": "#FF0000",
                        "stroke-width": 4
                    },
                    "geometry": { "type": geom_type, "coordinates": coords }
                }
                
                # 补充颜色
                color = g.value(s, Namespace("http://www.wikidata.org/prop/direct/").P465)
                if color: feature["properties"]["stroke"] = f"#{color}"
                
                features.append(feature)
                break 
        return features, []

    def _update_or_create_station(self, station_uri, line_name, existing_feature=None):
        # 简化逻辑：如果有现有特征且已有换乘信息，跳过
        if existing_feature and 'transfers' in existing_feature.get('properties', {}):
            return existing_feature, False
        
        g = self._fetch_graph(station_uri)
        if not g: return existing_feature, False

        transfers = self._extract_transfers(g, line_name)

        if existing_feature:
            existing_feature['properties']['transfers'] = transfers
            return existing_feature, True
        
        # 新建
        lat = lng = None
        for s, p, o in g.triples((None, self.GEO.lat, None)):
            try:
                lat = float(o)
                lng = float(g.value(s, self.GEO.long))
                break
            except: continue
            
        if lat is not None and lng is not None:
            name = urllib.parse.unquote(station_uri.split('/')[-1])
            new_feature = {
                "type": "Feature",
                "properties": {
                    "name": name, 
                    "line": line_name, 
                    "type": "station", 
                    "uri": station_uri, 
                    "transfers": transfers
                },
                "geometry": { "type": "Point", "coordinates": [lng, lat] }
            }
            return new_feature, True
        return None, False

    def _extract_transfers(self, g, current_line):
        transfers = set()
        for s, p, o in g.triples((None, self.WDT.P833, None)):
            try:
                parts = urllib.parse.unquote(str(o)).strip('/').split('/')
                if len(parts) >= 2 and parts[-2] != current_line:
                    transfers.add(parts[-2])
            except: pass
        return list(transfers)

    def _parse_wkt(self, wkt_str):
        wkt_str = wkt_str.upper()
        if "EMPTY" in wkt_str: return None, None
        
        if wkt_str.startswith("MULTILINESTRING"):
            content = re.search(r'\((.*)\)', wkt_str).group(1)
            parts = re.split(r'\),\s*\(', content)
            coords = []
            for p in parts:
                clean = p.replace('(', '').replace(')', '')
                points = [[float(v) for v in x.split()] for x in clean.split(',') if x.strip()]
                coords.append(points)
            return "MultiLineString", coords
        elif wkt_str.startswith("LINESTRING"):
            content = re.search(r'\((.*)\)', wkt_str).group(1)
            points = [[float(v) for v in x.split()] for x in content.split(',') if x.strip()]
            return "LineString", points
        return None, None

    def _get_encoded_uri(self, url):
        try:
            url = url.strip()
            if not url.endswith(('.ttl', '.json')): url += ".ttl"
            parsed = urllib.parse.urlparse(url)
            path = urllib.parse.quote(urllib.parse.unquote(parsed.path), safe='/:')
            return urllib.parse.urlunparse(parsed._replace(path=path))
        except: return url

def loop(workers):
    while True:
        now = time.time()
        
        for worker in workers:
            if worker.status['statcode'] in [0, 200] and now > worker.status.get('nextrun', 0):
                
                print(f"[Schedule] Starting normal run for {worker.name}")
                worker.status['retry']=0
                worker.run()

            elif worker.status['statcode'] == 500:
                
                current_retries = worker.status['retry']
                
                if current_retries < worker.max_retries:
                    print(f"[Retry] {worker.name} failed. Retrying immediately ({current_retries + 1}/{worker.max_retries})...")
                    
                    worker.mark_failed() # 计数+1
                    worker.run()         # 再次运行
                else:
                    pass 

        time.sleep(1) 
# ----------------------------------------------------
# 3. 运行测试
# ----------------------------------------------------
if __name__ == "__main__":
    # 创建模拟配置文件
    with open("company_data.json", "w") as f:
        json.dump({"Seibu": {}}, f) # 测试用

    # 实例化并运行
    worker = GeoJsonWorker(name="GeojsonWorker", period=360000)
    print(f"Worker Created: {worker.name} | Type: {worker.type}")
    print(f"Initial Status: {worker.status}")
    
    print("\n--- Running Worker ---")
    worker.run()
    
    print("\n--- Final Status ---")
    print(worker.status)