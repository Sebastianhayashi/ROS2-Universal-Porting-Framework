# ros_openeuler_tool/analyze_dependencies.py

import json
import networkx as nx
import subprocess
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

PACKAGE_DATA_FILE = 'ros_jazzy_packages.json'

def load_packages():
    if not os.path.isfile(PACKAGE_DATA_FILE):
        logging.error(f"包数据文件 {PACKAGE_DATA_FILE} 不存在。")
        return {}
    with open(PACKAGE_DATA_FILE, 'r') as f:
        packages = json.load(f)
    logging.info(f"加载了 {len(packages)} 个包的信息。")
    return packages

def build_dependency_graph(packages):
    G = nx.DiGraph()
    for pkg, details in packages.items():
        G.add_node(pkg)
        for dep in details.get('dependencies', []):
            G.add_edge(dep, pkg)  # dep -> pkg
    logging.info("依赖关系图已构建。")
    return G

def analyze_dependencies():
    packages = load_packages()
    if not packages:
        logging.error("没有包数据可供分析。")
        return

    graph = build_dependency_graph(packages)
    try:
        build_order = list(nx.topological_sort(graph))
        logging.info("构建顺序已生成。")
        print("构建顺序:")
        for pkg in build_order:
            print(pkg)
    except nx.NetworkXUnfeasible:
        logging.error("检测到循环依赖。")
        cycles = list(nx.simple_cycles(graph))
        logging.error(f"循环依赖环: {cycles}")
        print("错误: 检测到循环依赖。请检查日志了解详细信息。")
