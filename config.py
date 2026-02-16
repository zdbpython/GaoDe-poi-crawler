# -*- coding: utf-8 -*-
"""
高德POI数据采集工具 - 配置管理模块

【合规声明】仅用于个人学习/内部项目，不批量爬取、存储、转售高德数据，不用于商业用途。

功能：
- 管理用户配置的保存与加载
- 定义默认配置参数
- 管理API Key轮询
"""

import json
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
import logging

logger = logging.getLogger(__name__)

CONFIG_FILE = "./config.json"
CACHE_DIR = "./cache"
DATA_DIR = "./data"
LOG_DIR = "./logs"

DISTRICT_BOUNDS_CACHE = os.path.join(CACHE_DIR, "district_bounds.json")


@dataclass
class AppConfig:
    """
    应用配置数据类
    
    Attributes:
        api_keys: 高德API Key列表
        poi_threshold: POI超量阈值，超过此值触发四叉树拆分
        request_interval: 请求间隔（秒）
        max_workers: 并发请求数
        selected_districts: 已选择的区县列表 [{province, city, district, adcode}]
        selected_poi_types: 已选择的POI类型列表 [{name, code}]
        coord_conversions: 已选择的坐标转换类型列表 ['wgs84', 'bd09']
        selected_fields: 已选择的输出字段列表
    """
    api_keys: List[str] = field(default_factory=list)
    poi_threshold: int = 180
    request_interval: float = 0.3
    max_workers: int = 3
    selected_districts: List[Dict[str, str]] = field(default_factory=list)
    selected_poi_types: List[Dict[str, str]] = field(default_factory=list)
    coord_conversions: List[str] = field(default_factory=list)
    selected_fields: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        """从字典创建配置对象"""
        return cls(
            api_keys=data.get('api_keys', []),
            poi_threshold=data.get('poi_threshold', 180),
            request_interval=data.get('request_interval', 0.3),
            max_workers=data.get('max_workers', 3),
            selected_districts=data.get('selected_districts', []),
            selected_poi_types=data.get('selected_poi_types', []),
            coord_conversions=data.get('coord_conversions', []),
            selected_fields=data.get('selected_fields', [])
        )


class ConfigManager:
    """
    配置管理器类
    
    负责配置的保存、加载和验证
    """
    
    def __init__(self):
        self.config = AppConfig()
        self._current_key_index = 0
    
    def save_config(self) -> bool:
        """
        保存配置到文件
        
        Returns:
            bool: 保存是否成功
        """
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config.to_dict(), f, ensure_ascii=False, indent=2)
            logger.info(f"配置已保存到 {CONFIG_FILE}")
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False
    
    def load_config(self) -> bool:
        """
        从文件加载配置
        
        Returns:
            bool: 加载是否成功
        """
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.config = AppConfig.from_dict(data)
                logger.info(f"配置已从 {CONFIG_FILE} 加载")
                return True
            else:
                logger.info("配置文件不存在，使用默认配置")
                return False
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return False
    
    def get_current_key(self) -> Optional[str]:
        """
        获取当前使用的API Key
        
        Returns:
            Optional[str]: 当前API Key，如果没有可用Key则返回None
        """
        if not self.config.api_keys:
            return None
        return self.config.api_keys[self._current_key_index]
    
    def rotate_key(self) -> Optional[str]:
        """
        轮询切换到下一个API Key
        
        Returns:
            Optional[str]: 新的API Key，如果没有可用Key则返回None
        """
        if not self.config.api_keys:
            return None
        
        self._current_key_index = (self._current_key_index + 1) % len(self.config.api_keys)
        logger.warning(f"API Key已切换，当前使用第 {self._current_key_index + 1} 个Key")
        return self.config.api_keys[self._current_key_index]
    
    def has_valid_key(self) -> bool:
        """
        检查是否有可用的API Key
        
        Returns:
            bool: 是否有可用Key
        """
        return len(self.config.api_keys) > 0
    
    def validate_params(self) -> Dict[str, str]:
        """
        验证配置参数的有效性
        
        Returns:
            Dict[str, str]: 错误信息字典，空字典表示验证通过
        """
        errors = {}
        
        if not self.config.api_keys:
            errors['api_keys'] = "请输入至少一个高德API Key"
        
        if self.config.poi_threshold < 1 or self.config.poi_threshold > 200:
            errors['poi_threshold'] = "POI超量阈值应在1-200之间"
        
        if self.config.request_interval < 0.1:
            errors['request_interval'] = "请求间隔不能小于0.1秒"
        
        if self.config.max_workers < 1 or self.config.max_workers > 10:
            errors['max_workers'] = "并发请求数应在1-10之间"
        
        return errors


