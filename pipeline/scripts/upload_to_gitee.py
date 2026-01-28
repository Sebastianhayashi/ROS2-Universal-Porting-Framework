#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将本地 repos/<pkg_name> 推送到 Gitee 并生成 eulermaker_links.txt （支持多线程并行）

约定：
  - 远端 Gitee 仓库名 = 本地目录名 = pkg_name
    例如：repos/ament_package -> Gitee 仓库名 ament_package

行为：
  - 对 pkg_list.txt 中的每个包（多线程并行处理）：
      * 如果 repos/<pkg_name> 不是 git 仓库，则：
            git init -b <branch>
            git add .
            git commit -m "Initial import: <pkg_name>"
      * 调用 Gitee API 创建私有仓库（name = pkg_name）
      * 配置 local remote origin -> https://<user>:<token>@gitee.com/<user>/<pkg_name>.git
      * git push -u origin <branch>
      * 调用 Gitee API 将仓库改为公开（private=false）
  - 根据成功 push + 设为 public 的仓库，生成 eulermaker_links.txt：

      # 软件包（选填）
      package_repos:
        # 软件包名（必填）
        - spec_name: ament_package
          # 软件包仓库url（必填）
          spec_url: https://gitee.com/<user>/ament_package.git
          # 软件包仓库分支（选填， 默认master分支）
          spec_branch: master

认证：
  - 使用环境变量：
      GITEE_USER  : Gitee 用户名（例如 sebastianmo）
      GITEE_TOKEN : Gitee Personal Access Token
