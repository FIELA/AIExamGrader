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
> This project is licensed under the **[NCEL-Strict License (Version 2.0)](./LICENSE)**.
> This is a **Source Available** but **Strictly Limited** non-commercial license.
>
> 🚫 **Commercial Use Strictly Prohibited**: Includes sale, subscription, sponsorship, **Internal Use**, SaaS services, and AI model training.  
> 🚫 **Distribution of Modified Versions Prohibited**: You may **NOT** directly distribute modified source code or binaries (only Patch/Diff files are allowed).  
> 🚫 **Fork Restriction**: Public Forks are allowed ONLY for submitting PRs and must be deleted within 14 days after the PR is closed.  
> ✅ **Non-Commercial Only**: Personal study, academic research, and non-commercial use must retain the full copyright notice and license file.
>
> 💼 **Commercial License**:
> For commercial use or custom development, please contact the author for licensing: [nicofiela@outlook.com](mailto:nicofiela@outlook.com)

## ✨ Features

-   **🤖 Intelligent Grading Engine**
    -   **Multi-Model Support**: 
        - Supports OpenAI (GPT-4o, etc.) and compatible APIs (Custom Base URL)
        - Supports Google Gemini (gemini-3.0-pro, etc.)
    -   **Smart OCR Recognition**: Automatically extracts handwritten student names, IDs, and class information
    -   **Flexible Grading Rubrics**: Supports custom rubrics for precise subjective question grading
    -   **Batch Concurrent Processing**: Multi-threaded architecture for high-speed grading of large batches

    > [!NOTE]
    > This application relies heavily on the model's **visual understanding** and **reasoning capabilities**. For best results, we recommend using more powerful models (e.g., GPT-4o, Gemini 3.0 Pro).

-   **📊 Smart Data Management**
    - Chain auto-validation (Answer Key → Layout → CSV)
    - Automatic CSV rebuild when missing
    - Incremental processing with resume capability
    - Seamless CN/EN directory support

-   **🔍 Manual Review System**
    - Three-step review process (Info → Objective → Subjective)
    - Dual-mode viewing (Text/Image)
    - Smart navigation and search
    - Complete review history tracking

-   **📋 Comprehensive Reports + 🌐 Internationalization**
    - Markdown reports + Enhanced CSV + Structured JSON
    - Full Chinese-English support
    - Quick-switch configuration profiles



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

### Quick Workflow (5 Steps)

#### Step 1: Configure API

```
API Settings
├─ API Key: Enter your API key
├─ Service Provider: OpenAI / Gemini
├─ Model Name: gpt-4o / gemini-1.5-pro
└─ Base URL: (Optional)
```

#### Step 2: Upload Resources

```
Resource Files
├─ 📄 Rubric: Upload exam questions and answers document
├─ 📁 Answer Sheets Folder: Select folder containing scanned images
└─ 👥 Student List: (Optional) Upload Excel/CSV student roster
```

#### Step 3: Start Grading

Click **"Start Grading"** button

**Automated Flow**:
```
Check Answer Key → Confirm Answers → Detect Layout → Confirm Layout → Generate CSV → Start Grading
```

**User Interaction Points**:
- 🔍 **Answer Key Confirmation**: Confirm AI-extracted answers on first run
- 🔍 **Layout Description Confirmation**: Confirm answer sheet structure on first run

#### Step 4: Manual Review

After grading completes, click **"Review"** button

**Three-Step Review Process**:
```
Step 1: Verify Student Information
Step 2: Verify Objective Questions
Step 3: Verify Subjective Question Scores
```

**Quick Actions**:
- 📝/🖼 Toggle Text/Image Mode
- ⬅️/➡️ Previous/Next Student
- 🔍 Search Student (Name/ID)
- ✅ Confirm and Continue

#### Step 5: Export Results

```
Output File Locations
├─ 📊 Grade_Summary.csv (in grading_data/ folder)
├─ 📝 Grading_Report.md (in reports/ folder, one per student)
└─ 📄 Student_Data.json (in reports/ folder, one per student)
```

### Directory Structure (Auto-Generated)

