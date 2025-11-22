import PyInstaller.__main__
import customtkinter
import os
import sys

# Get customtkinter path for data inclusion
ctk_path = os.path.dirname(customtkinter.__file__)
add_data_sep = ':' if os.name == 'posix' else ';'
ctk_data_arg = f'{ctk_path}{add_data_sep}customtkinter'

print(f"Build script starting...")
print(f"CustomTkinter path: {ctk_path}")

# Define PyInstaller arguments
args = [
    'AutoGrader.py',  # Main script
    '--name=AI Exam Grader',  # App name
    '--windowed',  # No terminal window
    '--noconfirm',  # Overwrite output directory
    '--clean',  # Clean cache
    f'--add-data={ctk_data_arg}',  # Include customtkinter assets
    '--hidden-import=PIL._tkinter_finder', # Fix for some PIL issues
    '--collect-all=customtkinter', # Ensure all ctk submodules are found
]

# Run PyInstaller
try:
    PyInstaller.__main__.run(args)
    output_name = "AI Exam Grader.app" if os.name == 'posix' else "AI Exam Grader"
    print(f"\nBuild successful! The application is located in 'dist/{output_name}'")
except Exception as e:
    print(f"\nBuild failed: {e}")
    sys.exit(1)
