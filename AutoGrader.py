# Copyright (c) 2025 JASim. Licensed under NCEL-Strict License v2.0.
# STRICT NON-COMMERCIAL USE ONLY. No AI/ML training, fine-tuning, or public distribution of Derivative Works.
# Modifications may only be shared as Patch Files.
# Public forks allowed solely for PRs (delete within 14 days after PR merged, rejected, or closed).
# Commercial licensing inquiries: nicofiela@outlook.com. See LICENSE file for full terms.

import os
import sys
import threading
import time
import platform
from utils import sort_csv_headers
import re
import shutil
import datetime
import concurrent.futures
import json
import csv
import copy
from typing import List, Dict, Any, Optional
import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog
from PIL import Image, ImageTk
import customtkinter as ctk
from tooltip import ToolTip
from tkinter import filedialog, messagebox
import subprocess

# Import new modules
from config_manager import ConfigManager
from student_manager import StudentManager
from grader_engine import AIGraderEngine
from translations import TRANSLATIONS
from review_window import ReviewWindow
from theme import Theme
from PIL import Image

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Hide main window initially
        self.withdraw()
        
        # Show Splash Screen
        try:
            from splash_screen import SplashScreen
            splash = SplashScreen(self)
            splash.update_progress(0, "Initializing application...")
        except Exception as e:
            print(f"Failed to load splash screen: {e}")
            splash = None

        self.title("AI Exam Grader")
        self.geometry("1200x820")
        self.center_window(1200, 820)
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        
        # Update splash progress
        if splash:
            splash.update_progress(20, "Loading icons...")
            splash.update() # Force splash update
        
        # Load Icons
        self.load_icons()

        if splash:
            splash.update_progress(40, "Loading configuration...")
            splash.update()
        
        self.config_manager = ConfigManager()
        self.student_manager = StudentManager()
        
        self.rubric_path = ""
        self.exam_folder = ""
        
        self.processing = False
        self.write_lock = threading.RLock()  # Use RLock for reentrant locking
        self.completed_count = 0

        self.total_files = 0
        
        self.answer_key = {} # Store standard answers locally
        
        # Control events
        self.pause_event = threading.Event()
        self.pause_event.set() # Initially set to True (running)
        self.stop_event = threading.Event()
        
        # Time tracking
        self.start_time = 0
        self.session_completed_count = 0

        self.current_lang = "CN" # Default language
        
        # Template Detection State
        self.layout_description = None
        self.template_confirmed = False
        
        if splash:
            splash.update_progress(50, "Setting up window...")
            splash.update()
        
        # Set App Icon
        try:
            # On Windows, use .ico for better taskbar integration
            if sys.platform.startswith("win"):
                icon_path_ico = self.resource_path(os.path.join("assets", "icon.ico"))
                if os.path.exists(icon_path_ico):
                    self.iconbitmap(icon_path_ico)
                else:
                    # Fallback to PNG if ICO missing
                    icon_path = self.resource_path(os.path.join("assets", "icon.png"))
                    if os.path.exists(icon_path):
                        from PIL import ImageTk
                        icon_img = ImageTk.PhotoImage(file=icon_path)
                        self.wm_iconphoto(True, icon_img)
            else:
                # On Mac/Linux, use PNG
                icon_path = self.resource_path(os.path.join("assets", "icon.png"))
                if os.path.exists(icon_path):
                    from PIL import ImageTk
                    icon_img = ImageTk.PhotoImage(file=icon_path)
                    self.wm_iconphoto(True, icon_img)
        except Exception as e:
            print(f"Warning: Could not set app icon: {e}")

        if splash:
            splash.update_progress(60, "Building user interface...")
            splash.update()
        
        self.setup_ui()
        
        if splash:
            splash.update_progress(80, "Loading translations...")
            splash.update()
        
        self.load_initial_config()
        self.update_ui_text() # Apply initial language
        
        if splash:
            splash.update_progress(95, "Finalizing...")
            splash.update()
        
        if platform.system() == "Darwin":
            self.apply_mac_paste_fix(self.entry_key)
            self.apply_mac_paste_fix(self.entry_base)
            try: self.apply_mac_paste_fix_to_widget(self.combo_model._entry)
            except: pass

        # Initialization complete
        if splash:
            splash.update_progress(100, "Ready!")
            splash.update()
            # Small delay to let user see 100%
            import time
            time.sleep(0.5)
            
            # Show main window FIRST before destroying splash
            # This ensures we never have 0 visible windows
            self.deiconify()
            self.center_window(1200, 820) # Re-center to be sure
            self.update()
            
            # Now close splash
            splash.close()
        else:
            self.deiconify()
            self.center_window(1200, 820)





    def resource_path(self, relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS (onefile)
            base_path = sys._MEIPASS
        except Exception:
            # If sys._MEIPASS is not set, check if we are frozen (onedir)
            if getattr(sys, 'frozen', False):
                # In onedir mode, assets might be in _internal/assets or just assets relative to exe
                # PyInstaller v6+ puts dependencies in _internal
                exe_dir = os.path.dirname(sys.executable)
                internal_dir = os.path.join(exe_dir, '_internal')
                
                # Check _internal first (v6+ default)
                if os.path.exists(os.path.join(internal_dir, relative_path)):
                    base_path = internal_dir
                # Fallback to exe dir (older PyInstaller or different config)
                elif os.path.exists(os.path.join(exe_dir, relative_path)):
                    base_path = exe_dir
                else:
                    # Last resort: check if it's in _internal but we missed it?
                    # Or maybe it's just not there. Default to exe dir.
                    base_path = exe_dir
            else:
                base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)

        return os.path.join(base_path, relative_path)

    def load_icons(self):
        self.icons = {}
        icon_names = ["start", "pause", "stop", "review", "folder", "document", "refresh", "open", "clear"]
        
        def process_icon(img, color=None):
            """
            1. Remove background (assume corners are background).
            2. Recolor non-transparent pixels to target color.
            """
            img = img.convert("RGBA")
            data = img.getdata()
            width, height = img.size
            
            # 1. Background Removal
            # Sample corners to find background color
            corners = [
                data[0], # Top-left
                data[width-1], # Top-right
                data[(height-1)*width], # Bottom-left
                data[len(data)-1] # Bottom-right
            ]
            
            # Find most common corner color (simple voting)
            bg_color = max(set(corners), key=corners.count)
            
            # If background is transparent, skip removal
            if bg_color[3] < 50:
                new_data = list(data)
            else:
                new_data = []
                threshold = 40
                bg_r, bg_g, bg_b = bg_color[:3]
                
                for item in data:
                    # Check if pixel is close to background color
                    r, g, b, a = item
                    if a > 0 and \
                       abs(r - bg_r) < threshold and \
                       abs(g - bg_g) < threshold and \
                       abs(b - bg_b) < threshold:
                        new_data.append((0, 0, 0, 0)) # Transparent
                    else:
                        new_data.append(item)
            
            # 2. Recolor if color is specified
            if color:
                final_data = []
                for item in new_data:
                    if item[3] > 0: # If not transparent
                        # Apply color but keep alpha
                        final_data.append(color + (item[3],))
                    else:
                        final_data.append(item)
                img.putdata(final_data)
            else:
                img.putdata(new_data)
                
            return img

        for name in icon_names:
            path = self.resource_path(os.path.join("assets", "icons", f"{name}.png"))
            if os.path.exists(path):
                pil_img = Image.open(path)
                
                # For solid buttons (Start, Pause, Stop, Folder, Document, Review, Refresh, Open, Clear), use White icons
                if name in ["start", "pause", "stop", "folder", "document", "review", "refresh", "open", "clear"]:
                    processed_img = process_icon(pil_img, (255, 255, 255))
                    self.icons[name] = ctk.CTkImage(light_image=processed_img, dark_image=processed_img, size=(20, 20))
            else:
                self.icons[name] = None

    def apply_mac_paste_fix(self, ctk_widget):
        try:
            if hasattr(ctk_widget, "_entry"):
                ctk_widget._entry.bind("<Command-v>", lambda e: ctk_widget._entry.event_generate("<<Paste>>"))
                ctk_widget._entry.bind("<Command-c>", lambda e: ctk_widget._entry.event_generate("<<Copy>>"))
                ctk_widget._entry.bind("<Command-x>", lambda e: ctk_widget._entry.event_generate("<<Cut>>"))
                ctk_widget._entry.bind("<Command-a>", lambda e: ctk_widget._entry.select_range(0, 'end'))
            else:
                ctk_widget.bind("<Command-v>", lambda e: ctk_widget.event_generate("<<Paste>>"))
                ctk_widget.bind("<Command-c>", lambda e: ctk_widget.event_generate("<<Copy>>"))
                ctk_widget.bind("<Command-x>", lambda e: ctk_widget.event_generate("<<Cut>>"))
                ctk_widget.bind("<Command-a>", lambda e: ctk_widget.select_range(0, 'end'))
        except Exception as e:
            print(f"Error applying Mac paste fix: {e}")

    def apply_mac_paste_fix_to_widget(self, widget):
        try:
            widget.bind("<Command-v>", lambda e: widget.event_generate("<<Paste>>"))
            widget.bind("<Command-c>", lambda e: widget.event_generate("<<Copy>>"))
            widget.bind("<Command-x>", lambda e: widget.event_generate("<<Cut>>"))
            widget.bind("<Command-a>", lambda e: widget.select_range(0, 'end'))
        except Exception as e:
            print(f"Error applying fix to widget: {e}")

        except Exception as e:
            print(f"Error applying fix to widget: {e}")

    def get_folder_path(self, key):
        """
        Get the path for a specific folder type (grading_data, reports, etc.)
        Checks for existing folders in both languages, defaults to current language.
        key: 'grading_data', 'original_files', 'reports', 'success', 'failed'
        """
        if not self.exam_folder: return None
        
        # Define possible names (EN, CN)
        # We could load from translations, but hardcoding here ensures we know what to look for
        # regardless of current loaded language file state.
        names_map = {
            'grading_data': ['grading_data', '阅卷数据'],
            'original_files': ['original_files', '原始文件'],
            'reports': ['reports', '阅卷报告'],
            'success': ['success', '成功归档'],
            'failed': ['failed', '失败归档']
        }
        
        possible_names = names_map.get(key, [key])
        
        # 1. Check if any exist
        for name in possible_names:
            path = os.path.join(self.exam_folder, name)
            if os.path.exists(path):
                return path
                
        # 2. If none exist, return path based on current language
        # Get translation key
        trans_key = f"dir_{key}"
        folder_name = self.t(trans_key)
        # Fallback if translation missing (shouldn't happen if translations.py updated)
        if folder_name == trans_key: 
            folder_name = possible_names[0] # Default to EN
            
        return os.path.join(self.exam_folder, folder_name)

    def paste_event_handler(self, event):
        try:
            clipboard = self.clipboard_get()
            event.widget.insert("insert", clipboard)
            return "break"
        except Exception: return None

    def setup_ui(self):
        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Configure grid layout (1x2)
        self.grid_columnconfigure(0, minsize=260, weight=0) # Enforce fixed sidebar width
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar (Left) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=260, corner_radius=0, fg_color=(Theme.BG_LIGHT, Theme.BG_DARK))
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False) # Prevent resizing based on content
        self.sidebar_frame.grid_rowconfigure(20, weight=1) # Push content to top

        # Logo
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text=self.t("logo"), font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Language Switcher
        self.lbl_lang = ctk.CTkLabel(self.sidebar_frame, text=self.t("lbl_language"), anchor="w")
        self.lbl_lang.grid(row=1, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.combo_lang = ctk.CTkComboBox(self.sidebar_frame, values=["中文", "English"], command=self.change_language, width=220)
        self.combo_lang.grid(row=2, column=0, padx=20, pady=(5, 20))
        self.combo_lang.set("中文" if self.current_lang == "CN" else "English")

        # Config Profile
        self.lbl_config_profile = ctk.CTkLabel(self.sidebar_frame, text=self.t("lbl_config_profile"), anchor="w")
        self.lbl_config_profile.grid(row=3, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.combo_profile = ctk.CTkComboBox(self.sidebar_frame, values=self.config_manager.get_profile_names(), command=self.on_profile_select, width=220) # Changed command to on_profile_select
        self.combo_profile.grid(row=4, column=0, padx=20, pady=(5, 10))
        # self.combo_profile.set(self.config_manager.current_profile) # This line might cause an error if current_profile is not set or profiles are empty. Handled in load_initial_config.
        
        self.profile_btn_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent", width=220)
        self.profile_btn_frame.grid(row=5, column=0, padx=20, pady=(0, 20))
        self.profile_btn_frame.grid_columnconfigure(0, weight=1)
        self.profile_btn_frame.grid_columnconfigure(1, weight=1)
        
        self.btn_save_profile = ctk.CTkButton(self.profile_btn_frame, text=self.t("btn_save_profile"), command=self.save_current_profile, width=60, height=32, corner_radius=8, font=ctk.CTkFont(size=13), fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER)
        self.btn_save_profile.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        
        self.btn_delete_profile = ctk.CTkButton(self.profile_btn_frame, text=self.t("btn_delete_profile"), command=self.delete_current_profile, width=60, height=32, fg_color=Theme.DANGER, hover_color=Theme.DANGER_HOVER, corner_radius=8, font=ctk.CTkFont(size=13))
        self.btn_delete_profile.grid(row=0, column=1, padx=(6, 0), sticky="ew")

        # 1. Provider
        self.lbl_provider = ctk.CTkLabel(self.sidebar_frame, text=self.t("lbl_provider"), anchor="w", font=ctk.CTkFont(size=13, weight="normal"))
        self.lbl_provider.grid(row=6, column=0, padx=16, pady=(10, 4), sticky="w")
        self.provider_var = ctk.StringVar(value="OpenAI")
        self.combo_provider = ctk.CTkComboBox(self.sidebar_frame, values=["OpenAI", "Gemini"], variable=self.provider_var, command=self.on_provider_change, height=32, corner_radius=8, width=228)
        self.combo_provider.grid(row=7, column=0, padx=16, pady=(0, 10))

        # 2. API Key
        self.lbl_key = ctk.CTkLabel(self.sidebar_frame, text=self.t("lbl_key"), anchor="w")
        self.lbl_key.grid(row=8, column=0, padx=20, pady=(0, 4), sticky="w")
        self.entry_key = ctk.CTkEntry(self.sidebar_frame, width=220)
        self.entry_key.grid(row=9, column=0, padx=20, pady=(0, 10))
        
        # Bind events for masking
        self.entry_key.bind("<FocusIn>", self._on_key_focus_in)
        self.entry_key.bind("<FocusOut>", self._on_key_focus_out)
        self.entry_key.bind("<KeyRelease>", self._on_key_release)

        # 3. Base URL
        self.lbl_base = ctk.CTkLabel(self.sidebar_frame, text=self.t("lbl_base"), anchor="w", font=ctk.CTkFont(size=13, weight="normal"))
        self.lbl_base.grid(row=10, column=0, padx=16, pady=(0, 4), sticky="w")
        self.entry_base = ctk.CTkEntry(self.sidebar_frame, placeholder_text="https://...", height=32, corner_radius=8, width=228)
        self.entry_base.grid(row=11, column=0, padx=16, pady=(0, 10))

        # 4. Get Models Button
        self.btn_get_models = ctk.CTkButton(self.sidebar_frame, text=self.t("btn_get_models"), command=self.check_models, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"), height=36, corner_radius=8, font=ctk.CTkFont(size=13), width=228)
        self.btn_get_models.grid(row=12, column=0, padx=16, pady=(0, 10))

        # 5. Model Name
        self.lbl_model = ctk.CTkLabel(self.sidebar_frame, text=self.t("lbl_model"), anchor="w", font=ctk.CTkFont(size=13, weight="normal"))
        self.lbl_model.grid(row=13, column=0, padx=16, pady=(0, 4), sticky="w")
        self.combo_model = ctk.CTkComboBox(self.sidebar_frame, values=["gemini-2.5-pro-maxthinking", "gpt-4o"], height=32, corner_radius=8, width=228)
        self.combo_model.set("gemini-2.5-pro-maxthinking")
        self.combo_model.grid(row=14, column=0, padx=16, pady=(0, 10))
        
        # 6. Test Connection Button
        self.btn_test_connection = ctk.CTkButton(self.sidebar_frame, text=self.t("btn_test_connection"), command=self.test_connection, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"), height=36, corner_radius=8, font=ctk.CTkFont(size=13), width=228)
        self.btn_test_connection.grid(row=15, column=0, padx=16, pady=(0, 16))

        # --- Main Content (Right) ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)
        # Row 0: Files, Row 1: Dashboard, Row 2: Progress, Row 3: Logs
        self.main_frame.grid_rowconfigure(0, weight=0)
        self.main_frame.grid_rowconfigure(1, weight=0)
        self.main_frame.grid_rowconfigure(2, weight=0)
        self.main_frame.grid_rowconfigure(3, weight=1) # Give weight to logs
        self.main_frame.grid_columnconfigure(0, weight=1)

        # 1. Files Card
        self.files_card = ctk.CTkFrame(self.main_frame, corner_radius=12, fg_color=(Theme.BG_LIGHT, Theme.BG_DARK)) # Slightly darker/lighter than bg
        self.files_card.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        self.files_card.grid_columnconfigure(1, weight=0) # Don't expand button area
        self.files_card.grid_columnconfigure(3, weight=1) # Expand status label area

        self.lbl_resources = ctk.CTkLabel(self.files_card, text=self.t("lbl_resources"), font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_resources.grid(row=0, column=0, padx=20, pady=(16, 12), sticky="w")

        # Rubric
        self.btn_rubric = ctk.CTkButton(self.files_card, text=" " + self.t("btn_rubric"), image=self.icons.get("document"), command=self.load_rubric, width=160, height=36, corner_radius=8, font=ctk.CTkFont(size=13), fg_color=Theme.INFO, text_color="white", anchor="w")
        self.btn_rubric.grid(row=1, column=0, padx=20, pady=6, sticky="w")
        
        # Rubric Controls (Open/Clear)
        self.btn_rubric_open = ctk.CTkButton(self.files_card, text="", image=self.icons.get("open"), command=self.open_rubric, width=36, height=36, corner_radius=8, fg_color=Theme.INFO, hover_color=Theme.PRIMARY_HOVER)
        self.btn_rubric_open.grid(row=1, column=1, padx=(0, 6), pady=6, sticky="w")
        ToolTip(self.btn_rubric_open, "打开文件")
        
        self.btn_rubric_clear = ctk.CTkButton(self.files_card, text="", image=self.icons.get("clear"), command=self.clear_rubric, width=36, height=36, corner_radius=8, fg_color=Theme.DANGER, hover_color=Theme.DANGER_HOVER)
        self.btn_rubric_clear.grid(row=1, column=2, padx=(0, 12), pady=6, sticky="w")
        ToolTip(self.btn_rubric_clear, "取消选择")
        
        self.lbl_rubric_status = ctk.CTkLabel(self.files_card, text=self.t("status_not_selected"), text_color=("gray40", "gray60"), font=ctk.CTkFont(size=13))
        self.lbl_rubric_status.grid(row=1, column=3, padx=12, sticky="w")

        # Folder
        self.btn_folder = ctk.CTkButton(self.files_card, text=" " + self.t("btn_folder"), image=self.icons.get("folder"), command=self.select_folder, width=160, height=36, corner_radius=8, font=ctk.CTkFont(size=13), fg_color=Theme.INFO, text_color="white", anchor="w")
        self.btn_folder.grid(row=2, column=0, padx=20, pady=6, sticky="w")
        
        # Folder Controls
        self.btn_folder_open = ctk.CTkButton(self.files_card, text="", image=self.icons.get("open"), command=self.open_folder, width=36, height=36, corner_radius=8, fg_color=Theme.INFO, hover_color=Theme.PRIMARY_HOVER)
        self.btn_folder_open.grid(row=2, column=1, padx=(0, 6), pady=6, sticky="w")
        ToolTip(self.btn_folder_open, "打开文件夹")
        
        self.btn_folder_clear = ctk.CTkButton(self.files_card, text="", image=self.icons.get("clear"), command=self.clear_folder, width=36, height=36, corner_radius=8, fg_color=Theme.DANGER, hover_color=Theme.DANGER_HOVER)
        self.btn_folder_clear.grid(row=2, column=2, padx=(0, 12), pady=6, sticky="w")
        ToolTip(self.btn_folder_clear, "取消选择")
        
        self.lbl_folder_status = ctk.CTkLabel(self.files_card, text=self.t("status_not_selected"), text_color=("gray40", "gray60"), font=ctk.CTkFont(size=13))
        self.lbl_folder_status.grid(row=2, column=3, padx=12, sticky="w")

        # Student List
        self.btn_list = ctk.CTkButton(self.files_card, text=" " + self.t("btn_list"), image=self.icons.get("document"), command=self.load_student_list, width=160, height=36, corner_radius=8, font=ctk.CTkFont(size=13), fg_color=Theme.INFO, text_color="white", anchor="w")
        self.btn_list.grid(row=3, column=0, padx=20, pady=(6, 16), sticky="w")
        
        # List Controls
        self.btn_list_open = ctk.CTkButton(self.files_card, text="", image=self.icons.get("open"), command=self.open_list, width=36, height=36, corner_radius=8, fg_color=Theme.INFO, hover_color=Theme.PRIMARY_HOVER)
        self.btn_list_open.grid(row=3, column=1, padx=(0, 6), pady=(6, 16), sticky="w")
        ToolTip(self.btn_list_open, "打开文件")
        
        self.btn_list_clear = ctk.CTkButton(self.files_card, text="", image=self.icons.get("clear"), command=self.clear_list, width=36, height=36, corner_radius=8, fg_color=Theme.DANGER, hover_color=Theme.DANGER_HOVER)
        self.btn_list_clear.grid(row=3, column=2, padx=(0, 12), pady=(6, 16), sticky="w")
        ToolTip(self.btn_list_clear, "取消选择")
        
        self.lbl_list_status = ctk.CTkLabel(self.files_card, text=self.t("status_not_uploaded"), text_color=("gray40", "gray60"), font=ctk.CTkFont(size=13))
        self.lbl_list_status.grid(row=3, column=3, padx=12, pady=(6, 16), sticky="w")

        # 2. Dashboard / Controls
        self.dashboard_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.dashboard_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.dashboard_frame.grid_columnconfigure(0, weight=4) # Give more space to controls
        self.dashboard_frame.grid_columnconfigure(1, weight=1, minsize=180) # Ensure stats visible

        # Controls
        self.controls_card = ctk.CTkFrame(self.dashboard_frame, corner_radius=12)
        self.controls_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        
        # Configure grid for equal button widths (5 buttons)
        for i in range(5):
            self.controls_card.grid_columnconfigure(i, weight=1)

        # Ultra Compact buttons: height 40, pady 5
        self.btn_start = ctk.CTkButton(self.controls_card, text=self.t("btn_start"), image=self.icons.get("start"), fg_color=Theme.SECONDARY, hover_color=Theme.SECONDARY_HOVER, text_color="#FFFFFF", text_color_disabled="#E0E0E0", height=40, font=ctk.CTkFont(size=14, weight="bold"), corner_radius=8, command=self.start_grading_thread, anchor="center")
        self.btn_start.grid(row=0, column=0, padx=4, pady=5, sticky="ew")
        
        self.btn_pause = ctk.CTkButton(self.controls_card, text=self.t("btn_pause"), image=self.icons.get("pause"), fg_color=Theme.WARNING, hover_color=Theme.WARNING_HOVER, text_color="#FFFFFF", text_color_disabled="#E0E0E0", height=40, font=ctk.CTkFont(size=14, weight="bold"), corner_radius=8, state="disabled", command=self.toggle_pause, anchor="center")
        self.btn_pause.grid(row=0, column=1, padx=4, pady=5, sticky="ew")
        
        self.btn_stop = ctk.CTkButton(self.controls_card, text=self.t("btn_stop"), image=self.icons.get("stop"), fg_color=Theme.DANGER, hover_color=Theme.DANGER_HOVER, text_color="#FFFFFF", text_color_disabled="#E0E0E0", height=40, font=ctk.CTkFont(size=14, weight="bold"), corner_radius=8, state="disabled", command=self.stop_grading, anchor="center")
        self.btn_stop.grid(row=0, column=2, padx=4, pady=5, sticky="ew")

        self.btn_review = ctk.CTkButton(self.controls_card, text=self.t("btn_review"), image=self.icons.get("review"), fg_color=Theme.INFO, hover_color=Theme.PRIMARY_HOVER, text_color="#FFFFFF", height=40, font=ctk.CTkFont(size=14, weight="bold"), corner_radius=8, command=self.open_review_window, anchor="center")
        self.btn_review.grid(row=0, column=3, padx=4, pady=5, sticky="ew")
        
        self.btn_regrade_obj = ctk.CTkButton(self.controls_card, text=self.t("btn_regrade_obj"), image=self.icons.get("refresh"), fg_color="#7C3AED", hover_color="#6D28D9", text_color="#FFFFFF", height=40, font=ctk.CTkFont(size=14, weight="bold"), corner_radius=8, command=self.regrade_all_objective, anchor="center")
        self.btn_regrade_obj.grid(row=0, column=4, padx=4, pady=5, sticky="ew")


        # Stats
        self.stats_card = ctk.CTkFrame(self.dashboard_frame, corner_radius=12)
        self.stats_card.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        
        # Ultra Compact stats
        self.lbl_progress = ctk.CTkLabel(self.stats_card, text=self.t("lbl_progress", completed=0, total=0), font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_progress.pack(pady=(5, 0))
        
        self.lbl_etr = ctk.CTkLabel(self.stats_card, text=self.t("lbl_etr", time="--:--"), font=ctk.CTkFont(size=12), text_color=("gray40", "gray60"))
        self.lbl_etr.pack(pady=(0, 5))

        # 3. Progress Bar (Restored visibility but kept compact padding)
        self.progress_bar = ctk.CTkProgressBar(self.main_frame, height=6, corner_radius=3)
        self.progress_bar.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        self.progress_bar.set(0)

        # 4. Logs (Expandable)
        self.log_frame = ctk.CTkFrame(self.main_frame, corner_radius=12, fg_color="transparent")
        self.log_frame.grid(row=3, column=0, sticky="nsew")
        self.log_frame.grid_rowconfigure(0, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)

        self.log_box = ctk.CTkTextbox(self.log_frame, font=ctk.CTkFont(family="SF Mono" if platform.system() == "Darwin" else "Consolas", size=12), corner_radius=12)
        self.log_box.grid(row=0, column=0, sticky="nsew")
        
        # Ensure row 3 (logs) takes up remaining space
        self.main_frame.grid_rowconfigure(3, weight=1)

    def load_initial_config(self):
        api_key = self.config_manager.get("api_key", "")
        base_url = self.config_manager.get("base_url", "")
        lang = self.config_manager.get("language", "CN")
        
        if api_key:
            self.entry_key.delete(0, "end")
            self.entry_key.insert(0, api_key)
        if base_url:
            self.entry_base.delete(0, "end")
            self.entry_base.insert(0, base_url)
            
        self.current_lang = lang
        self.combo_lang.set("中文" if lang == "CN" else "English")
        
        # Auto-load last used profile
        last_profile = self.config_manager.get_last_used()
        if last_profile and last_profile in self.config_manager.get_profile_names():
            profile_data = self.config_manager.load_profile(last_profile)
            if profile_data:
                self.apply_profile(profile_data)
                self.combo_profile.set(last_profile)
                self.log(self.t("log_auto_loaded", profile=last_profile))
        else:
            # No profile loaded, show placeholder
            profiles = self.get_profile_list()
            if profiles:
                self.combo_profile.set(profiles[0])
        
        self.log(self.t("msg_config_loaded"))

    def save_current_config(self):
        self.config_manager.set("api_key", self.entry_key.get().strip())
        self.config_manager.set("base_url", self.entry_base.get().strip())
        self.config_manager.set("language", self.current_lang)
    
    # Configuration Profile Management
    def get_profile_list(self):
        """Get list of profile names for dropdown"""
        profiles = self.config_manager.get_profile_names()
        return profiles if profiles else [self.t("profile_default_placeholder")]
    
    def on_profile_select(self, choice):
        """Handle profile selection change"""
        if choice == self.t("profile_default_placeholder"):
            return
        
        profile_data = self.config_manager.load_profile(choice)
        if profile_data:
            self.apply_profile(profile_data)
            # Update last_used in config
            self.config_manager.set("last_used", choice)
            self.log_separator()
            self.log(self.t("log_loaded_profile", profile=choice))
    
    def save_current_profile(self):
        """Save current settings as a profile"""
        # Get current settings
        api_key = getattr(self, "current_api_key", self.entry_key.get())
        
        profile_data = {
            "api_key": api_key,
            "base_url": self.entry_base.get().strip(),
            "provider": self.provider_var.get(),
            "model": self.combo_model.get(),
            "rubric_path": getattr(self, "rubric_path", ""),
            "exam_folder": getattr(self, "exam_folder", ""),
            "student_list": getattr(self.student_manager, "student_path", "") if hasattr(self, "student_manager") else ""
        }
        
        current_profile = self.combo_profile.get()
        default_placeholder = self.t("profile_default_placeholder")
        
        # If a valid profile is selected (not placeholder)
        if current_profile and current_profile != default_placeholder:
            # Ask to overwrite
            if messagebox.askyesno(self.t("title_overwrite"), self.t("msg_overwrite_profile", name=current_profile)):
                # Overwrite
                self.config_manager.save_profile(current_profile, profile_data)
                self.log_separator()
                self.log(self.t("log_saved_profile", profile=current_profile))
                return
        
        # If not overwriting, ask for new name
        dialog = ctk.CTkInputDialog(text=self.t("msg_enter_profile_name"), title=self.t("title_save_profile"))
        profile_name = dialog.get_input()
        
        if not profile_name or profile_name.strip() == "":
            return
            
        profile_name = profile_name.strip()
        self.config_manager.save_profile(profile_name, profile_data)
        
        # Update dropdown
        self.combo_profile.configure(values=self.config_manager.get_profile_names())
        self.combo_profile.set(profile_name)
        self.log_separator()
        self.log(self.t("log_saved_profile", profile=profile_name))
    
    def delete_current_profile(self):
        """Delete currently selected profile"""
        profile_name = self.combo_profile.get()
        
        if not profile_name:
            messagebox.showwarning(self.t("title_warning"), self.t("msg_no_profile_delete"))
            return
        
        # Confirm deletion
        if messagebox.askyesno(self.t("title_confirm_delete"), self.t("msg_confirm_delete", profile=profile_name)):
            self.config_manager.delete_profile(profile_name)
            
            # Update dropdown
            profiles = self.get_profile_list()
            self.combo_profile.configure(values=profiles)
            if profiles:
                self.combo_profile.set(profiles[0])
            
            self.log(self.t("log_deleted_profile", profile=profile_name))

    def _mask_api_key(self, key):
        if not key or len(key) < 8:
            return key
        return f"{key[:3]}...{key[-3:]}"

    def _on_key_focus_in(self, event):
        """Show real key on focus"""
        if hasattr(self, "current_api_key"):
            self.entry_key.delete(0, "end")
            self.entry_key.insert(0, self.current_api_key)

    def _on_key_focus_out(self, event):
        """Mask key on focus out"""
        key = self.entry_key.get()
        self.current_api_key = key # Update current key
        masked = self._mask_api_key(key)
        self.entry_key.delete(0, "end")
        self.entry_key.insert(0, masked)
        
    def _on_key_release(self, event):
        """Update current key as user types"""
        self.current_api_key = self.entry_key.get()
    
    def apply_profile(self, profile_data):
        """Apply a profile's configuration to the UI"""
        # Set API settings
        if "api_key" in profile_data:
            self.current_api_key = profile_data["api_key"]
            self.entry_key.delete(0, "end")
            self.entry_key.insert(0, self._mask_api_key(self.current_api_key))
        
        if "base_url" in profile_data:
            self.entry_base.delete(0, "end")
            self.entry_base.insert(0, profile_data["base_url"])
        
        if "provider" in profile_data:
            self.provider_var.set(profile_data["provider"])
            self.on_provider_change(profile_data["provider"])
        
        if "model" in profile_data:
            self.combo_model.set(profile_data["model"])
        
        # Set file paths
        # Rubric
        if "rubric_path" in profile_data and profile_data["rubric_path"]:
            self.rubric_path = profile_data["rubric_path"]
            if os.path.exists(self.rubric_path):
                self.lbl_rubric_status.configure(text=os.path.basename(self.rubric_path), text_color=("green", "lightgreen"))
            else:
                self.lbl_rubric_status.configure(text=self.t("status_not_selected"), text_color=("gray40", "gray60"))
        else:
            # Explicitly clear if not in profile or empty
            self.rubric_path = None
            self.lbl_rubric_status.configure(text=self.t("status_not_selected"), text_color=("gray40", "gray60"))
        
        # Exam Folder
        if "exam_folder" in profile_data and profile_data["exam_folder"]:
            self.exam_folder = profile_data["exam_folder"]
            if os.path.exists(self.exam_folder):
                self.lbl_folder_status.configure(text=os.path.basename(self.exam_folder), text_color=("green", "lightgreen"))
            else:
                self.lbl_folder_status.configure(text=self.t("status_not_selected"), text_color=("gray40", "gray60"))
        else:
            # Explicitly clear
            self.exam_folder = None
            self.lbl_folder_status.configure(text=self.t("status_not_selected"), text_color=("gray40", "gray60"))
        
        # Student List
        if "student_list" in profile_data and profile_data["student_list"]:
            student_path = profile_data["student_list"]
            if os.path.exists(student_path):
                count = self.student_manager.load_from_file(student_path)
                if count > 0:
                    self.lbl_list_status.configure(text=self.t("status_students", count=count), text_color=("green", "lightgreen"))
            else:
                self.lbl_list_status.configure(text=self.t("status_not_uploaded"), text_color=("gray40", "gray60"))
        else:
            # Explicitly clear
            if hasattr(self, "student_manager"):
                self.student_manager.student_path = None
                self.student_manager.students = []
            self.lbl_list_status.configure(text=self.t("status_not_uploaded"), text_color=("gray40", "gray60"))


    def t(self, key, **kwargs):
        """Translate helper"""
        text = TRANSLATIONS.get(self.current_lang, TRANSLATIONS["CN"]).get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text

    def change_language(self, choice):
        self.current_lang = "CN" if choice == "中文" else "EN"
        self.update_ui_text()
        self.save_current_config()

    def update_ui_text(self):
        self.title(self.t("app_title"))
        self.logo_label.configure(text=self.t("logo"))
        
        self.lbl_lang.configure(text=self.t("lbl_language"))
        self.lbl_config_profile.configure(text=self.t("lbl_config_profile"))
        self.btn_save_profile.configure(text=self.t("btn_save_profile"))
        self.btn_delete_profile.configure(text=self.t("btn_delete_profile"))
        
        # Update config profile dropdown placeholder if showing default text
        current_profile = self.combo_profile.get()
        if current_profile in ["未保存的配置", "Unsaved Config"]:
            self.combo_profile.set(self.t("profile_default_placeholder"))
            
        self.lbl_key.configure(text=self.t("lbl_key"))
        self.lbl_base.configure(text=self.t("lbl_base"))
        self.lbl_provider.configure(text=self.t("lbl_provider"))
        self.lbl_model.configure(text=self.t("lbl_model"))
        self.btn_get_models.configure(text=self.t("btn_get_models"))
        self.btn_test_connection.configure(text=self.t("btn_test_connection"))
        
        self.lbl_resources.configure(text=self.t("lbl_resources"))
        self.btn_rubric.configure(text=self.t("btn_rubric"))
        self.btn_folder.configure(text=self.t("btn_folder"))
        self.btn_list.configure(text=self.t("btn_list"))
        
        if "Not Selected" in self.lbl_rubric_status.cget("text") or "未选择" in self.lbl_rubric_status.cget("text"):
            self.lbl_rubric_status.configure(text=self.t("status_not_selected"))
        if "Not Selected" in self.lbl_folder_status.cget("text") or "未选择" in self.lbl_folder_status.cget("text"):
            self.lbl_folder_status.configure(text=self.t("status_not_selected"))
        
        # Update student list status - handle both "Not Uploaded" and student count
        current_list_text = self.lbl_list_status.cget("text")
        if "Not Uploaded" in current_list_text or "未上传" in current_list_text:
            self.lbl_list_status.configure(text=self.t("status_not_uploaded"))
        elif current_list_text:  # If there's any text
            # Extract count from current text and update with translation
            import re
            match = re.search(r'(\d+)', current_list_text)
            if match:
                count = int(match.group(1))
                # Check if it looks like a student count (has number + text)
                if "student" in current_list_text.lower() or "名学生" in current_list_text or "学生" in current_list_text:
                    self.lbl_list_status.configure(text=self.t("status_students", count=count))
             
        self.btn_start.configure(text=self.t("btn_start"))
        if self.pause_event.is_set():
            self.btn_pause.configure(text=self.t("btn_pause"))
        else:
            self.btn_pause.configure(text=self.t("btn_resume"))
        self.btn_stop.configure(text=self.t("btn_stop"))
        self.btn_review.configure(text=self.t("btn_review"))
        self.btn_regrade_obj.configure(text=self.t("btn_regrade_obj"))
        
        self.update_progress_ui() # Update progress text

    def on_provider_change(self, choice):
        current_model = self.combo_model.get()
        if choice == "OpenAI":
            if "gemini" in current_model.lower() and "maxthinking" not in current_model.lower():
                self.combo_model.set("gpt-4o")
        elif choice == "Gemini":
            if "gpt" in current_model.lower():
                self.combo_model.set("gemini-1.5-pro")

    def check_models(self):
        # Use current_api_key if available
        api_key = getattr(self, "current_api_key", self.entry_key.get())
        if not api_key:
            messagebox.showerror(self.t("title_error"), self.t("msg_enter_key"))
            return
        self.btn_get_models.configure(state="disabled", text=self.t("checking"))
        def run_check():
            try:
                engine = AIGraderEngine(self.provider_var.get(), api_key, self.entry_base.get())
                models = engine.get_available_models()
                self.after(0, lambda: self.update_model_list(models))
            except Exception as e:
                err = str(e)
                self.after(0, lambda: messagebox.showerror(self.t("title_check_failed"), err))
            finally:
                self.after(0, lambda: self.btn_get_models.configure(state="normal", text=self.t("btn_get_models")))
        threading.Thread(target=run_check, daemon=True).start()

    def test_connection(self):
        """Test API connection with current settings"""
        api_key = getattr(self, "current_api_key", self.entry_key.get())
        if not api_key:
            messagebox.showerror(self.t("title_error"), self.t("msg_enter_key"))
            return
            
        self.btn_test_connection.configure(state="disabled", text=self.t("checking"))
        
        def run_test():
            try:
                engine = AIGraderEngine(self.provider_var.get(), api_key, self.entry_base.get(), self.combo_model.get())
                
                # Simple generation test
                if engine.provider == "OpenAI":
                    engine.client.chat.completions.create(
                        model=engine.model_name,
                        messages=[{"role": "user", "content": "Hi"}],
                        max_tokens=1
                    )
                elif engine.provider == "Gemini":
                    engine.gemini_model.generate_content("Hi")
                
                self.after(0, lambda: messagebox.showinfo(self.t("title_success"), self.t("msg_test_success")))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror(self.t("title_error"), self.t("msg_test_failed", error=str(e))))
            finally:
                self.after(0, lambda: self.btn_test_connection.configure(state="normal", text=self.t("btn_test_connection")))
        
        threading.Thread(target=run_test, daemon=True).start()

    def update_model_list(self, models):
        if not models: return
        self.combo_model.configure(values=models)
        self.combo_model.set(models[0])
        messagebox.showinfo(self.t("title_success"), self.t("check_success", count=len(models)))

    def log(self, message):
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{current_time}] {message}\n")
        self.log_box.see("end")

    def log_separator(self):
        self.log_box.insert("end", "--------------------------------------------------\n")
        self.log_box.see("end")

    def check_ready_and_verify(self):
        """
        Only trigger verification if all 3 resources are selected.
        """
        if self.rubric_path and self.exam_folder and self.student_manager.students:
            self.check_completion_status()

    def load_rubric(self):
        default_dir = os.path.expanduser("~/Downloads")
        path = filedialog.askopenfilename(initialdir=default_dir, filetypes=[("Text Files", "*.txt"), ("Markdown", "*.md")])
        if path:
            self.rubric_path = path
            self.lbl_rubric_status.configure(text=os.path.basename(path), text_color="#106A38")
            
            self.check_ready_and_verify()

    def select_folder(self):
        default_dir = os.path.expanduser("~/Downloads/photo")
        if not os.path.exists(default_dir):
            default_dir = os.path.expanduser("~/Downloads")
        path = filedialog.askdirectory(initialdir=default_dir)
        if path:
            self.exam_folder = path
            self.lbl_folder_status.configure(text=os.path.basename(path), text_color="#106A38")
            self.check_ready_and_verify()

    def load_student_list(self):
        default_dir = os.path.expanduser("~/Downloads")
        path = filedialog.askopenfilename(initialdir=default_dir, filetypes=[("Excel/CSV", "*.xlsx *.csv")])
        if path:
            try:
                count = self.student_manager.load_from_file(path)
                self.lbl_list_status.configure(text=self.t("status_students", count=count), text_color="#106A38")
                self.log(self.t("msg_list_loaded", count=count))
                self.check_ready_and_verify()
            except Exception as e:
                self.log(self.t("msg_list_failed", error=e))
                self.lbl_list_status.configure(text=self.t("status_failed"), text_color="#DC2626")

    def _verify_files_sync(self):
        """Synchronous version of verification logic. Returns (missing_reports, missing_jsons, missing_csv, failed_files)"""
        if not self.exam_folder: return [], [], [], []
        
        # 1. Get Images
        valid_extensions = ('.png', '.jpg', '.jpeg')
        try:
            images = [f for f in os.listdir(self.exam_folder) if f.lower().endswith(valid_extensions)]
            total_images = len(images)
        except Exception: return [], [], [], []

        if total_images == 0: return [], [], [], []

        # 2. Load CSV Data for quick lookup
        csv_data = set() # Stores (Room, Seat) tuples
        csv_filenames = set() # Stores Original Filenames
        
        # Check grading_data first, then root
        grading_data_dir = os.path.join(self.exam_folder, "grading_data")
        csv_names = ["成绩汇总表.csv", "Grade_Summary.csv"]
        csv_path = None
        
        # Try grading_data first
        for name in csv_names:
            p = os.path.join(grading_data_dir, name)
            if os.path.exists(p):
                csv_path = p
                break
        
        # Fallback to root
        if not csv_path:
            for name in csv_names:
                p = os.path.join(self.exam_folder, name)
                if os.path.exists(p):
                    csv_path = p
                    break
                
        if csv_path:
            try:
                import csv
                with open(csv_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Handle localized headers
                        r = (row.get('考场') or row.get('Room') or '').strip()
                        s = (row.get('座号') or row.get('Seat') or '').strip()
                        if r and s: csv_data.add((r, s))
                        
                        # Track original filename
                        orig = (row.get('原始文件') or row.get('Original File') or '').strip()
                        if orig: csv_filenames.add(orig)
                        
                        # Track renamed filename
                        renamed = (row.get('重命名文件') or row.get('Renamed File') or '').strip()
                        if renamed: 
                            csv_filenames.add(renamed)
            except Exception as e:
                self.log(self.t("log_failed_csv", error=e))

        # 3. Verify 1-to-1
        missing_reports = []
        missing_csv = []
        missing_jsons = []
        failed_files = []
        
        reports_dir = os.path.join(self.exam_folder, "reports")
        failed_dir = os.path.join(self.exam_folder, "failed")
        success_dir = os.path.join(self.exam_folder, "success") # New success folder
        
        checked_count = 0
        for filename in images:
            checked_count += 1
            # Only log progress if running in main thread context (optional check, or just skip logging in sync mode)
            # if checked_count % 50 == 0:
            #     self.after(0, lambda c=checked_count: self.log(self.t("log_verified_progress", current=c, total=total_images)))

            # Check 0: If filename is in CSV, it's verified (for CSV part)
            is_in_csv = filename in csv_filenames

            # Get Student Info
            student_info, _ = self.student_manager.get_student_by_filename(filename)
            room = str(student_info.get('room', '未知'))
            seat = str(student_info.get('seat', '未知'))
            
            # Check Report (.md)
            md_name = f"{room}-{seat}.md"
            md_path = os.path.join(reports_dir, md_name)
            
            report_found = False
            if os.path.exists(md_path):
                report_found = True
            else:
                # Try zero-padded version
                if room.isdigit() and seat.isdigit():
                    padded_room = room.zfill(2)
                    padded_seat = seat.zfill(2)
                    padded_path = os.path.join(reports_dir, f"{padded_room}-{padded_seat}.md")
                    if os.path.exists(padded_path):
                        report_found = True
                        
                # Fallback: Check by filename (basename) ALWAYS if not found by Room-Seat
                if not report_found:
                    base_name = os.path.splitext(filename)[0]
                    fallback_path = os.path.join(reports_dir, f"{base_name}.md")
                    if os.path.exists(fallback_path):
                        report_found = True
            
            # Check JSON (.json)
            json_name = f"{room}-{seat}.json"
            json_path = os.path.join(reports_dir, json_name)
            
            json_found = False
            if os.path.exists(json_path):
                json_found = True
            else:
                # Try zero-padded version
                if room.isdigit() and seat.isdigit():
                    padded_room = room.zfill(2)
                    padded_seat = seat.zfill(2)
                    padded_path = os.path.join(reports_dir, f"{padded_room}-{padded_seat}.json")
                    if os.path.exists(padded_path):
                        json_found = True

                if not json_found:
                        base_name = os.path.splitext(filename)[0]
                        if os.path.exists(os.path.join(reports_dir, f"{base_name}.json")):
                            json_found = True

            # Check CSV
            in_csv = (room, seat) in csv_data
            if not in_csv and room.isdigit() and seat.isdigit():
                in_csv = (room.zfill(2), seat.zfill(2)) in csv_data
            
            # --- Reverse Lookup Strategy (New) ---
            # If standard checks failed, try to find by original filename in JSONs
            if (not report_found or not json_found) and os.path.exists(reports_dir):
                # Lazy load the reverse map only if needed
                if not hasattr(self, '_reverse_lookup_map'):
                    self._reverse_lookup_map = {}
                    try:
                        for f in os.listdir(reports_dir):
                            if f.endswith(".json"):
                                j_path = os.path.join(reports_dir, f)
                                try:
                                    with open(j_path, 'r', encoding='utf-8') as jf:
                                        data = json.load(jf)
                                        orig_name = data.get('original_filename', '')
                                        if orig_name:
                                            base_f = os.path.splitext(f)[0]
                                            self._reverse_lookup_map[orig_name] = base_f
                                except: pass
                    except: pass
                
                # Check map
                if filename in self._reverse_lookup_map:
                    found_base = self._reverse_lookup_map[filename]
                    
                    if not report_found:
                        if os.path.exists(os.path.join(reports_dir, f"{found_base}.md")):
                            report_found = True
                            
                    if not json_found:
                        if os.path.exists(os.path.join(reports_dir, f"{found_base}.json")):
                            json_found = True
                            
                    # Also check CSV via found_base (which is usually Room-Seat)
                    if not in_csv:
                        # Try to parse Room-Seat from found_base
                        parts = found_base.split('-')
                        if len(parts) == 2:
                            r, s = parts[0], parts[1]
                            if (r, s) in csv_data: in_csv = True
                            elif (r.zfill(2), s.zfill(2)) in csv_data: in_csv = True

            # Final Check: If still not found after reverse lookup, add to missing list
            if not report_found:
                missing_reports.append(filename)
            if not json_found:
                missing_jsons.append(filename)
            # CSV check: Either by filename OR by (room, seat)
            if not is_in_csv and not in_csv:
                missing_csv.append(filename)

        # Check Failed Folder
        if os.path.exists(failed_dir):
                try:
                    failed_files.extend([f for f in os.listdir(failed_dir) if f.lower().endswith(valid_extensions)])
                except: pass
            
        # Check Success Folder (files here are considered processed/verified if they have reports)

        if os.path.exists(success_dir):
             try:
                success_files = [f for f in os.listdir(success_dir) if f.lower().endswith(valid_extensions)]
                pass
             except: pass
            
        return missing_reports, missing_jsons, missing_csv, failed_files

    def check_completion_status(self):
        """
        Strict 1-to-1 verification (Async Wrapper)
        """
        if not self.exam_folder: return

        # 1. Get Images count for log
        valid_extensions = ('.png', '.jpg', '.jpeg')
        try:
            images = [f for f in os.listdir(self.exam_folder) if f.lower().endswith(valid_extensions)]
            total_images = len(images)
        except Exception: return

        if total_images == 0: return

        self.log(self.t("log_verifying", total=total_images))
        
        # Use a thread to avoid blocking UI during verification of many files
        def verify_task():
            missing_reports, missing_jsons, missing_csv, failed_files = self._verify_files_sync()
            
            # Result
            self.after(0, lambda: self.handle_verification_result(total_images, missing_reports, missing_csv, missing_jsons, failed_files))

        threading.Thread(target=verify_task, daemon=True).start()

    def handle_verification_result(self, total, missing_reports, missing_csv, missing_jsons, failed_files):
        if not missing_reports and not missing_csv and not missing_jsons and not failed_files:
            self.log(self.t("msg_verification_pass"))
            
            if messagebox.askyesno(self.t("msg_grading_complete"), self.t("msg_enter_review")):
                self.after(100, self.open_review_window)
            self.btn_review.configure(state="normal")
        else:
            msg = self.t("msg_verification_fail", total=total) + "\n"
            # Enable review if at least some reports exist
            if len(missing_reports) < total:
                self.btn_review.configure(state="normal")
            else:
                # If no reports found, keep disabled? Or enable if user wants to check?
                # But ReviewWindow filters by report existence. So if 0 reports, it shows "No images".
                # So enabling it is safe (it will just show empty or close).
                self.btn_review.configure(state="normal")
            
            missing_set = set()
            
            if missing_reports:
                msg += self.t("msg_missing_reports", count=len(missing_reports)) + "\n"
                missing_set.update(missing_reports)
            if missing_jsons:
                msg += self.t("msg_missing_jsons", count=len(missing_jsons)) + "\n"
                missing_set.update(missing_jsons)
            if missing_csv:
                msg += self.t("msg_missing_csv", count=len(missing_csv)) + "\n"
                missing_set.update(missing_csv)
            if failed_files:
                msg += self.t("msg_failed_files", count=len(failed_files)) + "\n"
                missing_set.update(failed_files)
                
            self.log(msg)
            
            # Prompt to fix
            if messagebox.askyesno(self.t("msg_incomplete_title"), self.t("msg_incomplete_body", msg=msg)):
                self.start_grading_thread()

    def ensure_jsons_exist(self):
        """
        If .md exists but .json missing (Legacy), try to generate a minimal .json 
        so ReviewWindow can open.
        """
        reports_dir = os.path.join(self.exam_folder, "reports")
        if not os.path.exists(reports_dir): return
        
        # We iterate known students/images to reconstruct
        # Ideally we parse the CSV to get the scores back
        csv_path = os.path.join(self.exam_folder, "成绩汇总表.csv")
        if not os.path.exists(csv_path): return
        
        import csv
        csv_rows = []
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            csv_rows = list(reader)
            
        for row in csv_rows:
            room = row.get('考场')
            seat = row.get('座号')
            if not room or not seat: continue
            
            json_name = f"{room}-{seat}.json"
            json_path = os.path.join(reports_dir, json_name)
            
            if not os.path.exists(json_path):
                data = {
                    'total_score': row.get('总分', 0),
                    'ocr_name': row.get('OCR姓名', ''),
                    'ocr_class': row.get('OCR班级', ''),
                    'ocr_room': row.get('OCR考场', ''),
                    'ocr_seat': row.get('OCR座号', ''),
                    'ocr_id_written': row.get('OCR手写考号', ''),
                    'ocr_id_filled': row.get('OCR填涂考号', ''),
                    'db_student_info': {
                        'name': row.get('姓名', ''),
                        'id': row.get('考号', ''),
                        'class': row.get('班级', ''),
                        'room': room,
                        'seat': seat
                    },
                    'details': [] 
                }
                try:
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except: pass

    def load_layout_config(self):
        if not self.exam_folder: return
        
        # Ensure grading_data folder exists
        grading_data_dir = self.get_folder_path('grading_data')
        if not os.path.exists(grading_data_dir):
            os.makedirs(grading_data_dir)

        # Check grading_data first
        config_path = os.path.join(grading_data_dir, "layout_config.json")
        
        # Legacy check
        legacy_path = os.path.join(self.exam_folder, "layout_config.json")
        
        if not os.path.exists(config_path) and os.path.exists(legacy_path):
            self.log(f"⚠️ 发现旧版布局配置: {os.path.basename(legacy_path)}")
            self.log("🔄 正在迁移至 grading_data 目录...")
            try:
                shutil.move(legacy_path, config_path)
                self.log("✅ 迁移完成。")
            except Exception as e:
                self.log(f"❌ 迁移失败: {e}")
                try:
                    shutil.copy2(legacy_path, config_path)
                except: pass
        
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.layout_description = data.get("layout_description")
                    if self.layout_description:
                        self.template_confirmed = True
                        self.log("📄 Loaded saved layout configuration.")
            except Exception as e:
                self.log(self.t("log_failed_layout_load", error=e))

    def save_layout_config(self):
        if not self.exam_folder or not self.layout_description: return
        
        grading_data_dir = self.get_folder_path('grading_data')
        if not os.path.exists(grading_data_dir): os.makedirs(grading_data_dir)
        
        config_path = os.path.join(grading_data_dir, "layout_config.json")
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump({"layout_description": self.layout_description}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(self.t("log_failed_layout_save", error=e))

    def ensure_layout_and_run(self, callback):
        """
        Ensures layout is confirmed before running the callback.
        1. Check if confirmed.
        2. If not, try load.
        3. If not loaded, run detection.
        4. Show confirmation.
        5. Save and run.
        """
        self.log_separator()
        self.log(self.t("log_detecting_layout"))
        
        if self.template_confirmed:
            self.log(self.t("log_layout_detected"))
            callback()
            return

        # Try load
        self.load_layout_config()
        if self.template_confirmed:
            self.log(self.t("log_layout_detected"))
            callback()
            return

        # Need detection
        self.log(self.t("log_no_layout_generating"))
        self.start_detection_thread(callback)

    def on_closing(self):
        if messagebox.askokcancel(self.t("title_quit"), self.t("msg_quit_confirm")):
            try:
                self.stop_grading(silent=True)
            except:
                pass
            self.destroy()
            os._exit(0)

    def start_grading_thread(self):
        if not self.rubric_path or not self.exam_folder:
            messagebox.showerror(self.t("title_error"), self.t("msg_select_files"))
            return
        if not self.entry_key.get():
            messagebox.showerror(self.t("title_error"), self.t("msg_enter_key"))
            return
        self.save_current_config()
        
        self.log_separator()
        self.log(self.t("log_checking_answer_key"))
        
        # Check and generate answer key if needed (BEFORE grading)
        # Chain: Answer Key -> Layout -> CSV -> Grading
        self.ensure_answer_key_and_run(lambda: self.ensure_layout_and_run(lambda: self.ensure_csv_and_run(self._run_grading_process)))
    
    def ensure_answer_key_and_run(self, callback):
        """Ensure answer key exists before running callback"""
        # Check if answer_key.json exists
        # self.log_separator() # Redundant, handled by start_grading_thread
        # self.log("🔍 正在检测标准答案配置...") # Redundant
        key_loaded = False
        if self.exam_folder:
            grading_data_dir = self.get_folder_path('grading_data')
            json_path = os.path.join(grading_data_dir, "answer_key.json")
            
            # Legacy check
            legacy_path = os.path.join(self.exam_folder, "answer_key.json")
            if not os.path.exists(json_path) and os.path.exists(legacy_path):
                json_path = legacy_path
                
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        self.answer_key = json.load(f)
                    self.log(self.t("log_answer_key_found"))
                    key_loaded = True
                except Exception as e:
                    self.log(f"Failed to load existing answer key: {e}")
        
        if key_loaded:
            callback()
            return
    
        # No answer key found, need to extract
        self.log(self.t("log_no_answer_key"))
        if not self.rubric_path:
            messagebox.showerror(self.t("title_error"), "Cannot generate answer key: no rubric loaded.")
            return
        
        # Extract in background, then run callback after confirmation
        threading.Thread(target=self.extract_answer_key_for_grading, args=(callback,), daemon=True).start()
    
    def extract_answer_key_for_grading(self, callback):
        """Extract answer key and then run callback after user confirms"""
        try:
            with open(self.rubric_path, 'r', encoding='utf-8') as f:
                rubric_text = f.read()
            
            api_key = getattr(self, "current_api_key", self.entry_key.get())
            if not api_key: 
                self.after(0, lambda: messagebox.showerror(self.t("title_error"), "API key required"))
                return
            
            engine = AIGraderEngine(self.provider_var.get(), api_key, self.entry_base.get(), self.combo_model.get())
            
            self.after(0, lambda: self.log(self.t("log_request_sent_rocket")))
            
            # Use Concurrent Extraction & Consolidation (with detailed logging)
            raw_results = engine.extract_answer_key_concurrent(rubric_text, log_callback=lambda msg: self.after(0, lambda m=msg: self.log(m)), t_func=self.t)
            
    
            
            final_key, report = engine.consolidate_answer_keys(raw_results, log_callback=lambda msg: self.after(0, lambda m=msg: self.log(m)), t_func=self.t)
            
            count = len(final_key)
            self.after(0, lambda: self.log(self.t("log_answers_extracted", count=count)))
            
            # Show Review Dialog
            json_path = None
            if self.exam_folder:
                grading_data_dir = self.get_folder_path('grading_data')
                if not os.path.exists(grading_data_dir): os.makedirs(grading_data_dir)
                json_path = os.path.join(grading_data_dir, "answer_key.json")
            
            def on_confirm_and_run(confirmed_json):
                self.answer_key = confirmed_json
                
                # Save to JSON
                if json_path:
                    try:
                        with open(json_path, 'w', encoding='utf-8') as f:
                            json.dump(self.answer_key, f, ensure_ascii=False, indent=2)
                        self.log(self.t("log_answer_key_confirmed_generated"))
                        
                        # Trigger CSV generation immediately -> REMOVED
                        # We wait for ensure_csv_and_run to handle this at the correct time.
                        # self.generate_csv_headers_from_key()
                        
                    except Exception as e:
                        self.log(f"Failed to save answer key: {e}")
                
                # Now run the grading process
                callback()
            
            self.after(0, lambda: self.log(self.t("log_waiting_confirmation")))
            self.after(0, lambda: self.show_standard_answer_dialog_with_callback(final_key, report, json_path, on_confirm_and_run))
            
        except Exception as e:
            self.after(0, lambda e=e: self.log(f"Failed to extract answer key: {e}"))
            self.after(0, lambda: messagebox.showerror(self.t("title_error"), f"Answer key extraction failed: {e}"))

    def ensure_csv_and_run(self, callback):
        """Ensure CSV exists before running callback"""
        self.log_separator() # Add separator before CSV check/generation
        grading_data_dir = self.get_folder_path('grading_data')
        csv_en = "Grade_Summary.csv"
        csv_cn = "成绩汇总表.csv"
        
        # Use language-specific filename
        csv_filename = csv_cn if self.current_lang == "CN" else csv_en
        path_grading_data = os.path.join(grading_data_dir, csv_filename)
        
        # Legacy paths
        path_en_root = os.path.join(self.exam_folder, csv_en)
        path_cn_root = os.path.join(self.exam_folder, csv_cn)
        
        # Check for legacy files and migrate if needed
        legacy_found = None
        if os.path.exists(path_en_root): legacy_found = path_en_root
        elif os.path.exists(path_cn_root): legacy_found = path_cn_root
        
        if os.path.exists(path_grading_data):
            self.log("✅ 已找到成绩汇总表 (grading_data)。")

        elif legacy_found:
            self.log(f"⚠️ 发现旧版成绩汇总表: {os.path.basename(legacy_found)}")
            self.log("🔄 正在迁移至 grading_data 目录...")
            try:
                shutil.move(legacy_found, path_grading_data)
                self.log("✅ 迁移完成。")
            except Exception as e:
                self.log(f"❌ 迁移失败: {e}")


                try:
                    shutil.copy2(legacy_found, path_grading_data)
                except: pass
        
        # Final check
        if os.path.exists(path_grading_data):
            callback()
            return

        # CSV not found - check if we have JSON reports to rebuild from
        reports_dir = self.get_folder_path('reports')
        json_files = []
        if reports_dir and os.path.exists(reports_dir):
            json_files = [f for f in os.listdir(reports_dir) if f.endswith('.json')]
        
        if json_files:
            # JSON reports exist - rebuild CSV from them
            self.log(self.t("log_csv_missing_has_data"))
            self.log(self.t("log_rebuilding_csv_from_reports", count=len(json_files)))
            self.regenerate_summary_csv()
            self.log(self.t("log_csv_rebuild_complete"))
        else:
            # No JSON reports - generate empty CSV with headers only
            self.log(self.t("log_no_grade_summary"))
            self.log("📝 生成空白CSV模板（仅包含表头）...")
            self.generate_csv_headers_from_key()
            csv_filename = "成绩汇总表.csv" if self.current_lang == "CN" else "Grade_Summary.csv"
            self.log(self.t("log_grade_summary_generated", filename=csv_filename))
        
        callback()

    def generate_csv_headers_from_key(self):
        """Generate CSV with headers based on answer key"""
        if not self.answer_key: return
        
        is_en = (self.current_lang == "EN")
        
        # Construct dummy data_dict with all keys
        # We just need the headers, so we can use the same logic as regenerate_csv_from_jsons
        # Or simpler: just construct the header list directly.
        
        # 1. Basic Info
        if is_en:
            headers = ['Room', 'Seat', 'Class', 'Name', 'ID']
            headers += ['Consistency', 'Matches', 'Review Status', 'Absence Marker', 'Confirm Absence']
            headers += ['Total Score', 'Objective Total', 'Subjective Total']
        else:
            headers = ['考场', '座号', '班级', '姓名', '考号']
            headers += ['信息一致性', '匹配项数', '复审状态', '缺考标记', '确认缺考']
            headers += ['总分', '客观题', '主观题']
            
        # 4. Subjective Questions
        subj_keys = []
        main_q_ids = set()
        
        for item in self.answer_key:
            if isinstance(item, dict) and item.get('type') == 'subjective':
                qid = str(item.get('id', ''))
                
                # Check if it's a sub-question or main question
                match = re.match(r"(\d+)\((\d+)\)", qid)
                if match:
                    main_id = match.group(1)
                    main_q_ids.add(main_id)
                    key = f"Q{qid} Score" if is_en else f"Q{qid} 得分"
                    subj_keys.append(key)
                else:
                    # It's a main question ID (e.g. "17")
                    main_q_ids.add(qid)
                    # If it has score, it might be a single question


                    pass

        # Add Main Totals
        for m_id in main_q_ids:
            key = f"Q{m_id} Total" if is_en else f"Q{m_id} 总分"
            subj_keys.append(key)
            
        # Sort Subjective
        def subj_sort(k):
            nums = re.findall(r"\d+", k)
            if not nums: return (999, 999)
            main_id = int(nums[0])
            sub_id = int(nums[1]) if len(nums) > 1 else 0
            return (main_id, sub_id)
        subj_keys.sort(key=subj_sort)
        headers += subj_keys
        
        # 5. Objective Questions
        obj_keys = []
        for item in self.answer_key:
            if isinstance(item, dict) and item.get('type') == 'objective':
                qid = str(item.get('id', ''))
                ans_key = f"Q{qid} Answer" if is_en else f"Q{qid} 答案"
                score_key = f"Q{qid} Score" if is_en else f"Q{qid} 得分"
                obj_keys.append(ans_key)
                obj_keys.append(score_key)
        
        # Sort Objective
        def obj_sort(k):
            nums = re.findall(r"\d+", k)
            if not nums: return (999, 999)
            qid = int(nums[0])
            is_score = 1 if ("Score" in k or "得分" in k) else 0
            return (qid, is_score)
        obj_keys.sort(key=obj_sort)
        headers += obj_keys
        
        # 6. OCR Info
        if is_en:
            headers += ['OCR Name', 'OCR Class', 'OCR Room', 'OCR Seat', 'OCR Written ID', 'OCR Filled ID']
            headers += ['Original File']
        else:
            headers += ['OCR姓名', 'OCR班级', 'OCR考场', 'OCR座号', 'OCR手写考号', 'OCR填涂考号']
            headers += ['原始文件']
            
        # Write CSV with language-specific filename
        grading_data_dir = self.get_folder_path('grading_data')
        if not os.path.exists(grading_data_dir): os.makedirs(grading_data_dir)
        
        csv_filename = "成绩汇总表.csv" if self.current_lang == "CN" else "Grade_Summary.csv"
        csv_path = os.path.join(grading_data_dir, csv_filename)
        
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()

    def _run_grading_process(self):
        self.processing = True
        self.stop_event.clear()
        self.pause_event.set()
        
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal", text=self.t("btn_pause"))
        self.btn_stop.configure(state="normal")
        
        # Reset session stats
        self.start_time = time.time()
        self.session_completed_count = 0
        
        self.log_separator()
        threading.Thread(target=self.process_images, daemon=True).start()

    def start_detection_thread(self, callback):
        self.btn_start.configure(state="disabled")
        threading.Thread(target=self.run_detection, args=(callback,), daemon=True).start()

    # --- Resource Controls ---
    def open_path(self, path):
        if not path or not os.path.exists(path):
            return
        
        try:
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.call(['open', path])
            else:
                subprocess.call(['xdg-open', path])
        except Exception as e:
            self.log(f"Failed to open path: {e}")

    def open_rubric(self):
        self.open_path(self.rubric_path)

    def clear_rubric(self):
        self.rubric_path = None
        self.lbl_rubric_status.configure(text=self.t("status_not_selected"), text_color=("gray40", "gray60"))
        self.save_current_config()

    def open_folder(self):
        self.open_path(self.exam_folder)

    def clear_folder(self):
        self.exam_folder = None
        self.lbl_folder_status.configure(text=self.t("status_not_selected"), text_color=("gray40", "gray60"))
        self.save_current_config()

    def open_list(self):
        self.open_path(self.student_list_path)

    def clear_list(self):
        self.student_list_path = None
        if hasattr(self, "student_manager"):
            self.student_manager.student_path = None
            self.student_manager.students = [] # Clear loaded students too
            
        self.lbl_list_status.configure(text=self.t("status_not_uploaded"), text_color=("gray40", "gray60"))
        self.save_current_config()

    def parse_student_list_thread(self):
        # This method was likely intended to be called with a callback, but the snippet provided
        # seems to have merged it with the start_detection_thread.
        # Assuming the user wants to keep the original start_detection_thread and add these methods.
        # The snippet provided for `parse_student_list_thread` is incomplete and seems to be a copy-paste error.
        # I will insert the resource control methods and keep the original `start_detection_thread` and `run_detection`.
        # The user's snippet for `parse_student_list_thread` and the subsequent `start_detection_thread` and `run_detection`
        # are conflicting. I will assume the user wants to add the resource control methods and keep the existing
        # `start_detection_thread` and `run_detection` as they are.
        # The instruction says "Insert missing callback methods" but the snippet contains full method definitions.
        # Given the context, the user likely wants to add the `open_path`, `open_rubric`, `clear_rubric`, etc. methods.
        # The `parse_student_list_thread` in the snippet is malformed. I will insert the other methods.
        pass # Placeholder for the actual parse_student_list_thread implementation if it exists elsewhere.

    def run_detection(self, callback):
        try:
            # 1. Sample images
            valid_extensions = ('.png', '.jpg', '.jpeg')
            files = [f for f in os.listdir(self.exam_folder) if f.lower().endswith(valid_extensions)]
            
            if not files: # Changed from self.image_files to files as per original context
                self.after(0, lambda: messagebox.showerror(self.t("title_error"), self.t("msg_no_images")))
                self.after(0, lambda: self.reset_ui_state())
                return
                
            import random
            # Sample all files if total < 3, otherwise sample 3
            sample_count = len(files) if len(files) < 3 else 3
            sample_files = random.sample(files, sample_count)
            
            # 2. Detect concurrently
            api_key = getattr(self, "current_api_key", self.entry_key.get())
            grader = AIGraderEngine(self.provider_var.get(), api_key, self.entry_base.get(), self.combo_model.get())
            
            # Submit all detection tasks concurrently with 1 second stagger
            futures = []
            future_to_index = {}
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=sample_count)
            try:
                for i, fname in enumerate(sample_files):
                    # Log with filename
                    self.after(0, lambda i=i, fn=fname, sc=sample_count: self.log(self.t("msg_detecting", current=i+1, total=sc) + f" - {fn}"))
                    
                    path = os.path.join(self.exam_folder, fname)
                    future = executor.submit(grader.detect_regions, path)
                    future_to_index[future] = i + 1
                    futures.append(future)
                    
                    # Log Request Sent
                    self.after(0, lambda i=i: self.log(self.t("log_layout_req_sent", index=i+1)))
                    
                    # Stagger by 1 second between starts
                    if i < len(sample_files) - 1:
                        time.sleep(1)
                
                # Wait for all detections to complete
                descriptions = []
                for future in concurrent.futures.as_completed(futures):
                    idx = future_to_index[future]
                    try:
                        desc = future.result()
                        descriptions.append(desc)
                        # Log Request Received
                        self.after(0, lambda idx=idx: self.log(self.t("log_layout_req_received", index=idx)))
                    except Exception as e:
                        self.log(f"Request {idx} failed: {e}")
            finally:
                executor.shutdown(wait=True)
            
            # 3. Consolidate
            self.after(0, lambda: self.log(self.t("log_layout_req_all_received", count=len(descriptions))))
            self.after(0, lambda: self.log(self.t("log_consolidating_layout")))
            self.after(0, lambda: self.log(self.t("log_consolidation_sent")))
            
            self.after(0, lambda: self.log(self.t("msg_consolidating")))
            final_layout = grader.consolidate_layout(descriptions)
            
            self.after(0, lambda: self.log(self.t("log_consolidation_received")))
            
            # 4. Show Confirmation (on main thread)
            self.after(0, lambda: self.log(self.t("log_waiting_confirmation")))
            self.after(0, lambda: self.show_confirmation_dialog(final_layout, callback))
            
        except Exception as e:
            self.after(0, lambda: self.log(self.t("msg_detect_failed", error=str(e))))
            self.after(0, lambda: self.reset_ui_state())

    def show_confirmation_dialog(self, layout_description, callback):
        def on_confirm(new_desc):
            self.layout_description = new_desc
            self.template_confirmed = True
            self.save_layout_config()
            self.log(self.t("log_layout_confirmed_generated"))
            self.after(100, callback) # Run callback
            
        TemplateConfirmDialog(self, layout_description, on_confirm)

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.btn_pause.configure(text=self.t("btn_resume"), fg_color="#106A38")
            self.log(self.t("msg_paused"))
            
        else: # This was the original else block, the user's snippet had a syntax error here.
            self.pause_event.set()
            self.btn_pause.configure(text=self.t("btn_pause"), fg_color="#D97706")
            self.log(self.t("msg_resumed"))

    def stop_grading(self, silent=False):
        if not self.processing:
            return

        if silent or messagebox.askyesno(self.t("title_confirm"), self.t("msg_confirm_stop")):
            self.stop_event.set()
            self.pause_event.set() # Ensure threads can wake up to exit
            self.log(self.t("msg_stopping"))

    def write_summary_csv(self, data_dict, target_path=None):
        import csv
        
        is_en = (self.current_lang == "EN")
        if not self.exam_folder: return
        
        # Determine CSV path
        csv_path = target_path
        if not csv_path:
            # Check grading_data first
            grading_data_dir = self.get_folder_path('grading_data')
            csv_filename = "成绩汇总表.csv" if is_en == False else "Grade_Summary.csv"
            csv_path = os.path.join(grading_data_dir, csv_filename)
            
            # If not in grading_data, check root (legacy fallback)

            
            # 1. If target_path is None, try to find existing CSV.
            # 2. If no existing CSV, default to grading_data.
            
            existing_csv = None
            # Check grading_data first
            csv_filename_cn = "成绩汇总表.csv"
            csv_filename_en = "Grade_Summary.csv"
            current_csv = csv_filename_cn if is_en == False else csv_filename_en
            p1 = os.path.join(grading_data_dir, current_csv)
            if os.path.exists(p1): existing_csv = p1
            
            # Check root (try both names for legacy support)
            p2 = os.path.join(self.exam_folder, csv_filename_en)
            if not existing_csv and os.path.exists(p2): existing_csv = p2
            
            p3 = os.path.join(self.exam_folder, csv_filename_cn)
            if not existing_csv and os.path.exists(p3): existing_csv = p3
            
            if existing_csv:
                csv_path = existing_csv
            else:
                # Default to grading_data if folder exists, else create it
                if not os.path.exists(grading_data_dir): os.makedirs(grading_data_dir)
                csv_path = p1
            
        csv_filename = os.path.basename(csv_path)
        
        # Header Mappings
        header_map = {
            '考场': 'Room', '座号': 'Seat', '班级': 'Class', '姓名': 'Name', '考号': 'ID',
            '总分': 'Total Score', '信息一致性': 'Consistency', '匹配项数': 'Matches',
            'OCR姓名': 'OCR Name', 'OCR班级': 'OCR Class', 'OCR考场': 'OCR Room',
            'OCR座号': 'OCR Seat', 'OCR手写考号': 'OCR Written ID', 'OCR填涂考号': 'OCR Filled ID',
            '原始文件': 'Original File', '重命名文件': 'Renamed File', '客观题': 'Objective Score',
            '客观题正确数': 'Objective Correct', '客观题总数': 'Objective Total',
            '主观题': 'Subjective Score', '复审状态': 'Review Status', '缺考标记': 'Absence Marker',
            '确认缺考': 'Confirm Absence'
        }
        
        # Translate data_dict keys if EN, or translate dynamic keys if CN
        final_data = {}
        if is_en:
            for k, v in data_dict.items():
                new_key = header_map.get(k, k)
                final_data[new_key] = v
        else:
            # For Chinese, we need to translate dynamic keys (Qx Total -> Qx 总分)
            for k, v in data_dict.items():
                new_key = k
                if k.startswith("Q"):
                    new_key = new_key.replace(" Total", " 总分")
                    new_key = new_key.replace(" Answer", " 答案")
                    new_key = new_key.replace(" Score", " 得分")
                final_data[new_key] = v

        # Numeric Conversion for Excel
        for k, v in final_data.items():
            # Convert Room/Seat to int to remove leading zeros (e.g. "01" -> 1)
            if k in ['Room', 'Seat', '考场', '座号']:
                try:
                    final_data[k] = int(str(v).strip())
                except: pass
            # Convert Scores/ID to numbers if possible
            elif k in ['ID', '考号', 'Total Score', '总分', 'Objective Score', '客观题', 
                       'Subjective Score', '主观题', 'Objective Correct', '客观题正确数', 
                       'Objective Total', '客观题总数']:
                try:
                    s_val = str(v).strip()
                    if s_val.isdigit():
                        final_data[k] = int(s_val)
                    else:
                        val = float(s_val)
                        if val.is_integer():
                            final_data[k] = int(val)
                        else:
                            final_data[k] = val
                except: pass

        # Final Order: Priority -> Subjective Details -> Objective Details -> Others -> Original File
        headers = list(final_data.keys())
        
        def custom_sort(key):
            # Define order priority
            # 1. Basic Info
            fixed_order = [
                'Room', 'Seat', 'Class', 'Name', 'ID',
                '考场', '座号', '班级', '姓名', '考号',
                'Consistency', 'Matches', 'Review Status', 'Absence Marker', 'Confirm Absence',
                '信息一致性', '匹配项数', '复审状态', '缺考标记', '确认缺考',
                'Total Score', 'Objective Total', 'Subjective Total',
                '总分', '客观题', '主观题'
            ]
            
            if key in fixed_order:
                return (0, fixed_order.index(key))
                
            # 4. Subjective Questions (Sorted by QID)
            # Main Totals: Q17 Total / Q17 总分 -> 17, 0
            # Sub-scores: Q17(1) Score / Q17(1) 得分 -> 17, 1
            
            # Check for Subjective Keys
            if "Total" in key or "总分" in key:
                # Q17 Total
                try:
                    num = int(re.search(r"Q(\d+)", key).group(1))
                    return (1, num, 0)
                except: pass
            
            if "(" in key and ("Score" in key or "得分" in key):
                # Q17(1) Score
                try:
                    parts = re.search(r"Q(\d+)\((\d+)\)", key)
                    if parts:
                        return (1, int(parts.group(1)), int(parts.group(2)))
                except: pass
                
            # 5. Objective Questions (Sorted by QID)
            # Q1 Answer / Q1 答案 -> 2, 1, 0
            # Q1 Score / Q1 得分 -> 2, 1, 1
            if ("Answer" in key or "答案" in key or "Score" in key or "得分" in key) and "Total" not in key and "总分" not in key:
                 try:
                    num = int(re.search(r"Q(\d+)", key).group(1))
                    is_score = 1 if ("Score" in key or "得分" in key) else 0
                    return (2, num, is_score)
                 except: pass

            # 6. OCR Info
            ocr_order = [
                'OCR Name', 'OCR Class', 'OCR Room', 'OCR Seat', 'OCR Written ID', 'OCR Filled ID',
                'OCR姓名', 'OCR班级', 'OCR考场', 'OCR座号', 'OCR手写考号', 'OCR填涂考号'
            ]
            if key in ocr_order:
                return (3, ocr_order.index(key))

            # 7. Original File (Last)
            if key in ['Original File', '原始文件', 'Renamed File', '重命名文件']:
                return (4, 0)
                
            # Others
            return (5, key)

        sorted_headers = sorted(headers, key=custom_sort)

        with self.write_lock:
            file_exists = os.path.isfile(csv_path)
            existing_headers = []
            if file_exists:
                try:
                    with open(csv_path, 'r', encoding='utf-8-sig') as f:
                        reader = csv.reader(f)
                        existing_headers = next(reader, [])
                except: pass
            
            # If headers mismatch (or new file), rewrite/write header

            # Here we implement a check: if sorted_headers != existing_headers, we assume schema change.
            
            mode = 'a'
            if file_exists and existing_headers != sorted_headers:

                try:
                    all_rows = []
                    with open(csv_path, 'r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        all_rows = list(reader)
                    
                    mode = 'w' # Rewrite mode
                    # We will write all old rows + new row
                except Exception as e:
                    self.log(f"Error updating CSV schema: {e}")

                    mode = 'a'
            
            try:
                with open(csv_path, mode, newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=sorted_headers, extrasaction='ignore')
                    if mode == 'w' or not file_exists:
                        writer.writeheader()
                        if mode == 'w':
                            writer.writerows(all_rows)
                    
                    writer.writerow(final_data)
                self.after(0, lambda fn=csv_filename: self.log(self.t("log_csv_written", filename=fn)))
            except Exception as e:
                err = str(e)
                self.after(0, lambda e=err: self.log(self.t("log_csv_write_failed", error=e)))

    def regenerate_summary_csv(self, target_path=None):
        """Regenerate the entire summary CSV from report JSONs"""
        reports_dir = self.get_folder_path('reports')
        if not reports_dir or not os.path.exists(reports_dir):
            return
        
        # Determine target path
        if not target_path:
            grading_data_dir = self.get_folder_path('grading_data')
            if not os.path.exists(grading_data_dir): os.makedirs(grading_data_dir)
            csv_filename = "成绩汇总表.csv" if self.current_lang == "CN" else "Grade_Summary.csv"
            target_path = os.path.join(grading_data_dir, csv_filename)
            
        # Delete existing CSVs to start fresh (check both root and grading_data)
        csv_en = "Grade_Summary.csv"
        csv_cn = "成绩汇总表.csv"
        dirs_to_check = [self.exam_folder, self.get_folder_path('grading_data')]
        
        for d in dirs_to_check:
            if os.path.exists(d):
                for fname in [csv_en, csv_cn]:
                    path = os.path.join(d, fname)
                    if os.path.exists(path):
                        try: os.remove(path)
                        except: pass
        
        json_files = [f for f in os.listdir(reports_dir) if f.endswith('.json')]
        # Sort by room/seat if possible
        try:
            json_files.sort(key=lambda x: (int(x.split('-')[0]), int(x.split('-')[1].split('.')[0])))
        except:
            json_files.sort()
            
        for jf in json_files:
            try:
                with open(os.path.join(reports_dir, jf), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                db_info = data.get('db_student_info', {})
                
                # Calculate stats using helper
                _, _, consistency_note, matches, obj_score_sum = self.generate_report_content(data, db_info)
                
                total_score = data.get('total_score', 0)
                try:
                    total_score = float(total_score)
                    if total_score.is_integer():
                        total_score = int(total_score)
                except:
                    total_score = 0
                
                try:
                    obj_score_sum = int(obj_score_sum)
                except:
                    obj_score_sum = 0
                    
                if not isinstance(total_score, (int, float)):
                    total_score = 0
                if not isinstance(obj_score_sum, (int, float)):
                    obj_score_sum = 0
                    
                subj_score_sum = total_score - obj_score_sum
                if subj_score_sum < 0: subj_score_sum = 0
                
                # Count objective correct/total
                details = data.get('details', [])
                obj_items = [x for x in details if "客观" in x.get('type', '') or "选择" in x.get('type', '')]
                obj_total = len(obj_items)
                obj_correct = len([x for x in obj_items if x.get('score', 0) > 0])
                
                # Determine Review Status based on review_count
                review_count = data.get('review_count', 0)
                if review_count == 0:
                    review_status = ""
                elif review_count == 1:
                    review_status = "已复审"
                else:
                    review_status = "已二次复审"
                
                # Get Confirm Absence and translate if needed
                confirm_absence_value = data.get('confirm_absence', '')
                # If value is "Yes", display as "确认缺考" for Chinese CSV
                if confirm_absence_value == 'Yes':
                    confirm_absence_display = "确认缺考"
                else:
                    confirm_absence_display = confirm_absence_value
                
                data_dict = {
                    '考场': db_info.get('room', ''),
                    '座号': db_info.get('seat', ''),
                    '班级': db_info.get('class', ''),
                    '姓名': db_info.get('name', ''),
                    '考号': db_info.get('id', ''),
                    '总分': total_score,
                    '信息一致性': consistency_note,
                    '匹配项数': matches,
                    'OCR姓名': data.get('ocr_name', ''),
                    'OCR班级': data.get('ocr_class', ''),
                    'OCR考场': data.get('ocr_room', ''),
                    'OCR座号': data.get('ocr_seat', ''),
                    'OCR手写考号': data.get('ocr_id_written', ''),
                    'OCR填涂考号': data.get('ocr_id_filled', ''),
                    '原始文件': data.get('original_image', '') or data.get('original_filename', ''),
                    '重命名文件': data.get('renamed_filename', ''),
                    '客观题': obj_score_sum,
                    '客观题正确数': obj_correct,
                    '客观题总数': obj_total,
                    '主观题': subj_score_sum,
                    '复审状态': review_status,
                    '缺考标记': '是' if data.get('absent', False) else '',
                    '确认缺考': confirm_absence_display
                }

                # --- Add Detailed Scores ---
                
                # 1. Subjective Details
                subj_items = [x for x in details if "主观" in x.get('type', '') or "填空" in x.get('type', '') or "简答" in x.get('type', '')]
                main_q_scores = {}
                
                for item in subj_items:
                    qid = str(item.get('question_id', ''))
                    score = item.get('score', 0)
                    
                    # FIXED: Use Q prefix consistently to avoid duplication
                    # Sub-question score (e.g. Q17(1))
                    data_dict[f"Q{qid}"] = score
                    
                    # Aggregate for Main Question Total (e.g. 17(1) -> 17)
                    # Try to find the main number
                    match = re.match(r"(\d+)", qid)
                    if match:
                        main_id = match.group(1)
                        main_q_scores[main_id] = main_q_scores.get(main_id, 0) + score
                
                # Add Main Question Totals to dict with Chinese label
                for m_id, total in main_q_scores.items():
                    data_dict[f"Q{m_id} 总分"] = total

                # 2. Objective Details
                # Sort obj items by question id to be safe
                def get_q_num(x):
                    try: return int(re.search(r"(\d+)", str(x.get('question_id', '0'))).group(1))
                    except: return 0
                obj_items.sort(key=get_q_num)
                
                for item in obj_items:
                    qid = str(item.get('question_id', ''))
                    # Use robust answer extraction
                    ans = item.get('student_answer', '') or item.get('student_text', '') or item.get('answer', '')
                    score = item.get('score', 0)
                    
                    data_dict[f"Q{qid} Answer"] = ans
                    data_dict[f"Q{qid} Score"] = score
                
                self.write_summary_csv(data_dict, target_path=target_path)
                
            except Exception as e:
                print(f"Error processing {jf} for CSV: {e}")

    def generate_report_content(self, data, db_student_info):
        student_name = db_student_info.get('name', '未知')
        student_id = db_student_info.get('id', '未知')
        class_no = db_student_info.get('class', '未知')
        exam_room = db_student_info.get('room', '未知')
        seat_no = db_student_info.get('seat', '未知')
        
        ocr_name = data.get('ocr_name', '')
        ocr_class = data.get('ocr_class', '')
        ocr_room = data.get('ocr_room', '')
        ocr_seat = data.get('ocr_seat', '')
        ocr_id_written = data.get('ocr_id_written', '')
        ocr_id_filled = data.get('ocr_id_filled', '')
        
        if not ocr_id_written and 'ocr_id' in data:
            ocr_id_written = data['ocr_id']
        
        # --- Consistency Check (Any 2 matches) ---
        matches = 0
        details_msg = []
        
        def check_match(field_name, ocr_val, db_val):
            if ocr_val and db_val != '未知':
                s_ocr = str(ocr_val).strip()
                s_db = str(db_val).strip()
                if s_ocr.isdigit() and s_db.isdigit():
                    if int(s_ocr) == int(s_db): return True
                elif s_ocr == s_db: return True
            return False

        if check_match("姓名", ocr_name, student_name): matches += 1
        else: details_msg.append(f"姓名({ocr_name})")
        
        if check_match("班级", ocr_class, class_no): matches += 1
        else: details_msg.append(f"班级({ocr_class})")
        
        if check_match("考场", ocr_room, exam_room): matches += 1
        else: details_msg.append(f"考场({ocr_room})")
        
        if check_match("座号", ocr_seat, seat_no): matches += 1
        else: details_msg.append(f"座号({ocr_seat})")
        
        if check_match("手写考号", ocr_id_written, student_id): matches += 1
        else: details_msg.append(f"手写({ocr_id_written})")
        
        if check_match("填涂考号", ocr_id_filled, student_id): matches += 1
        else: details_msg.append(f"填涂({ocr_id_filled})")

        consistency_note = "一致"
        if matches >= 2:
            consistency_note = "一致"
        else:
            consistency_note = "不符: " + "; ".join(details_msg)
        
        total_score = data.get('total_score', 0)
        
        details = data.get('details', [])
        objective_q = [] 
        subjective_q = {} 
        obj_score_sum = 0
        
        sub_scores_dict = {}

        for item in details:
            q_type = item.get('type', '')
            q_id = str(item.get('question_id', ''))
            score = item.get('score', 0)
            
            if "客观" in q_type or "选择" in q_type:
                objective_q.append(item)
                obj_score_sum += score
            else:
                main_id = re.match(r"(\d+)", q_id)
                main_id = main_id.group(1) if main_id else q_id
                if main_id not in subjective_q: subjective_q[main_id] = []
                subjective_q[main_id].append(item)
                sub_scores_dict[q_id] = score

        for main_id, items in subjective_q.items():
            main_total = sum([x.get('score', 0) for x in items])
            sub_scores_dict[f"{main_id}"] = main_total

        md = ""
        is_english = (self.current_lang == "EN")
        
        # Report header - bilingual
        if is_english:
            md += f"# 📝 Grading Report\n\n"
            md += f"- **Basic Info**: Class {class_no} | {student_name} | {student_id}\n"
            md += f"- **Exam Seat**: Room {exam_room}, Seat {seat_no}\n"
            md += f"- **Info Check**: {consistency_note} (Matches: {matches})\n"
            md += f"- **OCR Recognition**:\n"
            md += f"  - Name: {ocr_name}\n"
            md += f"  - Class: {ocr_class}\n"
            md += f"  - Room: {ocr_room}\n"
            md += f"  - Seat: {ocr_seat}\n"
            md += f"  - Written ID: {ocr_id_written}\n"
            md += f"  - Filled ID: {ocr_id_filled}\n"
        else:
            md += f"# 📝 阅卷报告\n\n"
            md += f"- **基本信息**: {class_no}班 | {student_name} | {student_id}\n"
            md += f"- **考场座位**: {exam_room}考场 {seat_no}号\n"
            md += f"- **信息校验**: {consistency_note} (匹配项数: {matches})\n"
            md += f"- **OCR识别**:\n"
            md += f"  - 姓名: {ocr_name}\n"
            md += f"  - 班级: {ocr_class}\n"
            md += f"  - 考场: {ocr_room}\n"
            md += f"  - 座号: {ocr_seat}\n"
            md += f"  - 手写考号: {ocr_id_written}\n"
            md += f"  - 填涂考号: {ocr_id_filled}\n"

        # --- Score Summary ---
        try:
            total_score = float(total_score) if total_score else 0
            if isinstance(total_score, float) and total_score.is_integer():
                total_score = int(total_score)
        except:
            total_score = 0
            
        subj_score_sum = total_score - obj_score_sum
        if subj_score_sum < 0: subj_score_sum = 0
        
        if is_english:
            md += f"\n## 📊 Score Summary\n"
            md += f"| Total Score | Objective | Subjective |\n"
            md += f"| :---: | :---: | :---: |\n"
            md += f"| **{total_score}** | {obj_score_sum} | {subj_score_sum} |\n\n"
        else:
            md += f"\n## 📊 成绩汇总\n"
            md += f"| 总分 | 客观题 | 主观题 |\n"
            md += f"| :---: | :---: | :---: |\n"
            md += f"| **{total_score}** | {obj_score_sum} | {subj_score_sum} |\n\n"
        
        # --- 1. Objective Questions ---
        obj_correct_count = len([x for x in objective_q if x.get('score', 0) > 0])
        obj_total_count = len(objective_q)
        
        if is_english:
            md += "### 1. Objective Questions\n"
            md += f"**Score**: {obj_score_sum} (Correct: {obj_correct_count}/{obj_total_count})\n\n"
        else:
            md += "### 1. 客观题\n"
            md += f"**得分**: {obj_score_sum} (正确: {obj_correct_count}/{obj_total_count})\n\n"
        
        # Helper function to pad label to fixed character length
        def pad_to_length(text, target_length):
            """Pad text with spaces to reach target character length"""
            current_length = len(text)
            if current_length >= target_length:
                return text
            padding = target_length - current_length
            left_pad = padding // 2
            right_pad = padding - left_pad
            return " " * left_pad + text + " " * right_pad

        # Create one continuous table with groups of 5
        if objective_q:
            group_size = 5
            
            # Determine labels and widths based on language
            is_english = (self.current_lang == "EN")
            
            if is_english:
                # English labels - pad to 16 characters
                label_length = 16
                label_q_id = pad_to_length("Question ID", label_length)
                label_s_ans = pad_to_length("Student Answer", label_length)
                label_result = pad_to_length("Result", label_length)
                label_c_ans = pad_to_length("Correct Answer", label_length)
            else:
                # Chinese labels - pad to 8 characters
                label_length = 8
                label_q_id = pad_to_length("题号", label_length)
                label_s_ans = pad_to_length("考生答案", label_length)
                label_result = pad_to_length("结果", label_length)
                label_c_ans = pad_to_length("正确答案", label_length)
            
            max_cols = min(group_size, len(objective_q))
            
            # Process groups
            for group_idx, group_start in enumerate(range(0, len(objective_q), group_size)):
                group = objective_q[group_start:group_start + group_size]
                
                # For first group, create table header with question numbers
                if group_idx == 0:
                    # Header Row
                    md += f"| {label_q_id} | " + " | ".join([str(item.get('question_id')).center(4) for item in group]) + " |\n"
                    # Separator
                    md += "|" + "---|" * (len(group) + 1) + "\n"
                else:
                    # Blank separator row between groups
                    md += "| " + " " * label_length + " | " + " | ".join([" " * 4] * len(group)) + " |\n"
                    # Row: Question numbers for subsequent groups
                    md += f"| {label_q_id} | " + " | ".join([str(item.get('question_id')).center(4) for item in group]) + " |\n"
                
                # Row: Student answers
                md += f"| {label_s_ans} | " + " | ".join([str(item.get('student_answer', '') or item.get('student_text', '') or item.get('answer', '')).center(4) for item in group]) + " |\n"
                
                # Row: Results
                results = [f"{'✅' if item.get('score', 0) > 0 else '❌'}".center(4) for item in group]
                md += f"| {label_result} | " + " | ".join(results) + " |\n"

                # Row: Correct answers
                md += f"| {label_c_ans} | " + " | ".join([str(item.get('standard_answer', '')).center(4) for item in group]) + " |\n"
            
            md += "\n"
        
        # --- 2. Subjective Questions ---
        if is_english:
            md += f"\n### 2. Subjective Questions (Total Score: {subj_score_sum})\n"
        else:
            md += f"\n### 2. 主观题 (总分: {subj_score_sum})\n"
            
        sorted_keys = sorted(subjective_q.keys(), key=lambda x: int(x) if x.isdigit() else 999)
        
        for main_id in sorted_keys:
            items = subjective_q[main_id]
            main_total = sub_scores_dict.get(f"{main_id}", 0)
            
            # Add Main Question Header
            if is_english:
                md += f"\n#### Question {main_id} (Score: {main_total})\n"
            else:
                md += f"\n#### 第 {main_id} 题 (得分: {main_total})\n"
            
            for item in items:
                q_id = item.get('question_id', '')
                student_answer = item.get('student_answer', '') or item.get('student_text', '') or item.get('answer', '')
                student_text = student_answer if isinstance(student_answer, str) else str(student_answer)
                max_score = item.get('max_score', 0)
                score = item.get('score', 0)
                scoring_points = item.get('scoring_points', '')
                error_analysis = item.get('error_analysis', '')
                
                md += f"- **{q_id}**: {score}/{max_score}\n"
                if is_english:
                    md += f"  - **Student Answer**: {student_text}\n"
                    # Always show Scoring Points
                    sp_text = scoring_points if scoring_points else "No scoring points"
                    md += f"  - **Scoring Points**: {sp_text}\n"
                    
                    # Always show Analysis
                    ea_text = error_analysis if error_analysis else "None"
                    md += f"  - **Analysis**: {ea_text}\n"

                    # Get standard answer from local key or item
                    std_ans = self.answer_key.get(q_id) or item.get('standard_answer')
                    if std_ans:
                         md += f"  - **Correct Answer**: {std_ans}\n"
                else:
                    md += f"  - **考生答案**: {student_text}\n"
                    # Always show Scoring Points
                    sp_text = scoring_points if scoring_points else "无得分点"
                    md += f"  - **得分点**: {sp_text}\n"
                    
                    # Always show Error Analysis
                    ea_text = error_analysis if error_analysis else "无"
                    md += f"  - **失分原因**: {ea_text}\n"
                    
                    # Get standard answer from local key or item
                    std_ans = self.answer_key.get(q_id) or item.get('standard_answer')
                    if std_ans:
                         md += f"  - **正确答案**: {std_ans}\n"
                
                md += "\n"

        return md, sub_scores_dict, consistency_note, matches, obj_score_sum

    def parse_rubric_for_answers(self):
        """
        Parses the loaded rubric to extract standard answers.
        """
        if not self.rubric_path: return
        
        # 1. Check for existing JSON in exam_folder
        json_path = None
        if self.exam_folder:
            grading_data_dir = self.get_folder_path('grading_data')
            json_path = os.path.join(grading_data_dir, "answer_key.json")
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        self.answer_key = json.load(f)
                    self.log(self.t("log_answer_key_loaded"))
                    return # Done
                except Exception as e:
                    self.log(f"Failed to load existing answer key: {e}")
        
        # 2. Extract from Rubric (if no JSON or load failed)
        try:
            with open(self.rubric_path, 'r', encoding='utf-8') as f:
                rubric_text = f.read()
            
            self.log(self.t("log_extracting_answers"))
            
            api_key = getattr(self, "current_api_key", self.entry_key.get())
            if not api_key: return
            
            engine = AIGraderEngine(self.provider_var.get(), api_key, self.entry_base.get(), self.combo_model.get())
            
            # Use Concurrent Extraction & Consolidation
            log_cb = lambda msg: self.after(0, lambda m=msg: self.log(m))
            raw_results = engine.extract_answer_key_concurrent(rubric_text, log_callback=log_cb, t_func=self.t)
            final_key, report = engine.consolidate_answer_keys(raw_results, log_callback=log_cb, t_func=self.t)
            
            count = len(final_key)
            self.log(self.t("log_answers_extracted", count=count))
            
            # 3. Show Review Dialog (on Main Thread)
            # We pass a callback to handle the saving after user confirms
            self.after(0, lambda: self.show_standard_answer_dialog(final_key, report, json_path))
            
        except Exception as e:
            self.log(f"Failed to extract answer key: {e}")

    def show_standard_answer_dialog(self, initial_json, report, save_path):
        from standard_answer_dialog import StandardAnswerReviewDialog
        
        def on_confirm(confirmed_json):
            self.answer_key = confirmed_json
            
            # Recalculate save_path in case exam_folder was set after extraction
            actual_save_path = save_path
            if not actual_save_path and self.exam_folder:
                grading_data_dir = self.get_folder_path('grading_data')
                if not os.path.exists(grading_data_dir): os.makedirs(grading_data_dir)
                actual_save_path = os.path.join(grading_data_dir, "answer_key.json")
            
            # Save to JSON
            if actual_save_path:
                try:
                    with open(actual_save_path, 'w', encoding='utf-8') as f:
                        json.dump(self.answer_key, f, ensure_ascii=False, indent=2)
                    self.log(self.t("log_answer_key_saved"))
                except Exception as e:
                    self.log(f"Failed to save answer key: {e}")
            else:
                self.log("⚠️ Cannot save answer key: exam folder not selected yet.")
        
        StandardAnswerReviewDialog(self, initial_json, report, on_confirm)

    def show_standard_answer_dialog_with_callback(self, initial_json, report, save_path, callback):
        """Show dialog with custom callback instead of default save behavior"""
        from standard_answer_dialog import StandardAnswerReviewDialog
        
        def on_confirm(confirmed_json):
            self.log(self.t("log_answer_key_confirmed"))
            callback(confirmed_json)
        
        StandardAnswerReviewDialog(self, initial_json, report, on_confirm)

    def regrade_all_objective(self):
        """
        Re-grade all objective questions based on (potentially updated) answer key.
        """
        if not self.exam_folder:
            messagebox.showerror(self.t("title_error"), "Please select exam folder first.")
            return
        
        if not hasattr(self, 'answer_key') or not self.answer_key:
            # Try to load from file
            grading_data_dir = self.get_folder_path('grading_data')
            json_path = os.path.join(grading_data_dir, "answer_key.json")
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        self.answer_key = json.load(f)
                    self.log(self.t("log_answer_key_found"))
                except Exception as e:
                    self.log(f"Failed to load answer key: {e}")
            
            # Check again
            if not hasattr(self, 'answer_key') or not self.answer_key:
                messagebox.showerror(self.t("title_error"), "No answer key found. Please load rubric first.")
                return
        
        # Show Dialog to Edit Answer Key
        from standard_answer_dialog import ObjectiveAnswerEditDialog
        
        old_key = copy.deepcopy(self.answer_key)
        
        def on_confirm_regrade(new_key):
            self.answer_key = new_key
            
            # Save updated answer key to JSON
            grading_data_dir = self.get_folder_path('grading_data')
            if not os.path.exists(grading_data_dir): os.makedirs(grading_data_dir)
            json_path = os.path.join(grading_data_dir, "answer_key.json")
            try:
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(self.answer_key, f, ensure_ascii=False, indent=2)
                self.log(self.t("log_answer_key_saved"))
            except Exception as e:
                self.log(f"Failed to save updated answer key: {e}")
            
            # Detect Changes
            changed_qids = []
            for qid in set(list(old_key.keys()) + list(new_key.keys())):
                if old_key.get(qid) != new_key.get(qid):
                    changed_qids.append(qid)
            
            if not changed_qids:
                messagebox.showinfo(self.t("title_success"), "No changes detected in answer key.")
                return
            
            self.log_separator()
            self.log(self.t("log_answer_key_changes", qid=', '.join(changed_qids)))
            self.log(self.t("log_batch_regrading"))
            
            # Start batch re-grading in thread
            threading.Thread(target=self.batch_regrade_objective, args=(changed_qids,), daemon=True).start()
        
        # Show improved dialog with dropdown selectors
        ObjectiveAnswerEditDialog(self, self.answer_key, on_confirm_regrade, lang=self.current_lang)
    
    def batch_regrade_objective(self, changed_qids):
        """
        Batch re-grade all students' objective questions.
        """
        reports_dir = self.get_folder_path('reports')
        if not os.path.exists(reports_dir):
            self.after(0, lambda: messagebox.showerror(self.t("title_error"), "Reports directory not found."))
            return
        
        json_files = [f for f in os.listdir(reports_dir) if f.endswith('.json')]
        total = len(json_files)
        self.after(0, lambda: self.log(self.t("log_found_student_records", count=total)))
        
        updated_count = 0
        
        for idx, json_file in enumerate(json_files):
            json_path = os.path.join(reports_dir, json_file)
            
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                details = data.get('details', [])
                obj_items = [x for x in details if "客观" in x.get('type', '') or "选择" in x.get('type', '')]
                
                changed = False
                log_entries = []
                
                for item in obj_items:
                    qid = str(item.get('question_id', ''))
                    if qid not in changed_qids:
                        continue # Skip unchanged questions
                    
                    # Use student_answer (respects manual_override from review window)
                    student_ans = item.get('student_answer', '')
                    std_ans = self.answer_key.get(qid, '')
                    max_score = item.get('max_score', 3)
                    
                    old_score = item.get('score', 0)
                    new_score = max_score if student_ans == std_ans else 0
                    
                    if old_score != new_score:
                        item['score'] = new_score
                        log_entries.append(f"Q{qid}: {old_score} → {new_score}")
                        changed = True
                    
                    # Update standard_answer in JSON to reflect new answer key
                    item['standard_answer'] = std_ans
                
                if changed:
                    # Recalculate Total
                    old_total_score = data.get('total_score', 0)
                    total_score = sum(x.get('score', 0) for x in details)
                    data['total_score'] = total_score
                    
                    if old_total_score != total_score:
                        log_entries.append(f"Total Score: {old_total_score} → {total_score}")
                    
                    # Add Log Entry
                    log_entry = {
                        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "changes": ["Batch Re-grading"] + log_entries,
                        "user": "System"
                    }
                    if 'review_logs' not in data:
                        data['review_logs'] = []
                    data['review_logs'].append(log_entry)
                    
                    # Save JSON
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    
                    # Update Markdown
                    md_path = json_path.replace('.json', '.md')
                    db_info = data.get('db_student_info', {})
                    md_content, _, _, _, _ = self.generate_report_content(data, db_info)
                    with open(md_path, 'w', encoding='utf-8') as f:
                        f.write(md_content)
                    
                    updated_count += 1
                
            except Exception as e:
                self.after(0, lambda e=e, f=json_file: self.log(f"❌ Error processing {f}: {e}"))
        
        # Update CSV
        # Update CSV (Regenerate to ensure consistency)
        self.after(0, lambda: self.log(self.t("log_updating_summary_csv")))
        self.after(0, self.regenerate_summary_csv)
        
        # Done
        self.after(0, lambda u=updated_count, t=total: self.log(self.t("log_batch_regrade_complete", updated=u, total=t)))
        self.after(0, lambda u=updated_count: messagebox.showinfo(self.t("title_success"), f"Re-grading complete! Updated {u} students."))


    def save_markdown(self, data, original_filename, db_student_info, renamed_filename=None):
        exam_room = str(db_student_info.get('room', '未知'))
        seat_no = str(db_student_info.get('seat', '未知'))
        
        # Determine Filename Prefix
        # Priority: 1. Room-Seat (if valid) -> 2. OCR Filled ID -> 3. OCR Written ID -> 4. Original Filename
        if exam_room != '未知' and seat_no != '未知' and exam_room and seat_no:
            filename_prefix = f"{exam_room}-{seat_no}"
        else:
            # Fallback to OCR
            ocr_filled = str(data.get('ocr_id_filled', '')).strip()
            ocr_written = str(data.get('ocr_id_written', '')).strip()
            
            if ocr_filled and ocr_filled.lower() != 'none':
                filename_prefix = ocr_filled
            elif ocr_written and ocr_written.lower() != 'none':
                filename_prefix = ocr_written
            else:
                # Fallback to renamed filename if available, otherwise original
                if renamed_filename:
                    filename_prefix = os.path.splitext(renamed_filename)[0]
                else:
                    filename_prefix = os.path.splitext(original_filename)[0]
            
            # Log the fallback
            self.log(f"⚠️ Filename Fallback: {original_filename} -> {filename_prefix} (Room/Seat missing)")
        
        # Generate Content
        md_content, sub_scores_dict, consistency_note, matches, obj_score_sum = self.generate_report_content(data, db_student_info)
        
        reports_dir = self.get_folder_path('reports')
        if not os.path.exists(reports_dir):
            os.makedirs(reports_dir)
            
        # Save Markdown
        save_path = os.path.join(reports_dir, f"{filename_prefix}.md")
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        # Save JSON (New for Review System)
        json_path = os.path.join(reports_dir, f"{filename_prefix}.json")
        # Add metadata to JSON for easier loading
        data_to_save = data.copy()
        data_to_save['original_filename'] = original_filename
        if renamed_filename:
            data_to_save['renamed_filename'] = renamed_filename
        data_to_save['db_student_info'] = db_student_info
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            
        # Calculate objective question statistics
        details = data.get('details', [])
        objective_q = [x for x in details if "客观" in x.get('type', '') or "选择" in x.get('type', '')]
        if objective_q:
            obj_correct_count = len([x for x in objective_q if x.get('score', 0) > 0])
            obj_total_count = len(objective_q)
        else:
            # Fallback for legacy data
            obj_correct_count = int(obj_score_sum / 3) if obj_score_sum > 0 else 0
            obj_total_count = 16  # Default assumption
            
        # Calculate Subjective Score Sum
        subj_score_sum = data.get('total_score', 0) - obj_score_sum
        if subj_score_sum < 0: subj_score_sum = 0
        
        # Determine Review Status
        review_count = data.get('review_count', 0)
        if review_count == 0:
            review_status = ""
        elif review_count == 1:
            review_status = "已复审"
        else:
            review_status = "已二次复审"
        
        # Determine Absence (Filename OR Zero Score)
        is_absent_filename = db_student_info.get('is_absent', False)
        is_absent_score = (data.get('total_score', 0) == 0)
        is_absent_final = is_absent_filename or is_absent_score
            
        summary_data = {
            '考场': exam_room, '座号': seat_no, '班级': db_student_info.get('class', '未知'), 
            '姓名': db_student_info.get('name', '未知'), '考号': db_student_info.get('id', '未知'),
            '缺考标记': '是' if is_absent_final else '',
            '复审状态': review_status,
            '总分': data.get('total_score', 0),
            '客观题': obj_score_sum,
            '主观题': subj_score_sum,
            '客观题正确数': obj_correct_count,
            '客观题总数': obj_total_count,
            'OCR姓名': data.get('ocr_name', ''), 'OCR班级': data.get('ocr_class', ''),
            'OCR考场': data.get('ocr_room', ''), 'OCR座号': data.get('ocr_seat', ''),
            'OCR手写考号': data.get('ocr_id_written', ''), 'OCR填涂考号': data.get('ocr_id_filled', ''),
            '原始文件': original_filename,
            '重命名文件': renamed_filename if renamed_filename else '',
            '信息一致性': consistency_note
        }
        summary_data.update(sub_scores_dict)

        # --- Add Detailed Scores (Sync with regenerate_summary_csv) ---
        
        # 1. Subjective Details
        subj_items = [x for x in details if "主观" in x.get('type', '') or "填空" in x.get('type', '') or "简答" in x.get('type', '')]
        main_q_scores = {}
        
        for item in subj_items:
            qid = str(item.get('question_id', ''))
            score = item.get('score', 0)
            
            # Sub-question score (e.g. Q17(1))
            summary_data[f"Q{qid}"] = score
            
            # Aggregate for Main Question Total (e.g. 17(1) -> 17)
            match = re.match(r"(\d+)", qid)
            if match:
                main_id = match.group(1)
                main_q_scores[main_id] = main_q_scores.get(main_id, 0) + score
        
        # Add Main Question Totals
        for m_id, total in main_q_scores.items():
            summary_data[f"Q{m_id} Total"] = total

        # 2. Objective Details
        def get_q_num(x):
            try: return int(re.search(r"(\d+)", str(x.get('question_id', '0'))).group(1))
            except: return 0
        objective_q.sort(key=get_q_num)
        
        for item in objective_q:
            qid = str(item.get('question_id', ''))
            ans = item.get('student_answer', '') or item.get('student_text', '') or item.get('answer', '')
            score = item.get('score', 0)
            
            summary_data[f"Q{qid} Answer"] = ans
            summary_data[f"Q{qid} Score"] = score
        
        self.write_summary_csv(summary_data)

    def regrade_single_file(self, image_path):
        """
        Re-grades a single image file.
        1. Calls GraderEngine to process the image.
        2. Saves the new Report (MD & JSON) and updates CSV.
        3. Returns the new data.
        """
        self.log(self.t("log_regrading", filename=os.path.basename(image_path)))
        
        # Ensure grader engine exists
        if not hasattr(self, 'grader_engine') or self.grader_engine is None:
            try:
                # Use current_api_key if available
                api_key = getattr(self, "current_api_key", self.entry_key.get())
                self.grader_engine = AIGraderEngine(self.provider_var.get(), api_key, self.entry_base.get(), self.combo_model.get())
            except Exception as e:
                self.log(self.t("log_engine_init_failed", error=e))
                return False, str(e)

        try:
            with open(self.rubric_path, "r", encoding="utf-8") as f: rubric_text = f.read()
            
            # 1. Process Image
            result = self.grader_engine.grade_exam(rubric_text, image_path, self.layout_description)
            
            if 'error' in result:
                self.log(self.t("log_regrade_error", error=result['error']))
                return False, result['error']
                
            # 2. Resolve Student Info
            filename = os.path.basename(image_path)
            student_info, is_absent = self.student_manager.get_student_by_filename(filename)
            student_info['is_absent'] = is_absent
            
            # 3. Save Report (Overwrites existing)
            self.save_markdown(result, filename, student_info)
            
            self.log(self.t("log_regrade_complete", filename=filename))
            
            # Return success
            return True, "Success"
            
        except Exception as e:
            return False, str(e)

    def update_progress_ui(self):
        # Update Progress Label
        self.lbl_progress.configure(text=self.t("lbl_progress", completed=self.completed_count, total=self.total_files))
        self.progress_bar.set(self.completed_count / self.total_files if self.total_files > 0 else 0)
        
        # Calculate ETR
        if self.session_completed_count > 0:
            elapsed = time.time() - self.start_time
            avg_time = elapsed / self.session_completed_count
            remaining_items = self.total_files - self.completed_count
            
            if remaining_items > 0:
                etr_seconds = int(avg_time * remaining_items)
                etr_str = str(datetime.timedelta(seconds=etr_seconds))
                self.lbl_etr.configure(text=self.t("lbl_etr", time=etr_str))
            else:
                self.lbl_etr.configure(text=self.t("lbl_etr", time=self.t("etr_zero")))
        else:
            self.lbl_etr.configure(text=self.t("lbl_etr", time="--:--"))

    def handle_verification_result(self, total, missing_reports, missing_csv, missing_jsons, failed_files):
        if not missing_reports and not missing_csv and not missing_jsons and not failed_files:
            self.log(self.t("msg_verification_pass"))
            
            if messagebox.askyesno(self.t("msg_grading_complete"), self.t("msg_enter_review")):
                self.after(100, self.open_review_window)
        else:
            msg = self.t("msg_verification_fail", total=total) + "\n"
            
            missing_set = set()
            
            if missing_reports:
                msg += self.t("msg_missing_reports", count=len(missing_reports)) + "\n"
                missing_set.update(missing_reports)
            if missing_jsons:
                msg += self.t("msg_missing_jsons", count=len(missing_jsons)) + "\n"
                missing_set.update(missing_jsons)
            if missing_csv:
                msg += self.t("msg_missing_csv", count=len(missing_csv)) + "\n"
                missing_set.update(missing_csv)
            if failed_files:
                msg += self.t("msg_failed_files", count=len(failed_files)) + "\n"
                missing_set.update(failed_files)
                
            self.log(msg)
            
            # Check if it's a fresh start (All files are missing reports/data)
            # If so, do NOT prompt for targeted grading. User should click "Start Grading" to trigger detection.
            if len(missing_set) == total:
                self.log(self.t("msg_ready_start", count=total))
                return
            
            # Prompt to fix
            if messagebox.askyesno(self.t("msg_incomplete_title"), self.t("msg_incomplete_body", msg=msg)):
                
                def start_fix_flow():
                    # Re-verify to get the latest missing list (in case files were moved/deleted)
                    self.log("🔄 Re-verifying missing files...")
                    self.start_targeted_grading(None)

                self.ensure_layout_and_run(start_fix_flow)

    def ensure_jsons_exist(self):
        """
        If .md exists but .json missing (Legacy), try to generate a minimal .json 
        so ReviewWindow can open.
        """
        reports_dir = self.get_folder_path('reports')
        if not os.path.exists(reports_dir): return
        
        # We iterate known students/images to reconstruct
        # Ideally we parse the CSV to get the scores back
        csv_path = os.path.join(self.exam_folder, "成绩汇总表.csv")
        if not os.path.exists(csv_path): return
        
        import csv
        csv_rows = []
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            csv_rows = list(reader)
            
        for row in csv_rows:
            room = row.get('考场')
            seat = row.get('座号')
            if not room or not seat: continue
            
            json_name = f"{room}-{seat}.json"
            json_path = os.path.join(reports_dir, json_name)
            
            if not os.path.exists(json_path):
                data = {
                    'total_score': row.get('总分', 0),
                    'ocr_name': row.get('OCR姓名', ''),
                    'ocr_class': row.get('OCR班级', ''),
                    'ocr_room': row.get('OCR考场', ''),
                    'ocr_seat': row.get('OCR座号', ''),
                    'ocr_id_written': row.get('OCR手写考号', ''),
                    'ocr_id_filled': row.get('OCR填涂考号', ''),
                    'db_student_info': {
                        'name': row.get('姓名', ''),
                        'id': row.get('考号', ''),
                        'class': row.get('班级', ''),
                        'room': room,
                        'seat': seat
                    },
                    'details': [] 
                }
                try:
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except: pass

    def start_targeted_grading(self, target_files):
        # If target_files is None, it means we want to auto-detect missing files (Resume Mode)

        
        count_msg = len(target_files) if target_files else "ALL MISSING"
        self.log(self.t("msg_targeted_start", count=count_msg))
        
        self.processing = True
        self.stop_event.clear()
        self.pause_event.set()
        
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal", text=self.t("btn_pause"))
        self.btn_stop.configure(state="normal")
        
        # Reset session stats for this batch
        self.start_time = time.time()
        self.session_completed_count = 0
        
        # If target_files is None, process_images(None) will scan for pending files.
        threading.Thread(target=self.process_images, args=(target_files,), daemon=True).start()

    def process_single_file(self, grader, rubric_text, filename, folder, is_retry, file_num=None):
        # Capture original filename before any renaming
        original_filename_before_rename = filename

        # Check stop event before processing
        if self.stop_event.is_set():
            return False
            
        image_path = os.path.join(folder, filename)
        
        # Log which file we're processing (use provided file_num or calculate from counter)
        if file_num is None:
            with self.write_lock:
                file_num = self.completed_count + 1
        
        self.after(0, lambda fn=filename, num=file_num: self.log(self.t("log_processing_progress", current=num, total=self.total_files, filename=fn)))
        
        try:
            # Check stop event again before actual grading
            if self.stop_event.is_set():
                return False
                
            # Log API Request
            self.after(0, lambda fn=filename: self.log(self.t("log_api_sent", filename=fn)))

            # Pass layout_description if available
            result = grader.grade_exam(rubric_text, image_path, self.layout_description)
            
            # Log API Response
            self.after(0, lambda fn=filename: self.log(self.t("log_api_received", filename=fn)))

            if 'error' in result:
                err_msg = result['error']
                self.after(0, lambda fn=filename, e=err_msg: self.log(self.t("log_processing_error", filename=fn, error=e)))
                if not is_retry:
                    # Move to failed folder
                    failed_dir = self.get_folder_path('failed')
                    if not os.path.exists(failed_dir): os.makedirs(failed_dir)
                    shutil.move(image_path, os.path.join(failed_dir, filename))
                return False
            
            
            # --- Renaming Logic ---
            # Check if filename matches standard patterns: Room-Seat (d-d) ONLY
            import re
            is_standard = re.match(r"^\d+-\d+$", os.path.splitext(filename)[0])
            
            if not is_standard:
                # Try to extract ID from OCR
                ocr_filled = str(result.get('ocr_id_filled', '')).strip()
                ocr_written = str(result.get('ocr_id_written', '')).strip()
                
                new_name_base = None
                if ocr_filled and ocr_filled.lower() != 'none' and ocr_filled.isdigit():
                    new_name_base = ocr_filled
                elif ocr_written and ocr_written.lower() != 'none' and ocr_written.isdigit():
                    new_name_base = ocr_written
                
                if new_name_base:
                    ext = os.path.splitext(filename)[1]
                    new_filename = f"{new_name_base}{ext}"
                    
                    # Avoid collision
                    if new_filename != filename:
                        dest_path = os.path.join(folder, new_filename)
                        counter = 1
                        while os.path.exists(dest_path):
                            new_filename = f"{new_name_base}_{counter}{ext}"
                            dest_path = os.path.join(folder, new_filename)
                            counter += 1
                        
                        try:
                            os.rename(image_path, dest_path)
                            self.after(0, lambda o=filename, n=new_filename: self.log(self.t("log_renamed_file", old=o, new=n)))
                            
                            # Update variables
                            filename = new_filename
                            image_path = dest_path
                        except Exception as e:
                            self.after(0, lambda e=str(e): self.log(self.t("log_processing_error", filename=filename, error=f"Rename failed: {e}")))

            # Resolve Student Info (Re-resolve with potentially new filename)
            student_info, _ = self.student_manager.get_student_by_filename(filename)
            
            # Save Report
            with self.write_lock:
                # Use original_filename_before_rename for the record
                renamed_file = filename if filename != original_filename_before_rename else None
                self.save_markdown(result, original_filename_before_rename, student_info, renamed_file)
                
                # Log Saved Status
                self.after(0, lambda fn=filename: self.log(self.t("log_json_saved", filename=fn)))
                self.after(0, lambda fn=filename: self.log(self.t("log_report_saved", filename=fn)))
                
                # Increment counters AFTER successful completion (within lock)
                self.completed_count += 1
                self.session_completed_count += 1
            
            # If this was a retry, move the file from failed back to success folder (or main if we want to keep it there, but user wants success folder)

            success_dir = self.get_folder_path('success')
            if not os.path.exists(success_dir): os.makedirs(success_dir)
            
            try:
                final_dest = os.path.join(success_dir, filename)
                shutil.move(image_path, final_dest)
                # self.log(f"Moved to success: {filename}")
            except Exception as e:
                self.log(f"⚠️ Failed to move to success: {e}")

            if is_retry:

                self.after(0, lambda fn=filename: self.log(self.t("log_moved_back", filename=fn))) # Message might need update "Processed successfully"
            
            # Update UI and log (outside lock)
            self.after(0, lambda: self.update_progress_ui())
            self.after(0, lambda fn=filename: self.log(self.t("log_file_done", filename=fn)))
            return True
            
        except Exception as e:
            err_str = str(e)
            self.after(0, lambda fn=filename, e=err_str: self.log(self.t("log_processing_error", filename=fn, error=e)))
            if not is_retry:
                failed_dir = self.get_folder_path('failed')
                if not os.path.exists(failed_dir): os.makedirs(failed_dir)
                try: shutil.move(image_path, os.path.join(failed_dir, filename))
                except: pass
            return False

    def process_images(self, target_files=None):
        try:
            with open(self.rubric_path, "r", encoding="utf-8") as f: rubric_text = f.read()
            
            # Use current_api_key if available (handles masking), else fallback to entry
            api_key = getattr(self, "current_api_key", self.entry_key.get())
            # Double check: if api_key is masked (starts with sk- and has ...), try to get from entry if entry is not masked?

            # If entry has real key (user typed it but didn't trigger focus out?), use entry.
            entry_val = self.entry_key.get()
            if not api_key.startswith("sk-") or "..." not in api_key:
                 # api_key seems valid or at least not obviously masked
                 pass
            elif entry_val and not entry_val.startswith("sk-") or "..." not in entry_val:
                 # Entry has unmasked key, use it
                 api_key = entry_val
            
            grader = AIGraderEngine(self.provider_var.get(), api_key, self.entry_base.get(), self.combo_model.get())
            valid_extensions = ('.png', '.jpg', '.jpeg')
            
            # ===== PHASE 1: Main Folder Processing =====

            files = [f for f in os.listdir(self.exam_folder) if f.lower().endswith(valid_extensions)]
            
            # Also scan success folder for completed files
            success_dir = self.get_folder_path('success')
            success_files = []
            if os.path.exists(success_dir):
                success_files = [f for f in os.listdir(success_dir) if f.lower().endswith(valid_extensions)]
            
            # Total files known = root files + success files
            all_known_files = set(files + success_files)
            
            # Backup Logic: Copy all valid images to original_files
            original_files_dir = self.get_folder_path('original_files')
            if not os.path.exists(original_files_dir):
                os.makedirs(original_files_dir)
                
            # Backup root files
            for f in files:
                src = os.path.join(self.exam_folder, f)
                dst = os.path.join(original_files_dir, f)
                if not os.path.exists(dst): 
                    try: shutil.copy2(src, dst)
                    except: pass
            
            # Backup success files (if not already backed up)
            for f in success_files:
                src = os.path.join(success_dir, f)
                dst = os.path.join(original_files_dir, f)
                if not os.path.exists(dst):
                    try: shutil.copy2(src, dst)
                    except: pass

            pending_files = []
            
            if target_files:
                # Targeted Mode: Only process specific files
                failed_dir = self.get_folder_path('failed')
                
                for fname in target_files:
                    src_failed = os.path.join(failed_dir, fname)
                    dest_main = os.path.join(self.exam_folder, fname)
                    
                    if os.path.exists(src_failed):
                        try:
                            shutil.move(src_failed, dest_main)
                            self.log(self.t("msg_restored", filename=fname))
                        except: pass
                    
                    if os.path.exists(dest_main):
                        pending_files.append(fname)
                
                self.log(self.t("msg_targeted_ready", count=len(pending_files)))
                
            else:
                # Normal Mode: Use comprehensive verification to find pending files
                self.log(self.t("log_checking_completed"))
                
                # Run full verification
                missing_reports, missing_jsons, missing_csv, failed_files = self._verify_files_sync()
                
                # Build set of all files that are missing something
                files_needing_work = set()
                files_needing_work.update(missing_reports)
                files_needing_work.update(missing_jsons)
                files_needing_work.update(missing_csv)
                
                # Add all files from the main folder that need processing

                for f in files:
                    if f in files_needing_work:
                        pending_files.append(f)
                
                # Also check success files - if they are missing reports, move them back to root to re-process?

                # process_single_file expects 'filename' and looks in self.exam_folder.
                # If we add success files to pending_files, process_single_file will fail if file is not in root.

                
                for f in success_files:
                    if f in files_needing_work:
                        # Move back to root
                        src = os.path.join(success_dir, f)
                        dst = os.path.join(self.exam_folder, f)
                        try:
                            shutil.move(src, dst)
                            pending_files.append(f)
                            self.log(f"🔄 Found incomplete file in success folder, moving back to process: {f}")
                        except Exception as e:
                            self.log(f"⚠️ Failed to move incomplete file back: {e}")

                completed_count = len(all_known_files) - len(pending_files)
                if completed_count > 0:
                    self.log(self.t("log_files_completed", count=completed_count))
                if pending_files:
                    self.log(self.t("log_files_to_process", count=len(pending_files)))
            
            # Check failed folder count
            failed_dir = self.get_folder_path('failed')
            failed_count = 0
            if os.path.exists(failed_dir):
                failed_count = len([f for f in os.listdir(failed_dir) if f.lower().endswith(valid_extensions)])
            
            # Set total to PENDING files only
            self.total_files = len(pending_files)
            self.completed_count = 0
            self.after(0, lambda: self.update_progress_ui())
            
            # Log start with failed count
            if failed_count > 0:
                self.after(0, lambda fc=failed_count: self.log(self.t("log_start_failed_count", total=self.total_files, failed=fc)))
            else:
                self.after(0, lambda: self.log(self.t("msg_start", total=self.total_files, pending=self.total_files)))
            
            # Process pending files
            if pending_files:
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
                try:
                    futures = []
                    for idx, filename in enumerate(pending_files):
                        if self.stop_event.is_set(): 
                            break
                        # Sequential numbering starting from 1
                        file_num = idx + 1
                        f = executor.submit(self.process_single_file, grader, rubric_text, filename, self.exam_folder, False, file_num)
                        futures.append(f)
                        time.sleep(1)  # Stagger requests by 1 second 
                    
                    # Wait for all futures to complete, but check stop_event periodically
                    while futures:
                        done, futures = concurrent.futures.wait(futures, timeout=0.5, return_when=concurrent.futures.FIRST_COMPLETED)
                        if self.stop_event.is_set():
                            # Cancel remaining futures
                            for future in futures:
                                future.cancel()
                            break
                finally:
                    executor.shutdown(wait=True)  # Wait for all to complete
            
            # ===== PHASE 2: Retry Failed Files =====
            if not target_files and not self.stop_event.is_set():
                failed_dir = os.path.join(self.exam_folder, "failed")
                if os.path.exists(failed_dir):
                    failed_files = [f for f in os.listdir(failed_dir) if f.lower().endswith(valid_extensions)]
                    if failed_files:
                        # Update total_files for failed retry phase
                        self.total_files = len(failed_files)
                        self.completed_count = 0
                        
                        self.after(0, lambda fc=len(failed_files): self.log(self.t("log_retry_failed", count=fc)))
                        
                        executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
                        try:
                            futures = []
                            for idx, filename in enumerate(failed_files):
                                if self.stop_event.is_set(): break
                                file_num = idx + 1
                                f = executor.submit(self.process_single_file, grader, rubric_text, filename, failed_dir, True, file_num)
                                futures.append(f)
                                time.sleep(1)
                            
                            # Wait for all retry futures
                            while futures:
                                done, futures = concurrent.futures.wait(futures, timeout=0.5, return_when=concurrent.futures.FIRST_COMPLETED)
                                if self.stop_event.is_set():
                                    for future in futures:
                                        future.cancel()
                                    break
                        finally:
                            executor.shutdown(wait=True)

            # ===== PHASE 3: Final Verification =====
            if not self.stop_event.is_set():
                # Wait a bit for any pending writes to complete
                time.sleep(2)
                
                self.after(0, lambda: self.log(self.t("log_regen_csv")))
                self.regenerate_csv_from_jsons()
                
                # Final count verification

                self.after(0, lambda: self.log(self.t("log_verify_counts")))
                
                # Count images in root + success
                root_images = len([f for f in os.listdir(self.exam_folder) if f.lower().endswith(valid_extensions)])
                success_dir = self.get_folder_path('success')
                success_images = 0
                if os.path.exists(success_dir):
                    success_images = len([f for f in os.listdir(success_dir) if f.lower().endswith(valid_extensions)])
                total_images = root_images + success_images
                
                reports_dir = self.get_folder_path('reports')
                if os.path.exists(reports_dir):
                    json_count = len([f for f in os.listdir(reports_dir) if f.endswith('.json')])
                    md_count = len([f for f in os.listdir(reports_dir) if f.endswith('.md')])
                else:
                    json_count = md_count = 0
                
                grading_data_dir = self.get_folder_path('grading_data')
                csv_filename = "成绩汇总表.csv" if self.current_lang == "CN" else "Grade_Summary.csv"
                csv_path = os.path.join(grading_data_dir, csv_filename)
                csv_rows = 0
                if os.path.exists(csv_path):
                    try:
                        with open(csv_path, 'r', encoding='utf-8-sig') as f:
                            csv_rows = sum(1 for line in f) - 1  # Exclude header
                    except: pass
                
                self.after(0, lambda ti=total_images, jc=json_count, mc=md_count, cr=csv_rows: 
                    self.log(self.t("log_grading_stats", ti=ti, jc=jc, mc=mc, cr=cr)))

            if self.stop_event.is_set():
                self.after(0, lambda: self.log(self.t("msg_stopped")))
            else:
                self.after(0, lambda: self.log(self.t("msg_finished")))
                
                # Check completion again to prompt for review
                self.after(1000, self.check_completion_status)

        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda e=error_msg: self.log(self.t("msg_error", error=e)))
        finally:
            self.processing = False
            self.after(0, lambda: self.reset_ui_state())

    def open_review_window(self):
        if not self.exam_folder:
            messagebox.showerror(self.t("title_error"), self.t("msg_select_files"))
            return
            
        # Ensure JSONs exist (Legacy Support)
        self.ensure_jsons_exist()
        
        try:
            ReviewWindow(self, self.exam_folder, self.student_manager, self.on_review_save, 
                         lang=self.current_lang, translations=TRANSLATIONS)
        except Exception as e:
            self.log(self.t("msg_error", error=e))
        # db_info = data.get('db_student_info', {})
        # md_content, sub_scores_dict, consistency_note, matches = self.generate_report_content(data, db_info)
        
        # exam_room = db_info.get('room', '未知')
        # seat_no = db_info.get('seat', '未知')

    def on_review_save(self, data):
        # 1. Regenerate Markdown
        db_info = data.get('db_student_info', {})
        md_content, sub_scores_dict, consistency_note, matches, _ = self.generate_report_content(data, db_info)
        
        exam_room = db_info.get('room', '未知')
        seat_no = db_info.get('seat', '未知')
        filename_prefix = f"{exam_room}-{seat_no}"
        
        reports_dir = os.path.join(self.exam_folder, "reports")
        save_path = os.path.join(reports_dir, f"{filename_prefix}.md")
        
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        # 2. Update CSV
        self.regenerate_csv_from_jsons()

    def regenerate_csv_from_jsons(self):
        # Use get_folder_path which handles both "reports" and "阅卷报告"
        reports_dir = self.get_folder_path('reports')
        
        if not reports_dir or not os.path.exists(reports_dir):
            # Try alternative: check both possible names manually
            for possible_name in ['reports', '阅卷报告']:
                alt_path = os.path.join(self.exam_folder, possible_name) if self.exam_folder else None
                if alt_path and os.path.exists(alt_path):
                    reports_dir = alt_path
                    break
            else:
                return
        
        json_files = [f for f in os.listdir(reports_dir) if f.endswith(".json")]
        
        all_summaries = []
        
        is_en = (self.current_lang == "EN")
        
        # Header Mappings
        header_map = {
            '考场': 'Room', '座号': 'Seat', '班级': 'Class', '姓名': 'Name', '考号': 'ID',
            '总分': 'Total Score', '客观题': 'Objective Total', '主观题': 'Subjective Total',
            '信息一致性': 'Consistency', '匹配项数': 'Matches',
            '复审状态': 'Review Status', '缺考标记': 'Absence Marker', '确认缺考': 'Confirm Absence',
            'OCR姓名': 'OCR Name', 'OCR班级': 'OCR Class', 'OCR考场': 'OCR Room',
            'OCR座号': 'OCR Seat', 'OCR手写考号': 'OCR Written ID', 'OCR填涂考号': 'OCR Filled ID',
            '原始文件': 'Original File', '重命名文件': 'Renamed File'
        }
        
        # Load Answer Key for sorting
        answer_key_order = []
        if hasattr(self, 'answer_key') and self.answer_key:
             pass

        for jf in json_files:
            try:
                with open(os.path.join(reports_dir, jf), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    db_info = data.get('db_student_info', {})
                    
                    # Re-calculate consistency/scores for summary
                    _, sub_scores_dict, consistency_note, matches, obj_score_sum = self.generate_report_content(data, db_info)
                    
                    # Determine Review Status
                    review_count = data.get('review_count', 0)
                    review_status = ""
                    if review_count == 1:
                        review_status = "Reviewed" if is_en else "已复审"
                    elif review_count >= 2:
                        review_status = "Second Review" if is_en else "已二次复审"
                    
                    # Get Confirm Absence with proper translation
                    confirm_absence_value = data.get('confirm_absence', '')
                    if is_en:
                        confirm_absence_display = confirm_absence_value
                    else:
                        if confirm_absence_value == 'Yes':
                            confirm_absence_display = "确认缺考"
                        else:
                            confirm_absence_display = confirm_absence_value
                    
                    total_score = data.get('total_score', 0)
                    subj_score_sum = total_score - obj_score_sum
                    if subj_score_sum < 0: subj_score_sum = 0

                    summary = {
                        '考场': db_info.get('room', '未知'), 
                        '座号': db_info.get('seat', '未知'), 
                        '班级': db_info.get('class', '未知'), 
                        '姓名': db_info.get('name', '未知'), 
                        '考号': db_info.get('id', '未知'),
                        '信息一致性': consistency_note,
                        '匹配项数': matches,
                        '复审状态': review_status,
                        '缺考标记': data.get('缺考标记', ''),
                        '确认缺考': confirm_absence_display,
                        '总分': total_score,
                        '客观题': obj_score_sum,
                        '主观题': subj_score_sum,
                        'OCR姓名': data.get('ocr_name', ''),
                        'OCR班级': data.get('ocr_class', ''),
                        'OCR考场': data.get('ocr_room', ''),
                        'OCR座号': data.get('ocr_seat', ''),
                        'OCR手写考号': data.get('ocr_id_written', ''),
                        'OCR填涂考号': data.get('ocr_id_filled', ''),
                        '原始文件': data.get('original_image', '') or data.get('original_filename', ''),
                        '重命名文件': data.get('renamed_filename', '')
                    }
                    
                    # Translate Absence Markers if EN
                    if is_en:
                        if summary.get('缺考标记') == '是': summary['缺考标记'] = 'Yes'
                    
                    # Add Sub-scores (Subjective)
                    # We need to ensure we have all sub-scores. generate_report_content returns sub_scores_dict
                    # which contains QID -> Score.
                    summary.update(sub_scores_dict)
                    
                    # Add Objective Answers and Scores
                    details = data.get('details', [])
                    objective_q = [x for x in details if "客观" in x.get('type', '') or "选择" in x.get('type', '')]
                    for item in objective_q:
                        qid = str(item.get('question_id', ''))
                        ans = item.get('student_answer', '') or item.get('student_text', '') or item.get('answer', '')
                        score = item.get('score', 0)
                        summary[f"Q{qid} Answer"] = ans
                        summary[f"Q{qid} Score"] = score

                    # If EN, translate keys in summary
                    if is_en:
                        new_summary = {}
                        for k, v in summary.items():
                            new_key = header_map.get(k, k)
                            # Translate Q-keys if needed? "Q1 Answer" -> "Q1 Answer" (Already EN)

 
                            # CN: "Q1 答案", "Q1 得分", "Q17 总分", "Q17(1) 得分"
                            # EN: "Q1 Answer", "Q1 Score", "Q17 Total", "Q17(1) Score"
                            

 

                            
                            if k.endswith(" Answer"):
                                 new_key = k # Already EN
                            elif k.endswith(" Score"):
                                 new_key = k # Already EN
                            elif k.endswith(" Total"):
                                 new_key = k # Already EN
                            
                            new_summary[new_key] = v
                        all_summaries.append(new_summary)
                    else:
                        # CN Mode: Translate "Q... Answer" to "Q... 答案" etc.
                        new_summary = {}
                        for k, v in summary.items():
                            if k.endswith(" Answer"):
                                new_key = k.replace(" Answer", " 答案")
                            elif k.endswith(" Score"):
                                new_key = k.replace(" Score", " 得分")
                            elif k.endswith(" Total"):
                                new_key = k.replace(" Total", " 总分")
                            elif re.match(r"Q\d+\(\d+\)$", k): # Q17(1) -> Q17(1) 得分 (if it's just the key)
                                 # sub_scores_dict keys are just "17(1)" or "17"



                                 pass
                            

                            pass
                        
                        # Re-do the loop to be cleaner
                        final_summary = {}
                        for k, v in summary.items():
                            # Handle fixed headers
                            if k in header_map:
                                final_summary[k] = v
                                continue
                                
                            # Handle Dynamic Headers
                            # Objective: Q{qid} Answer, Q{qid} Score
                            if k.endswith(" Answer"):
                                final_summary[k.replace(" Answer", " 答案")] = v
                            elif k.endswith(" Score"):
                                final_summary[k.replace(" Score", " 得分")] = v
                            # Subjective: Q{qid} Total (from save_markdown logic)
                            elif k.endswith(" Total"):
                                final_summary[k.replace(" Total", " 总分")] = v
                            # Subjective Sub-questions: "17(1)", "17"
                            # We need to detect these.
                            elif re.match(r"\d+(\(\d+\))?", k):
                                 # This is likely a subjective score key from sub_scores_dict
                                 if "(" in k:
                                     final_summary[f"Q{k} 得分"] = v
                                 else:
                                     # Main question total (if not handled by Q.. Total)
                                     final_summary[f"Q{k} 总分"] = v
                            else:
                                final_summary[k] = v
                        all_summaries.append(final_summary)
            except Exception as e:
                print(f"❌ Error processing {jf} for CSV regeneration: {e}")
                import traceback
                traceback.print_exc()

        # Sort by Room/Seat
        def sort_key(x):
            try: 
                r = x.get('Room') if is_en else x.get('考场')
                s = x.get('Seat') if is_en else x.get('座号')
                return (int(r), int(s))
            except: return (999, 999)
        all_summaries.sort(key=sort_key)
        
        if not all_summaries:
            print(f"⚠️ Warning: No summaries generated from {len(json_files)} JSON files")
            return
        
        # Determine Headers Order
        # 1. Basic Info
        if is_en:
            headers = ['Room', 'Seat', 'Class', 'Name', 'ID']
            headers += ['Consistency', 'Matches', 'Review Status', 'Absence Marker', 'Confirm Absence']
            headers += ['Total Score', 'Objective Total', 'Subjective Total']
        else:
            headers = ['考场', '座号', '班级', '姓名', '考号']
            headers += ['信息一致性', '匹配项数', '复审状态', '缺考标记', '确认缺考']
            headers += ['总分', '客观题', '主观题']
            
        # Collect all keys
        all_keys = set()
        for s in all_summaries:
            all_keys.update(s.keys())
            
        # 4. Subjective Questions (Sorted by QID)
        subj_keys = [k for k in all_keys if "主观" not in k and "客观" not in k and ("Total" in k or "总分" in k or "(" in k)]
        # Filter out non-question keys if any
        subj_keys = [k for k in subj_keys if re.search(r"Q?\d+", k)]
        
        def subj_sort(k):
            # Extract numbers: Q17(1) -> 17, 1. Q17 Total -> 17, 0.
            # We want Main Total first, then sub-questions.
            # Q17 总分 -> 17, 0
            # Q17(1) 得分 -> 17, 1
            nums = re.findall(r"\d+", k)
            if not nums: return (999, 999)
            main_id = int(nums[0])
            sub_id = int(nums[1]) if len(nums) > 1 else 0
            return (main_id, sub_id)
            
        subj_keys.sort(key=subj_sort)
        headers += subj_keys
        
        # 5. Objective Questions (Sorted by QID)
        obj_keys = [k for k in all_keys if "Answer" in k or "答案" in k or ("Score" in k or "得分" in k)]
        # Filter out keys that are already included in subjective keys or headers to avoid duplicates.
        # This ensures we distinguish between objective questions (e.g., "Q1 答案") and subjective ones (e.g., "Q17(1) 得分").
        obj_keys = [k for k in obj_keys if k not in subj_keys and k not in headers]
        
        def obj_sort(k):
            # Q1 Answer -> 1, 0
            # Q1 Score -> 1, 1
            nums = re.findall(r"\d+", k)
            if not nums: return (999, 999)
            qid = int(nums[0])
            is_score = 1 if ("Score" in k or "得分" in k) else 0
            return (qid, is_score)
            
        obj_keys.sort(key=obj_sort)
        headers += obj_keys
        
        # 6. OCR Info
        if is_en:
            headers += ['OCR Name', 'OCR Class', 'OCR Room', 'OCR Seat', 'OCR Written ID', 'OCR Filled ID']
            headers += ['Original File', 'Renamed File']
        else:
            headers += ['OCR姓名', 'OCR班级', 'OCR考场', 'OCR座号', 'OCR手写考号', 'OCR填涂考号']
            headers += ['原始文件', '重命名文件']
            
        # Write CSV

        grading_data_dir = self.get_folder_path('grading_data')
        if not os.path.exists(grading_data_dir): os.makedirs(grading_data_dir)
        
        csv_filename = "成绩汇总表.csv" if self.current_lang == "CN" else "Grade_Summary.csv"
        csv_path = os.path.join(grading_data_dir, csv_filename)
        
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(all_summaries)

    def center_window(self, width, height):
        """Center the window on the screen"""
        try:
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            x = (screen_width // 2) - (width // 2)
            y = (screen_height // 2) - (height // 2)
            self.geometry(f'{width}x{height}+{x}+{y}')
        except Exception as e:
            print(f"Failed to center window: {e}")
            self.geometry(f'{width}x{height}')

    def reset_ui_state(self):
        self.btn_start.configure(state="normal")
        self.btn_pause.configure(state="disabled", text=self.t("btn_pause"), fg_color="#D97706")
        self.btn_stop.configure(state="disabled")
        self.btn_review.configure(state="normal") # Enable review even if incomplete

class TemplateConfirmDialog(ctk.CTkToplevel):
    def __init__(self, parent, layout_description, on_confirm):
        super().__init__(parent)
        self.title(parent.t("title_confirm_layout"))
        self.geometry("600x500")
        self.on_confirm = on_confirm
        
        # Center window
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 300
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 250
        self.geometry(f"+{x}+{y}")
        
        ctk.CTkLabel(self, text=parent.t("msg_confirm_layout"), font=("Arial", 14, "bold")).pack(pady=10, padx=20, anchor="w")
        
        self.textbox = ctk.CTkTextbox(self, font=("Arial", 12))
        self.textbox.pack(fill="both", expand=True, padx=20, pady=10)
        self.textbox.insert("1.0", layout_description)
        
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", pady=20)
        
        ctk.CTkButton(btn_frame, text=parent.t("btn_confirm_start"), fg_color="#106A38", width=200, command=self.confirm).pack()
        
        self.transient(parent)
        self.grab_set()
        
    def confirm(self):
        new_desc = self.textbox.get("1.0", "end-1c")
        self.on_confirm(new_desc)
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()