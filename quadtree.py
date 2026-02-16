# -*- coding: utf-8 -*-
"""
高德POI数据采集工具 - 四叉树递归拆分模块

【合规声明】仅用于个人学习/内部项目，不批量爬取、存储、转售高德数据，不用于商业用途。

功能：
- 四叉树空间拆分算法
- 自动检测POI超量并递归拆分
- 多边形区域处理

四叉树算法说明：
当某个区域内的POI数量超过阈值（API单次返回上限约200条）时，
将该区域等分为4个子区域，分别查询。如果子区域仍然超量，
继续递归拆分，直到满足终止条件。

终止条件：
1. POI数量 < 阈值
2. 网格跨度 < 0.005度（约500米）
3. 递归深度 > 20
"""

import logging
from typing import List, Dict, Tuple, Optional, Callable, Any
from dataclasses import dataclass
import concurrent.futures

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_THRESHOLD = 180  # POI超量阈值
MIN_GRID_SPAN = 0.005    # 最小网格跨度（度），约500米
MAX_DEPTH = 20           # 最大递归深度


@dataclass
class BoundingBox:
    """
    边界框数据类
    
    Attributes:
        min_lng: 最小经度
        min_lat: 最小纬度
        max_lng: 最大经度
        max_lat: 最大纬度
    """
    min_lng: float
    min_lat: float
    max_lng: float
    max_lat: float
    
    @property
    def width(self) -> float:
        """获取边界框宽度（经度跨度）"""
        return self.max_lng - self.min_lng
    
    @property
    def height(self) -> float:
        """获取边界框高度（纬度跨度）"""
        return self.max_lat - self.min_lat
    
    @property
    def center(self) -> Tuple[float, float]:
        """获取中心点坐标"""
        return (
            (self.min_lng + self.max_lng) / 2,
            (self.min_lat + self.max_lat) / 2
        )
    
    def to_polygon(self) -> str:
        """
        转换为高德polygon格式字符串
        
        高德API polygon参数格式：
        - 用 | 分隔不同的坐标点
        - 用 , 分隔经纬度（经度在前，纬度在后）
        - 矩形可只传左下和右上两个顶点
        
        Returns:
            str: polygon格式字符串
        """
        # 矩形只需要左下和右上两个顶点
        return f"{self.min_lng},{self.min_lat}|{self.max_lng},{self.max_lat}"
    
    def split(self) -> List['BoundingBox']:
        """
        将边界框四等分
        
        Returns:
            List[BoundingBox]: 四个子边界框列表
        """
        mid_lng = (self.min_lng + self.max_lng) / 2
        mid_lat = (self.min_lat + self.max_lat) / 2
        
        return [
            BoundingBox(self.min_lng, self.min_lat, mid_lng, mid_lat),  # 左下
            BoundingBox(mid_lng, self.min_lat, self.max_lng, mid_lat),  # 右下
            BoundingBox(self.min_lng, mid_lat, mid_lng, self.max_lat),  # 左上
            BoundingBox(mid_lng, mid_lat, self.max_lng, self.max_lat),  # 右上
        ]


