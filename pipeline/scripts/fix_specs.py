#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量修正 Bloom 生成的 template.spec：

1. spec 头部增加（如果尚不存在）：
     %bcond_without tests
     %bcond_without weak_deps
     %global debug_package %{nil}

2. 将 Name 统一为：
     Name: ros-<ros_distro>-<pkg-name-with-hyphen>

3. 将 Source 行统一改为：
     Source0: %{name}_%{version}.orig.tar.gz
   展开后为：ros-<ros_distro>-<pkg-name-with-hyphen>_<version>.orig.tar.gz

4. 将安装前缀统一为 /opt/ros/<ros_distro>：
   - CMake 包：修正 %cmake3 调用中的
       -DCMAKE_INSTALL_PREFIX=...
       -DAMENT_PREFIX_PATH=...
       -DCMAKE_PREFIX_PATH=...
   - Python 包：修正 %py3_install 行，使其包含
       --prefix "/opt/ros/<ros_distro>"

5. 在 %build / %install / %check 段开头注入：
     export ROS_PREFIX="/opt/ros/<ros_distro>"
     export PYTHONPATH="$ROS_PREFIX/lib64/python%{python3_version}/site-packages:$ROS_PREFIX/lib/python%{python3_version}/site-packages:${PYTHONPATH}"

6. 将主 %files 段改成：
     %files
     /opt/ros/<ros_distro>

7. 使用 repos/<pkg_name>/template.spec 作为输入，
   输出到 repos/<pkg_name>/<pkg-name-with-hyphen>.spec，
   并删除 template.spec。
