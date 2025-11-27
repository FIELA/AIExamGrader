# AI Exam Grader

[![License: Non-Commercial](https://img.shields.io/badge/License-Non--Commercial-orange.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

[简体中文](README_CN.md) | English

---

## 📖 Introduction

**AI Exam Grader** is an intelligent grading assistant powered by Large Language Models (LLMs), designed for teachers and educators. It leverages the visual understanding capabilities of **OpenAI (GPT-4o)** or **Google Gemini (Pro)** to automatically grade handwritten exam papers and generate detailed reports.

> [!IMPORTANT]
> **License Notice**
>
> This project is licensed under the **[NCEL-Strict+ License (Version 1.3)](./LICENSE)**.
> This is a **Source Available** but **Strictly Limited** non-commercial license.
>
> 🚫 **Commercial Use Strictly Prohibited**: Includes sale, subscription, sponsorship, **Internal Use**, SaaS services, and AI model training.
> 🚫 **Distribution of Modified Versions Prohibited**: You may **NOT** directly distribute modified source code or binaries (only Patch/Diff files are allowed).
> ✅ **Non-Commercial Only**: Personal study, academic research, and non-commercial use must retain the full copyright notice and license file.
>
> 💼 **Commercial License**:
> For commercial use or custom development, please contact the author for licensing: [nicofiela@outlook.com](mailto:nicofiela@outlook.com)

## ✨ Features

### Core Capabilities

-   **Multi-Model Support**: 
    -   Supports OpenAI (GPT-4o, GPT-4o-mini, etc.) and OpenAI-compatible APIs with custom base URLs
    -   Supports Google Gemini (gemini-2.5-pro, gemini-2.0-flash, etc.)
    -   Easy to switch between different providers and models
    
    > [!NOTE]
    > This application relies heavily on the model's **visual understanding** and **reasoning capabilities**. For best results, we recommend using more powerful models (e.g., GPT-4o, Gemini 2.5 Pro).
    
-   **Smart Recognition**: Automatically extracts handwritten student names, IDs, and class information using OCR.
-   **Flexible Grading**: Supports custom rubrics for precise subjective question grading.
-   **Batch Processing**: Multi-threaded processing for high-speed grading of large batches.
-   **Manual Review**: A dedicated interface to review, verify, and correct AI grading results.
-   **Data Verification**: Automatically validates OCR-extracted info against your student database.
-   **Detailed Reporting**:
    -   Generates individual Markdown grading reports for each student.
    -   **Enhanced CSV Export**: 
        -   Detailed breakdown of Subjective (Main/Sub) and Objective (Answer/Score) questions.
        -   Bilingual headers (English/Chinese) based on app language.
        -   Custom column sorting for optimal readability.
-   **Automated Pre-checks**: Automatically checks for and generates Answer Key, Layout, and CSV headers before grading to prevent errors.
-   **Internationalization**: Fully localized interface in English and Simplified Chinese.

### New Features (v1.2)

-   **🚀 Configuration Profiles**: Save and quickly switch between different grading configurations.
-   **📊 Enhanced Progress Tracking**: Real-time progress display, phase-based processing, and ETR updates.
-   **🎨 UI Refresh**: Modern interface with improved Review Window (scroll controls, cursor fixes) and safe application exit.

## 🚀 Quick Start

### 1. Requirements
-   macOS (Recommended) / Windows / Linux
-   Python 3.10+

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Application

**Method 1: Using Configuration Profiles (Recommended)**

Copy the example configuration file:
```bash
cp config_example.json config.json
```

Edit `config.json` with your actual API keys and file paths.

**Method 2: Manual Configuration**

You can also configure settings directly in the application interface.

See [README_CONFIG.md](README_CONFIG.md) for detailed configuration guide.

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
python build_windows.py
```
The executable (`.exe`) will be generated in the `dist/` folder.

## 🛠️ Usage Guide

### 1. Configuration
... (Same as before)

## 📂 Project Structure

```
AIExamGrader/
├── AutoGrader.py           # Main application
├── config_manager.py       # Configuration management
├── student_manager.py      # Student database management
├── grader_engine.py        # AI grading engine
├── review_window.py        # Manual review interface
├── translations.py         # Internationalization
├── utils.py                # Helper functions
├── theme.py                # UI Theme definitions
├── config_example.json     # Example configuration
├── README_CONFIG.md        # Configuration guide
├── requirements.txt        # Dependencies
├── build.py                # macOS build script
└── build_windows.py        # Windows build script
```

## 🔧 Configuration Files

-   `config.json`: Main configuration file (created from `config_example.json`)
-   `config_example.json`: Example configuration with sample profiles
-   See [README_CONFIG.md](README_CONFIG.md) for detailed configuration documentation

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📄 License

This project is licensed under the **NCEL-Strict+ License (Version 1.1)** - see the [LICENSE](LICENSE) file for details.

**For commercial use, please contact the project author for licensing options: nicofiela@outlook.com**

---

Made with ❤️ for educators worldwide
