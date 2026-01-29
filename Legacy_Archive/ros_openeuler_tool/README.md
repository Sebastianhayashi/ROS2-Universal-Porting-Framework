# ROS OpenEuler Tool

## 项目简介

该工具是根据该文章中的内容所做的一个工具。

ROS OpenEuler Tool 是一个旨在简化 ROS Jazzy 版本软件包在 openEuler 系统上的移植、打包和管理的工具集。该工具集成了多个自动化脚本，能够高效地处理 ROS 包的克隆、依赖分析、RPM 打包、Gitee 仓库同步等任务，帮助开发者减少手动操作的繁琐步骤，实现一键式自动化管理。

## 功能特性

1️⃣ 批量克隆 ROS Jazzy 仓库
- 命令: rot clone-repos
- 功能: 自动从 ROS 官方索引页面 (https://index.ros.org/) 获取所有 ROS Jazzy 软件包的仓库链接，并批量克隆到本地。

2️⃣ 批量处理 ROS 包
- 命令: rot batch-process
- 功能: 在本地批量处理 ROS 包，生成 RPM 规范文件，分析依赖关系，记录跳过的包和未解析的依赖项。

3️⃣ 列出缺失的依赖
- 命令: rot list-missing
- 功能: 列出在依赖关系中解析失败或缺失的 ROS 软件包和依赖项。

4️⃣ 分析依赖关系
- 命令: rot analyze-dependencies
- 功能: 分析软件包之间的依赖关系，并生成构建顺序图，确保正确的打包和安装流程。

5️⃣ 自动更新 YUM 映射
- 命令: rot update-yum-and-mapping
- 功能: 自动更新 YUM 上游仓库并同步到 rosdep 映射文件中，确保依赖项始终保持最新状态。

6️⃣ 生成 RPM 规范文件并打包源码
- 命令: rot process-packages
- 功能: 为 ROS 包自动生成 RPM 规范文件（spec），并打包完整的源码包，准备在 openEuler 构建机器上进行打包构建。

7️⃣ 同步源码到 Gitee
- 命令: rot sync-gitee
- 功能: 将 ROS 软件包的源码同步到 Gitee 仓库，并附带详细的 README.md 文件。

8️⃣ 将 Gitee 仓库设为公开
- 命令: rot make-public
- 功能: 将所有私人 Gitee 仓库批量设置为公开，方便团队协作和资源共享。

9️⃣ 提取未闭环依赖
- 命令: rot extract-unresolved-dependencies
- 功能: 提取 ROS Jazzy 构建中未闭环依赖的包，并生成详细的映射和去重的依赖清单文件。
使用方法：

```
rot extract-unresolved-dependencies xxx.xlsx \
    --mapping-file unresolved_dependencies_mapping.txt \
    --list-file unresolved_dependencies_list.txt
```

参数说明：
- xxxd.xlsx：输入的 Excel 文件路径。
- --mapping-file：解析后的依赖映射输出文件名，默认是 unresolved_dependencies_mapping.txt。
- --list-file：去重后的依赖项列表，默认是 unresolved_dependencies_list.txt。

🛠️ 依赖
- Python >= 3.8
- click：命令行工具库
- requests：HTTP 请求库
- beautifulsoup4：网页解析库
- PyYAML：YAML 文件处理
- networkx：依赖关系图构建
- pandas：数据处理库
- openpyxl：Excel 文件读取库

## 安装

1. 克隆仓库

```
git clone https://github.com/yourusername/ros_openeuler_tool.git
cd ros_openeuler_tool
```

2. 创建并激活虚拟环境（推荐）

使用 pyenv 或 venv 创建虚拟环境：

```
python3 -m venv venv
source venv/bin/activate
```

3. 安装工具

```
pip install --upgrade pip
pip install .
```

4. 配置环境变量

该工具依赖 GITEE_TOKEN 访问 Gitee API，请在系统中设置环境变量：

```
export GITEE_TOKEN=your_gitee_token
```

可选：如果您使用 Gitee 组织，请设置：

```
export GITEE_ORG=your_gitee_org
```

5.  验证安装

```
rot --help
```

## 项目目录结构

```
ros_openeuler_tool/
├── ros_openeuler_tool/
│   ├── __init__.py
│   ├── analyze_dependencies.py
│   ├── batch_process.py
│   ├── cli.py
│   ├── clone_repos.py
│   ├── extract_unresolved_dependencies.py
│   ├── list_missing.py
│   ├── make_public.py
│   ├── map_yum_rosdep.py  # 如果已删除，建议移除此文件
│   ├── process_packages.py
│   ├── sync_gitee.py
│   └── update_yum_mapping.py
├── setup.py
├── requirements.txt
├── README.md
├── LICENSE
├── CONTRIBUTING.md
└── ... (其他文件和目录)
```