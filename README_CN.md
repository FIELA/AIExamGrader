# AI Exam Grader - 智能阅卷助手

[![License: Non-Commercial](https://img.shields.io/badge/License-Non--Commercial-orange.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

[English](README.md) | 简体中文

---

## 📖 项目介绍

**AI Exam Grader** 是一款基于大语言模型（LLM）的智能阅卷助手，专为教师和教育工作者设计。它利用 **OpenAI (GPT-4o)** 或 **Google Gemini (Pro)** 的强大视觉理解能力，自动批改手写答题卡，生成详细的评分报告。

> [!IMPORTANT]
> **授权说明 (License Notice)**
>
> 本项目采用 **[NCEL-Strict License (Version 2.0)](./LICENSE)** 进行授权。
> 这是一个 **源码可见 (Source Available)** 但 **严格受限** 的非商业协议。
>
> 🚫 **严禁商业使用**：包括销售、订阅、赞助、**企业内部使用 (Internal Use)**、SaaS 服务及 AI 模型训练。  
> 🚫 **禁止分发修改版**：您**不**可以直接发布修改后的源代码或二进制文件（仅允许分享 Patch/Diff 文件）。  
> 🚫 **Fork 限制**：仅允许为提交 PR 而创建公开 Fork，且必须在 PR 结束后的 14 天内删除。  
> ✅ **仅限非商用**：个人学习、学术研究及非商业用途需保留完整的版权声明与许可文件。
>
> 💼 **商业授权 / Commercial License**：
> 如需商用或定制开发，请联系作者获取授权：[nicofiela@outlook.com](mailto:nicofiela@outlook.com)

## ✨ 核心功能

-   **🤖 智能阅卷引擎**
    -   **多模型支持**: 
        - 支持 OpenAI (GPT-4o 等) 及兼容 API (自定义 Base URL)
        - 支持 Google Gemini (gemini-3.0-pro 等)
    -   **OCR 智能识别**: 自动提取学生手写姓名、考号、班级等关键信息
    -   **灵活评分标准**: 支持自定义 Rubric，精准批改主观题
    -   **批量并发处理**: 多线程架构，快速完成大批量阅卷任务

    > [!NOTE]
    > 本应用高度依赖模型的**视觉理解**和**推理能力**。为获得最佳效果，建议使用更强大的模型（如 GPT-4o、Gemini 3.0 Pro）。

-   **📊 智能数据管理**
    - 链式自动校验（标准答案 → 布局 → CSV）
    - CSV 丢失自动重建
    - 增量处理，断点续传
    - 中英文目录无缝支持

-   **🔍 人工复审系统**
    - 三步复审流程（信息 → 客观题 → 主观题）
    - 双模式查看（文本/图文）
    - 智能导航与搜索
    - 完整复审历史追踪

-   **📋 全面报告 + 🌐 国际化**
    - Markdown 详细报告 + 增强CSV + 结构化JSON
    - 完整中英文支持
    - 配置方案快速切换



## 🚀 快速开始

### 1. 环境要求
-   macOS (推荐) / Windows / Linux
-   Python 3.10+

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置应用

**方法 1: 使用配置文件（推荐）**

复制示例配置文件：
```bash
cp config_example.json config.json
```

编辑 `config.json`，填入您的实际 API 密钥和文件路径。

**方法 2: 手动配置**

您也可以直接在应用界面中配置设置。

详细配置指南请参阅 [README_CONFIG.md](README_CONFIG.md)。

### 4. 运行程序
```bash
python AutoGrader.py
```

### 5. 打包应用 (可选)

**macOS:**
```bash
python build.py
```
生成的 `.app` 应用将位于 `dist/` 文件夹中。

**Windows:**
```bash
python build_windows.py
```
生成的可执行文件（`.exe`）将位于 `dist/` 文件夹中。

## 🛠️ 使用指南

### 快速工作流程（5步）

#### 步骤 1：配置 API

```
API 设置
├─ API Key: 输入您的 API 密钥
├─ 服务提供商: OpenAI / Gemini
├─ 模型名称: gpt-4o / gemini-1.5-pro
└─ Base URL: (可选)
```

#### 步骤 2：上传资源

```
资源文件
├─ 📄 评分标准: 上传试题和答案文档
├─ 📁 答题卡目录: 选择扫描图片文件夹
└─ 👥 学生名单: (可选) 上传 Excel/CSV 名单
```

#### 步骤 3：开始阅卷

点击 **"开始阅卷"** 按钮

**自动流程**：
```
检测标准答案 → 确认答案 → 检测答题卡布局 → 确认布局 → 生成 CSV → 开始评分
```

**用户交互点**：
- 🔍 **标准答案确认**：首次运行时确认 AI 提取的答案
- 🔍 **布局描述确认**：首次运行时确认答题卡结构

#### 步骤 4：人工复审

评分完成后，点击 **"复审"** 按钮

**三步复审流程**：
```
步骤 1: 核对学生基本信息
步骤 2: 核对客观题答案
步骤 3: 逐题核对主观题分数
```

**快捷操作**：
- 📝/🖼 切换文本/图文模式
- ⬅️/➡️ 上一个/下一个学生
- 🔍 搜索学生（姓名/考号）
- ✅ 确认并继续

#### 步骤 5：导出成绩

```
输出文件位置
├─ 📊 成绩汇总表.csv (在 阅卷数据/ 目录)
├─ 📝 阅卷报告.md (在 阅卷报告/ 目录，每个学生一份)
└─ 📄 成绩数据.json (在 阅卷报告/ 目录，每个学生一份)
```

### 目录结构（自动生成)

开始阅卷时，应用程序会自动创建：

```
答题卡文件夹/
├─ 阅卷数据/                    # 配置和汇总数据
│   ├─ answer_key.json         # 标准答案
│   ├─ layout_config.json      # 答题卡布局
│   └─ 成绩汇总表.csv           # 成绩汇总
│
├─ 阅卷报告/                    # 评分结果
│   ├─ 01-01.json              # 学生成绩数据
│   ├─ 01-01.md                # 学生阅卷报告
│   └─ ...
│
├─ 原始文件/                    # 原始答题卡备份
│   └─ *.jpg/png
│
├─ 成功归档/                    # 已评分答题卡
│   └─ *.jpg/png
│
└─ 失败归档/                    # 评分失败文件
    └─ *.jpg/png
```

### 数据校验流程

```
开始阅卷 → 标准答案 → 布局配置 → CSV文件 → 文件完整性 → 开始评分
   ↓          ↓          ↓         ↓          ↓           ↓
基础检查   智能提取   自动检测   智能恢复   增量处理    批量评分
```

**关键特性**：
- ✅ **链式校验**：Answer Key → Layout → CSV → Grading
- ✅ **智能恢复**：CSV 缺失时自动从 JSON 重建
- ✅ **增量处理**：只处理未完成的文件
- ✅ **自动迁移**：旧版文件自动移至新目录结构
- ✅ **用户确认**：标准答案和布局需用户确认
- ✅ **数据一致性**：评分完成后重建 CSV 确保准确

### 输出文件说明

**成绩汇总表 (CSV)**  
包含所有学生的完整成绩和信息
- 基本信息：考场、座号、姓名、考号、班级
- 成绩信息：总分、客观题、主观题、各题得分
- OCR 信息：识别的姓名、考号等
- 复审状态：未复审/已复审/已二次复审

**阅卷报告 (Markdown)**  
每个学生的详细评分报告
- 学生信息核对
- 客观题答案对照表
- 主观题逐题分析
- 总分统计

**成绩数据 (JSON)**  
结构化数据，包含所有评分细节
- 用于数据恢复
- 支持二次开发
- 复审历史记录

### 最佳实践

**评分前**
- ✅ 准备高清答题卡扫描件
- ✅ 准备完整的评分标准文档
- ✅ 检查 API 额度充足

**评分过程中**
- ✅ 保持网络连接稳定
- ✅ 不要关闭程序窗口
- ✅ 监控进度和日志

**复审时**
- ✅ 逐个核对学生信息
- ✅ 重点检查主观题分数
- ✅ 使用搜索功能快速定位

**完成后**
- ✅ 导出 CSV 到安全位置
- ✅ 备份阅卷数据文件夹
- ✅ 检查 CSV 行数与学生数是否一致

## 📂 项目结构

```
AIExamGrader/
├── AutoGrader.py           # 主应用程序
├── config_manager.py       # 配置管理
├── student_manager.py      # 学生数据库管理
├── grader_engine.py        # AI 阅卷引擎
├── review_window.py        # 人工复审界面
├── standard_answer_dialog.py # 标准答案配置
├── splash_screen.py        # 启动画面
├── translations.py         # 国际化支持
├── utils.py                # 辅助函数
├── tooltip.py              # 工具提示组件
├── theme.py                # UI 主题定义
├── generate_icon.py        # 图标生成脚本
├── config_example.json     # 示例配置文件
├── README_CONFIG.md        # 配置指南
├── requirements.txt        # 项目依赖
├── rthook_google.py        # PyInstaller 运行时钩子
├── build.py                # macOS 构建脚本
├── build_windows.py        # Windows 打包脚本
├── test_core.py            # 核心功能测试
└── test_review_logs.py     # 复审日志测试
```

## 🔧 配置文件

-   `config.json`: 主配置文件（从 `config_example.json` 创建）
-   `config_example.json`: 包含示例配置的样本文件
-   详细配置文档请参阅 [README_CONFIG.md](README_CONFIG.md)

## 🤝 贡献

欢迎贡献！详情请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 📄 许可证

本项目采用 **NCEL-Strict License (Version 2.0)** 进行授权 - 详见 [LICENSE](LICENSE) 文件。

**如需商业使用，请联系项目作者获取授权: nicofiela@outlook.com**

---

用 ❤️ 为全球教育工作者打造