class QuadTreeSplitter:
    """
    四叉树拆分器类
    
    负责自动检测POI超量并进行递归拆分
    """
    
    def __init__(
        self,
        api_client,
        poi_threshold: int = DEFAULT_THRESHOLD,
        min_grid_span: float = MIN_GRID_SPAN,
        max_depth: int = MAX_DEPTH,
        max_workers: int = 3
    ):
        """
        初始化四叉树拆分器
        
        Args:
            api_client: API客户端实例
            poi_threshold: POI超量阈值
            min_grid_span: 最小网格跨度（度）
            max_depth: 最大递归深度
            max_workers: 并发工作线程数
        """
        self.api_client = api_client
        self.poi_threshold = poi_threshold
        self.min_grid_span = min_grid_span
        self.max_depth = max_depth
        self.max_workers = max_workers
        self._cancelled = False
    
    def cancel(self) -> None:
        """取消当前操作"""
        self._cancelled = True
    
    def reset(self) -> None:
        """重置取消状态"""
        self._cancelled = False
    
    def get_poi_count(
        self,
        polygon: str,
        keywords: str = "",
        types: str = ""
    ) -> int:
        """
        获取区域内POI数量（通过多页请求估算）
        
        注意：高德V5 API的count字段返回的是当前页数据条数，不是总数。
        此方法通过请求多页来估算总数，但可能不准确。
        
        Args:
            polygon: 多边形区域坐标串
            keywords: 搜索关键词
            types: POI类型代码
            
        Returns:
            int: POI数量估算值，失败返回-1
        """
        # 请求第一页
        result = self.api_client.search_poi_by_polygon(
            polygon=polygon,
            keywords=keywords,
            types=types,
            page_size=25,
            page_num=1
        )
        
        if not result.success:
            logger.error(f"获取POI数量失败: {result.error_message}")
            return -1
        
        first_page_count = len(result.data)
        
        # 如果第一页不满25条，说明总数就是这么多
        if first_page_count < 25:
            return first_page_count
        
        # 如果第一页满25条，继续请求后续页面估算总数
        # 最多请求4页来估算（避免消耗太多配额）
        total = first_page_count
        for page in range(2, 5):  # 请求第2-4页
            result = self.api_client.search_poi_by_polygon(
                polygon=polygon,
                keywords=keywords,
                types=types,
                page_size=25,
                page_num=page
            )
            
            if not result.success or not result.data:
                break
            
            page_count = len(result.data)
            total += page_count
            
            # 如果某页不满25条，说明已经到最后了
            if page_count < 25:
                break
        
        # 如果4页都满了，说明数据量很大，返回一个大于阈值的数
        # 触发四叉树拆分
        if total >= 100:  # 4页 x 25条 = 100条
            return 999  # 返回一个大数触发拆分
        
        return total
    
    def fetch_pois_in_bounds(
        self,
        bounds: BoundingBox,
        keywords: str = "",
        types: str = "",
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        获取边界框内的所有POI数据（分页获取）
        
        优化策略：
        1. 先请求第8页判断数据量是否超过200条
        2. 如果第8页有数据，返回 (空列表, True) 表示需要拆分
        3. 否则从第1页开始获取所有数据，返回 (数据列表, False)
        
        Args:
            bounds: 边界框
            keywords: 搜索关键词
            types: POI类型代码
            on_progress: 进度回调函数 (current_page, total_pages)
            
        Returns:
            Tuple[List[Dict], bool]: (POI数据列表, 是否需要拆分)
        """
        all_pois = []
        polygon = bounds.to_polygon()
        
        # 【优化】先请求第8页判断数据量
        # 8页 x 25条 = 200条，是API返回上限
        result = self.api_client.search_poi_by_polygon(
            polygon=polygon,
            keywords=keywords,
            types=types,
            page_size=25,
            page_num=8
        )
        
        if result.success and result.data and len(result.data) > 0:
            # 第8页有数据，说明数据量超过200条，需要拆分
            logger.info(f"第8页有数据({len(result.data)}条)，数据量超过200，需要四叉树拆分")
            return [], True  # 返回空列表和需要拆分标志
        
        # 第8页无数据，说明数据量不超过200条，从第1页开始获取
        page = 1
        max_pages = 8  # 最多请求8页（200条）
        
        while page <= max_pages:
            if self._cancelled:
                logger.info("操作已取消")
                break
            
            result = self.api_client.search_poi_by_polygon(
                polygon=polygon,
                keywords=keywords,
                types=types,
                page_size=25,
                page_num=page
            )
            
            if not result.success:
                logger.error(f"获取第{page}页POI失败: {result.error_message}")
                break
            
            if not result.data:
                # 没有更多数据了
                break
            
            all_pois.extend(result.data)
            
            if on_progress:
                on_progress(page, max_pages)
            
            # 如果返回数据不满25条，说明是最后一页
            if len(result.data) < 25:
                break
            
            page += 1
        
        logger.info(f"共获取 {len(all_pois)} 条POI数据（{page}页）")
        return all_pois, False  # 返回数据和不需拆分标志
    
    def quadtree_split(
        self,
        bounds: BoundingBox,
        keywords: str = "",
        types: str = "",
        current_depth: int = 0,
        on_log: Optional[Callable[[str], None]] = None,
        on_poi_found: Optional[Callable[[List[Dict]], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        四叉树递归拆分获取POI
        
        算法流程：
        1. 先请求第8页判断数据量
        2. 如果第8页有数据（超过200条），触发四叉树拆分
        3. 否则获取所有数据返回
        
        Args:
            bounds: 边界框
            keywords: 搜索关键词
            types: POI类型代码
            current_depth: 当前递归深度
            on_log: 日志回调函数
            on_poi_found: POI发现回调函数
            
        Returns:
            List[Dict[str, Any]]: POI数据列表
        """
        if self._cancelled:
            return []
        
        indent = "  " * current_depth
        log_msg = f"{indent}处理区域: [{bounds.min_lng:.4f}, {bounds.min_lat:.4f}] - " \
                  f"[{bounds.max_lng:.4f}, {bounds.max_lat:.4f}] (深度: {current_depth})"
        
        if on_log:
            on_log(log_msg)
        logger.debug(log_msg)
        
        # 获取数据（返回数据列表和是否需要拆分标志）
        pois, need_split = self.fetch_pois_in_bounds(bounds, keywords, types)
        
        # 如果需要拆分
        if need_split:
            log_msg = f"{indent}数据量超过200条，需要四叉树拆分"
            if on_log:
                on_log(log_msg)
            logger.info(log_msg)
            
            # 检查终止条件
            if bounds.width < self.min_grid_span or bounds.height < self.min_grid_span:
                log_msg = f"{indent}网格已达最小跨度 ({bounds.width:.6f}°)，停止拆分"
                if on_log:
                    on_log(log_msg)
                logger.info(log_msg)
                return []
            
            if current_depth >= self.max_depth:
                log_msg = f"{indent}已达最大递归深度 ({self.max_depth})，停止拆分"
                if on_log:
                    on_log(log_msg)
                logger.info(log_msg)
                return []
            
            # 执行四叉树拆分
            log_msg = f"{indent}执行四叉树拆分..."
            if on_log:
                on_log(log_msg)
            logger.info(log_msg)
            
            sub_bounds = bounds.split()
            all_pois = []
            
            for i, sub_bound in enumerate(sub_bounds):
                if self._cancelled:
                    break
                
                log_msg = f"{indent}处理子区域 {i+1}/4..."
                if on_log:
                    on_log(log_msg)
                
                sub_pois = self.quadtree_split(
                    bounds=sub_bound,
                    keywords=keywords,
                    types=types,
                    current_depth=current_depth + 1,
                    on_log=on_log,
                    on_poi_found=on_poi_found
                )
                all_pois.extend(sub_pois)
            
            return all_pois
        
        # 数据量不超过200条，直接返回
        log_msg = f"{indent}获取到 {len(pois)} 个POI"
        if on_log:
            on_log(log_msg)
        logger.info(log_msg)
        
        if on_poi_found and pois:
            on_poi_found(pois)
        
        return pois
    
    def quadtree_split_parallel(
        self,
        bounds: BoundingBox,
        keywords: str = "",
        types: str = "",
        on_log: Optional[Callable[[str], None]] = None,
        on_poi_found: Optional[Callable[[List[Dict]], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        并行四叉树拆分获取POI
        
        使用线程池并行处理第一层拆分的4个子区域
        
        Args:
            bounds: 边界框
            keywords: 搜索关键词
            types: POI类型代码
            on_log: 日志回调函数
            on_poi_found: POI发现回调函数
            
        Returns:
            List[Dict[str, Any]]: POI数据列表
        """
        if self._cancelled:
            return []
        
        # 先获取数据（返回数据列表和是否需要拆分标志）
        pois, need_split = self.fetch_pois_in_bounds(bounds, keywords, types)
        
        # 如果需要拆分
        if need_split:
            log_msg = "数据量超过200条，开始并行四叉树拆分..."
            if on_log:
                on_log(log_msg)
            logger.info(log_msg)
            
            sub_bounds = bounds.split()
            all_pois = []
            
            def process_sub_region(sub_bound: BoundingBox, index: int) -> List[Dict]:
                if self._cancelled:
                    return []
                
                log_msg = f"并行处理子区域 {index+1}/4..."
                if on_log:
                    on_log(log_msg)
                
                return self.quadtree_split(
                    bounds=sub_bound,
                keywords=keywords,
                types=types,
                current_depth=1,
                on_log=on_log,
                on_poi_found=on_poi_found
            )
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(self.max_workers, 4)) as executor:
                futures = {
                    executor.submit(process_sub_region, sb, i): i
                    for i, sb in enumerate(sub_bounds)
                }
                
                for future in concurrent.futures.as_completed(futures):
                    if self._cancelled:
                        executor.shutdown(wait=False)
                        break
                    
                    try:
                        sub_pois = future.result()
                        all_pois.extend(sub_pois)
                    except Exception as e:
                        logger.error(f"子区域处理失败: {e}")
            
            return all_pois
        
        # 数据量不超过200条，直接返回
        if on_poi_found and pois:
            on_poi_found(pois)
        return pois


def bbox_from_polyline(polyline: str) -> Optional[BoundingBox]:
    """
    从polyline字符串创建边界框
    
    高德polyline格式说明：
    - 多个多边形用 | 分隔（如行政区有飞地）
    - 每个多边形的点用 ; 分隔
    - 每个点的坐标用 , 分隔，格式为 lng,lat（经度在前）
    
    Args:
        polyline: 高德polyline格式字符串
        
    Returns:
        Optional[BoundingBox]: 边界框，解析失败返回None
    """
    try:
        if not polyline or not polyline.strip():
            return None
        
        # 清理字符串：移除换行、多余空格
        polyline = polyline.strip().replace('\n', '').replace('\r', '')
        
        coords = []
        
        # 先按 | 分割多个多边形
        polygons = polyline.split('|')
        
        for polygon in polygons:
            polygon = polygon.strip()
            if not polygon:
                continue
            
            # 每个多边形按 ; 分割点
            for point_str in polygon.split(';'):
                point_str = point_str.strip()
                if not point_str:
                    continue
                
                # 每个点按 , 分割经纬度 (lng,lat格式)
                if ',' in point_str:
                    parts = point_str.split(',')
                    if len(parts) >= 2:
                        try:
                            lng = float(parts[0].strip())
                            lat = float(parts[1].strip())
                            coords.append((lng, lat))
                        except ValueError:
                            continue
        
        if not coords:
            return None
        
        lngs = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        
        return BoundingBox(
            min_lng=min(lngs),
            min_lat=min(lats),
            max_lng=max(lngs),
            max_lat=max(lats)
        )
    except Exception as e:
        logger.error(f"解析polyline失败: {e}, polyline前100字符: {str(polyline)[:100]}")
        return None


def bbox_from_adcode(
    api_client,
    adcode: str
) -> Optional[BoundingBox]:
    """
    根据行政区划代码获取边界框
    
    Args:
        api_client: API客户端实例
        adcode: 行政区划代码
        
    Returns:
        Optional[BoundingBox]: 边界框
    """
    polyline = api_client.get_district_bounds(adcode)
    if not polyline:
        return None
    
    return bbox_from_polyline(polyline)
