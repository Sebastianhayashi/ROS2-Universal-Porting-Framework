# 目标范围与依赖分析报告

## 1. Target Definition (目标定义)

本项目的核心是将 ROS2 的最新长期支持版本 Jazzy（LTS）完整迁移至 openEuler 操作系统，建立一套可复现、自动化的构建流水线。

### 1.1 Target OS & Architecture

- Operating System: openEuler 24.03 LTS.

- Architectures:

  - x86_64
  - RISC-V (riscv64)
  - Aarch64

### 1.2 Target ROS Version

- Version: ROS 2 Jazzy Jalisco (LTS).

- Rationale: 适配最新 LTS 版本，确保与 openEuler 24.03 LTS 的生命周期重叠，提供长期的稳定支持。

### 1.3 Variant Selection Strategy (变体选择与边界控制)

主要的策略是以 Desktop 为边界，如果 Desktop 能够稳定构建才更进一步的考虑是否往更进一步的模拟器（如 Gazebo、Moveit）进行构建。

目标设定为 `ros-desktop` 主要是因为开发者的甜蜜点（Sweet Spot）。它包含了通信核心、几何库以及 `rviz`、`rqt` 等必要的 GUI 调试工具，足以支撑 90% 的常规机器人开发与算法验证工作。

基于我们在 openEuler 上移植 ROS Humble 的历史经验，Gazebo 仿真器与 MoveIt 运动规划库涉及极其复杂的图形栈与物理引擎依赖（如 Ogre, Dart 等）。这些组件并非“顺手”可以解决的事情，而本阶段的主要目标是跑通 ROS 基础链路，加入高复杂仿真组件会拖慢核心功能的交付。

Gazebo 等仿真组件在后续会被列为单独构建项目，不混入本项目的主线中。

## 2. Scope Layering: Adhering to REP 2001 (移植范围：遵循 REP 2001 标准)

## 2.1 The Standard Hierarchy (标准分层结构)
- L1: ros_core (Minimal System)

  - Official Definition: The absolute minimum requirements to run a ROS 2 application.

  - Scope: 包含构建系统 (ament, colcon)、客户端库 (rclcpp, rclpy) 以及通信中间件。这是 ROS 的“内核”。

- L2: ros_base (Robot Variant)

  - Official Definition: The "Robot" variant. It extends ros_core with libraries generally needed for a robot but does not require a graphical interface.

  - Scope: 引入了 geometry (几何库), kdl (运动学), urdf (机器人描述) 以及 tf2 (坐标变换)。

- L3: ros_desktop (Development Variant)

  - Official Definition: The entry point for users running ROS 2 on a development machine.

  - Scope: 在 ros_base 基础上增加了可视化工具 (rviz2)、交互演示 (turtlesim) 以及入门教程。这是验证图形栈（OpenGL/Wayland）兼容性的标准集合。

### 2.2 Compliance Verification (合规性验证策略)

为了确保我们的构建结果符合官方定义，我们采取了以下验证路径：

我们直接拉取 ROS 官方仓库 ros2/variants 中的 package.xml 定义。

既然 ros_desktop 依赖 ros_base，ros_base 依赖 ros_core，我们通过递归解析依赖树，生成了一份**“标准白名单”**。

我们的 263+ 个最终产物，能够完整覆盖 ros_desktop 变体所需的所有硬性依赖 (Hard Dependencies)，确保了在 openEuler 上 dnf install ros-jazzy-desktop 的体验与 Ubuntu 上完全一致。

## 3. Dependency Landscape & Challenges (依赖图谱与挑战)

将移植过程中遇到的 500+ 个依赖问题归纳为以下三类系统级差异 (Systemic Divergences)。这些差异无法通过简单的重编译解决，而是驱动我开发“动态修复流水线”的核心原因。

### 3.1 Diagnosis of System Packaging Irregularities (系统打包缺陷诊断)

在构建过程中发现，部分 openEuler 软件包并未严格遵循 RPM 标准的拆分规范（Packaging Guidelines），导致标准依赖解析链条断裂。

ROS 的构建依赖链明确指向 `opencv-devel`（开发头文件包）。但在构建初期，`rosdep` 始终报错缺包，尽管系统已安装了 `opencv`。

后来到了 openeuler-src（即 openEuler 源码仓）源码级溯源分析 (Root Cause Analysis)后，我发现这是一个上游打包规范性问题——openEuler 在打包 OpenCV 时未进行标准的 libs 与 devel 拆分，而是将头文件混入了主包或使用了非标准的命名逻辑。这在 RPM 生态中属于严重的规范性缺陷。

修改自动化流水线的映射逻辑，在 Spec 生成阶段强制将 `opencv-devel` 依赖重定向为系统实际存在的包名，确保流水线不中断。

这一点至关重要。我们将该问题整理为详细的 Bug Report 反馈给 openEuler 社区，指出了其打包规范的缺失。

### Infrastructure & Build Toolchain Gaps (构建基建缺失)

openEuler 的构建环境（EulerMaker/OBS）相比 RHEL 更加精简，缺少部分 RHEL 特有的“元工具包”。

Bloom 生成的 Spec 模板会默认注入 RHEL 的构建依赖，这些依赖在 openEuler 上并不存在。

比如说redhat-rpm-config: 这是 RHEL 用于配置编译参数的包，在 openEuler 上不存在且不需要。python-setuptools: ROS Jazzy 依赖特定的构建工具版本，而 OS 提供的版本可能过高或过低，导致 colcon 构建报错。

这会导致构建在环境初始化阶段直接报错（Nothing provides...）。

### 3.3 Middleware Policy Conflicts (中间件策略冲突)

ROS 2 的标准依赖树包含商业闭源中间件，而 openEuler 社区仓库严格遵循开源协议。

ROS 默认依赖 rti-connext-dds (商业软件)。而openEuler 开源仓库中是不会有该包的.

我们必须在构建策略层面对中间件进行裁剪 (Pruning)，强制指定 rmw_fastrtps_cpp (FastDDS) 作为唯一默认中间件，剔除闭源依赖。

## 4. 结论

通过“自底向上”的增量验证策略，我们成功在 openEuler 上构建了功能完备的 ros-desktop 环境。