When you start grading, the application automatically creates:

```
Answer Sheets Folder/
├─ grading_data/              # Configuration and summary data
│   ├─ answer_key.json       # Standard answers
│   ├─ layout_config.json    # Answer sheet layout
│   └─ Grade_Summary.csv     # Grade summary table
│
├─ reports/                   # Grading results
│   ├─ 01-01.json           # Student grade data
│   ├─ 01-01.md             # Student grading report
│   └─ ...
│
├─ original_files/           # Original answer sheet backups
│   └─ *.jpg/png
│
├─ success/                  # Successfully graded sheets
│   └─ *.jpg/png
│
└─ failed/                   # Failed grading attempts
    └─ *.jpg/png
```

### Data Validation Flow

```
Start Grading → Answer Key → Layout Config → CSV File → File Integrity → Begin Grading
     ↓             ↓            ↓             ↓            ↓              ↓
Basic Check   Smart Extract  Auto-Detect  Smart Recovery  Incremental  Batch Process
```

**Key Features**:
- ✅ **Chain Validation**: Answer Key → Layout → CSV → Grading
- ✅ **Smart Recovery**: Automatically rebuilds CSV from JSON if missing
- ✅ **Incremental Processing**: Only grades incomplete files
- ✅ **Auto Migration**: Legacy files automatically moved to new structure
- ✅ **User Confirmation**: Answer key and layout require user approval
- ✅ **Data Consistency**: Rebuilds CSV after grading to ensure accuracy

### Output Files Explained

**Grade Summary (CSV)**  
Contains complete grades and information for all students
- Basic Info: Room, Seat, Name, ID, Class
- Scores: Total, Objective, Subjective, Individual Questions
- OCR Info: Recognized name, ID, etc.
- Review Status: Unreviewed/Reviewed/Second Review

**Grading Report (Markdown)**  
Detailed grading report for each student
- Student information verification
- Objective question answer comparison table
- Subjective question analysis for each question
- Total score statistics

**Grade Data (JSON)**  
Structured data containing all grading details
- Used for data recovery
- Supports secondary development
- Review history records

### Best Practices

**Before Grading**
- ✅ Prepare high-resolution scanned answer sheets
- ✅ Prepare complete rubric document
- ✅ Check API quota is sufficient

**During Grading**
- ✅ Maintain stable network connection
- ✅ Do not close the application window
- ✅ Monitor progress and logs

**During Review**
- ✅ Verify each student's information individually
- ✅ Focus on checking subjective question scores
- ✅ Use search function to quickly locate students

**After Completion**
- ✅ Export CSV to a safe location
- ✅ Backup the grading data folder
- ✅ Verify CSV row count matches student count

## 📂 Project Structure

```
AIExamGrader/
├── AutoGrader.py           # Main application
├── config_manager.py       # Configuration management
├── student_manager.py      # Student database management
├── grader_engine.py        # AI grading engine
├── review_window.py        # Manual review interface
├── standard_answer_dialog.py # Standard answer configuration
├── splash_screen.py        # Application splash screen
├── translations.py         # Internationalization
├── utils.py                # Helper functions
├── tooltip.py              # Tooltip widget
├── theme.py                # UI Theme definitions
├── generate_icon.py        # Icon generation script
├── config_example.json     # Example configuration
├── README_CONFIG.md        # Configuration guide
├── requirements.txt        # Dependencies
├── rthook_google.py        # PyInstaller runtime hook
├── build.py                # macOS build script
├── build_windows.py        # Windows build script
├── test_core.py            # Core functionality tests
└── test_review_logs.py     # Review log tests
```

## 🔧 Configuration Files

-   `config.json`: Main configuration file (created from `config_example.json`)
-   `config_example.json`: Example configuration with sample profiles
-   See [README_CONFIG.md](README_CONFIG.md) for detailed configuration documentation

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📄 License

This project is licensed under the **NCEL-Strict License (Version 2.0)** - see the [LICENSE](LICENSE) file for details.

**For commercial use, please contact the project author for licensing options: nicofiela@outlook.com**

---

Made with ❤️ for educators worldwide
