# -*- coding: utf-8 -*-
"""
高德POI数据采集工具 - 数据处理与坐标转换模块

【合规声明】仅用于个人学习/内部项目，不批量爬取、存储、转售高德数据，不用于商业用途。

功能：
- GCJ02转WGS84坐标转换
- GCJ02转BD09坐标转换
- POI数据处理与去重
- CSV文件写入
"""

import math
import os
import csv
import logging
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 坐标转换常量
X_PI = 3.14159265358979324 * 3000.0 / 180.0
PI = 3.1415926535897932384626
A = 6378245.0  # 长半轴
EE = 0.00669342162296594323  # 扁率


def _transform_lat(lng: float, lat: float) -> float:
    """
    纬度转换辅助函数
    
    Args:
        lng: 经度
        lat: 纬度
        
    Returns:
        float: 转换后的纬度偏移量
    """
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + \
          0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * PI) + 20.0 *
            math.sin(2.0 * lng * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * PI) + 40.0 *
            math.sin(lat / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * PI) + 320 *
            math.sin(lat * PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(lng: float, lat: float) -> float:
    """
    经度转换辅助函数
    
    Args:
        lng: 经度
        lat: 纬度
        
    Returns:
        float: 转换后的经度偏移量
    """
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + \
          0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * PI) + 20.0 *
            math.sin(2.0 * lng * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * PI) + 40.0 *
            math.sin(lng / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * PI) + 300.0 *
            math.sin(lng / 30.0 * PI)) * 2.0 / 3.0
    return ret


def _out_of_china(lng: float, lat: float) -> bool:
    """
    判断坐标是否在中国境内
    
    Args:
        lng: 经度
        lat: 纬度
        
    Returns:
        bool: 是否在中国境外
    """
    if lng < 72.004 or lng > 137.8347:
        return True
    if lat < 0.8293 or lat > 55.8271:
        return True
    return False


def gcj02_to_wgs84(lng_gcj: float, lat_gcj: float) -> Tuple[float, float]:
    """
    GCJ02坐标转WGS84坐标（GPS标准坐标）
    
    算法原理：
    GCJ02是在WGS84基础上加上偏移量，WGS84 = GCJ02 - 偏移量
    通过逆向计算偏移量来还原WGS84坐标
    
    Args:
        lng_gcj: GCJ02经度
        lat_gcj: GCJ02纬度
        
    Returns:
        Tuple[float, float]: (WGS84经度, WGS84纬度)
    """
    if _out_of_china(lng_gcj, lat_gcj):
        return lng_gcj, lat_gcj
    
    dlat = _transform_lat(lng_gcj - 105.0, lat_gcj - 35.0)
    dlng = _transform_lng(lng_gcj - 105.0, lat_gcj - 35.0)
    radlat = lat_gcj / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    
    dlat = (dlat * 180.0) / ((A * (1 - EE)) / (magic * sqrtmagic) * PI)
    dlng = (dlng * 180.0) / (A / sqrtmagic * math.cos(radlat) * PI)
    
    mglat = lat_gcj + dlat
    mglng = lng_gcj + dlng
    
    return lng_gcj * 2 - mglng, lat_gcj * 2 - mglat


def gcj02_to_bd09(lng_gcj: float, lat_gcj: float) -> Tuple[float, float]:
    """
    GCJ02坐标转BD09坐标（百度坐标）
    
    算法原理：
    BD09是在GCJ02基础上再次加密，通过极坐标转换实现
    
    Args:
        lng_gcj: GCJ02经度
        lat_gcj: GCJ02纬度
        
    Returns:
        Tuple[float, float]: (BD09经度, BD09纬度)
    """
    if _out_of_china(lng_gcj, lat_gcj):
        return lng_gcj, lat_gcj
    
    z = math.sqrt(lng_gcj * lng_gcj + lat_gcj * lat_gcj) + \
        0.00002 * math.sin(lat_gcj * X_PI)
    theta = math.atan2(lat_gcj, lng_gcj) + \
            0.000003 * math.cos(lng_gcj * X_PI)
    
    lng_bd = z * math.cos(theta) + 0.0065
    lat_bd = z * math.sin(theta) + 0.006
    
    return lng_bd, lat_bd


