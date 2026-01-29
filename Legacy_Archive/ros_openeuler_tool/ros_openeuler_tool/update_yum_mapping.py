# ros_openeuler_tool/update_yum_mapping.py

import subprocess
import logging
from ros_openeuler_tool.map_yum_rosdep import get_yum_packages, map_yum_to_rosdep, save_rosdep_yaml

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def update_yum():
    logging.info("正在更新 YUM 仓库...")
    try:
        subprocess.run(['yum', 'makecache'], check=True)
        subprocess.run(['yum', 'update', '-y'], check=True)
        logging.info("YUM 仓库更新完成。")
    except subprocess.CalledProcessError as e:
        logging.error(f"更新 YUM 仓库失败: {e}")

def update_yum_and_mapping():
    update_yum()
    yum_packages = get_yum_packages()
    existing_rosdep = {}
    rosdep_mapping = map_yum_to_rosdep(yum_packages, existing_rosdep)
    save_rosdep_yaml(rosdep_mapping)
    logging.info("YUM 仓库和 rosdep 映射文件已更新。")
