#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量删除当前 Gitee 用户拥有的所有仓库（危险操作！）

行为说明：
  1. 通过 Gitee Open API /user/repos 分页拉取所有仓库
  2. 仅保留当前用户自己拥有的仓库（repo["owner"]["login"] == GITEE_USER）
  3. 打印仓库数量和名称，询问一次是否全部删除
  4. 确认后，使用多线程并行调用 DELETE /repos/{owner}/{repo} 删除所有这些仓库
  5. 输出删除成功 / 失败的汇总

认证：
  - 使用环境变量：
      GITEE_USER  : Gitee 用户名（例如 sebastianmo）
      GITEE_TOKEN : Gitee Personal Access Token

注意：
  - 这是不可逆操作！请确保该账号是你专门用来做实验的账号。
"""

import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Any


GITEE_API_BASE = "https://gitee.com/api/v5"
HTTP_TIMEOUT = 60  # 秒，适当放宽，避免大号/网络稍慢时超时


def require_user_and_token(token_env: str = "GITEE_TOKEN") -> Tuple[str, str]:
    user = os.environ.get("GITEE_USER")
    if not user:
        print("[ERROR] 请先设置环境变量 GITEE_USER 为你的 Gitee 用户名。", file=sys.stderr)
        sys.exit(1)

    token = os.environ.get(token_env)
    if not token:
        print(f"[ERROR] 请先设置环境变量 {token_env} 为你的 Gitee Access Token。", file=sys.stderr)
        sys.exit(1)

    return user, token


def http_get(url: str, timeout: int = HTTP_TIMEOUT) -> Tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return e.code, body
    except TimeoutError as e:
        # 显式捕获网络超时，避免抛到外层导致 traceback
        return 0, f"timeout: {e}"
    except urllib.error.URLError as e:
        return 0, str(e)


def http_delete(url: str, timeout: int = HTTP_TIMEOUT) -> Tuple[int, str]:
    req = urllib.request.Request(url)
    req.get_method = lambda: "DELETE"
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return e.code, body
    except TimeoutError as e:
        return 0, f"timeout: {e}"
    except urllib.error.URLError as e:
        return 0, str(e)


def list_all_owned_repos(user: str, token: str, per_page: int = 100) -> List[Dict[str, Any]]:
    """
    拉取 /user/repos 的所有页，然后过滤出 owner.login == user 的仓库。
    """
    page = 1
    owned: List[Dict[str, Any]] = []

    while True:
        url = (
            f"{GITEE_API_BASE}/user/repos"
            f"?access_token={urllib.parse.quote(token)}"
            f"&page={page}&per_page={per_page}"
        )
        status, body = http_get(url)
        if status != 200:
            print(
                f"[ERROR] 获取仓库列表失败（status={status}）：{body}",
                file=sys.stderr,
            )
            # status=0 一般是超时或网络错误，直接跳出，避免死循环
            break

        try:
            items = json.loads(body)
        except json.JSONDecodeError as e:
            print(f"[ERROR] 解析仓库列表 JSON 失败：{e}", file=sys.stderr)
            break

        if not items:
            break

        for repo in items:
            owner = repo.get("owner") or {}
            login = owner.get("login")
            if login == user:
                owned.append(repo)

        page += 1

    return owned


def delete_repo(owner: str, name: str, token: str) -> Tuple[str, bool, str]:
    """
    删除单个仓库：DELETE /repos/{owner}/{name}?access_token=...
    返回：(full_name, success, message)
    """
    full_name = f"{owner}/{name}"
    url = (
        f"{GITEE_API_BASE}/repos/{owner}/{name}"
        f"?access_token={urllib.parse.quote(token)}"
    )
    status, body = http_delete(url)
    if status in (200, 202, 204):
        return full_name, True, "deleted"

    return full_name, False, f"status={status}, body={body}"


def main() -> None:
    user, token = require_user_and_token(token_env="GITEE_TOKEN")

    print(f"[INFO] 当前 Gitee 用户: {user}")
    print("[INFO] 正在拉取该用户的所有仓库列表（仅保留自己拥有的仓库）...\n")

    repos = list_all_owned_repos(user, token)
    if not repos:
        print("[INFO] 未找到任何你自己拥有的仓库（或获取失败），无需删除。")
        return

    print(f"[INFO] 共发现 {len(repos)} 个你拥有的仓库：\n")
    for repo in repos:
        name = repo.get("name", "<unknown>")
        full_name = repo.get("full_name") or f"{user}/{name}"
        private = repo.get("private", False)
        vis = "private" if private else "public"
        print(f"  - {full_name}  ({vis})")

    print("\n[WARNING] 上述仓库将被【全部删除】，该操作不可恢复！")
    answer = input("确认删除请输入 YES（大写），其他任意输入取消：").strip()
    if answer != "YES":
        print("[INFO] 输入非 YES，已取消删除操作。")
        return

    print("\n[INFO] 开始并行删除仓库...\n")

    max_workers = 16  # 并行线程数，可根据需要调整
    successes: List[str] = []
    failures: List[Tuple[str, str]] = []
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_repo = {
            executor.submit(delete_repo, user, repo["name"], token): repo
            for repo in repos
        }

        for future in as_completed(future_to_repo):
            repo = future_to_repo[future]
            name = repo.get("name", "<unknown>")
            try:
                full_name, ok, msg = future.result()
            except Exception as e:
                with lock:
                    failures.append((name, f"exception: {e}"))
                print(f"[ERROR] 删除 {name} 时发生异常: {e}", file=sys.stderr)
                continue

            if ok:
                with lock:
                    successes.append(full_name)
                print(f"[OK]   已删除仓库: {full_name}")
            else:
                with lock:
                    failures.append((full_name, msg))
                print(f"[FAIL] 删除仓库失败: {full_name} -> {msg}", file=sys.stderr)

    print("\n[SUMMARY] delete_all_gitee_repos.py")
    print(f"[SUMMARY] 目标仓库总数 : {len(repos)}")
    print(f"[SUMMARY] 删除成功     : {len(successes)}")
    print(f"[SUMMARY] 删除失败     : {len(failures)}")

    if failures:
        print("\n[SUMMARY] 删除失败的仓库：")
        for full_name, msg in failures:
            print(f"  - {full_name}: {msg}")


if __name__ == "__main__":
    main()