@dataclass
class POIRecord:
    """
    POI记录数据类
    
    Attributes:
        id: POI唯一标识
        name: POI名称
        location_gcj02: GCJ02坐标字符串 "lng,lat"
        lng_gcj02: GCJ02经度
        lat_gcj02: GCJ02纬度
        lng_wgs84: WGS84经度（可选）
        lat_wgs84: WGS84纬度（可选）
        lng_bd09: BD09经度（可选）
        lat_bd09: BD09纬度（可选）
        其他动态字段...
    """
    id: str = ""
    name: str = ""
    location_gcj02: str = ""
    lng_gcj02: float = 0.0
    lat_gcj02: float = 0.0
    lng_wgs84: Optional[float] = None
    lat_wgs84: Optional[float] = None
    lng_bd09: Optional[float] = None
    lat_bd09: Optional[float] = None
    _extra_fields: Dict[str, Any] = None
    
    def __post_init__(self):
        if self._extra_fields is None:
            self._extra_fields = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            'id': self.id,
            'name': self.name,
            'location_gcj02': self.location_gcj02,
            'lng_gcj02': self.lng_gcj02,
            'lat_gcj02': self.lat_gcj02,
        }
        
        if self.lng_wgs84 is not None:
            result['lng_wgs84'] = self.lng_wgs84
            result['lat_wgs84'] = self.lat_wgs84
        
        if self.lng_bd09 is not None:
            result['lng_bd09'] = self.lng_bd09
            result['lat_bd09'] = self.lat_bd09
        
        result.update(self._extra_fields)
        return result


