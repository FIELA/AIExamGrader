# AI Exam Grader - 智能阅卷助手

[![License: Non-Commercial](https://img.shields.io/badge/License-Non--Commercial-orange.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

简体中文 | [English](README.md)

---

## 📖 项目介绍

**AI Exam Grader** 是一款基于大语言模型（LLM）的智能阅卷助手，专为教师和教育工作者设计。它利用 **OpenAI (GPT-4o)** 或 **Google Gemini (Pro)** 的强大视觉理解能力，自动批改手写答题卡，生成详细的评分报告。

> [!IMPORTANT]
> **授权说明 (License Notice)**
>
> 本项目采用 **[NCEL-Strict+ License (Version 1.3)](./LICENSE)** 进行授权。
> 这是一个 **源码可见 (Source Available)** 但 **严格受限** 的非商业协议。
>
> 🚫 **严禁商业使用**：包括销售、订阅、赞助、**企业内部使用 (Internal Use)**、SaaS 服务及 AI 模型训练。
> 🚫 **禁止分发修改版**：您**不**可以直接发布修改后的源代码或二进制文件（仅允许分享 Patch/Diff 文件）。
> ✅ **仅限非商用**：个人学习、学术研究及非商业用途需保留完整的版权声明与许可文件。
>
> 💼 **商业授权 / Commercial License**：
> 如需商用或定制开发，请联系作者获取授权：[nicofiela@outlook.com](mailto:nicofiela@outlook.com)

## ✨ 核心功能

### 基础能力

-   **多模型支持**: 
    -   支持 OpenAI（GPT-4o、GPT-4o-mini 等）及 OpenAI 兼容格式的 API（可自定义 Base URL）
    -   支持 Google Gemini（gemini-2.5-pro、gemini-2.0-flash 等）
    -   轻松切换不同服务商和模型
    
    > [!NOTE]
    > 本应用高度依赖模型的**视觉理解**和**推理能力**。为获得最佳效果，建议使用更强大的模型（如 GPT-4o、Gemini 2.5 Pro）。
    
-   **智能识别**: 利用 OCR 技术自动识别学生手写姓名、考号、班级等关键信息。
-   **灵活评分**: 支持自定义评分标准（Rubric），精准批改主观题。
-   **批量处理**: 多线程并发处理，快速完成大批量阅卷任务。
-   **人工复审**: 提供专用的人工复审界面，方便教师核对、校验和修正 AI 评分结果。
-   **数据校验**: 自动验证 OCR 识别信息与学生名单的一致性，确保成绩归属准确。
-   **详细报告**:
    -   为每个学生生成 Markdown 格式的详细评分报告。
    -   **增强的 CSV 导出**: 
        -   包含主观题（大题/小题）和客观题（答案/得分）的详细分值。
        -   根据应用语言自动生成双语表头（中/英）。
        -   自定义列排序，优化阅读体验。
-   **自动化预检查**: 阅卷前自动检测并生成标准答案、布局配置和 CSV 表头，防止运行错误。
-   **国际化支持**: 全面支持简体中文和英文界面切换。

### 新功能 (v1.2)

-   **🚀 配置文件快速切换**: 保存并快速切换不同的阅卷配置。
-   **📊 增强的进度跟踪**: 实时进度显示、分阶段处理和 ETR 更新。
-   **🎨 UI 焕新**: 现代界面，改进的复审窗口（滚动控制、光标修复）和安全退出机制。

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

### 1. 配置设置
... (同上)

## 📂 项目结构

```
AIExamGrader/
├── AutoGrader.py           # 主应用程序
├── config_manager.py       # 配置管理
├── student_manager.py      # 学生数据库管理
├── grader_engine.py        # AI 阅卷引擎
├── review_window.py        # 人工复审界面
├── translations.py         # 国际化支持
├── utils.py                # 辅助函数
├── theme.py                # UI 主题定义
├── config_example.json     # 示例配置文件
├── README_CONFIG.md        # 配置指南
├── requirements.txt        # 依赖列表
├── build.py                # macOS 打包脚本
└── build_windows.py        # Windows 打包脚本
```

## 🔧 配置文件

-   `config.json`: 主配置文件（从 `config_example.json` 创建）
-   `config_example.json`: 包含示例配置的样本文件
-   详细配置文档请参阅 [README_CONFIG.md](README_CONFIG.md)

## 🤝 贡献

欢迎贡献！详情请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 📄 许可证

本项目采用 **NCEL-Strict+ License (Version 1.1)** - 详情请参阅 [LICENSE](LICENSE) 文件。

**如需商业使用，请联系项目作者获取授权: nicofiela@outlook.com**

---

用 ❤️ 为全球教育工作者打造