def ensure_directories() -> None:
    """
    确保必要的目录存在
    """
    for dir_path in [CACHE_DIR, DATA_DIR, LOG_DIR]:
        os.makedirs(dir_path, exist_ok=True)


def _try_read_file(filepath: str) -> List[str]:
    """
    尝试用多种编码读取文件
    
    Args:
        filepath: 文件路径
        
    Returns:
        List[str]: 文件行列表
    """
    encodings = ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']
    
    for encoding in encodings:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                return f.readlines()
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    raise ValueError(f"无法识别文件编码: {filepath}")


def load_poi_types(filepath: str = "poi_temp.csv") -> List[Dict[str, str]]:
    """
    加载POI类型数据
    
    Args:
        filepath: POI类型文件路径
        
    Returns:
        List[Dict[str, str]]: POI类型列表，每项包含name和code
    """
    poi_types = []
    try:
        if os.path.exists(filepath):
            lines = _try_read_file(filepath)
            for line in lines:
                line = line.strip()
                if line:
                    parts = line.rsplit(',', 1)
                    if len(parts) == 2:
                        poi_types.append({
                            'name': parts[0].strip(),
                            'code': parts[1].strip()
                        })
            logger.info(f"已加载 {len(poi_types)} 个POI类型")
        else:
            logger.warning(f"POI类型文件 {filepath} 不存在")
    except Exception as e:
        logger.error(f"加载POI类型失败: {e}")
    return poi_types


def load_cities(filepath: str = "city_temp.csv") -> List[Dict[str, str]]:
    """
    加载城市行政区划数据
    
    Args:
        filepath: 城市文件路径
        
    Returns:
        List[Dict[str, str]]: 城市列表，每项包含province, city, district, adcode
    """
    cities = []
    try:
        if os.path.exists(filepath):
            lines = _try_read_file(filepath)
            for line in lines:
                line = line.strip()
                if line:
                    parts = line.split(',')
                    if len(parts) >= 4:
                        cities.append({
                            'province': parts[0].strip(),
                            'city': parts[1].strip(),
                            'district': parts[2].strip(),
                            'adcode': parts[3].strip()
                        })
            logger.info(f"已加载 {len(cities)} 个行政区划")
        else:
            logger.warning(f"城市文件 {filepath} 不存在")
    except Exception as e:
        logger.error(f"加载城市数据失败: {e}")
    return cities


def get_provinces(cities: List[Dict[str, str]]) -> List[str]:
    """
    从城市数据中提取省份列表（去重）
    
    Args:
        cities: 城市数据列表
        
    Returns:
        List[str]: 省份列表
    """
    provinces = list(set(c['province'] for c in cities))
    return sorted(provinces)


def get_cities_by_province(cities: List[Dict[str, str]], province: str) -> List[str]:
    """
    根据省份获取城市列表（去重）
    
    Args:
        cities: 城市数据列表
        province: 省份名称
        
    Returns:
        List[str]: 城市列表
    """
    city_list = list(set(
        c['city'] for c in cities 
        if c['province'] == province
    ))
    return sorted(city_list)


def get_districts_by_city(cities: List[Dict[str, str]], province: str, city: str) -> List[Dict[str, str]]:
    """
    根据省份和城市获取区县列表
    
    Args:
        cities: 城市数据列表
        province: 省份名称
        city: 城市名称
        
    Returns:
        List[Dict[str, str]]: 区县列表
    """
    districts = [
        c for c in cities 
        if c['province'] == province and c['city'] == city
    ]
    return sorted(districts, key=lambda x: x['district'])