class DataProcessor:
    """
    数据处理器类
    
    负责POI数据的处理、转换、去重和存储
    """
    
    def __init__(self, coord_conversions: List[str] = None, selected_fields: List[str] = None):
        """
        初始化数据处理器
        
        Args:
            coord_conversions: 需要进行的坐标转换类型列表 ['wgs84', 'bd09']
            selected_fields: 用户选择的输出字段列表
        """
        self.coord_conversions = coord_conversions or []
        self.selected_fields = selected_fields or []
        self._seen_ids: Set[str] = set()
        self._seen_name_loc: Set[str] = set()
        self._file_initialized = False
        self._csv_file = None
        self._csv_writer = None
    
    def parse_poi_data(self, poi_data: Dict[str, Any]) -> Optional[POIRecord]:
        """
        解析API返回的单条POI数据
        
        Args:
            poi_data: API返回的POI数据字典
            
        Returns:
            Optional[POIRecord]: 解析后的POI记录，无效数据返回None
        """
        try:
            poi_id = poi_data.get('id', '')
            name = poi_data.get('name', '')
            location = poi_data.get('location', '')
            
            if not name or not location:
                return None
            
            parts = location.split(',')
            if len(parts) != 2:
                return None
            
            try:
                lng_gcj = float(parts[0])
                lat_gcj = float(parts[1])
            except ValueError:
                return None
            
            if lng_gcj == 0 or lat_gcj == 0:
                return None
            
            record = POIRecord(
                id=poi_id,
                name=name,
                location_gcj02=location,
                lng_gcj02=lng_gcj,
                lat_gcj02=lat_gcj
            )
            
            if 'wgs84' in self.coord_conversions:
                record.lng_wgs84, record.lat_wgs84 = gcj02_to_wgs84(lng_gcj, lat_gcj)
            
            if 'bd09' in self.coord_conversions:
                record.lng_bd09, record.lat_bd09 = gcj02_to_bd09(lng_gcj, lat_gcj)
            
            extra_fields = {}
            base_fields = {'id', 'name', 'location'}
            for key, value in poi_data.items():
                if key not in base_fields:
                    extra_fields[key] = value
            
            record._extra_fields = extra_fields
            
            return record
            
        except Exception as e:
            logger.error(f"解析POI数据失败: {e}")
            return None
    
    def is_duplicate(self, record: POIRecord) -> bool:
        """
        检查记录是否重复
        
        Args:
            record: POI记录
            
        Returns:
            bool: 是否重复
        """
        if record.id and record.id in self._seen_ids:
            return True
        
        name_loc_key = f"{record.name}_{record.location_gcj02}"
        if name_loc_key in self._seen_name_loc:
            return True
        
        return False
    
    def mark_as_seen(self, record: POIRecord) -> None:
        """
        标记记录为已处理
        
        Args:
            record: POI记录
        """
        if record.id:
            self._seen_ids.add(record.id)
        
        name_loc_key = f"{record.name}_{record.location_gcj02}"
        self._seen_name_loc.add(name_loc_key)
    
    def init_csv_file(self, filepath: str) -> bool:
        """
        初始化CSV文件
        
        Args:
            filepath: CSV文件路径
            
        Returns:
            bool: 初始化是否成功
        """
        try:
            directory = os.path.dirname(filepath)
            if directory and not os.path.exists(directory):
                os.makedirs(directory)
            
            file_exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0
            
            self._csv_file = open(filepath, 'a', newline='', encoding='gbk', errors='replace')
            self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=self.selected_fields)
            
            if not file_exists:
                self._csv_writer.writeheader()
                self._csv_file.flush()
                logger.info(f"CSV文件已创建: {filepath}")
            
            self._file_initialized = True
            return True
            
        except PermissionError:
            logger.error(f"无写入权限: {filepath}")
            return False
        except Exception as e:
            logger.error(f"初始化CSV文件失败: {e}")
            return False
    
    def write_record(self, record: POIRecord) -> bool:
        """
        写入单条记录到CSV文件
        
        Args:
            record: POI记录
            
        Returns:
            bool: 写入是否成功
        """
        if not self._file_initialized:
            logger.error("CSV文件未初始化")
            return False
        
        if self.is_duplicate(record):
            return False
        
        try:
            row_data = record.to_dict()
            filtered_row = {k: row_data.get(k, '') for k in self.selected_fields}
            self._csv_writer.writerow(filtered_row)
            self._csv_file.flush()
            self.mark_as_seen(record)
            return True
        except Exception as e:
            logger.error(f"写入记录失败: {e}")
            return False
    
    def write_records(self, records: List[POIRecord]) -> int:
        """
        批量写入记录
        
        Args:
            records: POI记录列表
            
        Returns:
            int: 成功写入的记录数
        """
        count = 0
        for record in records:
            if self.write_record(record):
                count += 1
        return count
    
    def close(self) -> None:
        """关闭CSV文件"""
        if self._csv_file:
            self._csv_file.close()
            self._csv_file = None
            self._csv_writer = None
            self._file_initialized = False
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取处理统计信息
        
        Returns:
            Dict[str, int]: 统计信息
        """
        return {
            'total_ids': len(self._seen_ids),
            'total_name_loc': len(self._seen_name_loc)
        }


def get_all_available_fields(api_response: Dict[str, Any], coord_conversions: List[str]) -> List[str]:
    """
    从API响应中提取所有可用字段，并根据坐标转换选项添加转换字段
    
    Args:
        api_response: API返回的单条POI数据
        coord_conversions: 坐标转换类型列表
        
    Returns:
        List[str]: 可用字段列表
    """
    fields = []
    
    for key in api_response.keys():
        if key == 'location':
            fields.append('location_gcj02')
            fields.append('lng_gcj02')
            fields.append('lat_gcj02')
        else:
            fields.append(key)
    
    if 'wgs84' in coord_conversions:
        fields.append('lng_wgs84')
        fields.append('lat_wgs84')
    
    if 'bd09' in coord_conversions:
        fields.append('lng_bd09')
        fields.append('lat_bd09')
    
    return fields
