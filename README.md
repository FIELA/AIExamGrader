# AI Exam Grader

[![License: Non-Commercial](https://img.shields.io/badge/License-Non--Commercial-orange.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

[简体中文](README_CN.md) | English

---

## 📖 Introduction

**AI Exam Grader** is an intelligent grading assistant powered by Large Language Models (LLMs), designed for teachers and educators. It leverages the visual understanding capabilities of **OpenAI (GPT-4o)** or **Google Gemini (Pro)** to automatically grade handwritten exam papers and generate detailed reports.

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
    -   Automatically compiles a CSV summary with detailed scores for every question.
-   **Internationalization**: Fully localized interface in English and Simplified Chinese.

### New Features (v1.1)

-   **🚀 Configuration Profiles**: Save and quickly switch between different grading configurations
    -   Save multiple profiles with different API keys, models, and file paths
    -   Quick switch via dropdown menu in sidebar
    -   Auto-loads last used profile on startup
    -   Perfect for managing multiple exams or switching between API providers
    
-   **📊 Enhanced Progress Tracking**: 
    -   Real-time progress display with accurate file counting
    -   Phase-based processing (Main → Failed Retry → Verification)
    -   Estimated Time Remaining (ETR) updates
    -   Final verification counts for quality assurance

-   **🎨 UI Refresh**:
    -   Modern, clean interface with a new color theme
    -   Intuitive icons for better navigation
    -   Improved layout and readability

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

Edit `config.json` with your actual API keys and file paths. The example file includes two sample profiles that you can customize.

**Method 2: Manual Configuration**

You can also configure settings directly in the application interface (saved automatically).

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
python build.py
```
The executable folder will be generated in the `dist/` folder.

## 🛠️ Usage Guide

### 1. Configuration

#### Using Configuration Profiles
-   **Select Profile**: Choose from saved profiles in the dropdown menu
-   **Save Profile**: Click 💾 Save to save current settings as a new profile
-   **Delete Profile**: Select a profile and click 🗑️ Delete to remove it

#### Manual Configuration
-   **API Key**: Enter your OpenAI or Google Gemini API Key in the sidebar
-   **Provider**: Select your preferred service provider
-   **Model**: Choose the model (e.g., `gpt-4o`, `gemini-2.5-pro-maxthinking`)
-   **Base URL**: (Optional) For custom API endpoints

### 2. Prepare Resources
-   **Rubric**: A text file containing questions, standard answers, and scoring rules
-   **Exam Folder**: A folder containing images of student exam papers (supported formats: .jpg, .png, .jpeg)
-   **Student List**: (Optional) An Excel/CSV file containing student roster for validation

#### 📝 Image File Naming Requirements

**Required Format**: `考场号-座号.扩展名`

**Examples**:
-   `01-15.jpg` → Room 1, Seat 15
-   `02-08.png` → Room 2, Seat 8
-   `03-22.jpeg` → Room 3, Seat 22

**Absence Marker** (Optional):
-   Add `缺` after the seat number for absent students
-   Example: `01-05缺.jpg` → Room 1, Seat 5, Absent

**Important Notes**:
-   The `-` separator is **required** to distinguish room and seat numbers
-   File extensions are **case-insensitive** (.jpg, .JPG, .Jpg all work)
-   Room and seat numbers should match your student list for accurate identification
-   If filenames don't follow this format:
    -   ✅ AI grading will still work
    -   ❌ Student information will show as "Unknown"
    -   ❌ Results cannot be matched to your student roster
    -   ❌ Manual review and searching will be difficult

### 3. Start Grading
-   Click **▶️ Start Grading**
-   The system will:
    1. Detect answer sheet layout (first-time only, saved for reuse)
    2. Process all pending files in parallel
    3. Retry failed files automatically
    4. Verify final counts
-   Real-time progress and Estimated Time Remaining (ETR) will be displayed

### 4. Manual Review
-   After grading, click **🔍 Review**
-   Verify student information, objective scores, and subjective grading
-   Make corrections if necessary
-   The system will update reports and CSV summary automatically

### 5. View Results
-   **Reports**: Individual `.md` and `.json` files in `[Exam Folder]/reports/`
-   **Summary**: A consolidated `成绩汇总表.csv` (or `Grade_Summary.csv`) in the exam folder

## 📂 Project Structure

```
AIExamGrader/
├── AutoGrader.py           # Main application
├── config_manager.py       # Configuration management
├── student_manager.py      # Student database management
├── grader_engine.py        # AI grading engine
├── review_window.py        # Manual review interface
├── translations.py         # Internationalization
├── config_example.json     # Example configuration with profiles
├── README_CONFIG.md        # Configuration guide
├── requirements.txt        # Dependencies
└── build.py               # Application builder
```

## 🔧 Configuration Files

-   `config.json`: Main configuration file (created from `config_example.json`)
-   `config_example.json`: Example configuration with sample profiles
-   See [README_CONFIG.md](README_CONFIG.md) for detailed configuration documentation

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📄 License

This project is licensed under the Non-Commercial Educational License (NCEL-1.0) - see the [LICENSE](LICENSE) file for details.

**For commercial use, please contact the project author for licensing options.**

---

Made with ❤️ for educators worldwide
