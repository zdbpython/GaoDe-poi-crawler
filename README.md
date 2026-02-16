# 高德POI数据采集工具

一个基于Python的高德地图POI（兴趣点）数据采集工具，支持四叉树递归拆分算法，可突破API单次返回数据量限制，获取完整的POI数据。

## ✨ 功能特性

- 🔍 **多边形区域搜索** - 支持按行政区划边界进行POI搜索
- 🌳 **四叉树递归拆分** - 自动检测数据量超限并拆分区域，突破API 200条返回限制
- 🔄 **多API Key轮询** - 支持配置多个API Key，自动切换和配额管理
- 📍 **坐标转换** - 支持GCJ02、WGS84、BD09三种坐标系转换
- 🖥️ **图形化界面** - 基于tkinter的友好GUI界面
- 💾 **数据导出** - 支持CSV格式导出，自动去重

## 📋 目录结构

```
高德地图/
├── main.py          # 主入口程序
├── api.py           # 高德API请求模块
├── config.py        # 配置管理模块
├── data.py          # 数据处理模块
├── gui.py           # GUI界面模块
├── quadtree.py      # 四叉树拆分算法
├── generate_csv.py  # 数据生成工具
├── config.json      # 配置文件
├── cache/           # 缓存目录
├── city_temp/       # 城市数据源
├── poi_temp/        # POI类型数据源
├── data/            # 输出目录
└── logs/            # 日志目录
```

## 🚀 快速开始

### 环境要求

- Python 3.8+
- 依赖库：requests, pandas, openpyxl

### 安装依赖

```bash
pip install requests pandas openpyxl
```

### 获取API Key

1. 访问 [高德开放平台](https://lbs.amap.com/)
2. 注册账号并创建应用
3. 获取Web服务API Key

### 运行程序

```bash
python main.py
```

## 📖 使用说明

### 1. 选择区域

- 在左侧选择省份、城市、区县
- 点击"添加选中区县"添加到目标列表

### 2. 选择POI类型

- 在左侧列表中搜索或浏览POI类型
- 双击或点击"添加→"按钮添加到目标列表
- 已选类型会显示在右侧"目标兴趣点"区域
- 点击标签右侧"×"可移除单个类型

### 3. 配置参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| API Key | 高德Web服务API Key | - |
| POI超量阈值 | 超过此值触发四叉树拆分 | 180 |
| 请求间隔 | 每次请求间隔（秒） | 0.35 |
| 并发数 | 并行处理的线程数 | 3 |
| 坐标转换 | WGS84/GCJ02/BD09 | GCJ02 |

### 4. 开始采集

1. 点击"开始采集"按钮
2. 首次会弹出字段选择对话框
3. 选择需要导出的字段
4. 等待采集完成

## 🔧 四叉树算法说明

### 算法原理

高德API限制单次请求最多返回约200条数据。当区域内POI数量超过此限制时，使用四叉树算法递归拆分区域：

```
原始区域（数据量>200）
┌─────────────────────────────┐
│        │        │        │
│ 子区域1│ 子区域2│ 子区域3│ 子区域4
│ ~200条 │ ~200条 │ ~200条 │ ~200条
│        │        │        │
└─────────────────────────────┘
```

### 终止条件

1. POI数量 < 阈值（默认180条）
2. 网格跨度 < 0.005度（约500米）
3. 递归深度 > 20

## ⚠️ 注意事项

### API限制

| 限制项 | 说明 |
|--------|------|
| 每页数据量 | 最大25条 |
| 单区域上限 | 约200条（8页） |
| 请求频率 | 每个Key每秒最多3次 |
| 日配额 | 根据账户等级不同 |

### 合规声明

本工具仅用于个人学习/内部项目，不批量爬取、存储、转售高德数据，不用于商业用途。使用前请确保遵守[高德开放平台服务条款](https://lbs.amap.com/pages/terms/)。

## 📊 输出字段

| 字段 | 说明 |
|------|------|
| id | POI唯一标识 |
| name | POI名称 |
| type | POI类型 |
| typecode | POI类型编码 |
| address | 地址 |
| location | 经纬度坐标 |
| pname | 省份名称 |
| cityname | 城市名称 |
| adname | 区域名称 |
| tel | 电话 |
| ... | 更多字段可选 |

## 🛠️ 开发说明

### 核心模块

- **api.py**: 封装高德API请求，支持Key轮询、错误重试、配额管理
- **quadtree.py**: 实现四叉树空间拆分算法
- **data.py**: 数据处理、坐标转换、CSV导出
- **gui.py**: tkinter图形界面
- **config.py**: 配置管理、POI类型加载

### 扩展开发

```python
# 自定义采集脚本示例
from api import AmapAPI
from quadtree import QuadTreeSplitter, BoundingBox

api = AmapAPI(['your_api_key'], request_interval=0.35)
splitter = QuadTreeSplitter(api, poi_threshold=180)

bbox = BoundingBox(116.0, 39.0, 117.0, 40.0)
pois = splitter.quadtree_split(bounds=bbox, types='050500')

print(f"获取 {len(pois)} 条POI数据")
```

## 📝 更新日志

### v2.1
- 优化四叉树拆分逻辑，先请求第8页判断数据量
- 新增GUI兴趣点标签选择功能
- 修复API请求频率限制问题
- 升级到高德V5 API

### v2.0
- 重构四叉树算法
- 新增GUI界面
- 支持多API Key轮询

## 📄 许可证

MIT License

## 🙏 致谢

- [高德开放平台](https://lbs.amap.com/) 提供API服务
- POI分类数据来源于高德官方分类编码表
