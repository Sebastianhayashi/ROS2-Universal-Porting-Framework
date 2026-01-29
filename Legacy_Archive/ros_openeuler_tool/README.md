# 📂 Legacy Archive: ROS OpenEuler Tool (The Pipeline Prototype)

> **⚠️ Deprecated / 已废弃**
> 本项目是 **EulerROS-Automation** 架构早期的流水线雏形（Prototype）。
> 它的核心逻辑是试图构建一个**全能型工具（Monolith）**，来自动化维护 `rosdep` 的 YAML 依赖映射。由于其高昂的维护成本和代码侵入性，已被现有的“动态清洗”架构取代。

---

## 🧐 What was this? (这是什么)

这是我们对自动化构建流水线的**第一次尝试**。

与现在的“轻量级脚本组”不同，这个工具试图通过一个复杂的 Python CLI (`rot`) 解决所有问题：从克隆代码、分析依赖、同步 Gitee 到生成 RPM Spec。

它代表了我们在 **Phase 1** 的核心设计思路：
**"如果我们能编写脚本，自动扫描 openEuler 的 YUM 仓库，并自动生成 rosdep 的 YAML 映射文件，问题不就解决了吗？"**

## ❌ The "Automated Mapping" Trap (自动化映射陷阱)

本工具最大的设计败笔在于 `rot update-yum-and-mapping` 这一功能。

我们试图建立一条 **"Active Sync" (主动同步)** 流水线：

1.  **Scan**: 扫描 openEuler 官方仓库的所有包名。
2.  **Match**: 尝试通过模糊匹配算法，将 ROS 的 Key (如 `python3-numpy`) 映射到 YUM 包名。
3.  **Generate**: 自动生成一份巨大的 `rosdep.yaml` 文件。
4.  **Patch**: 将这份文件注入到构建系统中。

### Why it failed? (为何失败)

尽管代码写得很复杂，但它并没有解决核心矛盾，反而制造了新的问题：

* **复杂度爆炸 (Complexity Explosion)**: 为了保证映射准确，我们不得不编写大量的特例规则（Heuristics）。代码库中充斥着针对特定包名的 `if/else` 补丁。
* **脆弱的自动化 (Brittle Automation)**: openEuler 仓库中任何包名的微小变动（甚至只是后缀变化）都会导致自动化脚本生成的映射失效，进而导致整个构建流水线崩溃。
* **侵入性 (Invasiveness)**: 这个工具强依赖于对 ROS 源码结构的特定假设，且生成的 Spec 文件高度定制化，无法通用。

## 🛠️ Evolution: From "Complex Tool" to "Simple Logic"

这个仓库证明了：**试图维护数据的自动化，远不如处理数据的自动化有效。**

| Feature | 🔴 Legacy (This Tool) | 🟢 Current Architecture |
| :--- | :--- | :--- |
| **Strategy** | **Auto-generate Static Mappings** | **Dynamic Sanitization** |
| **Dependency Logic** | 试图维护一张完美的 Excel/YAML 表 | 允许生成错误的 Spec，后期用正则修正 |
| **Architecture** | Monolithic (集成克隆/分析/上传) | Decoupled (拆分为独立的小脚本) |
| **Maintainability** | Low (需要维护复杂的 Python 逻辑) | High (仅需维护简单的正则规则) |

---

## 📜 Original Documentation

关于该工具的具体命令和原始设计文档，请参阅归档文件：

👉 **[README_OLD.md](./README_OLD.md)**

*(原 README 中详细描述了 `update-yum-and-mapping`, `batch-process` 等命令，这些现已作为反面案例供参考)*