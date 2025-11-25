import PyInstaller.__main__
import customtkinter
import os
import sys
from PyInstaller.utils.hooks import collect_all, copy_metadata

# Check dependencies
try:
    import google.generativeai
except ImportError:
    print("❌ Error: google.generativeai not found. Please run: pip install google-generativeai")
    sys.exit(1)

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
    '--runtime-hook=rthook_google.py', # Force google namespace fix
    '--hidden-import=PIL._tkinter_finder',
    '--hidden-import=google',
    '--collect-all=customtkinter',
    '--collect-binaries=PIL',
    # Windows-specific optimizations
    '--exclude-module=tkinter.test',
    '--exclude-module=test',
]

# Helper to collect package data
def add_package(name):
    try:
        datas, binaries, hiddenimports = collect_all(name)
        for src, dest in datas:
            args.append(f'--add-data={src};{dest}')
        for src, dest in binaries:
            args.append(f'--add-binary={src};{dest}')
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
            args.append(f'--add-data={src};{dest}')
        print(f"  -> Metadata copied for {name}")
    except Exception as e:
        print(f"  -> Warning: Could not copy metadata for {name}: {e}")

print("Collecting dependencies...")
add_package('google') # Collect the namespace package itself
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
    print(f"\n✅ Build successful! The application is located in 'dist/AI Exam Grader.exe'")
    print(f"📦 You can distribute the entire 'dist/AI Exam Grader' folder")
except Exception as e:
    print(f"\n❌ Build failed: {e}")
    sys.exit(1)
