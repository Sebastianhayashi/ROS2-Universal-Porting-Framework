# 02 OBS Configuration and CLI Reference

## 1. Project Configuration (Static Setup)

本节定义了 OBS 项目的静态元数据配置。对于 ROS Jazzy 移植，正确的仓库挂载（Meta）与宏定义（Prjconf）是构建必要的一环。

### 1.1 Meta Configuration (Repositories)

* **Access:** Web UI -> `Project` -> `Meta` 或 CLI `osc meta prj <project_name>`
* **Critical:** 必须挂载 **EPOL** 源以解决 `python3-flake8` 等扩展依赖。

```xml
<project name="home:YourUser:ROS_Jazzy">
  <title>ROS Jazzy Porting for openEuler 24.03</title>
  <description>Batch build for ROS 2 Jazzy.</description>
  
  <repository name="standard">
    <path project="openEuler:24.03:LTS" repository="standard_x86_64"/>
    <arch>x86_64</arch>
    <arch>riscv64</arch>
  </repository>

  <repository name="EPOL">
    <path project="openEuler:24.03:LTS:EPOL" repository="mainline_x86_64"/>
    <arch>x86_64</arch>
    <arch>riscv64</arch>
  </repository>
</project>

```

## 2. The CLI Workflow (Cheat Sheet)

基于 `osc` 命令行工具的标准操作流。适用于批量维护、调试构建失败的场景。

### 2.1 Initialization & Auth

首次使用需配置 API 端点与凭据（写入 `~/.config/osc/oscrc`）。

```bash
# 交互式登录并列出项目
osc -A https://build.openeuler.org ls

```

### 2.2 Repository Management (Checkout/Update)

```bash
# 1. 拉取整个项目到本地 (Checkout)
# 将下载项目下的所有包目录到当前文件夹
osc co home:YourUser:ROS_Jazzy

# 2. 进入特定包目录
cd home:YourUser:ROS_Jazzy/ros-jazzy-rclcpp

# 3. 同步服务端最新变更 (Update)
# 拉取其他协作者的修改或 Web 端所做的变更
osc up

```

### 2.3 Package Operations (Edit/Upload)

```bash
# 场景 A: 提交新版本
# 1. 替换 .spec 和 .orig.tar.gz
# 2. 自动识别删除旧文件并添加新文件
osc addremove

# 场景 B: 提交变更触发构建 (Commit)
# 这会将本地修改推送到 OBS 服务端，并立即触发调度器
osc ci -m "Fix: Add patch for missing header"

```

### 2.4 Build Monitoring & Logs

```bash
# 1. 查看项目下所有包的构建结果
# 状态包括: Succeeded, Failed, Unresolvable, Disabled
osc results

# 2. 查看特定包的构建日志 (Build Logs) - 最常用！
# 格式: osc bl <project> <package> <repo> <arch>
osc bl home:YourUser:ROS_Jazzy ros-jazzy-rclcpp standard x86_64

# 3. 获取构建产物 (RPMs) 列表
osc getbinaries home:YourUser:ROS_Jazzy ros-jazzy-rclcpp standard x86_64

```

### 2.5 Local Simulation (Local Build)

在推送到服务端之前，利用本地资源模拟 OBS 构建环境（需要 root 权限及 chroot 环境支持）。

```bash
# 在本地模拟构建 (用于快速验证 Spec 语法和基本依赖)
# 语法: osc build <repo_name> <arch> <spec_file>
# --clean: 构建前清理缓存
# --no-verify: 跳过签名检查
osc build standard x86_64 ros-jazzy-rclcpp.spec --clean --no-verify

```

## 3. Web UI & Project Setup

对于项目的初始化创建和源的配置，Web UI 通常比 CLI 更直观。

### 3.1 Project Creation

* **Entry:** 登录后点击顶部导航栏的 `Home Project`。
* **Subproject:** 为了环境隔离，强烈建议创建子项目。
* *Path:* `Home Project` -> `Subprojects` -> `Add New Subproject`
* *Naming:* `ROS_Jazzy` (Full name: `home:User:ROS_Jazzy`)



### 3.2 Repositories Configuration (关键步骤)

OBS 需要知道从哪里获取基础包（如 gcc, cmake, python3）。

1. 进入项目页面 -> 点击 `Repositories` 标签。
2. 点击 `Add from a Distribution`。
3. 在列表中选择 `openEuler:24.03:LTS`。
4. **Important:** 默认只挂载 `standard` 库。
* 构建 ROS 通常需要 `EPOL`。
* 需手动点击 `Add Repository` -> `Advanced` -> 手动输入 EPOL 路径（参考 1.1 节 XML）。



### 3.3 Build Status Reference

在 Web 端右侧面板可直观查看构建状态：

* **succeeded:** 构建成功，可下载 RPM。
* **failed:** 构建失败（点击查看 Log，搜索 `error:`）。
* **unresolvable:** 依赖缺失。
* *Check:* 是否挂载了 EPOL？
* *Check:* Spec 中的 `BuildRequires` 包名是否写错？


* **excluded:** 架构不支持（检查 Spec 中的 `ExcludeArch`）。
