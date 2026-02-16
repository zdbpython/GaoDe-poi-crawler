# -*- coding: utf-8 -*-
"""
高德POI数据采集工具 - GUI界面模块

【合规声明】仅用于个人学习/内部项目，不批量爬取、存储、转售高德数据，不用于商业用途。

功能：
- tkinter/ttk图形界面
- 省-市-区县三级联动选择
- POI类型多选
- 参数配置（含坐标转换多选）
- 采集日志实时显示
- 结果预览表格
- 操作控制与进度条
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Dict, List, Optional, Callable, Any
import threading
import logging
import queue
import json
import os

from config import (
    ConfigManager, load_poi_types, load_cities,
    get_provinces, get_cities_by_province, get_districts_by_city,
    ensure_directories
)
from api import AmapAPI, APIResult
from quadtree import QuadTreeSplitter, BoundingBox, bbox_from_adcode
from data import DataProcessor, POIRecord, get_all_available_fields

# GUI版本
VERSION = "v2.1（坐标多选版）"

# 日志队列处理器
class QueueHandler(logging.Handler):
    """将日志消息发送到队列的处理器"""
    
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue
    
    def emit(self, record):
        self.log_queue.put(self.format(record))


class POICrawlerGUI:
    """
    POI数据采集工具GUI主类
    
    实现完整的图形界面，包括区域选择、类型选择、参数配置、
    日志显示、结果预览和采集控制功能。
    """
    
    def __init__(self, root: tk.Tk):
        """
        初始化GUI
        
        Args:
            root: Tkinter根窗口
        """
        self.root = root
        self.root.title(f"高德POI数据采集工具 {VERSION}")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        
        # 配置管理器
        self.config_manager = ConfigManager()
        
        # 数据
        self.poi_types = load_poi_types()
        self.cities = load_cities()
        
        # 状态
        self.is_collecting = False
        self.is_paused = False
        self._collect_thread = None
        self._stop_event = threading.Event()
        
        # 日志队列
        self.log_queue = queue.Queue()
        
        # 数据处理器
        self.data_processor: Optional[DataProcessor] = None
        
        # 选中的字段
        self.selected_fields: List[str] = []
        
        # 设置日志
        self._setup_logging()
        
        # 构建界面
        self._build_ui()
        
        # 加载配置
        self._load_config()
        
        # 启动日志更新
        self._update_log_display()
    
    def _setup_logging(self):
        """设置日志系统"""
        ensure_directories()
        
        log_file = os.path.join("./logs", "poi_crawler.log")
        
        # 文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        
        # 队列处理器
        queue_handler = QueueHandler(self.log_queue)
        queue_handler.setLevel(logging.INFO)
        queue_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        
        # 根日志器
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(queue_handler)
    
    def _build_ui(self):
        """构建用户界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 顶部：区域选择区
        self._build_district_selector(main_frame)
        
        # 中间区域（左右分栏）
        middle_frame = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        middle_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 左侧：POI类型选择
        left_frame = ttk.Frame(middle_frame)
        middle_frame.add(left_frame, weight=1)
        self._build_poi_selector(left_frame)
        
        # 右侧：标签页区
        right_frame = ttk.Frame(middle_frame)
        middle_frame.add(right_frame, weight=3)
        self._build_notebook(right_frame)
        
        # 底部：操作控制区
        self._build_control_panel(main_frame)
    
    def _build_district_selector(self, parent: ttk.Frame):
        """
        构建区域选择器
        
        Args:
            parent: 父容器
        """
        frame = ttk.LabelFrame(parent, text="区域选择", padding="5")
        frame.pack(fill=tk.X, pady=5)
        
        # 左侧：下拉选择
        select_frame = ttk.Frame(frame)
        select_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 省份选择
        ttk.Label(select_frame, text="省份:").grid(row=0, column=0, padx=5, pady=2)
        self.province_var = tk.StringVar()
        self.province_combo = ttk.Combobox(
            select_frame, textvariable=self.province_var,
            state="readonly", width=15
        )
        self.province_combo.grid(row=0, column=1, padx=5, pady=2)
        self.province_combo.bind("<<ComboboxSelected>>", self._on_province_selected)
        
        # 城市选择
        ttk.Label(select_frame, text="城市:").grid(row=0, column=2, padx=5, pady=2)
        self.city_var = tk.StringVar()
        self.city_combo = ttk.Combobox(
            select_frame, textvariable=self.city_var,
            state="readonly", width=15
        )
        self.city_combo.grid(row=0, column=3, padx=5, pady=2)
        self.city_combo.bind("<<ComboboxSelected>>", self._on_city_selected)
        
        # 区县选择（多选列表）
        ttk.Label(select_frame, text="区县:").grid(row=0, column=4, padx=5, pady=2)
        
        district_frame = ttk.Frame(select_frame)
        district_frame.grid(row=0, column=5, padx=5, pady=2)
        
        self.district_listbox = tk.Listbox(
            district_frame, selectmode=tk.EXTENDED,
            height=4, width=15, exportselection=False
        )
        district_scrollbar = ttk.Scrollbar(
            district_frame, orient=tk.VERTICAL,
            command=self.district_listbox.yview
        )
        self.district_listbox.configure(yscrollcommand=district_scrollbar.set)
        self.district_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        district_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 按钮区
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side=tk.LEFT, padx=10)
        
        ttk.Button(
            btn_frame, text="添加选中区县",
            command=self._add_selected_districts
        ).pack(fill=tk.X, pady=2)
        
        ttk.Button(
            btn_frame, text="清空目标区县",
            command=self._clear_target_districts
        ).pack(fill=tk.X, pady=2)
        
        # 右侧：目标区县列表
        target_frame = ttk.LabelFrame(frame, text="目标区县列表", padding="5")
        target_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=5)
        
        self.target_districts_text = scrolledtext.ScrolledText(
            target_frame, height=4, width=40, state=tk.DISABLED
        )
        self.target_districts_text.pack(fill=tk.BOTH, expand=True)
        
        # 初始化省份列表
        provinces = get_provinces(self.cities)
        self.province_combo['values'] = provinces
    
    def _build_poi_selector(self, parent: ttk.Frame):
        """
        构建POI类型选择器（优化版）
        
        功能：
        - 左侧：可选POI类型列表
        - 中间：添加/移除按钮
        - 右侧：已选POI类型标签展示区
        
        Args:
            parent: 父容器
        """
        frame = ttk.LabelFrame(parent, text="兴趣点类型选择", padding="5")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # 主容器：三列布局
        main_frame = ttk.Frame(frame)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左侧：可选POI类型列表
        left_frame = ttk.LabelFrame(main_frame, text="可选类型（双击添加）", padding="5")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 搜索框
        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT)
        self.poi_search_var = tk.StringVar()
        self.poi_search_var.trace('w', self._filter_poi_list)
        poi_search_entry = ttk.Entry(search_frame, textvariable=self.poi_search_var, width=20)
        poi_search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # POI列表
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.poi_listbox = tk.Listbox(
            list_frame, selectmode=tk.EXTENDED,
            height=15, exportselection=False,
            bg='white', selectbackground='#4a90d9'
        )
        
        scrollbar_y = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.poi_listbox.yview)
        scrollbar_x = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.poi_listbox.xview)
        
        self.poi_listbox.configure(
            yscrollcommand=scrollbar_y.set,
            xscrollcommand=scrollbar_x.set
        )
        
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.poi_listbox.pack(fill=tk.BOTH, expand=True)
        
        # 加载POI类型
        self._poi_data = []  # 存储原始数据
        for poi in self.poi_types:
            display_text = f"{poi['name']} ({poi['code']})"
            self.poi_listbox.insert(tk.END, display_text)
            self._poi_data.append(poi)
        
        # 双击添加
        self.poi_listbox.bind('<Double-Button-1>', lambda e: self._add_selected_poi_types())
        
        # 中间：操作按钮
        mid_frame = ttk.Frame(main_frame, width=80)
        mid_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        mid_frame.pack_propagate(False)
        
        ttk.Button(mid_frame, text="添加 →", command=self._add_selected_poi_types).pack(fill=tk.X, pady=2)
        ttk.Button(mid_frame, text="← 移除", command=self._remove_selected_poi_tags).pack(fill=tk.X, pady=2)
        ttk.Separator(mid_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        ttk.Button(mid_frame, text="全部添加", command=self._add_all_poi_types).pack(fill=tk.X, pady=2)
        ttk.Button(mid_frame, text="全部清空", command=self._clear_all_poi_tags).pack(fill=tk.X, pady=2)
        
        # 右侧：已选POI类型展示区
        right_frame = ttk.LabelFrame(main_frame, text="目标兴趣点", padding="5")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # 统计信息
        self.poi_count_label = ttk.Label(right_frame, text="已选: 0 个类型")
        self.poi_count_label.pack(anchor=tk.W)
        
        # 标签容器（带滚动）
        tags_container = ttk.Frame(right_frame)
        tags_container.pack(fill=tk.BOTH, expand=True)
        
        # 创建Canvas实现滚动
        self.poi_tags_canvas = tk.Canvas(tags_container, bg='#f5f5f5', highlightthickness=0)
        tags_scrollbar = ttk.Scrollbar(tags_container, orient=tk.VERTICAL, command=self.poi_tags_canvas.yview)
        
        self.poi_tags_frame = ttk.Frame(self.poi_tags_canvas)
        
        self.poi_tags_canvas.configure(yscrollcommand=tags_scrollbar.set)
        
        tags_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.poi_tags_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.poi_tags_window = self.poi_tags_canvas.create_window((0, 0), window=self.poi_tags_frame, anchor=tk.NW)
        
        # 绑定滚动区域更新
        self.poi_tags_frame.bind('<Configure>', self._on_tags_frame_configure)
        self.poi_tags_canvas.bind('<Configure>', self._on_tags_canvas_configure)
        
        # 鼠标滚轮滚动
        self.poi_tags_canvas.bind('<MouseWheel>', self._on_mousewheel)
        self.poi_tags_frame.bind('<MouseWheel>', self._on_mousewheel)
        
        # 已选POI存储
        self._selected_poi_tags: Dict[str, Dict] = {}  # code -> {name, frame}
    
    def _on_tags_frame_configure(self, event):
        """更新滚动区域"""
        self.poi_tags_canvas.configure(scrollregion=self.poi_tags_canvas.bbox('all'))
    
    def _on_tags_canvas_configure(self, event):
        """调整内部frame宽度"""
        self.poi_tags_canvas.itemconfig(self.poi_tags_window, width=event.width)
    
    def _on_mousewheel(self, event):
        """鼠标滚轮滚动"""
        self.poi_tags_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
    
    def _filter_poi_list(self, *args):
        """过滤POI列表"""
        search_text = self.poi_search_var.get().lower()
        self.poi_listbox.delete(0, tk.END)
        
        for i, poi in enumerate(self._poi_data):
            if search_text in poi['name'].lower() or search_text in poi['code']:
                # 检查是否已选
                if poi['code'] in self._selected_poi_tags:
                    display_text = f"✓ {poi['name']} ({poi['code']})"
                else:
                    display_text = f"  {poi['name']} ({poi['code']})"
                self.poi_listbox.insert(tk.END, display_text)
    
    def _refresh_poi_list_display(self):
        """刷新POI列表显示（更新选中状态标记）"""
        search_text = self.poi_search_var.get().lower()
        current_selection = list(self.poi_listbox.curselection())
        
        self.poi_listbox.delete(0, tk.END)
        
        for poi in self._poi_data:
            if search_text in poi['name'].lower() or search_text in poi['code']:
                if poi['code'] in self._selected_poi_tags:
                    display_text = f"✓ {poi['name']} ({poi['code']})"
                else:
                    display_text = f"  {poi['name']} ({poi['code']})"
                self.poi_listbox.insert(tk.END, display_text)
    
    def _add_selected_poi_types(self):
        """添加选中的POI类型到目标列表"""
        for idx in self.poi_listbox.curselection():
            text = self.poi_listbox.get(idx)
            # 解析名称和代码
            if text.startswith('✓ '):
                text = text[2:]
            name = text.rsplit(' (', 1)[0]
            code = text.rsplit('(', 1)[1].rstrip(')')
            
            if code not in self._selected_poi_tags:
                self._create_poi_tag(name, code)
        
        self._refresh_poi_list_display()
        self._update_poi_count()
    
    def _add_all_poi_types(self):
        """添加所有POI类型"""
        for poi in self._poi_data:
            if poi['code'] not in self._selected_poi_tags:
                self._create_poi_tag(poi['name'], poi['code'])
        
        self._refresh_poi_list_display()
        self._update_poi_count()
    
    def _create_poi_tag(self, name: str, code: str):
        """创建POI标签"""
        # 标签框架
        tag_frame = ttk.Frame(self.poi_tags_frame, relief=tk.SOLID, borderwidth=1)
        tag_frame.pack(fill=tk.X, pady=2, padx=2)
        
        # 颜色标识（根据大类）
        category_colors = {
            '01': '#e3f2fd',  # 汽车服务 - 蓝色
            '02': '#e8f5e9',  # 餐饮服务 - 绿色
            '03': '#fff3e0',  # 购物服务 - 橙色
            '04': '#fce4ec',  # 生活服务 - 粉色
            '05': '#f3e5f5',  # 体育休闲服务 - 紫色
            '06': '#e0f7fa',  # 医疗保健服务 - 青色
            '07': '#fff8e1',  # 住宿服务 - 黄色
            '08': '#efebe9',  # 风景名胜 - 棕色
            '09': '#e8eaf6',  # 商务住宅 - 靛蓝
            '10': '#eceff1',  # 政府机构 - 灰色
            '11': '#ffebee',  # 科教文化服务 - 红色
            '12': '#e1f5fe',  # 交通设施服务 - 浅蓝
            '13': '#f1f8e9',  # 金融保险服务 - 浅绿
            '14': '#fafafa',  # 公司企业 - 白色
            '15': '#fffde7',  # 道路附属设施 - 浅黄
        }
        
        # 颜色条颜色（深色）
        bar_colors = {
            '01': '#1976d2',  # 汽车服务 - 蓝色
            '02': '#388e3c',  # 餐饮服务 - 绿色
            '03': '#f57c00',  # 购物服务 - 橙色
            '04': '#c2185b',  # 生活服务 - 粉色
            '05': '#7b1fa2',  # 体育休闲服务 - 紫色
            '06': '#0097a7',  # 医疗保健服务 - 青色
            '07': '#ffa000',  # 住宿服务 - 黄色
            '08': '#5d4037',  # 风景名胜 - 棕色
            '09': '#3f51b5',  # 商务住宅 - 靛蓝
            '10': '#607d8b',  # 政府机构 - 灰色
            '11': '#d32f2f',  # 科教文化服务 - 红色
            '12': '#0288d1',  # 交通设施服务 - 浅蓝
            '13': '#689f38',  # 金融保险服务 - 浅绿
            '14': '#9e9e9e',  # 公司企业 - 白色
            '15': '#fbc02d',  # 道路附属设施 - 浅黄
        }
        
        category = code[:2]
        bg_color = category_colors.get(category, '#f5f5f5')
        bar_color = bar_colors.get(category, '#9e9e9e')
        
        # 内容框架
        content_frame = tk.Frame(tag_frame, bg=bg_color)
        content_frame.pack(fill=tk.X, expand=True)
        
        # 颜色条
        color_bar = tk.Frame(content_frame, bg=bar_color, width=4)
        color_bar.pack(side=tk.LEFT, fill=tk.Y)
        
        # 名称标签
        name_label = tk.Label(
            content_frame, 
            text=name, 
            bg=bg_color,
            font=('Microsoft YaHei UI', 9),
            anchor=tk.W
        )
        name_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=3)
        
        # 代码标签
        code_label = tk.Label(
            content_frame,
            text=code,
            bg=bg_color,
            fg='#666666',
            font=('Consolas', 8),
            anchor=tk.E
        )
        code_label.pack(side=tk.LEFT, padx=5)
        
        # 删除按钮
        delete_btn = tk.Button(
            content_frame,
            text='×',
            bg='#ff5252',
            fg='white',
            font=('Arial', 10, 'bold'),
            width=2,
            relief=tk.FLAT,
            cursor='hand2',
            command=lambda c=code: self._remove_poi_tag(c)
        )
        delete_btn.pack(side=tk.RIGHT, padx=2, pady=2)
        
        # 存储引用
        self._selected_poi_tags[code] = {
            'name': name,
            'frame': tag_frame
        }
    
    def _remove_poi_tag(self, code: str):
        """移除单个POI标签"""
        if code in self._selected_poi_tags:
            self._selected_poi_tags[code]['frame'].destroy()
            del self._selected_poi_tags[code]
            self._refresh_poi_list_display()
            self._update_poi_count()
    
    def _remove_selected_poi_tags(self):
        """移除选中的POI标签（从左侧列表选中的）"""
        for idx in self.poi_listbox.curselection():
            text = self.poi_listbox.get(idx)
            if text.startswith('✓ '):
                text = text[2:]
            code = text.rsplit('(', 1)[1].rstrip(')')
            self._remove_poi_tag(code)
    
    def _clear_all_poi_tags(self):
        """清空所有POI标签"""
        for code in list(self._selected_poi_tags.keys()):
            self._selected_poi_tags[code]['frame'].destroy()
        self._selected_poi_tags.clear()
        self._refresh_poi_list_display()
        self._update_poi_count()
    
    def _update_poi_count(self):
        """更新POI计数"""
        count = len(self._selected_poi_tags)
        self.poi_count_label.config(text=f"已选: {count} 个类型")
    
    def _build_notebook(self, parent: ttk.Frame):
        """
        构建标签页区
        
        Args:
            parent: 父容器
        """
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # 标签页1：参数配置
        config_frame = ttk.Frame(notebook, padding="10")
        notebook.add(config_frame, text="参数配置")
        self._build_config_tab(config_frame)
        
        # 标签页2：采集日志
        log_frame = ttk.Frame(notebook, padding="10")
        notebook.add(log_frame, text="采集日志")
        self._build_log_tab(log_frame)
        
        # 标签页3：结果预览
        result_frame = ttk.Frame(notebook, padding="10")
        notebook.add(result_frame, text="结果预览")
        self._build_result_tab(result_frame)
    
    def _build_config_tab(self, parent: ttk.Frame):
        """
        构建参数配置标签页
        
        Args:
            parent: 父容器
        """
        # API Key
        key_frame = ttk.Frame(parent)
        key_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(key_frame, text="高德API Key（多个用逗号分隔）:").pack(anchor=tk.W)
        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(key_frame, textvariable=self.api_key_var, width=60)
        self.api_key_entry.pack(fill=tk.X, pady=2)
        
        # 参数设置
        params_frame = ttk.Frame(parent)
        params_frame.pack(fill=tk.X, pady=10)
        
        # POI超量阈值
        ttk.Label(params_frame, text="POI超量阈值（≥该值则拆分）:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.threshold_var = tk.StringVar(value="180")
        self.threshold_entry = ttk.Entry(params_frame, textvariable=self.threshold_var, width=10)
        self.threshold_entry.grid(row=0, column=1, sticky=tk.W, pady=2, padx=5)
        
        # 请求间隔
        ttk.Label(params_frame, text="请求间隔（秒）:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.interval_var = tk.StringVar(value="0.35")
        self.interval_entry = ttk.Entry(params_frame, textvariable=self.interval_var, width=10)
        self.interval_entry.grid(row=1, column=1, sticky=tk.W, pady=2, padx=5)
        self.interval_entry.bind("<FocusOut>", self._validate_interval)
        
        # 并发请求数
        ttk.Label(params_frame, text="并发请求数:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.workers_var = tk.StringVar(value="3")
        self.workers_entry = ttk.Entry(params_frame, textvariable=self.workers_var, width=10)
        self.workers_entry.grid(row=2, column=1, sticky=tk.W, pady=2, padx=5)
        self.workers_entry.bind("<FocusOut>", self._validate_workers)
        
        # 坐标转换（多选）
        coord_frame = ttk.LabelFrame(parent, text="坐标转换（可多选，原始GCJ02坐标始终保留）", padding="5")
        coord_frame.pack(fill=tk.X, pady=10)
        
        self.wgs84_var = tk.BooleanVar(value=False)
        self.bd09_var = tk.BooleanVar(value=False)
        
        ttk.Checkbutton(
            coord_frame, text="转WGS84（GPS标准坐标）",
            variable=self.wgs84_var
        ).pack(anchor=tk.W, pady=2)
        
        ttk.Checkbutton(
            coord_frame, text="转BD09（百度坐标）",
            variable=self.bd09_var
        ).pack(anchor=tk.W, pady=2)
        
        # 配置按钮
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(btn_frame, text="保存配置", command=self._save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="加载上次配置", command=self._load_config).pack(side=tk.LEFT, padx=5)
    
    def _build_log_tab(self, parent: ttk.Frame):
        """
        构建采集日志标签页
        
        Args:
            parent: 父容器
        """
        self.log_text = scrolledtext.ScrolledText(
            parent, state=tk.DISABLED, wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
    
    def _build_result_tab(self, parent: ttk.Frame):
        """
        构建结果预览标签页
        
        Args:
            parent: 父容器
        """
        # 表格框架
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # 垂直滚动条
        scrollbar_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 水平滚动条
        scrollbar_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 结果表格
        self.result_tree = ttk.Treeview(
            tree_frame,
            yscrollcommand=scrollbar_y.set,
            xscrollcommand=scrollbar_x.set
        )
        
        scrollbar_y.config(command=self.result_tree.yview)
        scrollbar_x.config(command=self.result_tree.xview)
        
        self.result_tree.pack(fill=tk.BOTH, expand=True)
        
        # 统计信息
        self.stats_label = ttk.Label(parent, text="共采集: 0 条数据")
        self.stats_label.pack(anchor=tk.W, pady=5)
    
    def _build_control_panel(self, parent: ttk.Frame):
        """
        构建操作控制面板
        
        Args:
            parent: 父容器
        """
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=5)
        
        # 按钮区
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side=tk.LEFT)
        
        self.start_btn = ttk.Button(
            btn_frame, text="开始采集",
            command=self._start_collection
        )
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.pause_btn = ttk.Button(
            btn_frame, text="暂停采集",
            command=self._pause_collection,
            state=tk.DISABLED
        )
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        
        self.resume_btn = ttk.Button(
            btn_frame, text="继续采集",
            command=self._resume_collection,
            state=tk.DISABLED
        )
        self.resume_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(
            btn_frame, text="停止采集",
            command=self._stop_collection,
            state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # 进度区
        progress_frame = ttk.Frame(frame)
        progress_frame.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=10)
        
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame, variable=self.progress_var,
            maximum=100, length=300
        )
        self.progress_bar.pack(side=tk.LEFT, padx=5)
        
        self.progress_label = ttk.Label(
            progress_frame, text="整体进度: 0%"
        )
        self.progress_label.pack(side=tk.LEFT, padx=5)
        
        self.task_label = ttk.Label(
            progress_frame, text="当前任务: 无"
        )
        self.task_label.pack(side=tk.LEFT, padx=5)
    
    # ========== 事件处理 ==========
    
    def _on_province_selected(self, event):
        """省份选择事件处理"""
        province = self.province_var.get()
        cities = get_cities_by_province(self.cities, province)
        self.city_combo['values'] = cities
        self.city_var.set('')
        self.district_listbox.delete(0, tk.END)
    
    def _on_city_selected(self, event):
        """城市选择事件处理"""
        province = self.province_var.get()
        city = self.city_var.get()
        districts = get_districts_by_city(self.cities, province, city)
        
        self.district_listbox.delete(0, tk.END)
        for d in districts:
            self.district_listbox.insert(tk.END, f"{d['district']} ({d['adcode']})")
    
    def _add_selected_districts(self):
        """添加选中的区县到目标列表"""
        province = self.province_var.get()
        city = self.city_var.get()
        
        if not province or not city:
            messagebox.showwarning("提示", "请先选择省份和城市")
            return
        
        selections = self.district_listbox.curselection()
        if not selections:
            messagebox.showwarning("提示", "请选择要添加的区县")
            return
        
        for idx in selections:
            text = self.district_listbox.get(idx)
            district_name = text.split(' (')[0]
            adcode = text.split('(')[1].rstrip(')')
            
            district_info = {
                'province': province,
                'city': city,
                'district': district_name,
                'adcode': adcode
            }
            
            if district_info not in self.config_manager.config.selected_districts:
                self.config_manager.config.selected_districts.append(district_info)
        
        self._update_target_districts_display()
    
    def _clear_target_districts(self):
        """清空目标区县列表"""
        self.config_manager.config.selected_districts.clear()
        self._update_target_districts_display()
    
    def _update_target_districts_display(self):
        """更新目标区县列表显示"""
        self.target_districts_text.config(state=tk.NORMAL)
        self.target_districts_text.delete(1.0, tk.END)
        
        for d in self.config_manager.config.selected_districts:
            line = f"{d['province']} > {d['city']} > {d['district']} ({d['adcode']})\n"
            self.target_districts_text.insert(tk.END, line)
        
        self.target_districts_text.config(state=tk.DISABLED)
    
    def _validate_interval(self, event=None):
        """验证请求间隔"""
        try:
            value = float(self.interval_var.get())
            if value < 0.34:
                self.interval_var.set("0.35")
                messagebox.showwarning("提示", "请求间隔不能小于0.34秒（高德API限制每秒最多3次请求）")
        except ValueError:
            self.interval_var.set("0.35")
    
    def _validate_workers(self, event=None):
        """验证并发请求数"""
        try:
            value = int(self.workers_var.get())
            if value < 1:
                self.workers_var.set("1")
            elif value > 10:
                self.workers_var.set("10")
                messagebox.showwarning("提示", "并发请求数不能超过10")
        except ValueError:
            self.workers_var.set("3")
    
    def _save_config(self):
        """保存配置"""
        # 更新配置
        api_keys_str = self.api_key_var.get().strip()
        self.config_manager.config.api_keys = [
            k.strip() for k in api_keys_str.split(',') if k.strip()
        ]
        
        try:
            self.config_manager.config.poi_threshold = int(self.threshold_var.get())
            self.config_manager.config.request_interval = float(self.interval_var.get())
            self.config_manager.config.max_workers = int(self.workers_var.get())
        except ValueError:
            messagebox.showerror("错误", "参数格式错误")
            return
        
        # 坐标转换选项
        self.config_manager.config.coord_conversions = []
        if self.wgs84_var.get():
            self.config_manager.config.coord_conversions.append('wgs84')
        if self.bd09_var.get():
            self.config_manager.config.coord_conversions.append('bd09')
        
        # 保存选中的POI类型（从标签字典获取）
        self.config_manager.config.selected_poi_types = []
        for code, data in self._selected_poi_tags.items():
            self.config_manager.config.selected_poi_types.append({
                'name': data['name'],
                'code': code
            })
        
        if self.config_manager.save_config():
            messagebox.showinfo("成功", "配置已保存")
        else:
            messagebox.showerror("错误", "配置保存失败")
    
    def _load_config(self):
        """加载配置"""
        if self.config_manager.load_config():
            config = self.config_manager.config
            
            # API Key
            self.api_key_var.set(', '.join(config.api_keys))
            
            # 参数
            self.threshold_var.set(str(config.poi_threshold))
            self.interval_var.set(str(config.request_interval))
            self.workers_var.set(str(config.max_workers))
            
            # 坐标转换
            self.wgs84_var.set('wgs84' in config.coord_conversions)
            self.bd09_var.set('bd09' in config.coord_conversions)
            
            # 目标区县
            self._update_target_districts_display()
            
            # POI类型 - 恢复已选标签
            for poi in config.selected_poi_types:
                if poi['code'] not in self._selected_poi_tags:
                    self._create_poi_tag(poi['name'], poi['code'])
            
            self._refresh_poi_list_display()
            self._update_poi_count()
    
    def _update_log_display(self):
        """更新日志显示"""
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, msg + '\n')
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        
        self.root.after(100, self._update_log_display)
    
    # ========== 采集控制 ==========
    
    def _start_collection(self):
        """开始采集"""
        # 验证配置
        errors = self._validate_collection_config()
        if errors:
            messagebox.showerror("配置错误", '\n'.join(errors.values()))
            return
        
        # 保存当前配置
        self._save_config()
        
        # 测试API并选择字段
        if not self._test_api_and_select_fields():
            return
        
        # 更新UI状态
        self._set_collecting_state(True)
        
        # 开始采集线程
        self._stop_event.clear()
        self._collect_thread = threading.Thread(
            target=self._collect_task,
            daemon=True
        )
        self._collect_thread.start()
    
    def _validate_collection_config(self) -> Dict[str, str]:
        """验证采集配置"""
        errors = {}
        
        if not self.config_manager.config.api_keys:
            errors['api_keys'] = "请输入高德API Key"
        
        if not self.config_manager.config.selected_districts:
            errors['districts'] = "请选择目标区县"
        
        # 从标签字典获取已选POI类型
        selected_pois = [
            {'name': data['name'], 'code': code}
            for code, data in self._selected_poi_tags.items()
        ]
        
        if not selected_pois:
            errors['poi_types'] = "请选择POI类型"
        else:
            self.config_manager.config.selected_poi_types = selected_pois
        
        return errors
    
    def _test_api_and_select_fields(self) -> bool:
        """测试API并让用户选择字段"""
        # 获取第一个区县
        district = self.config_manager.config.selected_districts[0]
        poi_type = self.config_manager.config.selected_poi_types[0]
        
        logging.info(f"测试API请求: 区县={district['district']}, POI类型={poi_type['name']}({poi_type['code']})")
        
        # 创建API客户端
        api_client = AmapAPI(
            self.config_manager.config.api_keys,
            self.config_manager.config.request_interval
        )
        
        # 获取边界框
        bbox = bbox_from_adcode(api_client, district['adcode'])
        if not bbox:
            messagebox.showerror("错误", f"无法获取区县边界: {district['district']}")
            return False
        
        logging.info(f"获取到边界框: {bbox}")
        
        # 发起测试请求
        result = api_client.search_poi_by_polygon(
            polygon=bbox.to_polygon(),
            types=poi_type['code'],
            page_size=1,
            page_num=1
        )
        
        if not result.success:
            logging.error(f"API测试失败: {result.error_message}")
            messagebox.showerror("API测试失败", result.error_message)
            return False
        
        logging.info(f"API返回: 成功={result.success}, 数量={result.count}, 数据条数={len(result.data)}")
        
        if not result.data:
            # 尝试使用keywords参数搜索
            logging.info("尝试使用keywords方式搜索...")
            result2 = api_client.search_poi_by_keyword(
                keywords=poi_type['name'].split('>')[-1],  # 使用POI类型名称的最后部分
                types=poi_type['code'],
                region=district['adcode'],
                city_limit=True,
                page_size=1,
                page_num=1
            )
            
            if result2.success and result2.data:
                sample_poi = result2.data[0]
                logging.info(f"keywords搜索成功，找到数据")
            else:
                msg = f"测试请求未返回数据\n\n可能原因：\n"
                msg += f"1. 该区域({district['district']})没有此类型的POI\n"
                msg += f"2. POI类型代码({poi_type['code']})可能不正确\n"
                msg += f"3. API Key权限问题\n\n"
                msg += f"建议：尝试选择其他POI类型或区域"
                messagebox.showwarning("提示", msg)
                return False
        else:
            sample_poi = result.data[0]
        
        # 获取坐标转换选项
        coord_conversions = []
        if self.wgs84_var.get():
            coord_conversions.append('wgs84')
        if self.bd09_var.get():
            coord_conversions.append('bd09')
        self.config_manager.config.coord_conversions = coord_conversions
        
        # 获取可用字段
        available_fields = get_all_available_fields(sample_poi, coord_conversions)
        
        # 显示字段选择对话框
        return self._show_field_selection_dialog(sample_poi, available_fields)
    
    def _show_field_selection_dialog(self, sample_poi: Dict, available_fields: List[str]) -> bool:
        """
        显示字段选择对话框
        
        Args:
            sample_poi: 示例POI数据
            available_fields: 可用字段列表
            
        Returns:
            bool: 用户是否确认
        """
        dialog = tk.Toplevel(self.root)
        dialog.title("API测试结果 - 字段选择")
        dialog.geometry("700x500")
        dialog.transient(self.root)
        dialog.grab_set()
        
        result = {'confirmed': False}
        
        # 原始JSON显示
        json_frame = ttk.LabelFrame(dialog, text="测试API返回的完整原始字段（格式化JSON）", padding="5")
        json_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        json_text = scrolledtext.ScrolledText(json_frame, height=10, wrap=tk.WORD)
        json_text.pack(fill=tk.BOTH, expand=True)
        json_text.insert(tk.END, json.dumps(sample_poi, ensure_ascii=False, indent=2))
        json_text.config(state=tk.DISABLED)
        
        # 字段选择
        field_frame = ttk.LabelFrame(dialog, text="请选择要保存的字段（可多选）", padding="5")
        field_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 列表框
        list_frame = ttk.Frame(field_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        field_listbox = tk.Listbox(
            list_frame, selectmode=tk.EXTENDED,
            height=8, exportselection=False
        )
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=field_listbox.yview)
        field_listbox.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        field_listbox.pack(fill=tk.BOTH, expand=True)
        
        # 添加字段并默认全选
        for field in available_fields:
            field_listbox.insert(tk.END, field)
        
        field_listbox.select_set(0, tk.END)
        
        # 按钮区
        btn_frame = ttk.Frame(field_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(
            btn_frame, text="全选",
            command=lambda: field_listbox.select_set(0, tk.END)
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame, text="清空",
            command=lambda: field_listbox.selection_clear(0, tk.END)
        ).pack(side=tk.LEFT, padx=5)
        
        # 确认/取消按钮
        confirm_frame = ttk.Frame(dialog)
        confirm_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def on_confirm():
            selected = [field_listbox.get(i) for i in field_listbox.curselection()]
            if not selected:
                messagebox.showwarning("提示", "请至少选择一个字段")
                return
            
            self.selected_fields = selected
            self.config_manager.config.selected_fields = selected
            result['confirmed'] = True
            dialog.destroy()
        
        def on_cancel():
            dialog.destroy()
        
        ttk.Button(confirm_frame, text="确认并开始采集", command=on_confirm).pack(side=tk.RIGHT, padx=5)
        ttk.Button(confirm_frame, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=5)
        
        # 等待对话框关闭
        self.root.wait_window(dialog)
        
        return result['confirmed']
    
    def _set_collecting_state(self, collecting: bool):
        """设置采集状态"""
        self.is_collecting = collecting
        
        if collecting:
            self.start_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.NORMAL)
            self.resume_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
        else:
            self.start_btn.config(state=tk.NORMAL)
            self.pause_btn.config(state=tk.DISABLED)
            self.resume_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.DISABLED)
    
    def _pause_collection(self):
        """暂停采集"""
        self.is_paused = True
        self.pause_btn.config(state=tk.DISABLED)
        self.resume_btn.config(state=tk.NORMAL)
        logging.info("采集已暂停")
    
    def _resume_collection(self):
        """继续采集"""
        self.is_paused = False
        self.pause_btn.config(state=tk.NORMAL)
        self.resume_btn.config(state=tk.DISABLED)
        logging.info("采集已继续")
    
    def _stop_collection(self):
        """停止采集"""
        if messagebox.askyesno("确认", "确定要停止采集吗？"):
            self._stop_event.set()
            self.is_paused = False
            logging.info("正在停止采集...")
    
    def _collect_task(self):
        """采集任务（在子线程中执行）"""
        try:
            config = self.config_manager.config
            
            # 打印详细配置信息
            logging.info("=" * 50)
            logging.info("采集配置信息:")
            logging.info(f"  API Key数量: {len(config.api_keys)}")
            logging.info(f"  目标区县数量: {len(config.selected_districts)}")
            logging.info(f"  POI类型数量: {len(config.selected_poi_types)}")
            logging.info(f"  POI超量阈值: {config.poi_threshold}")
            logging.info(f"  请求间隔: {config.request_interval}秒")
            logging.info(f"  并发数: {config.max_workers}")
            logging.info(f"  坐标转换: {config.coord_conversions if config.coord_conversions else '无'}")
            
            logging.info("\n选择的区县:")
            for d in config.selected_districts:
                logging.info(f"  - {d['province']} > {d['city']} > {d['district']} ({d['adcode']})")
            
            logging.info("\n选择的POI类型:")
            for p in config.selected_poi_types:
                logging.info(f"  - {p['name']} (代码: {p['code']})")
            logging.info("=" * 50)
            
            # 初始化API客户端
            api_client = AmapAPI(
                config.api_keys,
                config.request_interval
            )
            
            # 初始化四叉树拆分器
            splitter = QuadTreeSplitter(
                api_client=api_client,
                poi_threshold=config.poi_threshold,
                max_workers=config.max_workers
            )
            
            # 初始化数据处理器
            self.data_processor = DataProcessor(
                coord_conversions=config.coord_conversions,
                selected_fields=self.selected_fields
            )
            
            # 初始化CSV文件
            output_file = "./data/poi_result.csv"
            if not self.data_processor.init_csv_file(output_file):
                logging.error("无法创建输出文件")
                self.root.after(0, lambda: self._set_collecting_state(False))
                return
            
            # 计算总任务数
            total_districts = len(config.selected_districts)
            total_types = len(config.selected_poi_types)
            total_tasks = total_districts * total_types
            completed_tasks = 0
            
            logging.info(f"\n开始采集，共 {total_tasks} 个任务")
            
            # 遍历区县和类型
            for district in config.selected_districts:
                if self._stop_event.is_set():
                    break
                
                # 等待暂停恢复
                while self.is_paused and not self._stop_event.is_set():
                    import time
                    time.sleep(0.5)
                
                if self._stop_event.is_set():
                    break
                
                # 获取边界框
                bbox = bbox_from_adcode(api_client, district['adcode'])
                if not bbox:
                    logging.error(f"无法获取区县边界: {district['district']}")
                    completed_tasks += total_types
                    continue
                
                logging.info(f"区县边界: {district['district']} - {bbox}")
                
                for poi_type in config.selected_poi_types:
                    if self._stop_event.is_set():
                        break
                    
                    # 等待暂停恢复
                    while self.is_paused and not self._stop_event.is_set():
                        import time
                        time.sleep(0.5)
                    
                    if self._stop_event.is_set():
                        break
                    
                    # 更新任务标签
                    task_name = f"{district['district']}-{poi_type['name']}"
                    self.root.after(0, lambda t=task_name: self.task_label.config(text=f"当前任务: {t}"))
                    
                    logging.info(f"开始采集: {task_name} (类型代码: {poi_type['code']})")
                    
                    # 执行四叉树拆分采集
                    pois = splitter.quadtree_split(
                        bounds=bbox,
                        types=poi_type['code'],
                        on_log=lambda msg: logging.info(msg),
                        on_poi_found=self._on_poi_found
                    )
                    
                    completed_tasks += 1
                    
                    # 更新进度
                    progress = (completed_tasks / total_tasks) * 100
                    self.root.after(0, lambda p=progress: self._update_progress(p))
                    
                    logging.info(f"任务完成: {task_name}，获取 {len(pois)} 条数据")
            
            # 完成
            if not self._stop_event.is_set():
                stats = self.data_processor.get_stats()
                logging.info(f"采集完成！共处理 {stats['total_ids']} 条有效数据")
                self.root.after(0, lambda: messagebox.showinfo(
                    "完成",
                    f"采集完成！\n共采集 {stats['total_ids']} 条数据\n保存至: {output_file}"
                ))
            
        except Exception as e:
            logging.error(f"采集任务异常: {e}")
            self.root.after(0, lambda: messagebox.showerror("错误", f"采集任务异常: {e}"))
        
        finally:
            if self.data_processor:
                self.data_processor.close()
            self.root.after(0, lambda: self._set_collecting_state(False))
    
    def _on_poi_found(self, pois: List[Dict]):
        """
        POI数据回调处理
        
        Args:
            pois: POI数据列表
        """
        if self.data_processor:
            count = self.data_processor.write_records([
                self.data_processor.parse_poi_data(p) for p in pois
                if self.data_processor.parse_poi_data(p) is not None
            ])
            if count > 0:
                logging.debug(f"写入 {count} 条数据")
    
    def _update_progress(self, value: float):
        """
        更新进度条
        
        Args:
            value: 进度值（0-100）
        """
        self.progress_var.set(value)
        self.progress_label.config(text=f"整体进度: {value:.1f}%")
    
    def update_result_preview(self, records: List[Dict]):
        """
        更新结果预览表格
        
        Args:
            records: POI记录列表
        """
        # 清空表格
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        
        # 设置列
        if records and self.selected_fields:
            self.result_tree['columns'] = self.selected_fields
            
            for field in self.selected_fields:
                self.result_tree.heading(field, text=field)
                self.result_tree.column(field, width=100)
            
            # 添加数据（最多100条）
            for record in records[:100]:
                values = [str(record.get(f, '')) for f in self.selected_fields]
                self.result_tree.insert('', tk.END, values=values)
        
        self.stats_label.config(text=f"共采集: {len(records)} 条数据")


def run_gui():
    """启动GUI应用"""
    root = tk.Tk()
    app = POICrawlerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
