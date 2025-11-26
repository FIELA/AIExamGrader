import PyInstaller.__main__
import customtkinter
import os
import sys
from PyInstaller.utils.hooks import collect_all, copy_metadata

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
    '--icon=assets/icon.icns',  # Custom application icon
    f'--add-data={ctk_data_arg}',  # Include customtkinter assets
    f'--add-data=assets{add_data_sep}assets',  # Include assets folder (for runtime icon)
    '--hidden-import=PIL._tkinter_finder', # Fix for some PIL issues
    '--hidden-import=google',
    '--collect-all=customtkinter', # Ensure all ctk submodules are found
    '--collect-binaries=PIL',  # Collect PIL binary dependencies
]

# Add --onefile for Windows to create a single executable
if os.name != 'posix':  # Windows
    args.append('--onefile')
    print("Windows build: Using --onefile mode (single executable)")

# Helper to collect package data
def add_package(name):
    try:
        datas, binaries, hiddenimports = collect_all(name)
        for src, dest in datas:
            args.append(f'--add-data={src}{add_data_sep}{dest}')
        for src, dest in binaries:
            args.append(f'--add-binary={src}{add_data_sep}{dest}')
        for h in hiddenimports:
            args.append(f'--hidden-import={h}')
        print(f"  -> Collected {name}")
    except Exception as e:
        print(f"  -> Warning: Could not collect {name}: {e}")

# Helper to copy metadata
def add_metadata(name):
    try:
        datas = copy_metadata(name)
        for src, dest in datas:
            args.append(f'--add-data={src}{add_data_sep}{dest}')
        print(f"  -> Metadata copied for {name}")
    except Exception as e:
        print(f"  -> Warning: Could not copy metadata for {name}: {e}")

print("Collecting dependencies...")
add_package('google.generativeai')
add_package('google.ai.generativelanguage')
add_package('google.api_core')
add_package('google.auth')
add_package('grpc')

print("Copying metadata...")
add_metadata('google-generativeai')
add_metadata('google-api-core')
add_metadata('google-auth')

# Run PyInstaller
try:
    PyInstaller.__main__.run(args)
    if os.name == 'posix':
        output_name = "AI Exam Grader.app"
        output_type = "application bundle"
    else:
        output_name = "AI Exam Grader.exe"
        output_type = "single executable"
    print(f"\n✅ Build successful! The {output_type} is located in 'dist/{output_name}'")
except Exception as e:
    print(f"\n❌ Build failed: {e}")
    sys.exit(1)
