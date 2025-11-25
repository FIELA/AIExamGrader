# Windows Build Instructions

## Prerequisites

1. **Windows 10/11** computer
2. **Python 3.10-3.13** installed
3. **Git** installed

## Step-by-Step Build Process

### 1. Get the Source Code

**Option A: Using Git (Recommended)**
```bash
git clone https://github.com/FIELA/AIExamGrader.git
cd AIExamGrader
```

**Option B: Download ZIP (No Git required)**
1. Go to https://github.com/FIELA/AIExamGrader
2. Click **Code** -> **Download ZIP**
3. Extract the ZIP file
4. Open PowerShell in the extracted folder

### 2. Create Virtual Environment
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
pip install pyinstaller
```

### 4. Convert Icon to ICO Format

**Option A: Use online converter**
- Upload `assets/icon.png` to https://convertio.co/png-ico/
- Download as `icon.ico` and save to `assets/`

**Option B: Use Python (ImageMagick required)**
```bash
pip install pillow
python -c "from PIL import Image; img = Image.open('assets/icon.png'); img.save('assets/icon.ico', format='ICO', sizes=[(256,256)])"
```

### 5. Build the Application
```bash
python build_windows.py
```

### 6. Find Your Application
The built application will be in:
```
dist/AI Exam Grader/
    AI Exam Grader.exe  ← Main executable
    [other dependencies]
```

## Distribution

### Single Folder Distribution
Distribute the entire `dist/AI Exam Grader` folder. Users double-click `AI Exam Grader.exe` to run.

### Create Installer (Optional)
Use [Inno Setup](https://jrsoftware.org/isinfo.php) to create a Windows installer:

1. Download and install Inno Setup
2. Create a script to package the `dist/AI Exam Grader` folder
3. Generate `AIExamGrader_Setup.exe`

## Troubleshooting

### PowerShell Script Error
If you see `cannot be loaded because running scripts is disabled on this system`:
1. Open PowerShell as Administrator
2. Run this command to allow scripts:
   ```powershell
   Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```
3. Type `Y` and press Enter
4. Try activating the venv again

### Microsoft Visual C++ 14.0+ Required
If you see `Microsoft Visual C++ 14.0 or greater is required` (often when installing `grpcio`):
1. Download **Microsoft C++ Build Tools**: https://visualstudio.microsoft.com/visual-cpp-build-tools/
2. Run the installer
3. Select **"Desktop development with C++"** workload
4. Click **Install** (approx. 2-6 GB)
5. Restart PowerShell and try again

> **Note for Windows ARM64 Users (e.g., Parallels on Mac)**:
> If installation still fails after installing Build Tools, try using **Python 3.11 or 3.12** instead of 3.13, as `grpcio` wheels might not be available for the latest Python version on ARM64 yet.

### Network Timeout (pip install fails)
If you see `ReadTimeoutError` or slow downloads:
Use a mirror source (e.g., Tsinghua University):
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install pyinstaller pillow -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### DLL Errors
If users get DLL errors:
- Install [Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)

### App Won't Start
- Right-click → Properties → Unblock
- Run as administrator

## Testing
After building, test the application on a **clean Windows machine** without Python installed.