"""

import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple, Any


GITEE_API_BASE = "https://gitee.com/api/v5"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload local repos/* packages to Gitee and generate eulermaker_links.txt"
    )
    parser.add_argument(
        "-w",
        "--workspace",
        default=".",
        help="工作区根目录（包含 src/、repos/），默认当前目录。",
    )
    parser.add_argument(
        "-l",
        "--pkg-list",
        default="pkg_list.txt",
        help="colcon list 输出文件（默认 workspace/pkg_list.txt）。",
    )
    parser.add_argument(
        "-d",
        "--ros-distro",
        default="jazzy",
        help="ROS 发行版（目前仅用于日志，仓库名不再使用该字段）。",
    )
    parser.add_argument(
        "-b",
        "--branch",
        default="master",
        help="推送的本地分支名（默认 master）。",
    )
    parser.add_argument(
        "--gitee-user",
        default=None,
        help="Gitee 用户名（默认从环境变量 GITEE_USER 读取）。",
    )
    parser.add_argument(
        "--token-env",
        default="GITEE_TOKEN",
        help="保存 Gitee Token 的环境变量名（默认 GITEE_TOKEN）。",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="并行 worker 线程数（默认 8）。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要执行的操作，不真正调用 API / git push / git init。",
    )
    return parser.parse_args()


def require_env_token(args: argparse.Namespace) -> Tuple[str, str]:
    user = args.gitee_user or os.environ.get("GITEE_USER")
    if not user:
        print(
            "[ERROR] Gitee user not provided. Use --gitee-user or set $GITEE_USER.",
            file=sys.stderr,
        )
        sys.exit(1)

    token = os.environ.get(args.token_env)
    if not token:
        print(
            f"[ERROR] Gitee token not found in env ${args.token_env}.",
            file=sys.stderr,
        )
        sys.exit(1)

    return user, token


def http_post_form(url: str, data: Dict[str, str], timeout: int = 10) -> Tuple[int, str]:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            body = resp.read().decode("utf-8", errors="ignore")
            return status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return e.code, body
    except urllib.error.URLError as e:
        return 0, str(e)


def http_patch_form(url: str, data: Dict[str, str], timeout: int = 10) -> Tuple[int, str]:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded)
    req.get_method = lambda: "PATCH"
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            body = resp.read().decode("utf-8", errors="ignore")
            return status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return e.code, body
    except urllib.error.URLError as e:
        return 0, str(e)


def create_repo_if_needed(
    user: str,
    token: str,
    repo_name: str,
    dry_run: bool = False,
) -> bool:
    """
    调用 Gitee API 创建私有仓库。
    - 如果创建成功或已经存在，返回 True。
    - 其他错误返回 False。
    """
    url = f"{GITEE_API_BASE}/user/repos"
    data = {
        "access_token": token,
        "name": repo_name,
        "private": "true",
    }

    if dry_run:
        print(f"[DRY] Would POST {url} (name={repo_name}, private=true)")
        return True

    status, body = http_post_form(url, data)
    if status in (200, 201):
        print(f"[INFO] Created private repo {user}/{repo_name} on Gitee.")
        return True

    lowered = body.lower()
    if "already" in lowered or "exist" in lowered or "has been taken" in lowered:
        print(f"[WARN] Repo {user}/{repo_name} seems to already exist, reuse it.")
        return True

    print(
        f"[ERROR] Failed to create repo {user}/{repo_name} on Gitee "
        f"(status={status}): {body}",
        file=sys.stderr,
    )
    return False


def set_repo_public(
    user: str,
    token: str,
    repo_name: str,
    dry_run: bool = False,
) -> bool:
    """
    调用 Gitee API 将仓库从私有改为公开：
      PATCH /api/v5/repos/{owner}/{repo}
      参数：access_token, name, private=false
    """
    url = f"{GITEE_API_BASE}/repos/{user}/{repo_name}"
    data = {
        "access_token": token,
        "name": repo_name,
        "private": "false",
    }

    if dry_run:
        print(f"[DRY] Would PATCH {url} (private=false)")
        return True

    status, body = http_patch_form(url, data)
    if status in (200, 201):
        print(f"[INFO] Set repo {user}/{repo_name} to public.")
        return True

    print(
        f"[ERROR] Failed to set repo {user}/{repo_name} public "
        f"(status={status}): {body}",
        file=sys.stderr,
    )
    return False


def run_git(
    args: List[str],
    cwd: Optional[str] = None,
    dry_run: bool = False,
    capture_output: bool = False,
) -> Tuple[int, str, str]:
    """
    在子进程中运行 git 命令。
    """
    cmd_str = " ".join(args)
    if dry_run:
        print(f"[DRY] (cd {cwd or os.getcwd()}; {cmd_str})")
        return 0, "", ""

    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
            check=False,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        if result.returncode != 0 and not capture_output:
            print(
                f"[ERROR] Command failed (rc={result.returncode}): {cmd_str}",
                file=sys.stderr,
            )
        return result.returncode, stdout, stderr
    except FileNotFoundError:
        print("[ERROR] git not found in PATH.", file=sys.stderr)
        return 127, "", "git not found"


def init_git_repo(
    repo_dir: str,
    pkg_name: str,
    branch: str,
    dry_run: bool = False,
) -> bool:
    """
    如果 repo_dir 还不是 git 仓库，执行：
      git init -b <branch>   （失败则退回 git init; git checkout -b <branch>）
      git add .
      git commit -m "Initial import: <pkg_name>"
    """
    print(f"[INFO] Initializing git repo in {repo_dir} (branch={branch})")

    rc, _, stderr = run_git(
        ["git", "init", "-b", branch],
        cwd=repo_dir,
        dry_run=dry_run,
        capture_output=True,
    )
    if rc != 0 and not dry_run:
        print(
            f"[WARN] git init -b {branch} failed, fallback to "
            f"'git init' + 'git checkout -b {branch}'.",
            file=sys.stderr,
        )
        rc2, _, stderr2 = run_git(
            ["git", "init"],
            cwd=repo_dir,
            dry_run=dry_run,
            capture_output=True,
        )
        if rc2 != 0:
            print(
                f"[ERROR] git init failed in {repo_dir}, rc={rc2}:\n{stderr2}",
                file=sys.stderr,
            )
            return False
        rc3, _, stderr3 = run_git(
            ["git", "checkout", "-b", branch],
            cwd=repo_dir,
            dry_run=dry_run,
            capture_output=True,
        )
        if rc3 != 0:
            print(
                f"[ERROR] git checkout -b {branch} failed in {repo_dir}, rc={rc3}:\n{stderr3}",
                file=sys.stderr,
            )
            return False

    rc, _, stderr = run_git(
        ["git", "add", "."],
        cwd=repo_dir,
        dry_run=dry_run,
        capture_output=True,
    )
    if rc != 0:
        print(
            f"[ERROR] git add . failed in {repo_dir}, rc={rc}:\n{stderr}",
            file=sys.stderr,
        )
        return False

    msg = f"Initial import: {pkg_name}"
    rc, _, stderr = run_git(
        ["git", "commit", "-m", msg],
        cwd=repo_dir,
        dry_run=dry_run,
        capture_output=True,
    )
    if rc != 0:
        print(
            f"[ERROR] git commit failed in {repo_dir}, rc={rc}:\n{stderr}",
            file=sys.stderr,
        )
        return False

    return True


def ensure_remote_and_push(
    repo_dir: str,
    user: str,
    token: str,
    repo_name: str,
    branch: str,
    dry_run: bool = False,
) -> bool:
    """
    在 repo_dir 下：
      - 设置 origin 为 https://user:token@gitee.com/user/repo_name.git
      - git push -u origin <branch>
    """
    auth_url = f"https://{user}:{token}@gitee.com/{user}/{repo_name}.git"
    display_url = f"https://gitee.com/{user}/{repo_name}.git"

    rc, _, _ = run_git(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_dir,
        dry_run=dry_run,
        capture_output=True,
    )
    if rc == 0:
        print(f"[INFO] Update remote origin for {repo_dir} -> {display_url}")
        run_git(
            ["git", "remote", "set-url", "origin", auth_url],
            cwd=repo_dir,
            dry_run=dry_run,
        )
    else:
        print(f"[INFO] Add remote origin for {repo_dir} -> {display_url}")
        run_git(
            ["git", "remote", "add", "origin", auth_url],
            cwd=repo_dir,
            dry_run=dry_run,
        )

    print(f"[INFO] Pushing {repo_dir} -> {display_url} (branch={branch})")
    rc, _, stderr = run_git(
        ["git", "push", "-u", "origin", branch],
        cwd=repo_dir,
        dry_run=dry_run,
        capture_output=True,
    )
    if rc != 0:
        print(
            f"[ERROR] git push failed for {repo_dir} (branch={branch}), rc={rc}:\n{stderr}",
            file=sys.stderr,
        )
        return False

    return True


def load_pkg_list(pkg_list_path: str) -> List[Tuple[str, str]]:
    """
    解析 pkg_list.txt 中的行：
        <pkg_name> <pkg_path>
    """
    result: List[Tuple[str, str]] = []
    with open(pkg_list_path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                print(
                    f"[WARN] Invalid line {lineno} in {pkg_list_path}: {line}",
                    file=sys.stderr,
                )
                continue
            pkg_name, pkg_path = parts[0], parts[1]
            result.append((pkg_name, pkg_path))
    return result


def process_one_package(
    pkg_name: str,
    repos_root: str,
    branch: str,
    gitee_user: str,
    gitee_token: str,
    dry_run: bool,
) -> Tuple[bool, Optional[Dict[str, str]]]:
    """
    单个包的完整处理流程（在工作线程中调用）。
    返回：
      (ok, link_entry 或 None)
    """
    local_dir = os.path.join(repos_root, pkg_name)
    if not os.path.isdir(local_dir):
        print(f"[WARN] repos/{pkg_name} not found, skip.")
        return False, None

    git_dir = os.path.join(local_dir, ".git")
    if not os.path.isdir(git_dir):
        ok_init = init_git_repo(
            repo_dir=local_dir,
            pkg_name=pkg_name,
            branch=branch,
            dry_run=dry_run,
        )
        if not ok_init:
            return False, None

    repo_name = pkg_name  # 远端仓库名 = 本地目录名

    print(f"[INFO] === Package: {pkg_name} -> Gitee repo: {repo_name} ===")

    ok = create_repo_if_needed(
        user=gitee_user,
        token=gitee_token,
        repo_name=repo_name,
        dry_run=dry_run,
    )
    if not ok:
        return False, None

    ok = ensure_remote_and_push(
        repo_dir=local_dir,
        user=gitee_user,
        token=gitee_token,
        repo_name=repo_name,
        branch=branch,
        dry_run=dry_run,
    )
    if not ok:
        return False, None

    ok = set_repo_public(
        user=gitee_user,
        token=gitee_token,
        repo_name=repo_name,
        dry_run=dry_run,
    )
    if not ok:
        return False, None

    spec_name = repo_name
    spec_url = f"https://gitee.com/{gitee_user}/{repo_name}.git"
    spec_branch = branch

    link_entry = {
        "spec_name": spec_name,
        "spec_url": spec_url,
        "spec_branch": spec_branch,
    }

    return True, link_entry


def main() -> None:
    args = parse_args()
    workspace = os.path.abspath(args.workspace)

    pkg_list_path = args.pkg_list
    if not os.path.isabs(pkg_list_path):
        pkg_list_path = os.path.join(workspace, pkg_list_path)
    pkg_list_path = os.path.abspath(pkg_list_path)

    if not os.path.exists(pkg_list_path):
        print(f"[ERROR] pkg_list not found: {pkg_list_path}", file=sys.stderr)
        sys.exit(1)

    repos_root = os.path.join(workspace, "repos")
    if not os.path.isdir(repos_root):
        print(f"[ERROR] repos directory not found: {repos_root}", file=sys.stderr)
        sys.exit(1)

    gitee_user, gitee_token = require_env_token(args)

    print(f"[INFO] Workspace : {workspace}")
    print(f"[INFO] Pkg list  : {pkg_list_path}")
    print(f"[INFO] Repos dir : {repos_root}")
    print(f"[INFO] ROS distro: {args.ros_distro}")
    print(f"[INFO] Gitee user: {gitee_user}")
    print(f"[INFO] Branch    : {args.branch}")
    print(f"[INFO] Workers   : {args.workers}")
    print(f"[INFO] Dry run   : {args.dry_run}")
    print()

    pkgs = load_pkg_list(pkg_list_path)
    total = len(pkgs)
    if total == 0:
        print("[INFO] pkg_list is empty, nothing to do.")
        return

    success = 0
    failed = 0
    link_entries: List[Dict[str, str]] = []

    # 并行处理每个包
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_pkg = {
            executor.submit(
                process_one_package,
                pkg_name,
                repos_root,
                args.branch,
                gitee_user,
                gitee_token,
                args.dry_run,
            ): pkg_name
            for pkg_name, _pkg_path in pkgs
        }

        for future in as_completed(future_to_pkg):
            pkg = future_to_pkg[future]
            try:
                ok, entry = future.result()
            except Exception as e:
                print(f"[ERROR] Package {pkg} raised exception: {e}", file=sys.stderr)
                failed += 1
                continue

            if ok and entry is not None:
                success += 1
                link_entries.append(entry)
            else:
                failed += 1

    # 生成 eulermaker_links.txt（只包含成功处理的仓库）
    links_path = os.path.join(workspace, "eulermaker_links.txt")
    try:
        with open(links_path, "w", encoding="utf-8") as f:
            f.write("# 软件包（选填）\n")
            f.write("package_repos:\n")
            if link_entries:
                f.write("  # 软件包名（必填）\n")
            for entry in link_entries:
                f.write(f"  - spec_name: {entry['spec_name']}\n")
                f.write("    # 软件包仓库url（必填）\n")
                f.write(f"    spec_url: {entry['spec_url']}\n")
                f.write("    # 软件包仓库分支（选填， 默认master分支）\n")
                f.write(f"    spec_branch: {entry['spec_branch']}\n")
        print(f"[INFO] eulermaker_links.txt generated at {links_path}")
    except OSError as e:
        print(f"[ERROR] Failed to write eulermaker_links.txt: {e}", file=sys.stderr)

    print("\n[SUMMARY] upload_to_gitee.py")
    print(f"[SUMMARY] Total packages considered : {total}")
    print(f"[SUMMARY] Success (created+push+public): {success}")
    print(f"[SUMMARY] Failed/partial              : {failed}")


if __name__ == "__main__":
    main()

