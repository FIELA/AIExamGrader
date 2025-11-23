# AI Exam Grader (Pro) - 智能阅卷助手

[![License: Non-Commercial](https://img.shields.io/badge/License-Non--Commercial-orange.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

简体中文 | [English](README.md)

---

## 📖 项目介绍

**AI Exam Grader** 是一款基于大语言模型（LLM）的智能阅卷助手，专为教师和教育工作者设计。它利用 **OpenAI (GPT-4o)** 或 **Google Gemini (Pro)** 的强大视觉理解能力，自动批改手写答题卡，生成详细的评分报告。

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
    -   自动汇总生成包含每道题得分详情的 CSV 成绩单。
-   **国际化支持**: 全面支持简体中文和英文界面切换。

### 新功能 (v1.1)

-   **🚀 配置文件快速切换**: 保存并快速切换不同的阅卷配置
    -   保存多个配置文件，包含不同的 API 密钥、模型和文件路径
    -   通过侧边栏下拉菜单快速切换
    -   启动时自动加载上次使用的配置
    -   非常适合管理多场考试或在不同 API 提供商之间切换
    
-   **📊 增强的进度跟踪**: 
    -   实时进度显示，精确的文件计数
    -   分阶段处理（主文件夹 → 失败重试 → 最终验证）
    -   预计剩余时间（ETR）更新
    -   最终验证计数，确保质量

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

编辑 `config.json`，填入您的实际 API 密钥和文件路径。示例文件包含两个样本配置供您自定义。

**方法 2: 手动配置**

您也可以直接在应用界面中配置设置（会自动保存）。

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
python build.py
```
生成的可执行文件（文件夹形式）将位于 `dist/` 文件夹中。

## 🛠️ 使用指南

### 1. 配置设置

#### 使用配置文件
-   **选择配置**: 从下拉菜单中选择已保存的配置
-   **保存配置**: 点击 💾 保存，将当前设置保存为新配置
-   **删除配置**: 选择配置后点击 🗑️ 删除

#### 手动配置
-   **API Key**: 在侧边栏输入您的 OpenAI 或 Google Gemini API Key
-   **服务提供商**: 选择您使用的服务商
-   **模型**: 选择模型（如 `gpt-4o`、`gemini-2.5-pro-maxthinking`）
-   **Base URL**: （可选）用于自定义 API 端点

### 2. 准备资源
-   **评分标准 (Rubric)**: 包含题目、标准答案和评分规则的文本文件
-   **答题卡目录**: 包含学生答题卡图片的文件夹（支持 .jpg、.png、.jpeg）
-   **学生名单**: （可选）Excel/CSV 学生名单，用于信息验证

### 3. 开始阅卷
-   点击 **▶️ 开始阅卷**
-   系统将：
    1. 检测答题卡布局（首次使用，结果会被保存以供重复使用）
    2. 并发处理所有待处理文件
    3. 自动重试失败的文件
    4. 验证最终计数
-   界面会实时显示进度条和预计剩余时间（ETR）

### 4. 人工复审
-   阅卷完成后，点击 **🔍 复审**
-   核对学生基本信息、客观题得分和主观题批改情况
-   如有需要可直接修改
-   系统会自动更新报告和 CSV 汇总表

### 5. 查看结果
-   **个人报告**: 位于 `[答题卡目录]/reports/` 下的 `.md` 和 `.json` 文件
-   **成绩汇总**: 位于答题卡目录下的 `成绩汇总表.csv`（或 `Grade_Summary.csv`）

## 📂 项目结构

```
AIExamGrader/
├── AutoGrader.py           # 主应用程序
├── config_manager.py       # 配置管理
├── student_manager.py      # 学生数据库管理
├── grader_engine.py        # AI 阅卷引擎
├── review_window.py        # 人工复审界面
├── translations.py         # 国际化支持
├── config_example.json     # 示例配置文件（含配置切换）
├── README_CONFIG.md        # 配置指南
├── requirements.txt        # 依赖列表
└── build.py               # 应用打包脚本
```

## 🔧 配置文件

-   `config.json`: 主配置文件（从 `config_example.json` 创建）
-   `config_example.json`: 包含示例配置的样本文件
-   详细配置文档请参阅 [README_CONFIG.md](README_CONFIG.md)

## 🤝 贡献

欢迎贡献！详情请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 📄 许可证

本项目采用非商业教育许可证（NCEL-1.0）- 详情请参阅 [LICENSE](LICENSE) 文件。

**如需商业使用，请联系项目作者获取授权。**

## 💬 联系方式

如有问题、建议或商业授权咨询，请联系：
- **Email**: [邮箱地址]
- **GitHub Issues**: [项目 Issues 页面]

---

用 ❤️ 为全球教育工作者打造
