# -*- coding: utf-8 -*-
"""
高德POI数据采集工具 - API请求模块

【合规声明】仅用于个人学习/内部项目，不批量爬取、存储、转售高德数据，不用于商业用途。

功能：
- 高德POI搜索API封装
- 行政区域边界查询
- API Key轮询与错误处理
- 请求重试机制
"""

import json
import time
import logging
import requests
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import os

logger = logging.getLogger(__name__)

# 高德API基础URL (V5版本)
AMAP_POI_URL = "https://restapi.amap.com/v5/place/polygon"
AMAP_KEYWORD_URL = "https://restapi.amap.com/v5/place/around"
AMAP_DISTRICT_URL = "https://restapi.amap.com/v3/config/district"

# 请求超时时间（秒）
REQUEST_TIMEOUT = 10

# 重试配置
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]


@dataclass
class APIResult:
    """
    API请求结果数据类
    
    Attributes:
        success: 请求是否成功
        data: 返回的数据
        count: POI数量
        error_message: 错误信息
        status: API返回的状态码
        info: API返回的状态信息
    """
    success: bool = False
    data: List[Dict[str, Any]] = None
    count: int = 0
    error_message: str = ""
    status: str = ""
    info: str = ""
    
    def __post_init__(self):
        if self.data is None:
            self.data = []


