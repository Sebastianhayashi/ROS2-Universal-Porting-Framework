import yaml
import requests
import subprocess
import argparse
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# 结果存储
installed_packages = []
missing_packages = []
failed_packages = []

# 线程锁用于确保线程安全
lock = threading.Lock()

# 定义需要处理的前缀及其对应的处理方法
PREFIXES = {
    "python3-": "pip",
    # 可以在这里添加更多前缀及其处理方式
}

def download_yaml(url):
    ...
    # (中间内容与原脚本相同)
    ...

def save_yaml(yaml_data, file_path):
    ...
    # (中间内容与原脚本相同)
    ...

def query_package_dnf(pkg_name):
    ...
    # (中间内容与原脚本相同)
    ...

def query_package_pip(pkg_name):
    ...
    # (中间内容与原脚本相同)
    ...

def search_pip_package(pkg_name):
    ...
    # (中间内容与原脚本相同)
    ...

def process_base_yaml(base_yaml, package):
    ...
    # (中间内容与原脚本相同)
    ...

def process_python_yaml(python_yaml, package):
    ...
    # (中间内容与原脚本相同)
    ...

def update_yaml(base_yaml, python_yaml, executor):
    ...
    # (中间内容与原脚本相同)
    ...

def main_update_rosdep_yaml(base_yaml_url, python_yaml_url, output_base_yaml, output_python_yaml, threads):
    """
    main_update_rosdep_yaml 函数用于在不使用 argparse 的情况下，
    直接在 CLI 命令里调用该逻辑。
    """
    print(f"下载 base.yaml: {base_yaml_url}")
    base_yaml = download_yaml(base_yaml_url)
    print(f"下载 python.yaml: {python_yaml_url}")
    python_yaml = download_yaml(python_yaml_url)

    if not base_yaml or not python_yaml:
        print("错误: 下载 YAML 文件失败")
        sys.exit(1)

    with ThreadPoolExecutor(max_workers=threads) as executor:
        update_yaml(base_yaml, python_yaml, executor)

    save_yaml(base_yaml, output_base_yaml)
    save_yaml(python_yaml, output_python_yaml)

    if missing_packages:
        with open("missing_packages.txt", "w") as f:
            for pkg in missing_packages:
                f.write(pkg + "\n")
        print("\n❌ 缺失的包已记录到 'missing_packages.txt'。")
    else:
        print("\n✅ 所有包的 openeuler 条目已成功添加。")

    if installed_packages:
        with open("installed_packages.txt", "w") as f:
            for pkg in installed_packages:
                f.write(pkg + "\n")
        print("✅ 已安装的包已记录到 'installed_packages.txt'。")

    if failed_packages:
        with open("failed_packages.txt", "w") as f:
            for pkg in failed_packages:
                f.write(pkg + "\n")
        print("⚠️ 安装失败的包已记录到 'failed_packages.txt'。")
    else:
        print("⚠️ 没有安装失败的包。")

    print("\n[RESULTS]")
    print(f"✅ 已安装的包: {len(installed_packages)}")
    print(f"❌ 缺失的包: {len(missing_packages)} (见 'missing_packages.txt')")
    print(f"⚠️ 安装失败的包: {len(failed_packages)} (见 'failed_packages.txt')")

# 如果你想保留原 argparse 模式，可保留以下 main()，但在 CLI 中就会重复定义命令了。
# 这里通常只保留 main_update_rosdep_yaml()，方便 CLI 调用。
#
# if __name__ == "__main__":
#     ... 原 argparse 内容 ...
