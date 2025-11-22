# AI Exam Grader (Pro) - 智能阅卷助手

[![License: Non-Commercial](https://img.shields.io/badge/License-Non--Commercial-orange.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

简体中文 | [English](README.md)

---

## 📖 项目介绍

**AI Exam Grader** 是一款基于大语言模型（LLM）的智能阅卷助手，专为教师和教育工作者设计。它利用 **OpenAI (GPT-4o)** 或 **Google Gemini (Pro)** 的强大视觉理解能力，自动批改手写答题卡，生成详细的评分报告。

## ✨ 核心功能

-   **多模型支持**: 
    -   支持 OpenAI（GPT-4o、GPT-4o-mini 等）及 OpenAI 兼容格式的 API（可自定义 Base URL）
    -   支持 Google Gemini（1.5 Pro、2.0 Flash 等）
    -   轻松切换不同服务商和模型
-   **智能识别**: 利用 OCR 技术自动识别学生手写姓名、考号、班级等关键信息。
-   **灵活评分**: 支持自定义评分标准（Rubric），精准批改主观题。
-   **批量处理**: 多线程并发处理，快速完成大批量阅卷任务。
-   **人工复审**: 提供专用的人工复审界面，方便教师核对、校验和修正 AI 评分结果。
-   **数据校验**: 自动验证 OCR 识别信息与学生名单的一致性，确保成绩归属准确。
-   **详细报告**:
    -   为每个学生生成 Markdown 格式的详细评分报告。
    -   自动汇总生成包含每道题得分详情的 CSV 成绩单。
-   **国际化支持**: 全面支持简体中文和英文界面切换。

## 🚀 快速开始

### 1. 环境要求
-   macOS (推荐) / Windows / Linux
-   Python 3.10+

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置应用
复制 `config.json.example` 为 `config.json` 并填入您的 API 凭证：
```bash
cp config.json.example config.json
```
然后编辑 `config.json` 添加您的 API Key。

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
生成的 `.exe` 可执行文件（文件夹形式）将位于 `dist/` 文件夹中。

## 🛠️ 使用指南

### 1. 配置设置
-   **API Key**: 在侧边栏输入您的 OpenAI 或 Google Gemini API Key。
-   **服务提供商**: 选择您使用的服务商 (OpenAI/Gemini)。
-   **模型**: 选择模型 (如 `gpt-4o`, `gemini-1.5-pro`)。

### 2. 准备资源
-   **评分标准 (Rubric)**: 上传包含题目、标准答案和评分规则的文本文件。
-   **答题卡目录**: 选择包含学生答题卡图片的文件夹 (支持 .jpg, .png)。
-   **学生名单**: (可选) 上传 Excel/CSV 名单用于信息验证。

### 3. 开始阅卷
-   点击 **开始阅卷** 按钮。
-   系统将并发处理图片。
-   界面会实时显示进度条和预计剩余时间 (ETR)。

### 4. 人工复审
-   阅卷完成后，您可以进入 **人工复审** 模式。
-   核对学生基本信息、客观题得分和主观题批改情况。
-   如有需要可直接修改，系统会自动更新报告和 CSV 汇总表。

### 5. 查看结果
-   **个人报告**: 位于 `[答题卡目录]/reports/` 下的 `.md` 文件。
-   **成绩汇总**: 位于答题卡目录下的 `成绩汇总表.csv`。

## 📄 许可证

本项目采用非商业教育许可证 - 详情请参阅 [LICENSE](LICENSE) 文件。

**如需商业使用，请联系 JASim 获取授权。**
