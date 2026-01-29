# ros_openeuler_tool/extract_unresolved_dependencies.py

import pandas as pd
import re
import sys
import os
import logging

def extract_dependencies(detail):
    """
    从 detail 字段中提取未闭环的依赖包名称。

    参数：
        detail (str): 详细信息字段内容。

    返回：
        str: 依赖包名称或“无法解析”。
    """
    # 正则表达式示例：build_require [ros-jazzy-rclcpp]-[{}] no matched in latest repo
    pattern = r'\[ros-jazzy-(.*?)\]-\[\{\}\]'
    match = re.search(pattern, detail)
    if match:
        return match.group(1)
    else:
        return "无法解析"

def main_extract_unresolved_dependencies(input_file, mapping_file='unresolved_dependencies_mapping.txt', list_file='unresolved_dependencies_list.txt'):
    """
    提取未闭环依赖并生成映射和清单文件。

    参数：
        input_file (str): 输入的 Excel 文件路径。
        mapping_file (str): 映射文件的输出路径。
        list_file (str): 清单文件的输出路径。
    """
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("extract_unresolved_dependencies.log")
        ]
    )
    
    # 检查输入文件是否存在
    if not os.path.isfile(input_file):
        logging.error(f"错误：文件 '{input_file}' 不存在。")
        sys.exit(1)
    
    try:
        # 读取 Excel 文件
        df = pd.read_excel(input_file, engine='openpyxl')
    except Exception as e:
        logging.error(f"错误：无法读取 Excel 文件。详情：{e}")
        sys.exit(1)
    
    # 检查必要的字段是否存在
    required_columns = {'spec_name', 'packageName', 'status', 'detail'}
    if not required_columns.issubset(set(df.columns)):
        logging.error(f"错误：输入文件缺少必要的字段。需要字段：{required_columns}")
        sys.exit(1)
    
    # 筛选 status 为 JOB_UNRESOLVABLE 的行
    unresolved_df = df[df['status'] == 'JOB_UNRESOLVABLE']
    
    if unresolved_df.empty:
        logging.info("没有找到状态为 JOB_UNRESOLVABLE 的软件包。")
        sys.exit(0)
    
    # 存储映射和依赖项
    mapping_lines = []
    dependency_set = set()
    
    for index, row in unresolved_df.iterrows():
        spec_name = row['spec_name']
        detail = row['detail']
        dependency = extract_dependencies(detail)
        
        if dependency != "无法解析":
            dependency_set.add(dependency)
        
        line = f"{spec_name} -> {dependency}"
        mapping_lines.append(line)
    
    # 写入映射文件
    try:
        with open(mapping_file, 'w', encoding='utf-8') as f:
            for line in mapping_lines:
                f.write(line + '\n')
        logging.info(f"映射文件已写入 '{mapping_file}'。")
    except Exception as e:
        logging.error(f"错误：无法写入映射文件。详情：{e}")
        sys.exit(1)
    
    # 写入清单文件
    try:
        with open(list_file, 'w', encoding='utf-8') as f:
            for dependency in sorted(dependency_set):
                f.write(dependency + '\n')
        logging.info(f"清单文件已写入 '{list_file}'。")
    except Exception as e:
        logging.error(f"错误：无法写入清单文件。详情：{e}")
        sys.exit(1)
