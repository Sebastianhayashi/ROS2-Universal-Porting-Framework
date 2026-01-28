#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import re
import shutil
import subprocess
import tarfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
REPOS = ROOT / "repos"
STATE = Path.home() / ".local" / "state" / "rosrpm"
STATE.mkdir(parents=True, exist_ok=True)
ORDER = STATE / "order.ros"
MAP = STATE / "order.map"

def run(cmd, cwd=None, check=True):
    return subprocess.run(
        cmd, cwd=cwd, check=check, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    ).stdout

def which(prog: str) -> bool:
    from shutil import which as _which
    return _which(prog) is not None

def resolve_workspace(ws_arg: str | None) -> Path:
    if ws_arg:
        ws = Path(ws_arg).expanduser().resolve()
        return ws
    # default: ~/ros-rpm/ros2_ws -> fallback ~/ros-rpm/ros2
    ws1 = ROOT / "ros2_ws"
    ws2 = ROOT / "ros2"
    return ws1 if ws1.exists() else ws2

def src_dir_of(ws: Path) -> Path:
    return ws / "src"

def is_test_pkg(name: str) -> bool:
    # 典型 ROS 测试包命名：test_*、*tests、ros2test、test-*
    return bool(re.match(r"^(test[_-].*|ros2test.*|.*(_|-)?tests)$", name))

def colcon_names(ws: Path, up_to: list[str] | None, include_tests: bool) -> list[str]:
    if not which("colcon"):
        raise SystemExit("ERROR: 未找到 colcon，请先安装：pip install colcon-common-extensions")

    src = src_dir_of(ws)
    if not src.exists():
        raise SystemExit(f"ERROR: 工作区下没有 src：{src}")

    cmd = ["colcon", "list", "--base-paths", str(src), "--names-only", "--topological-order"]
    if up_to:
        # 逗号分隔传给 colcon：--packages-up-to a b c
        cmd += ["--packages-up-to", *up_to]

    out = run(cmd)
    names = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if not include_tests:
        names = [n for n in names if not is_test_pkg(n)]
    return names

def colcon_path(ws: Path, name: str) -> Path | None:
    try:
        out = run([
            "colcon", "list",
            "--base-paths", str(src_dir_of(ws)),
            "--packages-select", name, "--paths-only"
        ])
        p = out.strip()
        return Path(p) if p else None
    except subprocess.CalledProcessError:
        return None

def parse_version(pkg_path: Path) -> str:
    """优先读取 package.xml 的 <version>；失败则用 0.0.0"""
    pkg_xml = pkg_path / "package.xml"
    if pkg_xml.exists():
        try:
            root = ET.parse(pkg_xml).getroot()
            ver = root.findtext("version", default="0.0.0").strip()
            ver = re.sub(r"\s+", "", ver)
            if ver:
                return ver
        except Exception:
            pass
    return "0.0.0"

def safe_copytree(src: Path, dst: Path):
    if dst.exists():
        shutil.rmtree(dst)
    def _ignore(_dir, names):
        ig = {".git", ".svn", ".hg", "build", "install", "log", "__pycache__"}
        return ig.intersection(names)
    shutil.copytree(src, dst, ignore=_ignore)

def git_baseline(dst_pkg_dir: Path):
    if not (dst_pkg_dir / ".git").exists():
        run(["git", "init"], cwd=dst_pkg_dir)
        run(["git", "config", "user.name", "rosrpm"], cwd=dst_pkg_dir)
        run(["git", "config", "user.email", "rosrpm@example.invalid"], cwd=dst_pkg_dir)
        run(["git", "add", "-A"], cwd=dst_pkg_dir)
        run(["git", "commit", "-m", "baseline for bloom"], cwd=dst_pkg_dir)

def make_tar(topdir: str, src_dir: Path, out_tgz: Path):
    out_tgz.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out_tgz, "w:gz") as tf:
        for p in src_dir.rglob("*"):
            arc = Path(topdir) / p.relative_to(src_dir)
            tf.add(p, arcname=str(arc), recursive=False)

def process_one(ws: Path, name: str, distro: str, verbose: bool):
    src_path = colcon_path(ws, name)
    if not src_path or not src_path.exists():
        return ("FAIL", name, "no-path")

    ver = parse_version(src_path)
    hy = name.replace("_", "-")
    topdir = f"ros-{distro}-{hy}-{ver}"
    out_dir = REPOS / name
    orig_dir = out_dir / "original" / name
    tar_path = out_dir / f"{topdir}.orig.tar.gz"

    out_dir.mkdir(parents=True, exist_ok=True)

    if tar_path.exists():
        return ("SKIP", name, f"skip-tar:{tar_path.name}")

    orig_dir.parent.mkdir(parents=True, exist_ok=True)
    safe_copytree(src_path, orig_dir)
    git_baseline(orig_dir)

    make_tar(topdir, orig_dir, tar_path)
    return ("OK", name, tar_path.name)

def main():
    ap = argparse.ArgumentParser(description="为选定闭包生成 repos/* 的 .orig（使用 package.xml 版本号）")
    ap.add_argument("--distro", default="jazzy")
    ap.add_argument("--workspace", help="ROS 工作区路径（默认 ~/ros-rpm/ros2_ws，不在则回退 ~/ros-rpm/ros2）")
    ap.add_argument("--up-to", help="逗号分隔：只为这些包及其依赖闭包生成（等同 colcon --packages-up-to）")
    ap.add_argument("--include-tests", action="store_true", help="包含测试包（默认排除 test_* / *tests）")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 8)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    ws = resolve_workspace(args.workspace)
    src = src_dir_of(ws)

    print(f"ROOT : {ROOT}")
    print(f"WS   : {ws}")
    print(f"SRC  : {src}")
    print(f"REPOS: {REPOS}")
    print(f"STATE: {STATE}")

    up_to_list = None
    if args.up_to:
        up_to_list = [x.strip() for x in args.up_to.split(",") if x.strip()]

    names_ordered = colcon_names(ws, up_to_list, include_tests=args.include_tests)
    if not names_ordered:
        raise SystemExit("ERROR: 没有可处理的包（检查 --workspace 与 --up-to 参数，或 src/ 是否就绪）")

    print(f"并行度：{args.jobs}  总包数：{len(names_ordered)}"
          + (f"  up-to: {','.join(up_to_list)}" if up_to_list else "")
          + ("" if args.include_tests else "  (已排除测试包)")
    )

    ok = skip = fail = 0
    mapping = []

    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(process_one, ws, n, args.distro, args.verbose): n for n in names_ordered}
        for fut in as_completed(futs):
            n = futs[fut]
            try:
                st, n, msg = fut.result()
            except Exception as e:
                st, n, msg = ("FAIL", n, f"exc:{e}")
            if st == "OK":
                ok += 1
                print(f"OK    {n}: {msg}")
                mapping.append(f"{n} {msg}")
            elif st == "SKIP":
                skip += 1
                print(f"SKIP  {n}: {msg}")
            else:
                fail += 1
                print(f"FAIL  {n}: {msg}")

    # 按 colcon 的拓扑顺序写入清单
    ORDER.write_text("\n".join(names_ordered) + "\n", encoding="utf-8")
    MAP.write_text("\n".join(mapping) + "\n", encoding="utf-8")

    print("\n✅ 完成")
    print(f"  OK={ok}  SKIP={skip}  FAIL={fail}")
    print(f"  清单：{ORDER}")
    print(f"  映射：{MAP}")
    print("  每包输出：repos/<pkg>/original/ + ros-<distro>-<pkg-hyphen>-<ver>.orig.tar.gz")

if __name__ == "__main__":
    main()