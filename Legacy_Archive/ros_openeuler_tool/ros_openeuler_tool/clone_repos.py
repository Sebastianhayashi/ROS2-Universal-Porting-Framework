# ros_openeuler_tool/clone_repos.py

import os
import subprocess
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
import re
import json
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BRANCH = 'jazzy'
CLONE_BASE_DIR = './ros_repos'
MAX_THREADS = 32

def fetch_sitemap(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logging.error(f"无法获取 sitemap: {e}")
        return None

def get_ros_package_urls(sitemap):
    soup = BeautifulSoup(sitemap, 'xml')
    ros_package_urls = []
    for loc_tag in soup.find_all('loc'):
        url = loc_tag.text.strip()
        if '/repos/' in url:
            ros_package_urls.append(url)
    return ros_package_urls

def map_checkout_url(checkout_url):
    if checkout_url.startswith('https://github.com'):
        return checkout_url
    elif checkout_url.startswith('/r/'):
        match = re.match(r'^/r/(?P<repo_name>[^/]+)/github-ros-industrial-[^/]+$', checkout_url)
        if match:
            repo_name = match.group('repo_name')
            return f"https://github.com/ros-industrial/{repo_name}.git"
        else:
            logging.warning(f"未知的 checkout URL 格式: {checkout_url}")
            return None
    else:
        logging.warning(f"未知的 checkout URL 格式: {checkout_url}")
        return None

def get_checkout_url(package_url):
    try:
        response = requests.get(package_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        checkout_uri_tag = soup.find('a', href=lambda x: x and 'github.com' in x)
        if checkout_uri_tag:
            checkout_url = checkout_uri_tag['href'].strip()
            if not checkout_url.startswith('http'):
                checkout_url = urljoin(package_url, checkout_url)
            repo_url = map_checkout_url(checkout_url)
            return repo_url
        else:
            logging.warning(f"未找到 checkout URL: {package_url}")
            return None
    except requests.RequestException as e:
        logging.error(f"获取 checkout URL 失败 ({package_url}): {e}")
        return None

def clone_repository(repo_url, branch=BRANCH):
    if not repo_url:
        return
    package_name = os.path.basename(repo_url.rstrip('.git'))
    target_dir = os.path.join(CLONE_BASE_DIR, package_name)
    if os.path.exists(target_dir):
        logging.info(f"包 '{package_name}' 已存在，跳过。")
        return
    try:
        logging.info(f"正在克隆 '{repo_url}' 到 '{target_dir}'...")
        subprocess.run(['git', 'clone', repo_url, '-b', branch, target_dir], check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"克隆失败 '{repo_url}': {e}")
        logging.info(f"尝试克隆默认分支 '{repo_url}'...")
        try:
            subprocess.run(['git', 'clone', repo_url, target_dir], check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"克隆失败 '{repo_url}' (默认分支): {e}")

def process_package(package_url):
    logging.info(f"处理包: {package_url}")
    repo_url = get_checkout_url(package_url)
    if repo_url:
        clone_repository(repo_url, BRANCH)
    else:
        logging.warning(f"无效的 checkout URL，跳过包: {package_url}")

def clone_repositories():
    sitemap_url = 'https://index.ros.org/sitemap.xml'
    sitemap = fetch_sitemap(sitemap_url)
    if not sitemap:
        logging.error("无法获取或解析 sitemap。")
        return
    ros_package_urls = get_ros_package_urls(sitemap)
    logging.info(f"找到 {len(ros_package_urls)} 个 ROS 包。")
    os.makedirs(CLONE_BASE_DIR, exist_ok=True)
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = [executor.submit(process_package, url) for url in ros_package_urls]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"处理包时发生错误: {e}")
    logging.info("所有仓库克隆完成。")
