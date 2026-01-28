#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段 2：批量生成 ROS Jazzy 源码 orig tarball

增强点：
  - tarball 文件名：   ros-<ros_distro>-<name-hyphen>_<version>.orig.tar.gz
  - 解压顶层目录名：   ros-<ros_distro>-<name-hyphen>-<version>/
    -> 与 spec 里的 %{name}-%{version} 完全对齐，%autosetup 可以直接用
  - 如果 git archive 失败，自动 fallback 到 tarfile 打包（排除 .git）
  - 增加统计与汇总
"""

import argparse
import gzip
import os
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
from typing import Optional, List


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate ROS orig tarballs using git archive (with fallback) based on colcon list."
    )
    parser.add_argument(
        "-w",
        "--workspace",
        default=".",
        help="Workspace 根目录（包含 src/、repos/ 等），默认当前目录。",
    )
    parser.add_argument(
        "-l",
        "--pkg-list",
        default="pkg_list.txt",
        help="colcon list 的输出文件路径，默认为 workspace/pkg_list.txt。",
    )
    parser.add_argument(
        "-d",
        "--ros-distro",
        default="jazzy",
        help="ROS 发行版前缀（例如 jazzy，生成 ros-jazzy-*），默认 jazzy。",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="如果目标 tarball 已经存在，是否强制覆盖（默认不覆盖）。",
    )
    return parser.parse_args()


def find_git_root(start_path: str) -> Optional[str]:
    """从包目录开始向上查找，直到找到包含 .git 的目录为止。"""
    cur = os.path.abspath(start_path)
    while True:
        git_dir = os.path.join(cur, ".git")
        if os.path.isdir(git_dir):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def read_version_from_package_xml(pkg_root: str) -> Optional[str]:
    """从 package.xml 中读取 <version> 字段。"""
    pkg_xml = os.path.join(pkg_root, "package.xml")
    if not os.path.exists(pkg_xml):
        print(f"[WARN] package.xml not found in {pkg_root}, skip.", file=sys.stderr)
        return None

    try:
        tree = ET.parse(pkg_xml)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"[WARN] Failed to parse {pkg_xml}: {e}", file=sys.stderr)
        return None

    version_text = None
    for elem in root.iter():
        if elem.tag.endswith("version") and elem.text:
            version_text = elem.text.strip()
            if version_text:
                break

    if not version_text:
        print(f"[WARN] No <version> tag found in {pkg_xml}, skip.", file=sys.stderr)
        return None

    return version_text


def run_git_archive(
    repo_root: str,
    subdir: str,
    prefix_dir: str,
    dest_tar_gz: str,
) -> bool:
    """
    使用 git archive 打包 repo_root/subdir 为 tar.gz，并写入 dest_tar_gz。

    - prefix 使用 prefix_dir/，即解压后顶层目录为 <prefix_dir>/
    """
    cmd = [
        "git",
        "-C",
        repo_root,
        "archive",
        "--format=tar",
        f"--prefix={prefix_dir}/",
        f"HEAD:{subdir}",
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:
        print("[ERROR] git not found in PATH, please install git.", file=sys.stderr)
        return False

    if result.returncode != 0:
        print(
            f"[ERROR] git archive failed in {repo_root} for path {subdir}:\n"
            f"{result.stderr.decode(errors='ignore')}",
            file=sys.stderr,
        )
        return False

    os.makedirs(os.path.dirname(dest_tar_gz), exist_ok=True)
    try:
        with gzip.open(dest_tar_gz, "wb") as gz_out:
            gz_out.write(result.stdout)
    except OSError as e:
        print(f"[ERROR] Failed to write tar.gz to {dest_tar_gz}: {e}", file=sys.stderr)
        return False

    return True


def tar_filter_exclude_git(tarinfo: tarfile.TarInfo) -> Optional[tarfile.TarInfo]:
    """tarfile filter：排除 .git 目录及其内容。"""
    name = tarinfo.name
    parts = name.split("/")
    if ".git" in parts:
        return None
    return tarinfo


def run_fallback_tar_archive(
    repo_root: str,
    subdir: str,
    prefix_dir: str,
    dest_tar_gz: str,
) -> bool:
    """
    Fallback：使用 tarfile 打包工作区 repo_root/subdir，排除 .git。

    - tar 根目录为 <prefix_dir>/，与 git archive 一致
    """
    src_path = os.path.join(repo_root, subdir)
    src_path = os.path.abspath(src_path)

    if not os.path.isdir(src_path):
        print(f"[ERROR] Fallback tar: source path is not a dir: {src_path}", file=sys.stderr)
        return False

    os.makedirs(os.path.dirname(dest_tar_gz), exist_ok=True)

    try:
        with tarfile.open(dest_tar_gz, "w:gz") as tf:
            tf.add(src_path, arcname=prefix_dir, filter=tar_filter_exclude_git)
    except OSError as e:
        print(f"[ERROR] Fallback tar failed for {src_path}: {e}", file=sys.stderr)
        return False

    return True


def process_package(
    workspace: str,
    ros_distro: str,
    pkg_name: str,
    pkg_path: str,
    repos_dir: str,
    force: bool = False,
) -> str:
    """
    处理单个包：
      - 读取 version
      - 查找 git root + subdir
      - 优先用 git archive，失败则 fallback 用 tarfile
      - 在 repos/<pkg_name>/ 下生成
            ros-<ros_distro>-<name-hyphen>_<version>.orig.tar.gz

      解压后顶层目录：
            ros-<ros_distro>-<name-hyphen>-<version>/

    返回状态：
      'git-ok'       - git archive 成功
      'fallback-ok'  - git 失败但 fallback 成功
      'skipped-exist'- 目标已存在且未覆盖
      'no-version'   - 没找到 package.xml 或 version
      'no-git'       - 没有 .git 仓库（目前只作为统计）
      'failed'       - 两种方式都失败
    """
    # 计算包的绝对路径
    if os.path.isabs(pkg_path):
        pkg_root = pkg_path
    else:
        pkg_root = os.path.join(workspace, pkg_path)
    pkg_root = os.path.abspath(pkg_root)

    if not os.path.isdir(pkg_root):
        print(f"[WARN] Package path not a directory: {pkg_root}, skip.", file=sys.stderr)
        return "failed"

    # 读取 package.xml 中的 version
    version = read_version_from_package_xml(pkg_root)
    if not version:
        return "no-version"

    # name_hyphen: 将包名中的 '_' 转成 '-'
    name_hyphen = pkg_name.replace("_", "-")
    ros_pkg_name = f"ros-{ros_distro}-{name_hyphen}"

    # tarball 文件名保持不变
    tarball_name = f"{ros_pkg_name}_{version}.orig.tar.gz"

    # 解压后的顶层目录名（与 %{name}-%{version} 对齐）
    prefix_dir = f"{ros_pkg_name}-{version}"

    # 每个包一个子目录：repos/<pkg_name>/
    pkg_repo_dir = os.path.join(repos_dir, pkg_name)
    os.makedirs(pkg_repo_dir, exist_ok=True)
    dest_tar_gz = os.path.join(pkg_repo_dir, tarball_name)

    if os.path.exists(dest_tar_gz) and not force:
        print(f"[SKIP] {pkg_name}: {tarball_name} already exists (use --force to overwrite).")
        return "skipped-exist"

    # 查找 git 仓库根目录
    repo_root = find_git_root(pkg_root)
    if not repo_root:
        print(f"[WARN] No .git found above {pkg_root}, will try fallback tar.", file=sys.stderr)
        # 直接走 fallback
        ok_fb = run_fallback_tar_archive(
            repo_root=pkg_root, subdir=".", prefix_dir=prefix_dir, dest_tar_gz=dest_tar_gz
        )
        if ok_fb:
            print(f"[OK]   Fallback tar created {tarball_name}")
            return "fallback-ok"
        else:
            print(f"[FAIL] Fallback tar failed for {pkg_name}", file=sys.stderr)
            return "failed"

    # 计算包目录在仓库中的相对路径
    subdir = os.path.relpath(pkg_root, repo_root)

    print(
        f"[INFO] Packaging {pkg_name} (version {version})\n"
        f"       repo_root = {repo_root}\n"
        f"       subdir    = {subdir}\n"
        f"       output    = {dest_tar_gz}\n"
        f"       prefix    = {prefix_dir}/"
    )

    # 优先尝试 git archive
    ok_git = run_git_archive(
        repo_root=repo_root,
        subdir=subdir,
        prefix_dir=prefix_dir,
        dest_tar_gz=dest_tar_gz,
    )
    if ok_git:
        print(f"[OK]   Created {tarball_name} via git archive")
        return "git-ok"

    # git 失败，尝试 fallback
    print(f"[INFO] Trying fallback tar for {pkg_name} ...")
    ok_fb = run_fallback_tar_archive(
        repo_root=repo_root,
        subdir=subdir,
        prefix_dir=prefix_dir,
        dest_tar_gz=dest_tar_gz,
    )
    if ok_fb:
        print(f"[OK]   Created {tarball_name} via fallback tar")
        return "fallback-ok"

    print(f"[FAIL] Failed to create tarball for {pkg_name}", file=sys.stderr)
    return "failed"


def main() -> None:
    args = parse_args()

    workspace = os.path.abspath(args.workspace)
    repos_dir = os.path.join(workspace, "repos")
    os.makedirs(repos_dir, exist_ok=True)

    # pkg_list 路径
    pkg_list_path = args.pkg_list
    if not os.path.isabs(pkg_list_path):
        pkg_list_path = os.path.join(workspace, pkg_list_path)
    pkg_list_path = os.path.abspath(pkg_list_path)

    if not os.path.exists(pkg_list_path):
        print(f"[ERROR] pkg_list file not found: {pkg_list_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Workspace : {workspace}")
    print(f"[INFO] Pkg list  : {pkg_list_path}")
    print(f"[INFO] Repos dir : {repos_dir}")
    print(f"[INFO] ROS distro: {args.ros_distro}")
    print()

    total = 0
    git_ok = 0
    fb_ok = 0
    skipped_exist = 0
    no_version = 0
    no_git = 0
    failed = 0

    failed_pkgs: List[str] = []

    with open(pkg_list_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 2:
                print(
                    f"[WARN] Line {line_no} in pkg_list.txt is malformed: {line}",
                    file=sys.stderr,
                )
                continue

            pkg_name = parts[0]
            pkg_path = parts[1]

            total += 1
            status = process_package(
                workspace=workspace,
                ros_distro=args.ros_distro,
                pkg_name=pkg_name,
                pkg_path=pkg_path,
                repos_dir=repos_dir,
                force=args.force,
            )
            print()

            if status == "git-ok":
                git_ok += 1
            elif status == "fallback-ok":
                fb_ok += 1
            elif status == "skipped-exist":
                skipped_exist += 1
            elif status == "no-version":
                no_version += 1
            elif status == "no-git":
                no_git += 1
            elif status == "failed":
                failed += 1
                failed_pkgs.append(pkg_name)

    print("\n[SUMMARY] gen_tarballs.py")
    print(f"[SUMMARY] Total packages processed : {total}")
    print(f"[SUMMARY] git archive OK           : {git_ok}")
    print(f"[SUMMARY] fallback tar OK          : {fb_ok}")
    print(f"[SUMMARY] skipped (tar exists)     : {skipped_exist}")
    print(f"[SUMMARY] no version/package.xml   : {no_version}")
    print(f"[SUMMARY] no .git (fallback tried) : {no_git}")
    print(f"[SUMMARY] failed (no tar created)  : {failed}")

    if failed_pkgs:
        print("\n[SUMMARY] Packages with FAILED tarball creation:")
        for name in failed_pkgs:
            print(f"  - {name}")


if __name__ == "__main__":
    main()

