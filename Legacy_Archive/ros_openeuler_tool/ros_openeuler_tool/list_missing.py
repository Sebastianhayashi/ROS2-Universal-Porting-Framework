# ros_openeuler_tool/list_missing.py

import json
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

def get_installed_packages():
    try:
        result = subprocess.run(['yum', 'list', 'installed'], stdout=subprocess.PIPE, text=True, check=True)
        installed = set()
        for line in result.stdout.splitlines()[1:]:  # Skip header
            parts = line.split()
            if len(parts) >= 1:
                installed.add(parts[0].split('.')[0])  # Remove version info
        logging.info(f"已安装的包数量: {len(installed)}")
        return installed
    except subprocess.CalledProcessError as e:
        logging.error(f"获取已安装包列表失败: {e}")
        return set()

def list_missing_packages():
    packages = load_packages()
    if not packages:
        logging.error("没有包数据可供分析。")
        return

    installed = get_installed_packages()
    all_deps = set()
    for details in packages.values():
        all_deps.update(details.get('dependencies', []))
    
    missing = all_deps - installed
    if missing:
        logging.info(f"发现 {len(missing)} 个缺失的依赖包。")
        print("缺失的依赖包:")
        for pkg in sorted(missing):
            print(pkg)
    else:
        logging.info("没有发现缺失的依赖包。")
        print("没有缺失的依赖包。")
