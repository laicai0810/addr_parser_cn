# addr_parser_cn: 智能地址解析与地理编码API包

`addr_parser_cn` 是一个功能强大的Python库，用于处理、清洗、解析不规范的中文地址，并返回结构化的省、市、区县信息及其对应的官方行政代码和经纬度。

## 主要功能

- **深度地址解析**: 能从包含重复、缺失、混淆信息的复杂地址文本中提取出准确的省、市、区县。
- **权威数据源**: 完全基于阿里云DataV的地理数据，确保行政区划和代码的准确性和时效性。
- **多层级地理编码**: 不仅提供最精确层级的坐标，还返回省、市、区县各自的中心点经纬度。
- **易于使用**: 将复杂的处理流程封装为简单的API，只需两行代码即可完成地址解析。
- **本地化与缓存**: 自动下载并缓存地理数据，后续运行无需网络连接，速度快。
- **零依赖**: 无需用户提供任何外部数据库，开箱即用。

## 安装

1.  将本项目克隆或下载到本地。
   ```bash
    D:cd my_projects
   git clone https://github.com/laicai0810/addr_parser_cn.git
   ```
2.  在项目的根目录（即`setup.py`所在的目录）下，通过pip进行安装：

    ```bash
    pip install .
    ```

## 快速开始

```python
from addr_parser_cn import AddressParser

# 1. 创建解析器实例
# 注意：首次实例化时，会自动下载约20MB的地理数据并创建权威数据库，
# 可能需要1-2分钟。此过程仅需一次。
parser = AddressParser()

# 2. 调用parse方法进行解析
address = "太原市小店区山西省太原市小店区坞城路92号"
parsed_result = parser.parse(address)

# 3. 打印结果
import json
print(json.dumps(parsed_result, indent=2, ensure_ascii=False))
```

### 预期输出
```json
{
  "province": "山西省",
  "city": "太原市",
  "district": "小店区",
  "province_code": "140000",
  "city_code": "140100",
  "district_code": "140105",
  "province_lng": 112.549248,
  "province_lat": 37.857014,
  "city_lng": 112.549248,
  "city_lat": 37.857014,
  "district_lng": 112.589464,
  "district_lat": 37.79091,
  "address_detail": "坞城路92号"
}
```
