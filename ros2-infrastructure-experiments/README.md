# 🧪 ROS 2 Infrastructure Experiments (The "Golden Samples")

>  Manual Proof of Concept (人工概念验证)
> 本目录包含了项目初期**经过人工验证、验证成功的软件包**。
> 这里的每一个 Spec 文件都代表了在自动化流水线建立之前，我们在 openEuler 上成功跑通的标准。

---

## 🧐 What is this? (这是什么)

在编写任何自动化脚本之前，我们必须回答一个核心问题：
**“ROS 2 的核心包到底能不能在 openEuler 上跑起来？如果能，Spec 文件需要怎么改？”**

这个目录就是围绕这个问题展开的。

这里存放的是我们在项目 **Phase 0** 阶段，通过手动或半自动方式，对 ROS 2 基础架构包（Infrastructure Packages）进行逐一攻关的产物。它们不是草稿，而是**达到了可构建标准的先行验证件**。

## 🧗 The Process: From "Manual" to "Automated"

这里的每一个包都经历了完整的**人工闭环流程**，正是这个流程的成功，赋予了我们后续开发自动化工具的信心：

1.  **Learning Bloom**: 首次尝试运行 Bloom，生成原始 Spec。
2.  **Manual Debugging**: 发现报错（如依赖名错误、宏缺失），手动修改 Spec 文件进行“打磨”。
3.  **Build Verification**: 在 openEuler 环境中反复编译，直到 RPM 构建成功。
4.  **Upstream Check**: 将验证无误的源码和 Spec 推送至 Gitee 进行托管。

**结论：**
只有当这里的手动构建成功后，我们才初步摸清了整个打包的流程以及打包的文件夹结构等各项标准，进而才敢启动大规模的批量自动化构建。

## 📂 The "Template" Artifacts (样板产物)

这些文件是后续自动化流水线（Pipeline）模仿的对象。我们的自动化脚本（Sanitizer）的目标，就是自动生成出和这里一样高质量的 Spec 文件。

```text
ros2-infrastructure-experiments/
├── ament-cmake-auto/
│   ├── ros-jazzy-ament-cmake-auto.spec  # 【已验证】经过修正，可成功构建的 Spec
│   └── ros-jazzy-ament-cmake-auto.tar.gz
├── Gazebo/
│   └── ... 
└── ...

```

## 📉 Significance (重要性)

**为后续的构建工作确立了一个可构建标准。**

---

### 🚀 Usage Status

* **Deliverable**: ✅ 这里的代码具备交付质量，可以直接用于构建。
* **Reference**: 它们是编写自动化规则的**原始依据**。

> *"We built these by hand first, so the robots would know what to do later."*
> *(我们先手工造出了这些样板，机器才知道该怎么批量生产。)*

