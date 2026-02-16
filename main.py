# -*- coding: utf-8 -*-
"""
高德POI数据采集工具 - 主入口文件

【合规声明】仅用于个人学习/内部项目，不批量爬取、存储、转售高德数据，不用于商业用途。

使用方法：
    python main.py

功能：
    - 启动图形界面
    - 初始化必要目录
    - 检查依赖环境
"""

import sys
import os


def check_dependencies() -> bool:
    """
    检查必要的依赖包是否已安装
    
    Returns:
        bool: 依赖检查是否通过
    """
    missing_packages = []
    
    try:
        import requests
    except ImportError:
        missing_packages.append('requests')
    
    try:
        import pandas
    except ImportError:
        missing_packages.append('pandas')
    
    if missing_packages:
        print("=" * 50)
        print("缺少必要的依赖包，请先安装：")
        print(f"    pip install {' '.join(missing_packages)}")
        print("=" * 50)
        return False
    
    return True


def ensure_directories():
    """确保必要的目录存在"""
    directories = ['logs', 'cache', 'data']
    for d in directories:
        if not os.path.exists(d):
            os.makedirs(d)
            print(f"已创建目录: {d}")


def check_data_files():
    """检查必要的数据文件是否存在"""
    files = {
        'poi_temp.csv': 'POI类型文件',
        'city_temp.csv': '城市行政区划文件'
    }
    
    missing_files = []
    for filename, desc in files.items():
        if not os.path.exists(filename):
            missing_files.append(f"{filename} ({desc})")
    
    if missing_files:
        print("=" * 50)
        print("警告：以下数据文件不存在：")
        for f in missing_files:
            print(f"    - {f}")
        print("请创建相应的CSV文件后再运行程序。")
        print("=" * 50)
        return False
    
    return True


def main():
    """
    主函数入口
    
    执行流程：
    1. 检查依赖
    2. 创建目录
    3. 检查数据文件
    4. 启动GUI
    """
    print("=" * 50)
    print("高德POI数据采集工具 v2.1（坐标多选版）")
    print("=" * 50)
    print()
    
    # 合规声明
    print("【合规声明】")
    print("本工具仅用于个人学习/内部项目，")
    print("不批量爬取、存储、转售高德数据，不用于商业用途。")
    print()
    
    # 检查依赖
    print("正在检查依赖...")
    if not check_dependencies():
        sys.exit(1)
    print("依赖检查通过。")
    print()
    
    # 创建目录
    print("正在初始化目录...")
    ensure_directories()
    print()
    
    # 检查数据文件
    print("正在检查数据文件...")
    if not check_data_files():
        print("提示：程序仍可启动，但部分功能可能不可用。")
        print()
    
    # 启动GUI
    print("正在启动图形界面...")
    print()
    
    try:
        from gui import run_gui
        run_gui()
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
