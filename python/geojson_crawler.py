import os
import json
import urllib.parse
import logging
import re
import requests
from rdflib import Graph, Namespace
import time
from worker_base import WorkerProcess

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

    def __init__(self, name, period, config_file='public/company_data.json', output_dir='test_geojson_output/'):
        # 传递类型为 "geojson_process"
        super().__init__(name, period, "geojson_process")
        self.config_file = config_file
        self.output_dir = output_dir
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def trigger(self):
        '''执行爬虫与生成逻辑'''
        # 1. 加载配置
        if not os.path.exists(self.config_file):
            raise FileNotFoundError(f"Config file {self.config_file} not found")

        # Ensure output directory exists
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        with open(self.config_file, 'r', encoding='utf-8') as f:
            companies = json.load(f)
            if not isinstance(companies, dict):
                companies = {}

        self.tracker.start(0, self.run_id)

        processed_count = 0
        skipped_count = 0

        # 2. 遍历处理
        for company_name in list(companies.keys()):
            if company_name != '東日本旅客鉄道':
                pass
            filename = os.path.join(self.output_dir, f"{company_name}.geojson")

            if os.path.exists(filename):
                skipped_count += 1
                continue

            # 执行生成逻辑
            self._generate_for_company(company_name)
            processed_count += 1
            if processed_count==len(companies.keys()):
                pass
            time.sleep(2) # 礼貌延迟

        result_msg = f"Completed. Processed: {processed_count}, Skipped: {skipped_count}"
        return result_msg

    # --- 内部核心逻辑 (封装原脚本函数) ---

    def _generate_for_company(self, company_name):
        self.logger.info(f"Generating for company: {company_name}")
        filename = os.path.join(self.output_dir, f"{company_name}.geojson")
        all_features = []
        feature_map = {}

        # 获取线路
        lines = self._get_company_lines(company_name)
        self.logger.info(f"Found {len(lines)} lines for {company_name}")
        self.tracker.add_to_total(len(lines))

        for line_uri in lines:
            line_name = urllib.parse.unquote(line_uri.split('/')[-1])
            self.logger.debug(f"Processing line: {line_name}")

            # 1. 处理线路轨迹
            if line_uri not in feature_map:
                line_feats, _ = self._get_line_data(line_uri)
                if line_feats:
                    all_features.extend(line_feats)
                    feature_map[line_uri] = line_feats[0]

            # 2. 处理车站
            g_line = self._fetch_graph(line_uri)
            if not g_line:
                self.tracker.increment(line_name)
                continue

            station_uris = [str(o) for s, p, o in g_line.triples((None, self.WDT.P527, None))]
            self.logger.debug(f"Found {len(station_uris)} stations for line {line_name}")

            for st_uri in station_uris:
                existing = feature_map.get(st_uri)
                feat, updated = self._update_or_create_station(st_uri, line_name, existing)
                if updated:
                    if not existing:
                        all_features.append(feat)
                        feature_map[st_uri] = feat

            self.tracker.increment(line_name)

        # 保存文件
        self.logger.info(f"Saving {len(all_features)} features to {filename}")
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({ "type": "FeatureCollection", "features": all_features }, f, ensure_ascii=False, indent=2)

    def _fetch_graph(self, url):
        safe_url = self._get_encoded_uri(url)
        self.logger.debug(f"Fetching graph: {safe_url}")

        try:
            resp = self.session.get(safe_url, timeout=10)
            resp.raise_for_status()
        except (requests.exceptions.ProxyError, requests.exceptions.SSLError) as e:
            if self.session.trust_env:
                self.logger.warning(f"Proxy/SSL Error with {url}: {e}. Disabling system proxy and retrying...")
                self.session.trust_env = False
                try:
                    resp = self.session.get(safe_url, timeout=10)
                    resp.raise_for_status()
                except Exception as e2:
                    self.logger.warning(f"Failed to fetch graph {url} (direct): {e2}")
                    return None
            else:
                self.logger.warning(f"Failed to fetch graph {url}: {e}")
                return None
        except Exception as e:
            self.logger.warning(f"Failed to fetch graph {url}: {e}")
            return None

        try:
            # 清洗非法字符
            raw_text = resp.text
            def encode_match(match):
                return f"<{urllib.parse.quote(match.group(1), safe=':/?#[]@!$&*+,;=%')}>"
            clean_text = re.sub(r'<(https?://[^>]+)>', encode_match, raw_text)

            g = Graph()
            g.parse(data=clean_text, format="turtle", publicID=safe_url)
            return g
        except Exception as e:
            self.logger.warning(f"Failed to parse graph {url}: {e}")
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
                lat_val = o
                lng_val = g.value(s, self.GEO.long)

                if lat_val is not None and lng_val is not None:
                    lat = float(lat_val)
                    lng = float(lng_val)
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
            match = re.search(r'\((.*)\)', wkt_str)
            if not match: return None, None
            content = match.group(1)
            parts = re.split(r'\),\s*\(', content)
            coords = []
            for p in parts:
                clean = p.replace('(', '').replace(')', '')
                points = [[float(v) for v in x.split()] for x in clean.split(',') if x.strip()]
                coords.append(points)
            return "MultiLineString", coords
        elif wkt_str.startswith("LINESTRING"):
            match = re.search(r'\((.*)\)', wkt_str)
            if not match: return None, None
            content = match.group(1)
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
