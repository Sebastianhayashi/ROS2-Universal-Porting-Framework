# 为什么放弃移植工具链？

初期在尝试少量的 ament 系列包构建时，尝试过使用同事过往的经验，即移植 rosdep bloom 等 ROS 官方工具链。

而为什么最终没有采取移植的方案，基于**工程死锁（Deadlock）与底层兼容性（RPM Lineage）**这两方面的因素判断决定去做自动化而不是去做依赖映射表的维护。

## 依赖死锁

在最开始修改 rosdep 源码（也就是做了一个 rosdep-oe）马上就遇到了  python 包管理机制的问题。

手动编译并且安装 rosdep-oe 之后，pip 马上就解析 setup.py 来安装 bloom 官方版（即没有修改过源码的 bloom），所以依旧是无法认出 openEuler 这个系统。

所以要做的话，要连带 fork bloom 的源并且修改。但是即使 fork 了 bloom 发现，bloom 0.25 与 rosdep 0.24 存在 API 不兼容，导致还需 Fork rosdistro。

最终，为了适配一个工具，被迫维护整个工具链的 Fork 分支。这违背了自动化工程“轻量化”的初衷。

## 系统伪装的合理性

既然“硬移植”走不通，就开始寻找有没有更加合理的方案，可是重新调研 ROS 相关的内容，在 ROS [官方文档](https://wiki.ros.org/ROS/EnvironmentVariables?utm_source=chatgpt.com#ROS_OS_OVERRIDE:~:text=that%20language%27s%20bindings.-,ROS_OS_OVERRIDE,-Format%3A%20%22OS_NAME%3AOS_VERSION_STRING)中发现一以下内容：

```
ROS_OS_OVERRIDE
Format: "OS_NAME:OS_VERSION_STRING:OS_CODENAME" This will force it to detect Ubuntu Bionic:

export ROS_OS_OVERRIDE=ubuntu:18.04:bionic
If defined, this will override the autodetection of an OS. This can be useful when debugging rosdep dependencies on alien platforms, when platforms are actually very similar and might need be forced, or of course if the autodetection is failing.
```

于是选择转向了 ROS_OS_OVERRIDE=rhel:9 的伪装方案。这一方案的安全性并非建立在运气的沙滩上，而是建立在 openEuler 与 RHEL 同源的 RPM 生态之上。

主要是因为考虑到同源的包管理生态 (Shared RPM Lineage)，openEuler、RHEL、CentOS 均属于 RPM 系 Linux 发行版。这意味着它们共享核心的构建逻辑和包命名惯例。

ROS 依赖的系统包（如 cmake, python3, gcc）在 RHEL 9 和 openEuler 上的命名重合度高达 90% 以上。伪装成 RHEL，本质上是复用 RHEL 庞大且成熟的 rosdep 规则库，从而省去了从零维护 openEuler 映射表的巨大成本。

bloom 的核心产物是 .spec 文件。RHEL 和 openEuler 的 rpmbuild 工具对 .spec 语法的解析（如 %build, %install, BuildRequires）是通用的。

但是必须讲清楚的是，伪装发生在构建阶段（Build-time），而非运行阶段（Run-time）。虽然 openEuler 与 RHEL 9 的 glibc 版本接近，但这并不是伪装成功的核心。流水线是从 Source Code 生成 .orig.tar.gz 并重新编译。我们只需要 源码兼容性 (Source Compatibility)。只要 openEuler 上的编译器和系统库满足 ROS 源码的最低要求，伪装就是安全的。

## 动态修复闭环

但是系统伪装也有系统伪装的问题，美，它会带来少量的“偏差”（Masquerade Leakage）。我们的架构通过 “动态修复 (Dynamic Fixing)” 机制来管理这些偏差。

| 偏差类型 | 风险描述 | 我们的解决方案 (Automated Fix) |
| :--- | :--- | :--- |
| **基础设施差异** | RHEL 特有的 `redhat-rpm-config` 包在 openEuler 上不存在，导致构建初期报错。 | **Spec Sanitizer**: 正则匹配并移除该 `BuildRequires`。 |
| **命名规范漂移** | Python 包名宏不一致（如 `python3-` vs `python%{py3_ver}-`）。 | **Spec Sanitizer**: 建立正则替换表，自动修正包名宏。 |
| **中间件空指** | RHEL 规则指向闭源商业软件（如 `rti-connext-dds`），导致解析超时。 | **Env Strategy**: 强制指定 `RMW_IMPLEMENTATION=rmw_fastrtps_cpp` 使用开源实现。 |

这种 “伪装（获取通用规则）+ 修复（修正特定偏差）” 的组合策略，将“维护整个系统的依赖表”这一高难度工作，降维成了“仅维护几个正则替换规则”的低成本工作。

## 结论

放弃工具链移植，是因为 “Fork 整个生态” 对于我目前的项目而言具有不可持续性，且效益低。 选择系统伪装，是因为洞察了 “RPM 同源性” 的技术红利。