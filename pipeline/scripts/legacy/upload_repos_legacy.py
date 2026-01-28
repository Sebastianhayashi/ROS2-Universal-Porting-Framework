#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, json, shutil, subprocess, getpass, time
from pathlib import Path
from urllib import request, parse, error

ROOT = Path.home() / "ros-rpm"
REPOS_DIR = ROOT / "repos"
YAML_OUT = ROOT / "package_repos.yaml"

def info(msg): print(msg, flush=True)
def warn(msg): print(f"!! {msg}", flush=True)
def run(cmd, cwd=None, check=True, quiet=False):
    p = subprocess.run(cmd, cwd=cwd, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if not quiet:
        for ln in p.stdout.splitlines(): pass  # mute normal noise; turn on if needed
    if check and p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(cmd)}")
    return p.returncode, p.stdout

# ---------- HTTP helpers ----------
def http_request(method, url, data=None, headers=None, timeout=30):
    req = request.Request(url, method=method.upper())
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if data is not None:
        if isinstance(data, dict):
            data = parse.urlencode(data).encode("utf-8")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        elif isinstance(data, (bytes, bytearray)):
            pass
        else:
            # assume JSON string
            data = data.encode("utf-8")
            req.add_header("Content-Type", "application/json")
    try:
        with request.urlopen(req, data=data, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.getcode(), body
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body
    except Exception as e:
        raise

# ---------- Gitee API ----------
def gitee_whoami(token: str):
    code, body = http_request("GET", f"https://gitee.com/api/v5/user?access_token={parse.quote(token)}")
    if code != 200:
        raise RuntimeError(f"Gitee token 校验失败: HTTP {code} {body}")
    j = json.loads(body)
    return j["login"]  # 小写用户名，eg. 'sebastianmo'

def gitee_repo_get(owner: str, name: str, token: str):
    code, body = http_request("GET", f"https://gitee.com/api/v5/repos/{owner}/{name}?access_token={parse.quote(token)}")
    if code == 200:
        return json.loads(body)
    if code == 404:
        return None
    raise RuntimeError(f"Gitee 查询仓库失败: HTTP {code} {body}")

def gitee_repo_create_personal(name: str, token: str, is_private: bool, description: str|None=None):
    data = {
        "access_token": token,
        "name": name,
        "private": "true" if is_private else "false",
        "auto_init": "false",
        "has_issues": "true",
    }
    if description:
        data["description"] = description
    code, body = http_request("POST", "https://gitee.com/api/v5/user/repos", data=data)
    if code not in (201, 200):
        raise RuntimeError(f"Gitee 创建仓库失败: HTTP {code} {body}")
    return json.loads(body)

def gitee_repo_update_visibility(owner: str, name: str, token: str, is_private: bool):
    data = {
        "access_token": token,
        "name": name,
        "private": "true" if is_private else "false",
    }
    code, body = http_request("PATCH", f"https://gitee.com/api/v5/repos/{owner}/{name}", data=data)
    if code not in (200, 201):
        # 某些情况下不可切换可见性（权限/策略），不致命，给提示即可
        warn(f"Gitee 切换公开/私有失败: HTTP {code} {body}")

# ---------- GitHub API (可选) ----------
def gh_whoami(token: str):
    code, body = http_request("GET", "https://api.github.com/user", headers={"Authorization": f"token {token}", "Accept":"application/vnd.github+json"})
    if code != 200:
        raise RuntimeError(f"GitHub token 校验失败: HTTP {code} {body}")
    return json.loads(body)["login"]

def gh_repo_get(owner: str, name: str, token: str):
    code, body = http_request("GET", f"https://api.github.com/repos/{owner}/{name}", headers={"Authorization": f"token {token}", "Accept":"application/vnd.github+json"})
    if code == 200:
        return json.loads(body)
    if code == 404:
        return None
    raise RuntimeError(f"GitHub 查询仓库失败: HTTP {code} {body}")

def gh_repo_create_personal(name: str, token: str, is_private: bool, description: str|None=None):
    payload = {"name": name, "private": is_private, "auto_init": False}
    if description: payload["description"] = description
    code, body = http_request("POST", "https://api.github.com/user/repos",
                              data=json.dumps(payload),
                              headers={"Authorization": f"token {token}", "Accept":"application/vnd.github+json"})
    if code not in (201, 200):
        raise RuntimeError(f"GitHub 创建仓库失败: HTTP {code} {body}")
    return json.loads(body)

def gh_repo_update_visibility(owner: str, name: str, token: str, is_private: bool):
    payload = {"private": is_private}
    code, body = http_request("PATCH", f"https://api.github.com/repos/{owner}/{name}",
                              data=json.dumps(payload),
                              headers={"Authorization": f"token {token}", "Accept":"application/vnd.github+json"})
    if code not in (200, 201):
        warn(f"GitHub 切换公开/私有失败: HTTP {code} {body}")

# ---------- Git ops ----------
def ensure_git_identity(repo_dir: Path):
    def getcfg(key):
        _, out = run(["git", "config", "--get", key], cwd=repo_dir, check=False, quiet=True)
        return out.strip() if out else ""
    name = getcfg("user.name")
    email = getcfg("user.email")
    if not name:
        run(["git", "config", "user.name", "rosrpm"], cwd=repo_dir)
    if not email:
        run(["git", "config", "user.email", "rosrpm@example.invalid"], cwd=repo_dir)

def purge_nested_git(repo_dir: Path):
    # 专门清理 original 下的嵌套 .git，避免 “embedded repo” 警告
    for g in repo_dir.glob("original/**/.git"):
        if g.is_dir():
            shutil.rmtree(g)

def init_and_commit(repo_dir: Path, branch: str):
    if not (repo_dir / ".git").exists():
        run(["git", "init"], cwd=repo_dir)
        # 把 HEAD 指向目标默认分支，从源头就用 main
        run(["git", "symbolic-ref", "HEAD", f"refs/heads/{branch}"], cwd=repo_dir, check=False)
    ensure_git_identity(repo_dir)
    purge_nested_git(repo_dir)
    # add/commit（无变化不报错）
    run(["git", "add", "-A"], cwd=repo_dir, check=True)
    rc, out = run(["git", "diff", "--cached", "--quiet"], cwd=repo_dir, check=False, quiet=True)
    # git diff --quiet: 0 表示无变化；非 0 表示有变化
    if rc != 0:
        run(["git", "commit", "-m", "sync"], cwd=repo_dir, check=True)
    # 确保在目标分支
    run(["git", "checkout", "-B", branch], cwd=repo_dir, check=True)

def set_remote_and_push(repo_dir: Path, remote_url: str, branch: str):
    run(["git", "remote", "remove", "origin"], cwd=repo_dir, check=False)
    run(["git", "remote", "add", "origin", remote_url], cwd=repo_dir, check=True)
    run(["git", "push", "-u", "origin", branch], cwd=repo_dir, check=True)

# ---------- Main ----------
def main():
    print(f"根目录:   {ROOT}")
    print(f"包目录:   {REPOS_DIR}")
    if not REPOS_DIR.exists():
        sys.exit("repos 目录不存在。")

    platform = input("选择平台 github / gitee [gitee]: ").strip().lower() or "gitee"
    auth = input("认证方式 token / ssh（ssh 仅用于 push；建仓建议 token） [token]: ").strip().lower() or "token"
    namespace = input(f"命名空间/用户名（例如 {platform} 用户名或组织名）: ").strip()
    default_branch = input("默认分支名 [main]: ").strip() or "main"

    token = ""
    if platform == "gitee":
        # Gitee 强烈建议 token，且我们默认用 token 方式
        token = getpass.getpass("请输入 API token（输入隐藏）：").strip()
        login = gitee_whoami(token).lower()
        print(f"Token OK，登录身份：{login}")
        # 强制用小写，避免 “The token username invalid”
        namespace = (namespace or login).lower()
    elif platform == "github":
        token = getpass.getpass("请输入 GitHub Token（输入隐藏）：").strip()
        login = gh_whoami(token)
        print(f"Token OK，登录身份：{login}")
        if not namespace:
            namespace = login
    else:
        sys.exit("仅支持 gitee / github")

    pkgs = sorted([p.name for p in REPOS_DIR.iterdir() if p.is_dir()])
    print(f"待上传仓库数：{len(pkgs)}")

    yaml_items = []
    ok = fail = 0

    for name in pkgs:
        repo_dir = REOS = REPOS_DIR / name  # 让你之前的肌肉记忆也“复活”一下😂
        try:
            # 1) 创建或获取远端（公开）
            if platform == "gitee":
                exists = gitee_repo_get(namespace, name, token)
                if not exists:
                    gitee_repo_create_personal(name, token, is_private=False, description=None)
                else:
                    # 若已存在则尝试切到公开
                    if exists.get("private", False):
                        gitee_repo_update_visibility(namespace, name, token, is_private=False)
                # 远端 URL（push 用凭据，YAML 用无凭据）
                remote_push = f"https://{namespace}:{token}@gitee.com/{namespace}/{name}.git"
                remote_yaml = f"https://gitee.com/{namespace}/{name}.git"

            else:  # github
                exists = gh_repo_get(namespace, name, token)
                if not exists:
                    gh_repo_create_personal(name, token, is_private=False, description=None)
                else:
                    if exists.get("private", False):
                        gh_repo_update_visibility(namespace, name, token, is_private=False)
                remote_push = f"https://{namespace}:{token}@github.com/{namespace}/{name}.git"
                remote_yaml = f"https://github.com/{namespace}/{name}.git"

            # 2) 本地 init / commit / push
            init_and_commit(repo_dir, default_branch)
            set_remote_and_push(repo_dir, remote_push, default_branch)

            # 3) YAML 项（spec_name 是目录名，不是 spec 文件里 Name 字段）
            yaml_items.append({
                "spec_name": name,
                "spec_url": remote_yaml,
                "spec_branch": default_branch,
            })
            ok += 1
            print(f"OK    {name}")

        except Exception as e:
            fail += 1
            warn(f"FAIL  {name}: {e}")

    # 写 YAML（不含凭据）
    if yaml_items:
        lines = ["package_repos:"]
        for it in yaml_items:
            lines.append(f"  - spec_name: {it['spec_name']}")
            lines.append(f"    spec_url: {it['spec_url']}")
            lines.append(f"    spec_branch: {it['spec_branch']}")
        YAML_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n已生成清单：{YAML_OUT}")

    print(f"\n完成：OK={ok} / {ok+fail}")
    if fail:
        print("部分失败可重跑本脚本（幂等）。")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n中断。")
        sys.exit(130)