#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键执行 ROS RPM 流水线：

1. （可选）删除当前用户在 Gitee 上的所有仓库（调用 delete_all_gitee_repos.py）
2. （默认）清理本地 workspace/repos 目录
3. 调用 gen_template_specs.py 生成 repos/<pkg>/template.spec
4. 调用 gen_tarballs.py 生成 repos/<pkg>/ros-<distro>-<pkg>_<ver>.orig.tar.gz
5. 调用 fix_specs.py 生成最终 spec，并删除 template.spec
6. 询问是否上传到 Gitee；如同意，则调用 upload_to_gitee.py 逐仓库 push，并生成 eulermaker_links.txt

依赖脚本（位于同一 scripts 目录）：
  - delete_all_gitee_repos.py
  - gen_template_specs.py
  - gen_tarballs.py
  - fix_specs.py
  - upload_to_gitee.py
"""

import argparse
import os
import shutil
import subprocess
import sys
from typing import Optional, List


def run_step(
    desc: str,
    cmd: List[str],
    cwd: Optional[str] = None,
    input_text: Optional[str] = None,
    allow_failure: bool = False,
) -> int:
    """封装 subprocess.run，统一打印命令和错误处理。"""
    print(f"\n[STEP] {desc}")
    print("       CMD:", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=False,
            text=True,
            input=input_text,
        )
    except FileNotFoundError as e:
        print(f"[ERROR] Command not found: {cmd[0]} ({e})", file=sys.stderr)
        if allow_failure:
            return 127
        sys.exit(127)

    if result.returncode != 0:
        print(
            f"[ERROR] Step failed: {desc}, exit code {result.returncode}",
            file=sys.stderr,
        )
        if not allow_failure:
            sys.exit(result.returncode)

    return result.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-key pipeline: clean Gitee, regenerate repos/tarballs/specs, and optionally upload."
    )
    parser.add_argument(
        "-w",
        "--workspace",
        default=".",
        help="工作区根目录（包含 src/、repos/、scripts/），默认当前目录。",
    )
    parser.add_argument(
        "-l",
        "--pkg-list",
        default="pkg_list.txt",
        help="colcon list 输出文件路径（相对 workspace），默认 pkg_list.txt。",
    )
    parser.add_argument(
        "--ros-distro",
        default="jazzy",
        help="ROS 发行版名（用于命名和 fix_specs），默认 jazzy。",
    )
    parser.add_argument(
        "--os-name",
        default="rhel",
        help="传给 bloom 的 --os-name，默认 rhel。",
    )
    parser.add_argument(
        "--os-version",
        default="9",
        help="传给 bloom 的 --os-version，默认 9。",
    )
    parser.add_argument(
        "--branch",
        default="master",
        help="上传到 Gitee 时使用的分支名，默认 master。",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="并行 worker 数，用于 gen_template_specs.py 和 upload_to_gitee.py，默认 8。",
    )
    parser.add_argument(
        "--skip-delete-remote",
        action="store_true",
        help="跳过删除 Gitee 上所有仓库（默认会删除）。",
    )
    parser.add_argument(
        "--no-clean-repos",
        action="store_true",
        help="不清理本地 repos/ 目录（默认会 rm -rf 再重建）。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    workspace = os.path.abspath(args.workspace)
    scripts_dir = os.path.dirname(os.path.abspath(__file__))

    pkg_list_path = args.pkg_list
    if not os.path.isabs(pkg_list_path):
        pkg_list_path = os.path.join(workspace, pkg_list_path)
    pkg_list_path = os.path.abspath(pkg_list_path)

    repos_dir = os.path.join(workspace, "repos")

    print("[INFO] ===== ROS RPM Pipeline Config =====")
    print(f"[INFO] Workspace      : {workspace}")
    print(f"[INFO] Scripts dir    : {scripts_dir}")
    print(f"[INFO] Pkg list       : {pkg_list_path}")
    print(f"[INFO] ROS distro     : {args.ros_distro}")
    print(f"[INFO] OS name        : {args.os_name}")
    print(f"[INFO] OS version     : {args.os_version}")
    print(f"[INFO] Gitee branch   : {args.branch}")
    print(f"[INFO] Workers        : {args.workers}")
    print(f"[INFO] Skip remote del: {args.skip_delete_remote}")
    print(f"[INFO] Clean repos    : {not args.no_clean_repos}")
    print("=========================================\n")

    if not os.path.exists(pkg_list_path):
        print(f"[ERROR] pkg_list not found: {pkg_list_path}", file=sys.stderr)
        sys.exit(1)

    # -----------------------------------------
    # Step 1: 删除 Gitee 上的所有仓库（可选）
    # -----------------------------------------
    if not args.skip_delete_remote:
        gitee_user = os.environ.get("GITEE_USER")
        gitee_token = os.environ.get("GITEE_TOKEN")
        if not gitee_user or not gitee_token:
            print(
                "[WARN] GITEE_USER 或 GITEE_TOKEN 未设置，无法删除远端仓库，跳过此步骤。",
                file=sys.stderr,
            )
        else:
            delete_script = os.path.join(scripts_dir, "delete_all_gitee_repos.py")
            if not os.path.exists(delete_script):
                print(
                    f"[WARN] delete_all_gitee_repos.py 不存在（{delete_script}），跳过远端删除。",
                    file=sys.stderr,
                )
            else:
                # 旧脚本内部有一次确认，这里直接喂一个 "yes\n" 实现自动确认
                run_step(
                    "Delete all Gitee repos",
                    [sys.executable, delete_script],
                    cwd=workspace,
                    input_text="yes\n",
                    allow_failure=False,
                )
    else:
        print("[INFO] 跳过删除 Gitee 仓库步骤 (--skip-delete-remote 已指定)。")

    # -----------------------------------------
    # Step 2: 清理 / 重建本地 repos/
    # -----------------------------------------
    if not args.no_clean_repos:
        print(f"\n[STEP] Clean local repos directory: {repos_dir}")
        if os.path.isdir(repos_dir):
            print(f"[INFO] Removing existing {repos_dir}")
            shutil.rmtree(repos_dir)
        os.makedirs(repos_dir, exist_ok=True)
        print(f"[INFO] Created empty {repos_dir}")
    else:
        print(f"[INFO] 不清理 repos/，保留现有内容：{repos_dir}")

    # -----------------------------------------
    # Step 3: 生成 template.spec（并行 bloom）
    # -----------------------------------------
    gen_template_script = os.path.join(scripts_dir, "gen_template_specs.py")
    if not os.path.exists(gen_template_script):
        print(f"[ERROR] gen_template_specs.py 不存在：{gen_template_script}", file=sys.stderr)
        sys.exit(1)

    run_step(
        "Generate template.spec via bloom",
        [
            sys.executable,
            gen_template_script,
            "--workspace",
            workspace,
            "--pkg-list",
            pkg_list_path,
            "--ros-distro",
            args.ros_distro,
            "--os-name",
            args.os_name,
            "--os-version",
            args.os_version,
            "--workers",
            str(args.workers),
        ],
        cwd=workspace,
    )

    # -----------------------------------------
    # Step 4: 生成 tarballs
    # -----------------------------------------
    gen_tarballs_script = os.path.join(scripts_dir, "gen_tarballs.py")
    if not os.path.exists(gen_tarballs_script):
        print(f"[ERROR] gen_tarballs.py 不存在：{gen_tarballs_script}", file=sys.stderr)
        sys.exit(1)

    run_step(
        "Generate source tarballs",
        [
            sys.executable,
            gen_tarballs_script,
            "--workspace",
            workspace,
            "--pkg-list",
            pkg_list_path,
            "--ros-distro",
            args.ros_distro,
        ],
        cwd=workspace,
    )

    # -----------------------------------------
    # Step 5: 修 spec（fix_specs.py）
    # -----------------------------------------
    fix_specs_script = os.path.join(scripts_dir, "fix_specs.py")
    if not os.path.exists(fix_specs_script):
        print(f"[ERROR] fix_specs.py 不存在：{fix_specs_script}", file=sys.stderr)
        sys.exit(1)

    run_step(
        "Fix specs (Name/Source0/prefix/PYTHONPATH/files/debug_package)",
        [
            sys.executable,
            fix_specs_script,
            "--workspace",
            workspace,
            "--pkg-list",
            pkg_list_path,
            "--ros-distro",
            args.ros_distro,
        ],
        cwd=workspace,
    )

    # -----------------------------------------
    # Step 6: 询问是否上传到 Gitee
    # -----------------------------------------
    print("\n[INFO] 本地 repos/ 目录已经重新生成：")
    print("       - tarball: repos/<pkg>/ros-<distro>-<pkg>_<ver>.orig.tar.gz")
    print("       - spec   : repos/<pkg>/<pkg-with-hyphen>.spec\n")

    answer = input("是否将所有 repos/<pkg> 上传到 Gitee？[y/N]: ").strip().lower()
    if answer not in ("y", "yes"):
        print("[INFO] 用户选择不上传到 Gitee，本次流水线到此结束。")
        sys.exit(0)

    gitee_user = os.environ.get("GITEE_USER")
    gitee_token = os.environ.get("GITEE_TOKEN")
    if not gitee_user or not gitee_token:
        print(
            "[ERROR] GITEE_USER 或 GITEE_TOKEN 未设置，无法上传到 Gitee。",
            file=sys.stderr,
        )
        sys.exit(1)

    upload_script = os.path.join(scripts_dir, "upload_to_gitee.py")
    if not os.path.exists(upload_script):
        print(f"[ERROR] upload_to_gitee.py 不存在：{upload_script}", file=sys.stderr)
        sys.exit(1)

    run_step(
        "Upload repos to Gitee and generate eulermaker_links.txt",
        [
            sys.executable,
            upload_script,
            "--workspace",
            workspace,
            "--pkg-list",
            pkg_list_path,
            "--ros-distro",
            args.ros_distro,
            "--branch",
            args.branch,
            "--workers",
            str(args.workers),
        ],
        cwd=workspace,
    )

    print("\n[INFO] 全部步骤完成。")


if __name__ == "__main__":
    main()

