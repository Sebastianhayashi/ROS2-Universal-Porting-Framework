#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段 3：批量生成 RPM template.spec，并复制到 repos/<pkg_name>/template.spec

新增能力：
  - bloom-generate 超时控制（默认 60s，可通过 --timeout-seconds 调整）
  - 超时/失败/成功等统计汇总
  - 多线程并行处理（通过 --workers 控制并发度）
"""

import argparse
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate RPM template.spec for each ROS package using bloom."
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
        "--ros-distro",
        default="jazzy",
        help="ROS 发行版名，默认 jazzy。",
    )
    # 注意：这里默认用 rhel/9，让 bloom 能正常识别
    parser.add_argument(
        "--os-name",
        default="rhel",
        help="传给 bloom 的 --os-name，默认 rhel（openEuler 会报错）。",
    )
    parser.add_argument(
        "--os-version",
        default="9",
        help="传给 bloom 的 --os-version，默认 9。",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="如果 repos/<pkg_name>/template.spec 已存在，是否覆盖（默认不覆盖）。",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="每个 bloom-generate 调用的超时时间（秒），默认 60。",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="并行 worker 数，默认 8。",
    )
    return parser.parse_args()


def run_bloom_generate_rpm(
    pkg_root: str,
    ros_distro: str,
    os_name: str,
    os_version: str,
    timeout_seconds: int,
) -> str:
    """
    在 pkg_root 目录下执行 bloom-generate rpm，使用 ROS_OS_OVERRIDE=rhel9 伪装系统。

    返回值:
        'ok'      - 命令成功结束（退出码 0）
        'timeout' - 超过 timeout_seconds
        'error'   - 非 0 退出码或命令不存在等错误
    """
    pkg_root = os.path.abspath(pkg_root)
    if not os.path.isdir(pkg_root):
        print(f"[WARN] Package root is not a directory: {pkg_root}, skip bloom.", file=sys.stderr)
        return "error"

    env = os.environ.copy()
    # 伪装为 rhel9，让 bloom 走 RHEL 的逻辑
    env["ROS_OS_OVERRIDE"] = "rhel9"

    cmd = [
        "bloom-generate",
        "rpm",
        "--ros-distro",
        ros_distro,
        "--os-name",
        os_name,
        "--os-version",
        os_version,
    ]

    print(f"[INFO] Running bloom-generate rpm in {pkg_root}")
    print(f"       ROS_OS_OVERRIDE=rhel9")
    print(f"       cmd: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=pkg_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        print("[ERROR] bloom-generate not found in PATH. Is bloom installed?", file=sys.stderr)
        return "error"
    except subprocess.TimeoutExpired:
        print(
            f"[ERROR] bloom-generate timed out after {timeout_seconds}s in {pkg_root}",
            file=sys.stderr,
        )
        return "timeout"

    if result.returncode != 0:
        stderr_text = result.stderr.decode(errors="ignore")
        print(
            f"[ERROR] bloom-generate failed in {pkg_root} (exit {result.returncode}):\n"
            f"{stderr_text}",
            file=sys.stderr,
        )
        return "error"

    return "ok"


def copy_template_spec_to_repos(
    workspace: str,
    pkg_name: str,
    pkg_path: str,
    force: bool = False,
) -> str:
    """
    从 <pkg_root>/rpm/template.spec 拷贝到 repos/<pkg_name>/template.spec

    返回:
        'copied'           - 成功复制
        'skipped-existing' - 目标已存在且未指定 force
        'missing-source'   - 源 template.spec 不存在
    """
    if os.path.isabs(pkg_path):
        pkg_root = pkg_path
    else:
        pkg_root = os.path.join(workspace, pkg_path)
    pkg_root = os.path.abspath(pkg_root)

    rpm_dir = os.path.join(pkg_root, "rpm")
    template_spec_src = os.path.join(rpm_dir, "template.spec")

    if not os.path.exists(template_spec_src):
        print(
            f"[WARN] template.spec not found in {rpm_dir}, skip copy for {pkg_name}.",
            file=sys.stderr,
        )
        return "missing-source"

    repos_pkg_dir = os.path.join(workspace, "repos", pkg_name)
    os.makedirs(repos_pkg_dir, exist_ok=True)
    template_spec_dst = os.path.join(repos_pkg_dir, "template.spec")

    if os.path.exists(template_spec_dst) and not force:
        print(
            f"[SKIP] repos/{pkg_name}/template.spec already exists "
            f"(use --force to overwrite)."
        )
        return "skipped-existing"

    print(f"[INFO] Copy template.spec -> {template_spec_dst}")
    shutil.copyfile(template_spec_src, template_spec_dst)
    return "copied"


def load_pkg_list(pkg_list_path: str) -> List[Tuple[str, str, int]]:
    """
    解析 pkg_list.txt 中的行：
        <pkg_name> <pkg_path>
    返回 (pkg_name, pkg_path, line_no)
    """
    result: List[Tuple[str, str, int]] = []
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
            result.append((pkg_name, pkg_path, line_no))
    return result


def process_one_package(
    workspace: str,
    pkg_name: str,
    pkg_path: str,
    line_no: int,
    ros_distro: str,
    os_name: str,
    os_version: str,
    timeout_seconds: int,
    force: bool,
) -> Tuple[str, str, Optional[str]]:
    """
    单个包的完整处理流程（在 worker 线程中执行）：

    返回:
        (pkg_name, bloom_status, copy_status)
        bloom_status in {'ok','error','timeout'}
        copy_status in {'copied','skipped-existing','missing-source', None}
    """
    print(f"[INFO] === Package #{line_no}: {pkg_name} ({pkg_path}) ===")
    pkg_root = os.path.join(workspace, pkg_path)

    bloom_status = run_bloom_generate_rpm(
        pkg_root=pkg_root,
        ros_distro=ros_distro,
        os_name=os_name,
        os_version=os_version,
        timeout_seconds=timeout_seconds,
    )

    if bloom_status == "timeout":
        print(
            f"[FAIL] bloom-generate timed out for {pkg_name}, skip copy.\n",
            file=sys.stderr,
        )
        return pkg_name, "timeout", None
    elif bloom_status == "error":
        print(
            f"[FAIL] bloom-generate failed for {pkg_name}, skip copy.\n",
            file=sys.stderr,
        )
        return pkg_name, "error", None

    copy_status = copy_template_spec_to_repos(
        workspace=workspace,
        pkg_name=pkg_name,
        pkg_path=pkg_path,
        force=force,
    )

    print()
    return pkg_name, "ok", copy_status


def main() -> None:
    args = parse_args()

    workspace = os.path.abspath(args.workspace)
    pkg_list_path = args.pkg_list
    if not os.path.isabs(pkg_list_path):
        pkg_list_path = os.path.join(workspace, pkg_list_path)
    pkg_list_path = os.path.abspath(pkg_list_path)

    if not os.path.exists(pkg_list_path):
        print(f"[ERROR] pkg_list file not found: {pkg_list_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Workspace      : {workspace}")
    print(f"[INFO] Pkg list       : {pkg_list_path}")
    print(f"[INFO] ROS distro     : {args.ros_distro}")
    print(f"[INFO] OS name        : {args.os_name}")
    print(f"[INFO] OS version     : {args.os_version}")
    print(f"[INFO] Timeout (sec)  : {args.timeout_seconds}")
    print(f"[INFO] Workers        : {args.workers}")
    print()

    pkgs = load_pkg_list(pkg_list_path)

    total = len(pkgs)
    bloom_ok = 0
    bloom_error = 0
    bloom_timeout = 0
    copied = 0
    skipped_existing = 0
    missing_source = 0

    timeout_pkgs = []
    error_pkgs = []

    # 并行执行
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_pkg = {
            executor.submit(
                process_one_package,
                workspace,
                pkg_name,
                pkg_path,
                line_no,
                args.ros_distro,
                args.os_name,
                args.os_version,
                args.timeout_seconds,
                args.force,
            ): pkg_name
            for (pkg_name, pkg_path, line_no) in pkgs
        }

        for future in as_completed(future_to_pkg):
            pkg_name = future_to_pkg[future]
            try:
                name, bloom_status, copy_status = future.result()
            except Exception as e:
                # 理论上不会太多，这里简单记为 error
                print(
                    f"[ERROR] Exception while processing {pkg_name}: {e}",
                    file=sys.stderr,
                )
                bloom_error += 1
                error_pkgs.append(pkg_name)
                continue

            if bloom_status == "ok":
                bloom_ok += 1
            elif bloom_status == "error":
                bloom_error += 1
                error_pkgs.append(pkg_name)
            elif bloom_status == "timeout":
                bloom_timeout += 1
                timeout_pkgs.append(pkg_name)

            if copy_status == "copied":
                copied += 1
            elif copy_status == "skipped-existing":
                skipped_existing += 1
            elif copy_status == "missing-source":
                missing_source += 1

    print("\n[SUMMARY] gen_template_specs.py")
    print(f"[SUMMARY] Total packages processed (from pkg_list): {total}")
    print(f"[SUMMARY] bloom OK                      : {bloom_ok}")
    print(f"[SUMMARY] bloom errors                  : {bloom_error}")
    print(f"[SUMMARY] bloom timeouts                : {bloom_timeout}")
    print(f"[SUMMARY] template.spec copied          : {copied}")
    print(f"[SUMMARY] template.spec skipped (exists): {skipped_existing}")
    print(f"[SUMMARY] template.spec missing source  : {missing_source}")

    if timeout_pkgs:
        print("\n[SUMMARY] Packages with bloom timeout:")
        for name in timeout_pkgs:
            print(f"  - {name}")

    if error_pkgs:
        print("\n[SUMMARY] Packages with bloom errors:")
        for name in error_pkgs:
            print(f"  - {name}")


if __name__ == "__main__":
    main()

