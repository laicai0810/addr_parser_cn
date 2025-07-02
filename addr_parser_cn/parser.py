import pandas as pd
import re
import json
import sqlite3
import os
import requests
from tqdm import tqdm


class AddressParser:
    """
    智能地址解析与地理编码器。
    """

    def __init__(self, data_dir=None):
        """
        初始化解析器。
        首次实例化时会自动下载并构建权威数据库。
        """
        if data_dir:
            self.data_dir = data_dir
        else:
            # 默认数据目录在包的安装路径下
            self.data_dir = os.path.join(os.path.dirname(__file__), 'data')

        os.makedirs(self.data_dir, exist_ok=True)

        self.aliyun_db_path = os.path.join(self.data_dir, 'aliyun_regions.sqlite')
        self.aliyun_raw_path = os.path.join(self.data_dir, 'aliyun_raw_data.json')

        print("正在初始化地址解析器...")
        self._create_aliyun_db_if_needed()
        self._load_all_data()
        print("解析器初始化完成。")

    def parse(self, address_string):
        """
        解析单个地址字符串。

        Args:
            address_string (str): 需要解析的地址。

        Returns:
            dict: 包含解析结果的字典。
        """
        if not isinstance(address_string, str) or not address_string.strip():
            return self._get_empty_result()

        # 步骤1：初步解析中文名
        parsed_names = self._pre_parse_address(address_string)

        # 步骤2：在权威库中匹配代码和坐标
        final_result = self._match_and_get_data(parsed_names)

        # 将剩余的详细地址附加到结果中
        final_result['address_detail'] = parsed_names.get('address_detail', '')

        return final_result

    def _get_empty_result(self):
        return {
            'province': None, 'city': None, 'district': None,
            'province_code': None, 'city_code': None, 'district_code': None,
            'province_lng': None, 'province_lat': None,
            'city_lng': None, 'city_lat': None,
            'district_lng': None, 'district_lat': None,
            'address_detail': ''
        }

    def _create_aliyun_db_if_needed(self):
        if os.path.exists(self.aliyun_db_path):
            return
        print(f"未找到权威数据库 '{self.aliyun_db_path}'，开始构建...")
        if not os.path.exists(self.aliyun_raw_path):
            self._download_raw_data()
        self._create_sqlite_from_json()

    def _download_raw_data(self):
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

        city_to_prov_map = cities_table.set_index('code')['provinceCode'].to_dict()
        for _, prov_row in provinces_table.iterrows():
            if prov_row['name'].endswith('市'): city_to_prov_map[prov_row['code']] = prov_row['code']
        districts_table['provinceCode'] = districts_table['cityCode'].map(city_to_prov_map)

        with sqlite3.connect(self.aliyun_db_path) as con:
            provinces_table.to_sql('provinces', con, if_exists='replace', index=False)
            cities_table.to_sql('cities', con, if_exists='replace', index=False)
            districts_table.to_sql('districts', con, if_exists='replace', index=False)
        print("权威数据库创建成功。")

    def _process_feature(self, feature):
        properties = feature.get('properties', {}) if 'properties' in feature else feature
        if not properties or not properties.get('adcode'): return None
        adcode = str(properties['adcode'])
        center = properties.get('center')
        longitude, latitude = (center[0], center[1]) if center and len(center) == 2 else (
        properties.get('lng'), properties.get('lat'))
        parent = properties.get('parent')
        parent_adcode = str(parent.get('adcode', '')) if isinstance(parent, dict) else str(parent or '')
        return {'code': adcode, 'name': properties.get('name'), 'level': properties.get('level'),
                'longitude': longitude, 'latitude': latitude, 'parentCode': parent_adcode}

    def _load_all_data(self):
        print("正在加载解析所需的数据索引...")
        with sqlite3.connect(self.aliyun_db_path) as con:
            self.provinces_df = pd.read_sql_query("SELECT * FROM provinces", con)
            self.cities_df = pd.read_sql_query("SELECT * FROM cities", con)
            self.districts_df = pd.read_sql_query("SELECT * FROM districts", con)

        self.province_alias_map = {}
        for _, row in self.provinces_df.iterrows():
            full_name = row['name']
            self.province_alias_map[full_name] = full_name
            alias = re.sub(r'省|市|自治区|特别行政区|壮族|回族|维吾尔|蒙古', '', full_name)
            if alias != full_name and alias: self.province_alias_map[alias] = full_name

        self.all_provinces = sorted(list(self.province_alias_map.keys()), key=len, reverse=True)
        self.all_cities = sorted(self.cities_df['name'].unique().tolist(), key=len, reverse=True)

        self.city_to_districts_map = self.districts_df.groupby('cityCode')['name'].apply(
            lambda x: sorted(x.tolist(), key=len, reverse=True)).to_dict()
        self.city_code_to_province_code_map = self.cities_df.set_index('code')['provinceCode'].to_dict()

    def _pre_parse_address(self, address_string):
        result = {'province': None, 'city': None, 'district': None, 'address_detail': ''}

        cleaned = re.sub(r'(null|undefined|none|na)+', '', address_string, flags=re.IGNORECASE)
        cleaned = re.sub(r'[_\-@\(\)\s]|市辖区|^\d+', '', cleaned)

        first_valid_pos = -1
        search_keywords = self.all_provinces + self.all_cities
        for keyword in search_keywords:
            pos = cleaned.find(keyword)
            if pos != -1 and (first_valid_pos == -1 or pos < first_valid_pos): first_valid_pos = pos
        if first_valid_pos > 0: cleaned = cleaned[first_valid_pos:]

        remaining_address = cleaned

        # 匹配省
        for prov_alias in self.all_provinces:
            if remaining_address.startswith(prov_alias):
                result['province'] = self.province_alias_map[prov_alias]
                remaining_address = remaining_address[len(prov_alias):]
                break

        # 如果省份未找到，尝试市+区组合
        if not result['province']:
            for city_name in self.all_cities:
                if remaining_address.startswith(city_name):
                    city_code_match = self.cities_df[self.cities_df['name'] == city_name]
                    if not city_code_match.empty:
                        # Handle multiple cities with the same name by iterating
                        for _, city_row in city_code_match.iterrows():
                            city_code = city_row['code']
                            districts_for_city = self.city_to_districts_map.get(city_code, [])
                            temp_addr_after_city = remaining_address[len(city_name):]
                            for district_name in districts_for_city:
                                if temp_addr_after_city.startswith(district_name):
                                    prov_code = self.city_code_to_province_code_map.get(city_code)
                                    prov_name_match = self.provinces_df[self.provinces_df['code'] == prov_code]
                                    if not prov_name_match.empty:
                                        result['province'] = prov_name_match.iloc[0]['name']
                                        result['city'] = city_name
                                        result['district'] = district_name
                                        remaining_address = temp_addr_after_city[len(district_name):]
                                        break
                            if result['province']: break
                if result['province']: break

        # 匹配市
        if result['province'] and not result['city']:
            prov_code_match = self.provinces_df[self.provinces_df['name'] == result['province']]
            if not prov_code_match.empty:
                prov_code = prov_code_match.iloc[0]['code']
                cities_in_province = self.cities_df[self.cities_df['provinceCode'] == prov_code]
                cities_in_province = sorted(cities_in_province['name'].unique().tolist(), key=len, reverse=True)
                for city_name in cities_in_province:
                    if remaining_address.startswith(city_name):
                        result['city'] = city_name
                        remaining_address = remaining_address[len(city_name):]
                        break

        # 匹配区
        if result['city'] and not result['district']:
            city_code_match = self.cities_df[self.cities_df['name'] == result['city']]
            prov_code_match = self.provinces_df[self.provinces_df['name'] == result['province']]
            if not city_code_match.empty and not prov_code_match.empty:
                # Handle multiple cities with same name
                for _, city_row in city_code_match.iterrows():
                    city_code = city_row['code']
                    # Ensure we are in the correct province
                    if self.city_code_to_province_code_map.get(city_code) == prov_code_match.iloc[0]['code']:
                        districts_in_city = self.districts_df[self.districts_df['cityCode'] == city_code]
                        districts_in_city = sorted(districts_in_city['name'].unique().tolist(), key=len, reverse=True)
                        for district_name in districts_in_city:
                            if remaining_address.startswith(district_name):
                                result['district'] = district_name
                                remaining_address = remaining_address[len(district_name):]
                                break
                    if result['district']: break

        result['address_detail'] = remaining_address
        return result

    def _match_and_get_data(self, parsed_names):
        result = self._get_empty_result()
        result['province'] = parsed_names['province']
        result['city'] = parsed_names['city']
        result['district'] = parsed_names['district']

        prov_name, city_name, dist_name = parsed_names['province'], parsed_names['city'], parsed_names['district']
        if pd.isna(prov_name): return result

        province_match = self.provinces_df[self.provinces_df['name'] == prov_name]
        if province_match.empty: return result

        province_row = province_match.iloc[0]
        result['province_code'] = province_row['code']
        result['province_lng'], result['province_lat'] = province_row['longitude'], province_row['latitude']
        province_adcode = province_row['code']

        if prov_name.endswith('市'): city_name = prov_name
        if pd.isna(city_name): return result

        city_match = self.cities_df[
            (self.cities_df['name'] == city_name) & (self.cities_df['provinceCode'] == province_adcode)]
        if city_match.empty: return result

        city_row = city_match.iloc[0]
        result['city_code'] = city_row['code']
        result['city_lng'], result['city_lat'] = city_row['longitude'], city_row['latitude']
        city_adcode = city_row['code']

        if pd.isna(dist_name): return result

        district_match = self.districts_df[
            (self.districts_df['name'] == dist_name) & (self.districts_df['cityCode'] == city_adcode)]
        if district_match.empty: return result

        district_row = district_match.iloc[0]
        result['district_code'] = district_row['code']
        result['district_lng'], result['district_lat'] = district_row['longitude'], district_row['latitude']

        return result