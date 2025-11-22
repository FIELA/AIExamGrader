# AI Exam Grader (Pro)

[![License: Non-Commercial](https://img.shields.io/badge/License-Non--Commercial-orange.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

[简体中文](README_CN.md) | English

---

## 📖 Introduction

**AI Exam Grader** is an intelligent grading assistant powered by Large Language Models (LLMs), designed for teachers and educators. It leverages the visual understanding capabilities of **OpenAI (GPT-4o)** or **Google Gemini (Pro)** to automatically grade handwritten exam papers and generate detailed reports.

## ✨ Features

-   **Multi-Model Support**: Seamlessly switch between OpenAI GPT-4o and Google Gemini 1.5/2.0 Pro.
-   **Smart Recognition**: Automatically extracts handwritten student names, IDs, and class information using OCR.
-   **Flexible Grading**: Supports custom rubrics for precise subjective question grading.
-   **Batch Processing**: Multi-threaded processing for high-speed grading of large batches.
-   **Manual Review**: A dedicated interface to review, verify, and correct AI grading results.
-   **Data Verification**: Automatically validates OCR-extracted info against your student database.
-   **Detailed Reporting**:
    -   Generates individual Markdown grading reports for each student.
    -   Automatically compiles a CSV summary with detailed scores for every question.
-   **Internationalization**: Fully localized interface in English and Simplified Chinese.

## 🚀 Quick Start

### 1. Requirements
-   macOS (Recommended) / Windows / Linux
-   Python 3.10+

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Application
Copy `config.json.example` to `config.json` and update with your API credentials:
```bash
cp config.json.example config.json
```
Then edit `config.json` to add your API key.

### 4. Run Application
```bash
python AutoGrader.py
```

### 5. Build App (Optional)

**macOS:**
```bash
python build.py
```
The `.app` bundle will be generated in the `dist/` folder.

**Windows:**
```bash
python build.py
```
The executable folder will be generated in the `dist/` folder.

## 🛠️ Usage Guide

### 1. Configuration
-   **API Key**: Enter your OpenAI or Google Gemini API Key in the sidebar.
-   **Provider**: Select your preferred service provider.
-   **Model**: Choose the model (e.g., `gpt-4o`, `gemini-1.5-pro`).

### 2. Prepare Resources
-   **Rubric**: A text file containing questions, standard answers, and scoring rules.
-   **Exam Folder**: A folder containing images of student exam papers (supported formats: .jpg, .png).
-   **Student List**: (Optional) An Excel/CSV file containing student roster for validation.

### 3. Start Grading
-   Click **Start Grading**.
-   The system will process images in parallel.
-   Real-time progress and Estimated Time Remaining (ETR) will be displayed.

### 4. Manual Review
-   After grading, you can enter **Manual Review** mode.
-   Verify student information, objective scores, and subjective grading.
-   Make corrections if necessary; the system will update reports and the CSV summary automatically.

### 5. View Results
-   **Reports**: Individual `.md` files in `[Exam Folder]/reports/`.
-   **Summary**: A consolidated `成绩汇总表.csv` in the exam folder.

## 📄 License

This project is licensed under the Non-Commercial Educational License - see the [LICENSE](LICENSE) file for details.

**For commercial use, please contact JASim for licensing options.**
