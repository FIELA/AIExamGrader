import PyInstaller.__main__
import customtkinter
import os
import sys
from PyInstaller.utils.hooks import collect_all, copy_metadata

# Check dependencies
try:
    import google
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
    '--onefile',  # Create a single executable file (CRITICAL for single .exe)
    '--windowed',  # No console window
    '--noconfirm',  # Overwrite output directory
    '--clean',  # Clean cache
    '--icon=assets/icon.ico',  # Windows icon (needs .ico format)
    f'--add-data={ctk_data_arg}',  # Include customtkinter assets
    '--add-data=assets;assets',  # Include assets folder (for runtime icon)
    '--hidden-import=PIL._tkinter_finder',
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

# BRUTE FORCE: Manually copy google package path
# This bypasses PyInstaller's namespace package issues
try:
    # Find where 'google' is installed
    google_path = os.path.dirname(google.generativeai.__file__) # Get into google/generativeai
    google_path = os.path.dirname(google_path) # Go up to google/
    
    print(f"  -> Found google package at: {google_path}")
    if os.path.exists(google_path):
        args.append(f'--add-data={google_path};google')
        print("  -> Added google directory to datas")
    else:
        print("  -> Warning: Could not find google directory path")
except Exception as e:
    print(f"  -> Error finding google path: {e}")

add_package('grpc')

print("Copying metadata...")
add_metadata('google-generativeai')
add_metadata('google-api-core')
add_metadata('google-auth')

# Run PyInstaller
try:
    PyInstaller.__main__.run(args)
    print(f"\n✅ Build successful! Single executable created!")
    print(f"📦 Location: 'dist/AI Exam Grader.exe'")
    print(f"💡 This is a standalone .exe file - no _internal folder needed!")
except Exception as e:
    print(f"\n❌ Build failed: {e}")
    sys.exit(1)
