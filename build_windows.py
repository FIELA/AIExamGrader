import PyInstaller.__main__
import customtkinter
import os
import sys

# Get customtkinter path for data inclusion
ctk_path = os.path.dirname(customtkinter.__file__)
ctk_data_arg = f'{ctk_path};customtkinter'  # Windows uses semicolon

print(f"Windows Build script starting...")
print(f"CustomTkinter path: {ctk_path}")

# Define PyInstaller arguments for Windows
args = [
    'AutoGrader.py',  # Main script
    '--name=AI Exam Grader',  # App name
    '--windowed',  # No console window
    '--noconfirm',  # Overwrite output directory
    '--clean',  # Clean cache
    '--icon=assets/icon.ico',  # Windows icon (needs .ico format)
    f'--add-data={ctk_data_arg}',  # Include customtkinter assets
    '--hidden-import=PIL._tkinter_finder',
    '--hidden-import=google.generativeai',
    '--hidden-import=google.ai.generativelanguage',
    '--collect-all=customtkinter',
    '--collect-all=google.generativeai',
    '--collect-binaries=PIL',
    # Windows-specific optimizations
    '--exclude-module=tkinter.test',
    '--exclude-module=test',
]

# Run PyInstaller
try:
    PyInstaller.__main__.run(args)
    print(f"\n✅ Build successful! The application is located in 'dist/AI Exam Grader.exe'")
    print(f"📦 You can distribute the entire 'dist/AI Exam Grader' folder")
except Exception as e:
    print(f"\n❌ Build failed: {e}")
    sys.exit(1)
