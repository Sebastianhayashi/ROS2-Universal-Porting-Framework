# ros_openeuler_tool/map_yum_rosdep.py

import os
import subprocess
import yaml
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

YUM_PACKAGES_CMD = ['yum', 'list', 'available']
ROSDEP_YAML_FILE = '50-openeuler.yaml'

def get_yum_packages():
    try:
        result = subprocess.run(YUM_PACKAGES_CMD, stdout=subprocess.PIPE, text=True, check=True)
        packages = set()
        for line in result.stdout.splitlines()[1:]:  # Skip header
            parts = line.split()
            if len(parts) >= 1:
                packages.add(parts[0].split('.')[0])  # Remove version info
        logging.info(f"获取到 {len(packages)} 个 YUM 可用包。")
        return packages
    except subprocess.CalledProcessError as e:
        logging.error(f"获取 YUM 包失败: {e}")
        return set()

def map_yum_to_rosdep(yum_packages, existing_rosdep=None):
    if existing_rosdep is None:
        existing_rosdep = {}
    for pkg in yum_packages:
        existing_rosdep[pkg] = {
            'fedora': pkg,
            'opensuse': pkg,
            'rhel': pkg
        }
    logging.info("完成 YUM 包到 rosdep 的映射。")
    return existing_rosdep

def save_rosdep_yaml(mapping, filename=ROSDEP_YAML_FILE):
    with open(filename, 'w') as f:
        yaml.dump(mapping, f, default_flow_style=False)
    logging.info(f"rosdep YAML 映射文件已保存到 {filename}。")

def map_yum_to_rosdep_yaml():
    yum_packages = get_yum_packages()
    existing_rosdep = {}
    rosdep_mapping = map_yum_to_rosdep(yum_packages, existing_rosdep)
    save_rosdep_yaml(rosdep_mapping)
