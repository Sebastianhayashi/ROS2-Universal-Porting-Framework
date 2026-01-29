# ros_openeuler_tool/batch_process.py

import os
import subprocess
import logging
import re 

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

PROCESS_SCRIPT = os.path.expanduser('~/process_ros_packages.sh')
MISSING_DEPS_DIR = os.path.expanduser('~/missing_deps')
MISSING_ROSDEPS_LOG = os.path.join(MISSING_DEPS_DIR, 'missing_rosdeps.log')
SKIPPED_PACKAGES_LOG = os.path.join(MISSING_DEPS_DIR, 'skipped_packages.log')
PARALLEL_JOBS = 32

def setup_logging():
    os.makedirs(MISSING_DEPS_DIR, exist_ok=True)
    open(MISSING_ROSDEPS_LOG, 'a').close()
    open(SKIPPED_PACKAGES_LOG, 'a').close()

def is_ros_package(dir_path):
    return os.path.isfile(os.path.join(dir_path, 'CMakeLists.txt')) and os.path.isfile(os.path.join(dir_path, 'package.xml'))

def collect_ros_packages(search_root):
    all_packages = []
    for root, dirs, files in os.walk(search_root):
        if is_ros_package(root):
            all_packages.append(root)
    return all_packages

def run_parent_process_script(pkg_path):
    parent_dir = os.path.dirname(pkg_path)
    pkg_basename = os.path.basename(pkg_path)

    # 拷贝脚本到 parent_dir
    try:
        subprocess.run(['cp', '-f', PROCESS_SCRIPT, parent_dir], check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"无法复制脚本到 {parent_dir}: {e}")
        return

    # 执行脚本
    try:
        result = subprocess.run([os.path.join(parent_dir, 'process_ros_packages.sh'), pkg_basename],
                                cwd=parent_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        output = result.stdout
    except subprocess.CalledProcessError as e:
        output = e.stdout + e.stderr
        logging.error(f"执行脚本失败: {pkg_basename}")
    
    # 检查是否有跳过的包
    skip_pkg = re.search(r'跳过包 (\S+)', output)
    if skip_pkg:
        pkg_name = skip_pkg.group(1)
        with open(SKIPPED_PACKAGES_LOG, 'a') as f:
            f.write(f"{pkg_name}\n")
        logging.info(f"跳过包: {pkg_name}")

    # 检查缺失的 rosdep key
    missing_keys = re.findall(r"Could not resolve rosdep key '([^']+)'", output)
    if missing_keys:
        with open(MISSING_ROSDEPS_LOG, 'a') as f:
            for key in set(missing_keys):
                f.write(f"{key}\n")
        logging.info(f"记录缺失的 rosdep key: {missing_keys}")

def batch_process_packages():
    setup_logging()
    search_root = os.getcwd()
    all_packages = collect_ros_packages(search_root)
    logging.info(f"共收集到 {len(all_packages)} 个 ROS 包，准备并行执行...")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=PARALLEL_JOBS) as executor:
        futures = [executor.submit(run_parent_process_script, pkg) for pkg in all_packages]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"批量处理时发生错误: {e}")

    logging.info("所有包批量处理完成。")
