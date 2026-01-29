# ros_openeuler_tool/sync_gitee.py

import subprocess
import os
import re
import shutil
import requests
import sys
from urllib.parse import urljoin
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SPECS_DIR = os.path.expanduser('~/rpmbuild/SPECS')
SOURCES_DIR = os.path.expanduser('~/rpmbuild/SOURCES')
OUTPUT_DIR = os.path.expanduser('~/gitee_repos')

GITEE_TOKEN = os.getenv('GITEE_TOKEN')
if not GITEE_TOKEN:
    logging.error("请在环境变量 GITEE_TOKEN 中设置您的 Gitee 个人访问令牌。")
    sys.exit(1)

GITEE_ORG = os.getenv('GITEE_ORG')
GITEE_API_BASE = "https://gitee.com/api/v5/"

def extract_spec_info(spec_path):
    name = None
    version = None
    requires = []
    build_requires = []

    with open(spec_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('Name:'):
                name = line.split(':', 1)[1].strip()
            elif line.startswith('Version:'):
                version = line.split(':', 1)[1].strip()
            elif line.startswith('Requires:'):
                dep = line.split(':', 1)[1].strip()
                dep_name = dep.split(' ')[0]
                requires.append(dep_name)
            elif line.startswith('BuildRequires:'):
                dep = line.split(':', 1)[1].strip()
                dep_name = dep.split(' ')[0]
                build_requires.append(dep_name)

    return name, version, requires, build_requires

def find_source_tarball(name, version):
    pattern = f"{name}-{version}.tar.gz"
    tarball_path = os.path.join(SOURCES_DIR, pattern)
    return tarball_path if os.path.isfile(tarball_path) else None

def generate_readme(name, version, dependencies):
    readme_content = f"""# {name}

## 版本

- 名称: {name}
- 版本: {version}

## 依赖

"""
    for dep in dependencies:
        if dep.startswith('ament-') or dep.startswith('ros-'):
            readme_content += f"- {dep}\n"

    return readme_content

def sanitize_repo_name(name):
    if name.startswith('ros-jazzy-'):
        name = name[len('ros-jazzy-'):]
    return name

def create_gitee_repo(repo_name):
    if GITEE_ORG:
        url = urljoin(GITEE_API_BASE, f'orgs/{GITEE_ORG}/repos')
    else:
        url = urljoin(GITEE_API_BASE, 'user/repos')

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'token {GITEE_TOKEN}'
    }

    data = {
        'name': repo_name,
        'private': False,
        'auto_init': False,
        'description': f'Repository for {repo_name}'
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 201:
        repo_info = response.json()
        logging.info(f"已在 Gitee 上创建仓库: {repo_info['full_name']}")
        return repo_info['ssh_url'], repo_info['html_url']
    else:
        logging.error(f"创建仓库失败: {repo_name}, 错误信息: {response.json().get('message', '未知错误')}")
        return None, None

def sync_to_gitee():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    uploaded_repos = []

    for spec_file in os.listdir(SPECS_DIR):
        if not spec_file.endswith('.spec'):
            continue
        spec_path = os.path.join(SPECS_DIR, spec_file)
        name, version, requires, build_requires = extract_spec_info(spec_path)

        if not name or not version:
            logging.warning(f"无法从 {spec_file} 中提取名称或版本，跳过。")
            continue

        logging.info(f"处理包: {name}, 版本: {version}")

        tarball_path = find_source_tarball(name, version)
        if not tarball_path:
            logging.warning(f"未找到源码压缩包: {name}-{version}.tar.gz，跳过。")
            continue

        dependencies = [dep for dep in requires + build_requires if dep.startswith('ros-jazzy-ament-') or dep.startswith('ament-') or dep.startswith('ros-')]

        readme_content = generate_readme(name, version, dependencies)

        repo_name = sanitize_repo_name(name)
        repo_dir = os.path.join(OUTPUT_DIR, repo_name)
        os.makedirs(repo_dir, exist_ok=True)

        shutil.copy(tarball_path, repo_dir)
        shutil.copy(spec_path, repo_dir)

        readme_path = os.path.join(repo_dir, 'README.md')
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)

        os.chdir(repo_dir)
        if not os.path.isdir(os.path.join(repo_dir, '.git')):
            subprocess.run(['git', 'init'], check=True)

        subprocess.run(['git', 'add', '.'], check=True)
        commit_status = subprocess.run(['git', 'diff', '--cached', '--quiet'], check=False)
        if commit_status.returncode != 0:
            subprocess.run(['git', 'commit', '-m', 'Initial commit with source tarball, spec file, and README.'], check=True)
        else:
            logging.info(f"包 {repo_name} 已经提交过，跳过提交步骤。")

        remote_info = create_gitee_repo(repo_name)
        if not remote_info[0]:
            logging.warning(f"跳过推送 {repo_name} 到 Gitee。")
            continue

        ssh_url, html_url = remote_info

        subprocess.run(['git', 'remote', 'add', 'origin', ssh_url], check=True)
        subprocess.run(['git', 'branch', '-M', 'main'], check=True)
        push_status = subprocess.run(['git', 'push', '-u', 'origin', 'main'], check=False)
        if push_status.returncode != 0:
            logging.error(f"推送 {repo_name} 到 Gitee 失败。")
        else:
            logging.info(f"已成功推送 {repo_name} 到 Gitee。")
            uploaded_repos.append(html_url)

    if uploaded_repos:
        logging.info("\n以下是所有成功上传到 Gitee 的仓库链接：")
        for repo_link in uploaded_repos:
            logging.info(repo_link)
    else:
        logging.info("\n没有仓库被成功上传到 Gitee。")

    logging.info("\n所有包的处理完成。")