"""

import argparse
import os
import re
import sys
from typing import List, Tuple, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fix Bloom-generated RPM spec files.")
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
        required=True,
        help="ROS 发行版（例如 jazzy），用于 /opt/ros/<distro> 和 Name: ros-<distro>-... 等前缀。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印修改结果，不写回文件、不删除 template.spec。",
    )
    return parser.parse_args()


def load_pkg_list(path: str) -> List[Tuple[str, str]]:
    """
    解析 pkg_list.txt 中的行：
        <pkg_name> <pkg_path>
    """
    result: List[Tuple[str, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                print(f"[WARN] Invalid line {lineno} in {path}: {line}", file=sys.stderr)
                continue
            pkg_name, pkg_path = parts[0], parts[1]
            result.append((pkg_name, pkg_path))
    return result


def ensure_bconds(text: str) -> str:
    """
    在文件顶部增加：
      %bcond_without tests
      %bcond_without weak_deps
    如果已存在则跳过。
    """
    needed = [
        "%bcond_without tests",
        "%bcond_without weak_deps",
    ]

    existing = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("%bcond_without"):
            existing.add(stripped)

    missing = [l for l in needed if l not in existing]
    if not missing:
        return text

    header = "\n".join(missing) + "\n\n"
    return header + text.lstrip("\n")


def ensure_debug_disabled(text: str) -> str:
    """
    确保关闭 debug 包：
      %global debug_package %{nil}

    如果已经存在 %global/%define debug_package 则不再添加。
    否则，将其插入在所有 %bcond_without 行之后（如果找得到），
    找不到则直接插到文件最前面。
    """
    if re.search(r"^%(?:global|define)\s+debug_package\b", text, re.MULTILINE):
        return text

    lines = text.splitlines(keepends=True)

    last_bcond_idx = -1
    for i, line in enumerate(lines):
        if line.lstrip().startswith("%bcond_without"):
            last_bcond_idx = i

    debug_line = "%global debug_package %{nil}\n"

    if last_bcond_idx >= 0:
        insert_pos = last_bcond_idx + 1
        while insert_pos < len(lines) and lines[insert_pos].strip() == "":
            insert_pos += 1
        new_lines = lines[:insert_pos] + [debug_line, "\n"] + lines[insert_pos:]
        return "".join(new_lines)

    return debug_line + "\n" + text.lstrip("\n")


def fix_name(text: str, rpm_name: str) -> str:
    """
    将 Name 行改为：
      Name:           <rpm_name>
    """
    pattern = re.compile(r"^Name:\s*.*$", re.MULTILINE)
    replacement = f"Name:           {rpm_name}"

    if pattern.search(text):
        return pattern.sub(replacement, text)
    else:
        return replacement + "\n" + text


def fix_source0(text: str) -> str:
    """
    将 Source/Source0 行改为：
      Source0: %{name}_%{version}.orig.tar.gz
    """
    pattern = re.compile(r"^(Source0?:\s*).*$", re.MULTILINE)
    replacement = r"\1%{name}_%{version}.orig.tar.gz"

    if pattern.search(text):
        return pattern.sub(replacement, text)

    lic_pat = re.compile(r"^(License:\s*.*)$", re.MULTILINE)
    m = lic_pat.search(text)
    new_line = "Source0: %{name}_%{version}.orig.tar.gz"
    if m:
        pos = m.end()
        return text[:pos] + "\n" + new_line + text[pos:]
    else:
        return text.rstrip() + "\n" + new_line + "\n"


def fix_cmake_prefixes(text: str, ros_prefix: str) -> str:
    """
    修正 CMake 调用中的安装前缀：
      -DCMAKE_INSTALL_PREFIX=...
      -DAMENT_PREFIX_PATH=...
      -DCMAKE_PREFIX_PATH=...
    -> 指向 /opt/ros/<ros_distro>
    """
    patterns = [
        (r"-DCMAKE_INSTALL_PREFIX(?:\s+|=)\"?[^\s\"]*\"?", f'-DCMAKE_INSTALL_PREFIX="{ros_prefix}"'),
        (r"-DAMENT_PREFIX_PATH(?:\s+|=)\"?[^\s\"]*\"?", f'-DAMENT_PREFIX_PATH="{ros_prefix}"'),
        (r"-DCMAKE_PREFIX_PATH(?:\s+|=)\"?[^\s\"]*\"?", f'-DCMAKE_PREFIX_PATH="{ros_prefix}"'),
    ]
    for pat, rep in patterns:
        text = re.sub(pat, rep, text)
    return text


def fix_py3_install(text: str, ros_prefix: str) -> str:
    """
    修正 %py3_install 行，使其包含 --prefix "/opt/ros/<ros_distro>"。
    示例：
      %py3_install -- --prefix "/usr"
    -> %py3_install -- --prefix "/opt/ros/<ros_distro>"
    """
    lines = text.splitlines(keepends=True)
    out: List[str] = []

    for line in lines:
        if "%py3_install" not in line:
            out.append(line)
            continue

        if "--prefix" in line:
            line = re.sub(
                r"(--prefix(?:\s+|=))(\"[^\"]*\"|\S+)",
                rf'\1"{ros_prefix}"',
                line,
            )
        else:
            stripped = line.rstrip("\n")
            if "--" in stripped:
                stripped += f' --prefix "{ros_prefix}"'
            else:
                stripped += f' -- --prefix "{ros_prefix}"'
            line = stripped + "\n"

        out.append(line)

    return "".join(out)


def inject_ros_pythonpath(text: str, ros_prefix: str) -> str:
    """
    在 %build / %install / %check 段开头注入：
      export ROS_PREFIX="<ros_prefix>"
      export PYTHONPATH="$ROS_PREFIX/lib64/python%{python3_version}/site-packages:..."

    为避免重复注入，如果文件中已经包含 '# BEGIN ros_pythonpath'，则不再处理。
    """
    if "# BEGIN ros_pythonpath" in text:
        return text

    block = (
        "# BEGIN ros_pythonpath\n"
        f'export ROS_PREFIX="{ros_prefix}"\n'
        'export PYTHONPATH="$ROS_PREFIX/lib64/python%{python3_version}/site-packages:'
        '$ROS_PREFIX/lib/python%{python3_version}/site-packages:${PYTHONPATH}"\n'
        "# END ros_pythonpath\n"
    )

    for section in ("build", "install", "check"):
        pattern = re.compile(rf"(^%{section}\b[^\n]*\n)", re.MULTILINE)
        m = pattern.search(text)
        if not m:
            continue
        insert_pos = m.end()
        text = text[:insert_pos] + block + "\n" + text[insert_pos:]

    return text


def fix_files_section(text: str, ros_prefix: str) -> str:
    """
    将主 %files 段改成：
      %files
      /opt/ros/<ros_distro>
    """
    files_block_pattern = re.compile(
        r"^%files[^\n]*\n.*?(?=^%changelog\b)",
        flags=re.MULTILINE | re.DOTALL,
    )
    new_block = f"%files\n{ros_prefix}\n"

    m = files_block_pattern.search(text)
    if m:
        return text[: m.start()] + new_block + text[m.end() :]

    changelog_pat = re.compile(r"^%changelog\b", re.MULTILINE)
    c = changelog_pat.search(text)
    if c:
        return text[: c.start()] + new_block + "\n" + text[c.start() :]

    return text.rstrip() + "\n\n" + new_block + "\n"


def patch_spec_text(text: str, rpm_name: str, ros_prefix: str) -> str:
    """
    组合所有修复动作。
    """
    text = ensure_bconds(text)
    text = ensure_debug_disabled(text)
    text = fix_name(text, rpm_name)
    text = fix_source0(text)
    text = fix_cmake_prefixes(text, ros_prefix)
    text = fix_py3_install(text, ros_prefix)
    text = inject_ros_pythonpath(text, ros_prefix)
    text = fix_files_section(text, ros_prefix)
    return text


def find_input_spec(spec_dir: str) -> Optional[str]:
    """
    优先使用 template.spec，否则尝试找到唯一的 .spec。
    """
    tmpl = os.path.join(spec_dir, "template.spec")
    if os.path.exists(tmpl):
        return tmpl

    specs = [f for f in os.listdir(spec_dir) if f.endswith(".spec")]
    if len(specs) == 1:
        return os.path.join(spec_dir, specs[0])

    if len(specs) == 0:
        return None

    print(f"[WARN] Multiple .spec files in {spec_dir}, skip.", file=sys.stderr)
    return None


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

    ros_prefix = f"/opt/ros/{args.ros_distro}"

    print(f"[INFO] Workspace : {workspace}")
    print(f"[INFO] Pkg list  : {pkg_list_path}")
    print(f"[INFO] Repos dir : {repos_root}")
    print(f"[INFO] ROS distro: {args.ros_distro}")
    print(f"[INFO] ROS prefix: {ros_prefix}")
    print(f"[INFO] Dry run   : {args.dry_run}")
    print()

    pkgs = load_pkg_list(pkg_list_path)

    total = 0
    patched = 0
    skipped = 0

    for pkg_name, _pkg_path in pkgs:
        total += 1
        spec_dir = os.path.join(repos_root, pkg_name)
        if not os.path.isdir(spec_dir):
            print(f"[WARN] repos/{pkg_name} not found, skip.")
            skipped += 1
            continue

        input_spec = find_input_spec(spec_dir)
        if not input_spec:
            print(f"[WARN] No spec file found in {spec_dir}, skip.")
            skipped += 1
            continue

        try:
            with open(input_spec, "r", encoding="utf-8") as f:
                original = f.read()
        except OSError as e:
            print(f"[ERROR] Failed to read {input_spec}: {e}", file=sys.stderr)
            skipped += 1
            continue

        pkg_hyphen = pkg_name.replace("_", "-")
        rpm_name = f"ros-{args.ros_distro}-{pkg_hyphen}"

        new_text = patch_spec_text(original, rpm_name, ros_prefix)

        spec_basename = pkg_hyphen + ".spec"
        output_spec = os.path.join(spec_dir, spec_basename)

        print(f"[INFO] Patch {input_spec} -> {output_spec} (Name={rpm_name})")

        if not args.dry_run:
            try:
                with open(output_spec, "w", encoding="utf-8") as f:
                    f.write(new_text)
            except OSError as e:
                print(f"[ERROR] Failed to write {output_spec}: {e}", file=sys.stderr)
                skipped += 1
                continue

            if os.path.basename(input_spec) == "template.spec" and os.path.abspath(
                input_spec
            ) != os.path.abspath(output_spec):
                try:
                    os.remove(input_spec)
                    print(f"[INFO] Removed {input_spec}")
                except OSError as e:
                    print(f"[WARN] Failed to remove {input_spec}: {e}", file=sys.stderr)

        patched += 1
        print()

    print("\n[SUMMARY] fix_specs.py")
    print(f"[SUMMARY] Total packages considered : {total}")
    print(f"[SUMMARY] Patched                    : {patched}")
    print(f"[SUMMARY] Skipped                    : {skipped}")


if __name__ == "__main__":
    main()

