import pandas as pd
import sqlite3
import os
import re
import json
import requests
from tqdm import tqdm
from functools import lru_cache
import unicodedata
from collections import defaultdict
import numpy as np


class AddressTrie:
    """地址前缀树，用于快速匹配地址组件"""
    def __init__(self):
        self.root = defaultdict(dict)
        self.is_end = "_end_"
    
    def insert(self, word, data):
        node = self.root
        for char in word:
            node = node.setdefault(char, defaultdict(dict))
        node[self.is_end] = data
    
    def search_all_matches(self, text):
        matches = []
        for i in range(len(text)):
            node = self.root
            for j in range(i, len(text)):
                if text[j] not in node:
                    break
                node = node[text[j]]
                if self.is_end in node:
                    matches.append({
                        'text': text[i:j+1],
                        'data': node[self.is_end]
                    })
        return matches


class AdvancedAddressParser:
    """高级地址解析器，使用多种策略提升解析准确率"""
    
    def __init__(self, data_dir=None):
        """
        初始化解析器
        
        Args:
            data_dir: 数据目录路径，默认在包的安装路径下
        """
        if data_dir:
            self.data_dir = data_dir
        else:
            self.data_dir = os.path.join(os.path.dirname(__file__), 'data')
        
        os.makedirs(self.data_dir, exist_ok=True)
        
        self.aliyun_db_path = os.path.join(self.data_dir, 'aliyun_regions.sqlite')
        self.aliyun_raw_path = os.path.join(self.data_dir, 'aliyun_raw_data.json')
        
        print("正在初始化高级地址解析器...")
        self._create_aliyun_db_if_needed()
        self._load_all_data()
        self._init_parsers()
        print("解析器初始化完成。")
    
    def _create_aliyun_db_if_needed(self):
        """如果数据库不存在，则创建"""
        if os.path.exists(self.aliyun_db_path):
            return
        
        print(f"未找到权威数据库 '{self.aliyun_db_path}'，开始构建...")
        if not os.path.exists(self.aliyun_raw_path):
            self._download_raw_data()
        self._create_sqlite_from_json()
    
    def _download_raw_data(self):
        """从阿里云下载地理数据"""
        print("正在从阿里云下载地理数据...")
        full_data_url = "https://geo.datav.aliyun.com/areas_v3/bound/all.json"
        try:
            response = requests.get(full_data_url, timeout=30)
            response.raise_for_status()
            geojson_data = response.json()
            with open(self.aliyun_raw_path, 'w', encoding='utf-8') as f:
                json.dump(geojson_data, f, ensure_ascii=False, indent=2)
            print("原始数据下载完成。")
        except Exception as e:
            raise RuntimeError(f"错误: 下载阿里云数据失败: {e}")
    
    def _create_sqlite_from_json(self):
        """从JSON创建SQLite数据库"""
        print(f"正在从 '{self.aliyun_raw_path}' 创建SQLite数据库...")
        with open(self.aliyun_raw_path, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)
        
        features = loaded_data.get('features', []) if isinstance(loaded_data, dict) else loaded_data
        
        all_regions = [self._process_feature(feat) for feat in tqdm(features, desc="处理JSON数据")]
        all_regions = [r for r in all_regions if r is not None]
        full_df = pd.DataFrame(all_regions)
        
        provinces_df = full_df[full_df['level'] == 'province'].copy()
        cities_df = full_df[full_df['level'] == 'city'].copy()
        districts_df = full_df[full_df['level'] == 'district'].copy()
        
        provinces_table = provinces_df[['code', 'name', 'longitude', 'latitude']].copy()
        cities_table = cities_df[['code', 'name', 'longitude', 'latitude', 'parentCode']].rename(
            columns={'parentCode': 'provinceCode'})
        districts_table = districts_df[['code', 'name', 'longitude', 'latitude', 'parentCode']].rename(
            columns={'parentCode': 'cityCode'})
        
        # 创建城市到省份的映射
        city_to_prov_map = cities_table.set_index('code')['provinceCode'].to_dict()
        for _, prov_row in provinces_table.iterrows():
            if prov_row['name'].endswith('市'):
                city_to_prov_map[prov_row['code']] = prov_row['code']
        
        districts_table['provinceCode'] = districts_table['cityCode'].map(city_to_prov_map)
        
        with sqlite3.connect(self.aliyun_db_path) as con:
            provinces_table.to_sql('provinces', con, if_exists='replace', index=False)
            cities_table.to_sql('cities', con, if_exists='replace', index=False)
            districts_table.to_sql('districts', con, if_exists='replace', index=False)
        
        print("权威数据库创建成功。")
    
    def _process_feature(self, feature):
        """处理GeoJSON特征"""
        properties = feature.get('properties', {}) if 'properties' in feature else feature
        if not properties or not properties.get('adcode'):
            return None
        
        adcode = str(properties['adcode'])
        center = properties.get('center')
        longitude, latitude = (center[0], center[1]) if center and len(center) == 2 else (
            properties.get('lng'), properties.get('lat'))
        
        parent = properties.get('parent')
        parent_adcode = str(parent.get('adcode', '')) if isinstance(parent, dict) else str(parent or '')
        
        return {
            'code': adcode,
            'name': properties.get('name'),
            'level': properties.get('level'),
            'longitude': longitude,
            'latitude': latitude,
            'parentCode': parent_adcode
        }
    
    def _load_all_data(self):
        """加载所有数据到内存"""
        print("正在加载解析所需的数据索引...")
        with sqlite3.connect(self.aliyun_db_path) as con:
            self.provinces_df = pd.read_sql_query("SELECT * FROM provinces", con)
            self.cities_df = pd.read_sql_query("SELECT * FROM cities", con)
            self.districts_df = pd.read_sql_query("SELECT * FROM districts", con)
        
        # 创建省份别名映射
        self.province_alias_map = {}
        for _, row in self.provinces_df.iterrows():
            full_name = row['name']
            self.province_alias_map[full_name] = full_name
            # 创建简称映射
            alias = re.sub(r'省|市|自治区|特别行政区|壮族|回族|维吾尔|蒙古', '', full_name)
            if alias != full_name and alias:
                self.province_alias_map[alias] = full_name
        
        self.all_provinces = sorted(list(self.province_alias_map.keys()), key=len, reverse=True)
        self.all_cities = sorted(self.cities_df['name'].unique().tolist(), key=len, reverse=True)
        self.all_prov_names = set(self.provinces_df['name'])
        
        # 创建城市到区县的映射
        self.city_to_districts_map = self.districts_df.groupby('cityCode')['name'].apply(
            lambda x: sorted(x.tolist(), key=len, reverse=True)).to_dict()
        
        # 创建城市代码到省代码的映射
        self.city_code_to_province_code_map = self.cities_df.set_index('code')['provinceCode'].to_dict()
        
        # 创建城市名到省名的映射
        self.city_to_province = {
            r.name: self.provinces_df.loc[self.provinces_df['code'] == r.provinceCode, 'name'].iloc[0]
            for r in self.cities_df.itertuples() 
            if not self.provinces_df[self.provinces_df['code'] == r.provinceCode].empty
        }
        self.city_to_province.update({
            n[:-1]: p for n, p in self.city_to_province.items() if n.endswith('市')
        })
    
    def _init_parsers(self):
        """初始化各种解析器"""
        # 初始化正则解析器
        self.province_patterns = [
            re.compile(r'([^市县区岛]*?(?:省|自治区|特别行政区))'),
            re.compile(r'(北京|上海|天津|重庆)(?=市|$)'),
            re.compile(r'(内蒙古|广西|西藏|宁夏|新疆)(?=自治区|$|市|区|县)'),
            re.compile(r'(香港|澳门)(?=特别行政区|$)')
        ]
        self.city_patterns = [
            re.compile(r'([^省市区县]*?(?:市|地区|州|盟))(?![辖区])'),
            re.compile(r'([^省市区县]*?(?:自治州))')
        ]
        self.district_patterns = [
            re.compile(r'([^省市街道乡镇]*?(?:区|县|县级市|自治县|旗|林区|特区))(?![级])')
        ]
        
        self.address_mappings = {
            '北京': '北京市', '上海': '上海市', '天津': '天津市', '重庆': '重庆市',
            '内蒙': '内蒙古自治区', '广西': '广西壮族自治区',
            '西藏': '西藏自治区', '宁夏': '宁夏回族自治区',
            '新疆': '新疆维吾尔自治区', '香港': '香港特别行政区', '澳门': '澳门特别行政区'
        }
        self.municipalities = {'北京市', '上海市', '天津市', '重庆市'}
        
        # 初始化Trie树
        self._init_trie()
    
    def _init_trie(self):
        """初始化Trie树用于智能匹配"""
        self.trie = AddressTrie()
        self.code_to_entity = {}
        self.dist_to_city_prov = {}
        
        city_to_prov_code = pd.Series(
            self.cities_df['provinceCode'].values,
            index=self.cities_df['code']
        ).to_dict()
        
        # 插入省份
        for _, row in self.provinces_df.iterrows():
            data = {
                'code': row['code'],
                'level': 'province',
                'name': row['name']
            }
            self.trie.insert(row['name'], data)
            self.code_to_entity[row['code']] = data
            if row['name'].endswith('省'):
                self.trie.insert(row['name'][:-1], data)
        
        # 插入城市
        for _, row in self.cities_df.iterrows():
            data = {
                'code': row['code'],
                'level': 'city',
                'name': row['name'],
                'parent_code': row['provinceCode']
            }
            self.trie.insert(row['name'], data)
            self.code_to_entity[row['code']] = data
            if row['name'].endswith('市'):
                self.trie.insert(row['name'][:-1], data)
        
        # 插入区县
        for _, row in self.districts_df.iterrows():
            prov_code = city_to_prov_code.get(row['cityCode'])
            data = {
                'code': row['code'],
                'level': 'district',
                'name': row['name'],
                'parent_code': row['cityCode']
            }
            self.trie.insert(row['name'], data)
            self.code_to_entity[row['code']] = data
            if any(row['name'].endswith(s) for s in ['区', '县', '市']):
                self.trie.insert(row['name'][:-1], data)
            self.dist_to_city_prov[row['code']] = (row['cityCode'], prov_code)
    
    def clean_address(self, address_str, anchor_prov=None):
        """清洗地址字符串"""
        if pd.isna(address_str) or not isinstance(address_str, str) or not address_str.strip():
            return ""
        
        # 标准化Unicode字符
        addr = unicodedata.normalize('NFKC', address_str)
        
        # 移除括号内容
        addr = re.sub(r'[（(【\[].*?[】)\]）]', '', addr)
        
        # 移除特殊字符
        addr = re.sub(r'[-－—_=\s/]+', '', addr)
        addr = addr.replace('中国', '', 1).replace('市辖区', '')
        
        # 处理多省份冲突
        found = {p for p in self.all_prov_names if p in addr}
        if len(found) > 1:
            target = anchor_prov if anchor_prov and anchor_prov in found else max(found, key=addr.rfind)
            idx = addr.rfind(target)
            if idx != -1:
                addr = addr[idx:]
        
        # 去重处理
        for prov in self.all_prov_names:
            count = addr.count(prov)
            if count > 1:
                addr = addr.replace(prov, "", count - 1)
        
        for cd in set(re.findall(r'.*?市|.*?区|.*?县', addr)):
            count = addr.count(cd)
            if count > 1:
                addr = addr.replace(cd, "", count - 1)
        
        return addr
    
    def _regex_parse(self, address):
        """使用正则表达式进行快速解析"""
        prov_name, city_name, dist_name = None, None, None
        
        # 匹配省份
        prov_matches = []
        for pattern in self.province_patterns:
            for match in pattern.finditer(address):
                matched = match.group(1).strip()
                mapped = self.address_mappings.get(matched, matched)
                prov_matches.append(mapped)
        
        if prov_matches:
            prov_name = prov_matches[-1]
        
        remaining = address
        if prov_name and prov_name in address:
            remaining = address[address.rfind(prov_name):]
        
        # 匹配城市
        if prov_name and prov_name in self.municipalities:
            city_name = prov_name
        else:
            city_matches = []
            for pattern in self.city_patterns:
                for match in pattern.finditer(remaining):
                    city_matches.append(match.group(1).strip())
            if city_matches:
                city_name = city_matches[-1]
        
        # 匹配区县
        dist_matches = []
        for pattern in self.district_patterns:
            for match in pattern.finditer(remaining):
                dist_matches.append(match.group(1).strip())
        if dist_matches:
            dist_name = dist_matches[-1]
        
        # 返回结果，如果没有省份但有城市，标记需要补充省份
        if not prov_name and city_name:
            return ('__NEED_PROVINCE__', city_name, dist_name)
        
        return (prov_name, city_name, dist_name)
    
    def _smart_parse(self, address, context_prov_code=None):
        """使用Trie树和决策评分的智能解析"""
        if not address:
            return None
        
        entities = self.trie.search_all_matches(address)
        if not entities:
            return None
        
        chains = self._generate_chains(entities)
        if not chains:
            return None
        
        # 评分并选择最佳链
        best_chain = None
        best_score = -float('inf')
        
        for chain in chains:
            score = self._score_chain(chain, address, entities, context_prov_code)
            if score > best_score:
                best_score = score
                best_chain = chain
        
        if not best_chain or best_score < 0:
            return None
        
        # 构建结果
        p_code, c_code, d_code = best_chain
        prov = self.code_to_entity.get(p_code, {}).get('name')
        city = self.code_to_entity.get(c_code, {}).get('name')
        dist = self.code_to_entity.get(d_code, {}).get('name')
        
        # 处理直辖市
        if prov in self.municipalities:
            city = prov
        
        return (prov, city, dist)
    
    def _generate_chains(self, entities):
        """生成所有可能的行政区划链"""
        chains = set()
        
        districts = [e for e in entities if e['data']['level'] == 'district']
        cities = [e for e in entities if e['data']['level'] == 'city']
        provinces = [e for e in entities if e['data']['level'] == 'province']
        
        # 从区县构建完整链
        for d in districts:
            c_code, p_code = self.dist_to_city_prov.get(d['data']['code'], (None, None))
            if p_code and c_code:
                chains.add((p_code, c_code, d['data']['code']))
        
        # 从城市构建链
        for c in cities:
            p_code = c['data']['parent_code']
            if p_code and not any(chain[1] == c['data']['code'] for chain in chains):
                chains.add((p_code, c['data']['code'], None))
        
        # 添加仅省份的链
        for p in provinces:
            p_code = p['data']['code']
            if not any(chain[0] == p_code for chain in chains):
                chains.add((p_code, None, None))
        
        return list(chains)
    
    def _score_chain(self, chain, address, entities, ctx_prov_code):
        """为行政区划链评分"""
        p_code, c_code, d_code = chain
        score = 0
        
        # 基础分：区县 > 城市 > 省份
        if d_code:
            score += 50
        elif c_code:
            score += 30
        else:
            score += 10
        
        # 上下文省份加分
        if ctx_prov_code and p_code == ctx_prov_code:
            score += 100
        
        # 文本覆盖率加分
        chain_entities = [e for e in entities if e['data']['code'] in {p_code, c_code, d_code}]
        if chain_entities:
            texts = sorted(list({e['text'] for e in chain_entities}), key=len, reverse=True)
            chain_text = "".join(texts)
            coverage = len(chain_text) / len(address) if address else 0
            score += coverage * 30
        
        # 冲突检测
        remaining = address
        for e in chain_entities:
            remaining = remaining.replace(e['text'], '')
        
        # 检查剩余文本中是否有其他省份
        for prov in self.all_prov_names:
            if prov in remaining and prov != self.code_to_entity.get(p_code, {}).get('name'):
                score -= 200
                break
        
        return score
    
    def _fix_missing_province(self, parsed):
        """修复缺失的省份"""
        if not parsed:
            return None
        
        prov, city, dist = parsed
        if prov == '__NEED_PROVINCE__' and city:
            # 从城市映射查找省份
            fixed_prov = self.city_to_province.get(city)
            if fixed_prov:
                return (fixed_prov, city, dist)
        
        return parsed
    
    def _is_valid_hierarchy(self, prov, city, dist):
        """验证行政区划层级是否合法"""
        if not prov:
            return True
        
        # 验证省份
        p_row = self.provinces_df[self.provinces_df['name'] == prov]
        if p_row.empty:
            return False
        
        if not city:
            return True
        
        # 验证城市
        p_code = p_row.iloc[0]['code']
        c_row = self.cities_df[
            (self.cities_df['name'] == city) & 
            (self.cities_df['provinceCode'] == p_code)
        ]
        if c_row.empty:
            return False
        
        if not dist:
            return True
        
        # 验证区县
        c_code = c_row.iloc[0]['code']
        d_row = self.districts_df[
            (self.districts_df['name'] == dist) & 
            (self.districts_df['cityCode'] == c_code)
        ]
        
        return not d_row.empty
    
    def _get_geodata(self, parsed):
        """获取地理编码数据"""
        result = {
            'province': None, 'city': None, 'district': None,
            'province_code': None, 'city_code': None, 'district_code': None,
            'province_lng': None, 'province_lat': None,
            'city_lng': None, 'city_lat': None,
            'district_lng': None, 'district_lat': None,
            'address_detail': ''
        }
        
        if not parsed:
            return result
        
        prov, city, dist = parsed
        result['province'] = prov
        result['city'] = city
        result['district'] = dist
        
        # 获取省份数据
        if prov:
            p_row = self.provinces_df[self.provinces_df['name'] == prov]
            if not p_row.empty:
                p_info = p_row.iloc[0]
                result['province_code'] = p_info['code']
                result['province_lng'] = p_info['longitude']
                result['province_lat'] = p_info['latitude']
                
                # 获取城市数据
                if city:
                    c_row = self.cities_df[
                        (self.cities_df['name'] == city) & 
                        (self.cities_df['provinceCode'] == p_info['code'])
                    ]
                    if not c_row.empty:
                        c_info = c_row.iloc[0]
                        result['city_code'] = c_info['code']
                        result['city_lng'] = c_info['longitude']
                        result['city_lat'] = c_info['latitude']
                        
                        # 获取区县数据
                        if dist:
                            d_row = self.districts_df[
                                (self.districts_df['name'] == dist) & 
                                (self.districts_df['cityCode'] == c_info['code'])
                            ]
                            if not d_row.empty:
                                d_info = d_row.iloc[0]
                                result['district_code'] = d_info['code']
                                result['district_lng'] = d_info['longitude']
                                result['district_lat'] = d_info['latitude']
        
        return result
    
    @lru_cache(maxsize=10000)
    def parse(self, address_string):
        """
        解析单个地址字符串
        
        Args:
            address_string (str): 需要解析的地址
            
        Returns:
            dict: 包含解析结果的字典，包括省市区名称、代码和坐标
        """
        if not isinstance(address_string, str) or not address_string.strip():
            return self._get_geodata(None)
        
        # 清洗地址
        cleaned = self.clean_address(address_string)
        if not cleaned:
            return self._get_geodata(None)
        
        # 第一步：正则快速解析
        parsed = self._regex_parse(cleaned)
        parsed = self._fix_missing_province(parsed)
        
        # 验证层级关系
        if parsed and self._is_valid_hierarchy(*parsed):
            result = self._get_geodata(parsed)
            # 计算详细地址
            admin_text = "".join(filter(None, parsed))
            result['address_detail'] = cleaned.replace(admin_text, '').strip()
            return result
        
        # 第二步：智能解析
        # 获取上下文省份代码
        context_prov_code = None
        if parsed and parsed[0]:
            p_row = self.provinces_df[self.provinces_df['name'] == parsed[0]]
            if not p_row.empty:
                context_prov_code = p_row.iloc[0]['code']
        
        parsed = self._smart_parse(cleaned, context_prov_code)
        result = self._get_geodata(parsed)
        
        # 计算详细地址
        if parsed:
            admin_text = "".join(filter(None, parsed))
            result['address_detail'] = cleaned.replace(admin_text, '').strip()
        else:
            result['address_detail'] = cleaned
        
        return result
    
    def parse_batch(self, addresses, num_workers=None):
        """
        批量解析地址
        
        Args:
            addresses (list): 地址列表
            num_workers (int): 并行工作进程数，默认为CPU核心数-1
            
        Returns:
            list: 解析结果列表
        """
        if not addresses:
            return []
        
        # 对于小批量，直接处理
        if len(addresses) < 100:
            return [self.parse(addr) for addr in tqdm(addresses, desc="解析地址")]
        
        # 使用多进程处理大批量
        import multiprocessing
        
        if num_workers is None:
            num_workers = max(1, multiprocessing.cpu_count() - 1)
        
        # 分块处理
        chunk_size = max(1, len(addresses) // (num_workers * 4))
        chunks = [addresses[i:i + chunk_size] for i in range(0, len(addresses), chunk_size)]
        
        with multiprocessing.Pool(num_workers) as pool:
            results = []
            with tqdm(total=len(addresses), desc="批量解析地址") as pbar:
                for chunk_results in pool.imap(self._parse_chunk, chunks):
                    results.extend(chunk_results)
                    pbar.update(len(chunk_results))
        
        return results
    
    def _parse_chunk(self, addresses):
        """解析地址块（用于多进程）"""
        return [self.parse(addr) for addr in addresses]
