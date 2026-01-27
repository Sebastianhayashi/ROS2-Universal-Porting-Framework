# 03 快速上手指南 (Quick Start Guide)

**文档状态:** Released
**目标:** 10分钟内完成从源码拉取到 RPM 资产生成的全流程。
**环境:** 推荐 openEuler 24.03 LTS (或兼容的 Linux 环境)。

## 1. 环境准备 (Prerequisites)

### 1.1 系统基础依赖

确保安装了基础的构建工具和 Python 开发库。

```bash
sudo dnf install -y git gcc gcc-c++ python3-devel python3-pip

```

### 1.2 Python 工具链 (Critical)

我们依赖 ROS 官方的打包工具链。
**注意：** 必须锁定 `empy` 版本并降级 `setuptools` 以兼容 Bloom 和 Colcon。

```bash
# 1. 创建并激活虚拟环境 (推荐)
python3 -m venv ~/ros-rpm-venv
source ~/ros-rpm-venv/bin/activate

# 2. 解决兼容性问题 (Setuptools < 80, EmPy == 3.3.4)
pip install -U pip
pip install "setuptools<80"

# 3. 安装核心工具
# bloom: 生成 Spec 模板
# vcstool: 拉取多仓库源码
pip install bloom empy==3.3.4 rosdep vcstool colcon-common-extensions PyYAML

```

### 1.3 环境变量 (Gitee Token)

流水线脚本需要通过 API 自动创建仓库并推送代码。请确保该 Token 拥有 `repo` (Admin) 权限。

```bash
export GITEE_TOKEN="your_private_token_here"
export GITEE_ORG="openeuler-ros-jazzy" # 你的目标组织名

```

## 2. 执行流水线 (Pipeline Execution)

请确保位于项目根目录。流程分为**拉取、生成、推送**三步。

```mermaid
graph LR
    A[1. 拉取源码 vcs import] --> B[2. 动态生成 stage.py]
    B --> C[3. 推送云端 upload_repos.py]

```

### Step 1: 拉取源码 (Fetch Sources)

直接使用 ROS 2 Jazzy 官方定义的源列表。

```bash
mkdir -p src repos scripts logs

# 1. 获取官方 repos 文件
wget https://raw.githubusercontent.com/ros2/ros2/jazzy/ros2.repos -O ros2.repos

# 2. 多线程拉取源码 (需确保网络通畅)
vcs import src < ros2.repos

```

### Step 2: 生成 Spec 与清洗 (Generate & Sanitize)

这是流水线的核心。脚本会自动执行“系统伪装”并应用正则修复。

```bash
# 1. 拓扑归档
# 将源码按依赖顺序打包为 .orig.tar.gz，仅处理到 desktop 变体
python3 scripts/split.py --up-to desktop

# 2. 生成与动态修复
# - 注入 ROS_OS_OVERRIDE=rhel:9
# - 修复 openEuler 特有的包名差异 (opencv, python路径等)
python3 scripts/stage.py

```

### Step 3: 推送至云端 (Upload & Trigger)

将生成的静态资产（Spec + Tarball）推送至 Gitee，触发 OBS/EulerMaker 构建。

```bash
# 自动初始化 git 仓并推送
python3 scripts/upload_repos.py --org $GITEE_ORG

```

## 3. 结果验证 (Verification)

### 3.1 本地产物检查

检查 `repos/` 目录下是否生成了对应的 Spec 文件，且已包含修复逻辑。

```bash
# 检查是否注入了路径宏
grep "_prefix" repos/ros-jazzy-rclcpp/ros-jazzy-rclcpp.spec
# 预期输出: %define _prefix /opt/ros/jazzy

```

### 3.2 导入清单检查

检查是否生成了用于 EulerMaker 批量导入的 YAML 清单。

```bash
cat package_repos.yaml
# 预期内容: 包含所有 200+ 个包的 git 仓库地址列表

```