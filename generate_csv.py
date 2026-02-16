# -*- coding: utf-8 -*-
"""
从Excel文件生成CSV模板
"""
import pandas as pd
import os
import glob

def find_excel_file(directory):
    """查找Excel文件"""
    for f in os.listdir(directory):
        if f.endswith('.xlsx') and not f.startswith('.'):
            return os.path.join(directory, f)
    return None

def generate_poi_csv():
    """生成POI类型CSV文件"""
    poi_dir = 'poi_temp'
    excel_file = find_excel_file(poi_dir)
    
    if not excel_file:
        print(f"未找到POI Excel文件")
        return
    
    print(f"读取POI文件: {excel_file}")
    
    try:
        df = pd.read_excel(excel_file)
        print(f"列名: {df.columns.tolist()}")
        
        output_file = 'poi_temp.csv'
        count = 0
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for _, row in df.iterrows():
                code = str(row['NEW_TYPE']).strip() if pd.notna(row['NEW_TYPE']) else ''
                big = str(row['大类']).strip() if pd.notna(row['大类']) else ''
                mid = str(row['中类']).strip() if pd.notna(row['中类']) else ''
                small = str(row['小类']).strip() if pd.notna(row['小类']) else ''
                
                if not code:
                    continue
                
                # 补齐为6位代码（高德V5 API要求）
                code = code.zfill(6)
                
                # 构建名称：大类>中类>小类
                parts = [p for p in [big, mid, small] if p and p != 'nan']
                if parts:
                    name = '>'.join(parts)
                    f.write(f"{name},{code}\n")
                    count += 1
        
        print(f"已生成 {output_file}，共 {count} 条记录")
            
    except Exception as e:
        print(f"处理POI文件失败: {e}")
        import traceback
        traceback.print_exc()

def generate_city_csv():
    """生成城市行政区划CSV文件"""
    city_dir = 'city_temp'
    excel_file = os.path.join(city_dir, 'AMap_adcode_citycode.xlsx')
    
    if not os.path.exists(excel_file):
        print(f"未找到城市Excel文件: {excel_file}")
        return
    
    print(f"读取城市文件: {excel_file}")
    
    try:
        df = pd.read_excel(excel_file)
        print(f"列名: {df.columns.tolist()}")
        print(f"总行数: {len(df)}")
        
        # 解析行政区划层级
        # 根据adcode长度判断级别：省(后4位为0)、市(后2位为0)、区县
        provinces = {}  # adcode -> name
        cities = {}     # adcode -> (name, province_adcode)
        districts = []  # (province, city, district, adcode)
        
        for _, row in df.iterrows():
            name = str(row['中文名']).strip() if pd.notna(row['中文名']) else ''
            adcode = str(row['adcode']).strip() if pd.notna(row['adcode']) else ''
            
            if not name or not adcode or name == '中国':
                continue
            
            # 判断级别
            if adcode.endswith('0000'):
                # 省级
                provinces[adcode] = name
            elif adcode.endswith('00'):
                # 市级
                province_code = adcode[:2] + '0000'
                cities[adcode] = (name, province_code)
            else:
                # 区县级
                province_code = adcode[:2] + '0000'
                city_code = adcode[:4] + '00'
                
                province_name = provinces.get(province_code, '')
                city_info = cities.get(city_code, ('', ''))
                city_name = city_info[0] if city_info else ''
                
                # 如果找不到对应的市，可能是直辖市
                if not city_name and province_code in provinces:
                    city_name = provinces[province_code]
                
                if province_name and name:
                    districts.append((province_name, city_name, name, adcode))
        
        output_file = 'city_temp.csv'
        count = 0
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for province, city, district, adcode in districts:
                f.write(f"{province},{city},{district},{adcode}\n")
                count += 1
        
        print(f"已生成 {output_file}，共 {count} 条记录")
        print(f"省级: {len(provinces)}, 市级: {len(cities)}, 区县级: {len(districts)}")
            
    except Exception as e:
        print(f"处理城市文件失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 50)
    print("生成POI类型CSV...")
    print("=" * 50)
    generate_poi_csv()
    
    print("\n" + "=" * 50)
    print("生成城市行政区划CSV...")
    print("=" * 50)
    generate_city_csv()
