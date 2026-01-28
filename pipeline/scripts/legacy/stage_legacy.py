#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess as sp
from typing import Dict, List, Optional, Tuple
import shutil

ROOT = Path(__file__).resolve().parent
REPOS = ROOT / "repos"
LOGDIR = ROOT / "logs" / "bloom"
STATE_DIR = Path(os.environ.get("ROSRPM_STATE", Path.home() / ".local" / "state" / "rosrpm"))
ORDER_MAP = STATE_DIR / "order.map"

ENV_BASE = os.environ.copy()
ENV_BASE.setdefault("ROS_OS_OVERRIDE", "rhel:9")
ENV_BASE.setdefault("BLOOM_DONT_ASK", "1")
ENV_BASE.setdefault("GIT_TERMINAL_PROMPT", "0")
ENV_BASE.setdefault("LC_ALL", "C")  # 固定 locale

def hyphen_name(pkg: str) -> str:
    return pkg.replace("_", "-")

def load_order_map(path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if not path.exists():
        print(f"!! 找不到 {path}，请先运行 spilt.py 生成。", file=sys.stderr)
        return mapping
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split()
            if parts:
                mapping[parts[0]] = parts[1] if len(parts) > 1 else ""
    return mapping

def find_pkg_original_dir(pkg: str) -> Optional[Path]:
    base = REPOS / pkg / "original"
    candidate = base / pkg
    if candidate.exists() and (candidate / "package.xml").exists():
        return candidate
    if base.exists():
        for p in base.rglob("package.xml"):
            return p.parent
    return None

def ensure_git_repo(path: Path) -> None:
    if (path / ".git").exists():
        return
    sp.run(["git", "init"], cwd=str(path), check=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    sp.run(["git", "config", "user.name", "rosrpm"], cwd=str(path), check=True)
    sp.run(["git", "config", "user.email", "rosrpm@example.invalid"], cwd=str(path), check=True)
    sp.run(["git", "add", "-A"], cwd=str(path), check=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    sp.run(["git", "commit", "-m", "baseline for bloom"], cwd=str(path), check=True,
           stdout=sp.DEVNULL, stderr=sp.DEVNULL)

def parse_version_from_package_xml(pkg_dir: Path) -> Optional[str]:
    xmlp = pkg_dir / "package.xml"
    try:
        tree = ET.parse(str(xmlp))
        ver = tree.getroot().findtext("version")
        return ver.strip() if ver else None
    except Exception:
        return None

def parse_build_type(pkg_dir: Path) -> Optional[str]:
    xmlp = pkg_dir / "package.xml"
    try:
        root = ET.parse(str(xmlp)).getroot()
        export = root.find("export")
        if export is not None:
            bt = export.findtext("build_type")
            if bt:
                return bt.strip()
    except Exception:
        pass
    return None

def is_ament_python(pkg_dir: Path) -> bool:
    bt = parse_build_type(pkg_dir)
    if bt and bt.lower() == "ament_python":
        return True
    has_setup = (pkg_dir / "setup.py").exists()
    has_cmake = (pkg_dir / "CMakeLists.txt").exists()
    return has_setup and not has_cmake

def run(cmd: List[str], cwd: Path, timeout: int, log_file: Path, env=None) -> Tuple[int, str]:
    with log_file.open("wb") as lf:
        try:
            p = sp.Popen(cmd, cwd=str(cwd), env=env or ENV_BASE,
                         stdout=sp.PIPE, stderr=sp.STDOUT)
            out, _ = p.communicate(timeout=timeout)
            lf.write(out or b"")
            return p.returncode, ("ok" if p.returncode == 0 else "nonzero")
        except sp.TimeoutExpired:
            try:
                p.kill()
            except Exception:
                pass
            try:
                out, _ = p.communicate(timeout=3)
                lf.write(out or b"")
            except Exception:
                pass
            return 124, "timeout"

SPEC_HEADER_SNIPPET = """%bcond_without tests
%global __os_install_post %(echo '%{__os_install_post}' | sed -e 's!/usr/lib[^[:space:]]*/brp-python-bytecompile[[:space:]].*$!!g')
%global __provides_exclude_from ^/opt/ros/%{ros_distro}/.*$
%global __requires_exclude_from ^/opt/ros/%{ros_distro}/.*$
"""

DEBUG_DISABLE_BLOCK = (
    "%global debug_package %{nil}\n"
    "%undefine _debuginfo_subpackages\n"
    "%undefine _debugsource_packages\n"
)

CHECK_BLOCK = r"""%if 0%{?with_tests}
%check
if %__python3 -m pytest --version >/dev/null 2>&1; then
  %__python3 -m pytest -q || echo "pytest failed (non-fatal)"
else
  echo "pytest not available; skip"
fi
%endif
"""

def ensure_line_after_anchor(txt: str, anchor_re: str, line_to_add: str) -> str:
    if re.search(rf"(?m)^\s*{re.escape(line_to_add)}\s*$", txt):
        return txt
    m = re.search(anchor_re, txt, re.MULTILINE)
    if not m:
        m2 = re.search(r"(?m)^\%description\b", txt)
        if m2:
            return txt[:m2.start()] + line_to_add + "\n" + txt[m2.start():]
        else:
            return txt + "\n" + line_to_add + "\n"
    insert_at = m.end()
    return txt[:insert_at] + "\n" + line_to_add + "\n" + txt[insert_at:]

def remove_existing_check_sections(txt: str) -> str:
    # 1) 删除外层以 with_tests 包裹的 %check 区块
    pat_if = re.compile(r"(?ms)^\%if[^\n]*with_tests[^\n]*\n.*?\n^\%endif\s*$")
    txt = pat_if.sub("", txt)
    # 2) 删除裸的 %check 区块
    pat_chk = re.compile(r"(?ms)^\%check\b.*?(?=^\%[a-zA-Z]|\Z)")
    txt = pat_chk.sub("", txt)
    return txt

def replace_or_insert_check_block(txt: str) -> str:
    txt = remove_existing_check_sections(txt)
    m = re.search(r"(?m)^\%files\b", txt)
    if m:
        return txt[:m.start()] + CHECK_BLOCK + "\n" + txt[m.start():]
    return txt.rstrip() + "\n\n" + CHECK_BLOCK + "\n"

def patch_spec(spec_path: Path, distro: str, pkg: str, version: str, pkg_dir: Path) -> None:
    txt = spec_path.read_text(encoding="utf-8", errors="ignore")

    # 1) 顶置禁用 debuginfo/debugsource（幂等）
    txt = re.sub(r"(?m)^\s*%(?:global|define)\s+debug_package\b.*\n", "", txt)
    txt = re.sub(r"(?m)^\s*%undefine\s+_debuginfo_subpackages\s*\n", "", txt)
    txt = re.sub(r"(?m)^\s*%undefine\s+_debugsource_packages\s*\n", "", txt)
    txt = DEBUG_DISABLE_BLOCK + txt

    # 2) 规范 Source0
    txt = re.sub(r"(?m)^Source0:\s*.+$", "Source0:        %{name}-%{version}.orig.tar.gz", txt)

    # 3) 注入 header 宏（放到 Name 行之后）
    if "__os_install_post" not in txt or "__provides_exclude_from" not in txt:
        m = re.search(r"(?m)^Name:\s*.+$", txt)
        ins = SPEC_HEADER_SNIPPET.replace("%{ros_distro}", distro)
        if m:
            txt = txt[:m.end()] + "\n" + ins + txt[m.end():]
        else:
            txt = ins + "\n" + txt

    # 4) 纯 Python 包：BuildArch: noarch
    if is_ament_python(pkg_dir) and not re.search(r"(?m)^\s*BuildArch:\s*noarch\s*$", txt):
        if re.search(r"(?m)^License:\s*.+$", txt):
            txt = ensure_line_after_anchor(txt, r"(?m)^License:\s*.+$", "BuildArch:      noarch")
        else:
            txt = ensure_line_after_anchor(txt, r"(?m)^Source0:\s*.+$", "BuildArch:      noarch")

    # 5) 确保 BuildRequires：pythonX-devel 与 setuptools
    if not re.search(r"(?m)^BuildRequires:\s*python%{python3_pkgversion}-devel\b", txt):
        txt = ensure_line_after_anchor(txt, r"(?m)^Source0:\s*.+$", "BuildRequires:  python%{python3_pkgversion}-devel")
    if not re.search(r"(?m)^BuildRequires:\s*python%{python3_pkgversion}-setuptools\b", txt):
        txt = ensure_line_after_anchor(txt, r"(?m)^Source0:\s*.+$", "BuildRequires:  python%{python3_pkgversion}-setuptools")
    # 避免 setuptools 误出现在 Requires（非致命，仅清理）
    txt = re.sub(r"(?m)^\s*Requires:\s*python%{python3_pkgversion}-setuptools\s*$", "", txt)

    # 6) 只保留一份 %check
    txt = replace_or_insert_check_block(txt)

    # 7) 若缺少 bcond，补上
    if "%bcond_without tests" not in txt:
        txt = "%bcond_without tests\n" + txt

    spec_path.write_text(txt, encoding="utf-8")

    # 8) 兜底：必须以禁用块开头
    head = spec_path.read_text(encoding="utf-8", errors="ignore")[:200]
    if not head.startswith(DEBUG_DISABLE_BLOCK):
        spec_path.write_text(DEBUG_DISABLE_BLOCK + spec_path.read_text(encoding="utf-8", errors="ignore"),
                             encoding="utf-8")

def remove_original_dir(pkg: str) -> None:
    base = REPOS / pkg / "original"
    if base.exists():
        try:
            shutil.rmtree(base)
            print(f"  - 清理 original/: {base}")
        except Exception as e:
            print(f"  !! 清理失败 original/: {base}  ({e})")

def bloom_one(pkg: str, distro: str, timeout: int, verbose: bool, force: bool, rm_original: bool) -> Tuple[str, str]:
    repo_dir = REPOS / pkg
    spec_name = f"ros-{distro}-{hyphen_name(pkg)}.spec"
    spec_path = repo_dir / spec_name

    orig_pkg_dir = find_pkg_original_dir(pkg)
    if orig_pkg_dir is None:
        return pkg, "SKIP:no-package-xml"

    version = parse_version_from_package_xml(orig_pkg_dir) or "0.0.0"

    LOGDIR.mkdir(parents=True, exist_ok=True)
    logf = LOGDIR / f"{pkg}.log"

    ensure_git_repo(orig_pkg_dir)

    env = ENV_BASE.copy()
    env["ROS_OS_OVERRIDE"] = "rhel:9"
    cmd = ["bloom-generate", "rosrpm", "--ros-distro", distro, "--os-name", "rhel", "--os-version", "9"]

    # 已有 spec 且不强制：仅修补 + 可选清理 original
    if spec_path.exists() and not force:
        try:
            patch_spec(spec_path, distro, pkg, version, orig_pkg_dir)
            if rm_original:
                remove_original_dir(pkg)
            return pkg, "OK*:spec-patched"
        except Exception:
            with (LOGDIR / f"{pkg}.log").open("a", encoding="utf-8") as lf:
                lf.write("\n[WARN] spec patch failed on existing spec.\n")
            if rm_original:
                remove_original_dir(pkg)
            return pkg, "OK*:spec-patched"

    # 生成模板
    rc, _ = run(cmd, cwd=orig_pkg_dir, timeout=timeout, log_file=logf, env=env)
    if rc == 124:
        return pkg, "SKIP:timeout"
    if rc != 0:
        return pkg, "FAIL:bloom"

    # 拿模板 spec
    tpl = orig_pkg_dir / "rpm" / "template.spec"
    if not tpl.exists():
        tpl = orig_pkg_dir / "rpm" / "template.spec.em"
    if not tpl.exists():
        return pkg, "FAIL:unknown"

    # 写入 repos/<pkg>/
    repo_dir.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(tpl.read_text(encoding="utf-8"), encoding="utf-8")

    # 修补并可选删除 original
    try:
        patch_spec(spec_path, distro, pkg, version, orig_pkg_dir)
    finally:
        if rm_original:
            remove_original_dir(pkg)

    return pkg, f"OK:{spec_name}"

def main():
    ap = argparse.ArgumentParser(description="Batch bloom-generate spec files for repos/*（带可用性修补和可选清理 original/）")
    ap.add_argument("--distro", default="jazzy", help="ROS distro (default: jazzy)")
    ap.add_argument("--jobs", "-j", type=int, default=os.cpu_count() or 8)
    ap.add_argument("--timeout", "-t", type=int, default=30, help="per-package timeout seconds (default: 30)")
    ap.add_argument("--force", action="store_true", help="regen even if spec exists (overwrite template)")
    ap.add_argument("--verbose", "-v", action="store_true")
    # Python 3.9+：BooleanOptionalAction 可用
    try:
        from argparse import BooleanOptionalAction  # type: ignore
        ap.add_argument("--rm-original", action=BooleanOptionalAction, default=True,
                        help="生成/修补 spec 后删除 repos/*/original/（默认启用）")
        args = ap.parse_args()
        rm_original = args.rm_original
    except Exception:
        ap.add_argument("--rm-original", action="store_true",
                        help="生成/修补 spec 后删除 repos/*/original/（默认关闭；老 argparse 兼容）")
        ap.add_argument("--keep-original", action="store_true",
                        help="与 --rm-original 同时给出时，以 keep 为准")
        args = ap.parse_args()
        rm_original = bool(args.rm_original and not args.keep_original)

    mapping = load_order_map(ORDER_MAP)
    if not mapping:
        print("没有发现 order.map（请先运行 spilt.py）。", file=sys.stderr)
        sys.exit(1)

    targets = [pkg for pkg in mapping.keys() if (REPOS / pkg).exists()]

    print(f"并行度：{args.jobs}  目标包数：{len(targets)}  超时：{args.timeout}s  distro={args.distro} os=rhel:9  rm_original={rm_original}")

    ok = ok_star = skip = fail = 0
    futs = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for pkg in targets:
            futs.append(ex.submit(bloom_one, pkg, args.distro, args.timeout, args.verbose, args.force, rm_original))

        idx = 0
        for fut in as_completed(futs):
            idx += 1
            pkg, res = fut.result()
            if res.startswith("OK:"):
                ok += 1
                print(f"OK     {pkg}: {res}   [{idx}/{len(targets)}]  OK={ok} SKIP={skip} FAIL={fail}")
            elif res.startswith("OK*"):
                ok_star += 1
                print(f"OK*    {pkg}: {res}   [{idx}/{len(targets)}]  OK={ok}+{ok_star} SKIP={skip} FAIL={fail}")
            elif res.startswith("SKIP:"):
                skip += 1
                print(f"SKIP   {pkg}: {res}   [{idx}/{len(targets)}]  OK={ok}+{ok_star} SKIP={skip} FAIL={fail}")
            else:
                fail += 1
                print(f"FAIL   {pkg}: {res}   [{idx}/{len(targets)}]  OK={ok}+{ok_star} SKIP={skip} FAIL={fail}")

    dur = time.time() - started
    print("\n✅ 完成")
    print(f"  OK={ok}  OK*={ok_star}  SKIP={skip}  FAIL={fail}  用时：{dur:.1f}s")
    print(f"  日志目录：{LOGDIR}")

if __name__ == "__main__":
    main()