class AmapAPI:
    """
    高德地图API封装类
    
    提供POI搜索、行政区域查询等功能
    
    注意：高德API限制每个Key每秒最多3次请求
    """
    
    # 每个Key每秒最多3次请求，最小间隔0.34秒
    MIN_REQUEST_INTERVAL = 0.34
    
    def __init__(self, api_keys: List[str], request_interval: float = 0.35):
        """
        初始化API客户端
        
        Args:
            api_keys: API Key列表
            request_interval: 请求间隔（秒），最小0.34秒
        """
        self.api_keys = api_keys
        # 确保请求间隔不小于最小值
        self.request_interval = max(request_interval, self.MIN_REQUEST_INTERVAL)
        self._current_key_index = 0
        self._last_request_time = 0
        self._key_status: Dict[str, Dict[str, Any]] = {
            key: {'valid': True, 'quota_exceeded': False, 'error_count': 0}
            for key in api_keys
        }
        # 每个Key的最后请求时间
        self._key_last_request: Dict[str, float] = {key: 0 for key in api_keys}
    
    def _get_current_key(self) -> Optional[str]:
        """
        获取当前可用的API Key
        
        Returns:
            Optional[str]: 可用的API Key，如果没有则返回None
        """
        for _ in range(len(self.api_keys)):
            key = self.api_keys[self._current_key_index]
            if self._key_status[key]['valid'] and not self._key_status[key]['quota_exceeded']:
                return key
            self._current_key_index = (self._current_key_index + 1) % len(self.api_keys)
        
        return None
    
    def _rotate_key(self) -> Optional[str]:
        """
        切换到下一个API Key
        
        Returns:
            Optional[str]: 新的API Key
        """
        self._current_key_index = (self._current_key_index + 1) % len(self.api_keys)
        return self._get_current_key()
    
    def _mark_key_invalid(self, key: str, reason: str = "") -> None:
        """
        标记API Key为无效
        
        Args:
            key: API Key
            reason: 无效原因
        """
        if key in self._key_status:
            self._key_status[key]['valid'] = False
            self._key_status[key]['error_count'] += 1
            logger.warning(f"API Key {key[:8]}... 已标记为无效: {reason}")
    
    def _mark_key_quota_exceeded(self, key: str) -> None:
        """
        标记API Key配额超限
        
        Args:
            key: API Key
        """
        if key in self._key_status:
            self._key_status[key]['quota_exceeded'] = True
            logger.warning(f"API Key {key[:8]}... 配额超限")
    
    def _wait_for_interval(self, key: str = None) -> None:
        """
        等待请求间隔
        
        确保每个Key每秒不超过3次请求
        
        Args:
            key: 当前使用的API Key
        """
        current_time = time.time()
        
        # 全局间隔
        elapsed = current_time - self._last_request_time
        if elapsed < self.request_interval:
            time.sleep(self.request_interval - elapsed)
        
        # 针对特定Key的间隔（确保每秒不超过3次）
        if key and key in self._key_last_request:
            key_elapsed = current_time - self._key_last_request[key]
            if key_elapsed < self.MIN_REQUEST_INTERVAL:
                time.sleep(self.MIN_REQUEST_INTERVAL - key_elapsed)
            self._key_last_request[key] = time.time()
        
        self._last_request_time = time.time()
    
    def _make_request(self, url: str, params: Dict[str, Any], key: str = None) -> Tuple[Optional[Dict], Optional[str]]:
        """
        发起HTTP请求（带重试机制）
        
        Args:
            url: 请求URL
            params: 请求参数
            key: 当前使用的API Key
            
        Returns:
            Tuple[Optional[Dict], Optional[str]]: (响应数据, 错误信息)
        """
        for attempt in range(MAX_RETRIES):
            try:
                self._wait_for_interval(key)
                
                response = requests.get(
                    url,
                    params=params,
                    timeout=REQUEST_TIMEOUT
                )
                response.raise_for_status()
                
                data = response.json()
                return data, None
                
            except requests.exceptions.Timeout:
                error_msg = f"请求超时 (尝试 {attempt + 1}/{MAX_RETRIES})"
                logger.warning(error_msg)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAYS[attempt])
                    
            except requests.exceptions.RequestException as e:
                error_msg = f"请求失败: {e}"
                logger.error(error_msg)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAYS[attempt])
                    
            except json.JSONDecodeError as e:
                error_msg = f"JSON解析失败: {e}"
                logger.error(error_msg)
                return None, error_msg
        
        return None, f"请求失败，已重试{MAX_RETRIES}次"
    
    def search_poi_by_polygon(
        self,
        polygon: str,
        keywords: str = "",
        types: str = "",
        page_size: int = 20,
        page_num: int = 1,
        show_fields: str = ""
    ) -> APIResult:
        """
        多边形区域内POI搜索 (V5版本API)
        
        高德API polygon参数格式：
        - 用 | 分隔不同的坐标点
        - 用 , 分隔经纬度（经度在前，纬度在后）
        - 矩形可只传左下和右上两个顶点，如: 116.36,39.86|116.44,39.98
        
        Args:
            polygon: 多边形区域坐标串，格式：lng1,lat1|lng2,lat2|...
            keywords: 搜索关键词（只支持一个关键字）
            types: POI类型代码，多个用|分隔
            page_size: 每页记录数（1-25）
            page_num: 当前页码
            show_fields: 返回字段控制，如 "business,indoor,navi,photos"
            
        Returns:
            APIResult: API请求结果
        """
        api_key = self._get_current_key()
        if not api_key:
            return APIResult(
                success=False,
                error_message="所有API Key均不可用"
            )
        
        params = {
            'key': api_key,
            'polygon': polygon,
            'page_size': min(page_size, 25),
            'page_num': page_num
        }
        
        if keywords:
            params['keywords'] = keywords
        if types:
            params['types'] = types
        if show_fields:
            params['show_fields'] = show_fields
        
        data, error = self._make_request(AMAP_POI_URL, params, api_key)
        
        if error:
            return APIResult(success=False, error_message=error)
        
        status = data.get('status', '')
        info = data.get('info', '')
        
        if status != '1':
            if info in ['DAILY_QUERY_OVER_LIMIT', 'ACCESS_TOO_FREQUENT', 'CUQPS_HAS_EXCEEDED_THE_LIMIT']:
                self._mark_key_quota_exceeded(api_key)
                new_key = self._rotate_key()
                if new_key:
                    logger.info(f"切换到新的API Key重试...")
                    return self.search_poi_by_polygon(polygon, keywords, types, page_size, page_num, show_fields)
                return APIResult(success=False, error_message="所有API Key配额已用尽")
            else:
                self._mark_key_invalid(api_key, info)
                return APIResult(success=False, error_message=f"API错误: {info}", status=status, info=info)
        
        pois = data.get('pois', [])
        count = int(data.get('count', 0))
        
        return APIResult(
            success=True,
            data=pois,
            count=count,
            status=status,
            info=info
        )
    
    def search_poi_by_keyword(
        self,
        keywords: str = "",
        types: str = "",
        location: str = "",
        radius: int = 5000,
        region: str = "",
        city_limit: bool = False,
        page_size: int = 20,
        page_num: int = 1,
        show_fields: str = ""
    ) -> APIResult:
        """
        关键字搜索POI (V5版本API - 周边搜索)
        
        Args:
            keywords: 搜索关键词（只支持一个关键字）
            types: POI类型代码，多个用|分隔
            location: 中心点坐标 lng,lat
            radius: 搜索半径（0-50000米）
            region: 搜索区划（城市名或adcode）
            city_limit: 是否限制在城市内
            page_size: 每页记录数（1-25）
            page_num: 当前页码
            show_fields: 返回字段控制
            
        Returns:
            APIResult: API请求结果
        """
        api_key = self._get_current_key()
        if not api_key:
            return APIResult(
                success=False,
                error_message="所有API Key均不可用"
            )
        
        params = {
            'key': api_key,
            'page_size': min(page_size, 25),
            'page_num': page_num
        }
        
        if keywords:
            params['keywords'] = keywords
        if types:
            params['types'] = types
        if location:
            params['location'] = location
        if radius:
            params['radius'] = min(radius, 50000)
        if region:
            params['region'] = region
        if city_limit:
            params['city_limit'] = 'true'
        if show_fields:
            params['show_fields'] = show_fields
        
        data, error = self._make_request(AMAP_KEYWORD_URL, params, api_key)
        
        if error:
            return APIResult(success=False, error_message=error)
        
        status = data.get('status', '')
        info = data.get('info', '')
        
        if status != '1':
            if info in ['DAILY_QUERY_OVER_LIMIT', 'ACCESS_TOO_FREQUENT', 'CUQPS_HAS_EXCEEDED_THE_LIMIT']:
                self._mark_key_quota_exceeded(api_key)
                new_key = self._rotate_key()
                if new_key:
                    logger.info(f"切换到新的API Key重试...")
                    return self.search_poi_by_keyword(keywords, types, location, radius, region, city_limit, page_size, page_num, show_fields)
                return APIResult(success=False, error_message="所有API Key配额已用尽")
            else:
                return APIResult(success=False, error_message=f"API错误: {info}", status=status, info=info)
        
        pois = data.get('pois', [])
        count = int(data.get('count', 0))
        
        return APIResult(
            success=True,
            data=pois,
            count=count,
            status=status,
            info=info
        )
    
    def get_district_bounds(
        self,
        adcode: str,
        cache_file: str = "./cache/district_bounds.json"
    ) -> Optional[str]:
        """
        获取行政区划边界坐标串
        
        Args:
            adcode: 行政区划代码
            cache_file: 缓存文件路径
            
        Returns:
            Optional[str]: 边界坐标串，格式：lng1,lat1;lng2,lat2;...
        """
        cache = {}
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                if adcode in cache:
                    logger.debug(f"从缓存加载行政区划边界: {adcode}")
                    return cache[adcode]
            except Exception as e:
                logger.warning(f"读取边界缓存失败: {e}")
        
        api_key = self._get_current_key()
        if not api_key:
            logger.error("无法获取API Key")
            return None
        
        params = {
            'key': api_key,
            'keywords': adcode,
            'subdistrict': 0,
            'extensions': 'all'
        }
        
        data, error = self._make_request(AMAP_DISTRICT_URL, params, api_key)
        
        if error:
            logger.error(f"获取行政区划边界失败: {error}")
            return None
        
        status = data.get('status', '')
        if status != '1':
            logger.error(f"API错误: {data.get('info', '')}")
            return None
        
        districts = data.get('districts', [])
        if not districts:
            logger.error(f"未找到行政区划: {adcode}")
            return None
        
        polyline = districts[0].get('polyline', '')
        if not polyline:
            logger.warning(f"行政区划 {adcode} 无边界数据")
            return None
        
        cache[adcode] = polyline
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            logger.debug(f"已缓存行政区划边界: {adcode}")
        except Exception as e:
            logger.warning(f"保存边界缓存失败: {e}")
        
        return polyline
    
    def get_district_bounds_coords(
        self,
        adcode: str
    ) -> Optional[List[Tuple[float, float]]]:
        """
        获取行政区划边界坐标点列表
        
        Args:
            adcode: 行政区划代码
            
        Returns:
            Optional[List[Tuple[float, float]]]: 坐标点列表 [(lng, lat), ...]
        """
        polyline = self.get_district_bounds(adcode)
        if not polyline:
            return None
        
        coords = []
        try:
            for point_str in polyline.split(';'):
                parts = point_str.split(',')
                if len(parts) == 2:
                    lng = float(parts[0])
                    lat = float(parts[1])
                    coords.append((lng, lat))
        except Exception as e:
            logger.error(f"解析边界坐标失败: {e}")
            return None
        
        return coords
    
    def get_district_bbox(
        self,
        adcode: str
    ) -> Optional[Tuple[float, float, float, float]]:
        """
        获取行政区划的边界框（最小外接矩形）
        
        Args:
            adcode: 行政区划代码
            
        Returns:
            Optional[Tuple[float, float, float, float]]: (min_lng, min_lat, max_lng, max_lat)
        """
        coords = self.get_district_bounds_coords(adcode)
        if not coords:
            return None
        
        lngs = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        
        return (min(lngs), min(lats), max(lngs), max(lats))
    
    def test_api_key(self, api_key: str) -> Tuple[bool, str]:
        """
        测试API Key是否有效
        
        Args:
            api_key: 要测试的API Key
            
        Returns:
            Tuple[bool, str]: (是否有效, 状态信息)
        """
        params = {
            'key': api_key,
            'location': '116.397428,39.90923',  # 北京天安门
            'page_size': 1
        }
        
        try:
            response = requests.get(
                AMAP_KEYWORD_URL,
                params=params,
                timeout=REQUEST_TIMEOUT
            )
            data = response.json()
            
            status = data.get('status', '')
            info = data.get('info', '')
            
            if status == '1':
                return True, "API Key有效"
            else:
                return False, f"API Key无效: {info}"
                
        except Exception as e:
            return False, f"测试失败: {e}"
    
    def get_key_status(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有API Key的状态
        
        Returns:
            Dict[str, Dict[str, Any]]: Key状态字典
        """
        return self._key_status.copy()


def parse_polyline_to_polygon(polyline: str) -> str:
    """
    将高德polyline格式转换为polygon格式
    
    高德polyline格式: lng1,lat1;lng2,lat2;lng3,lat3;...
    polygon格式: lng1,lat1;lng2,lat2;lng3,lat3;lng1,lat1 (首尾相连)
    
    Args:
        polyline: 高德polyline字符串
        
    Returns:
        str: polygon格式字符串
    """
    points = polyline.strip().split(';')
    if len(points) < 3:
        return polyline
    
    if points[0] != points[-1]:
        points.append(points[0])
    
    return ';'.join(points)
