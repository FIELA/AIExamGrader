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
from typing import List, Dict, Any, Optional
import customtkinter as ctk
from tkinter import filedialog, messagebox

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

        self.title("AI Exam Grader")
        self.geometry("1200x820")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        
        # Load Icons
        self.load_icons()

        self.config_manager = ConfigManager()
        self.student_manager = StudentManager()
        
        self.rubric_path = ""
        self.exam_folder = ""
        
        self.processing = False
        self.write_lock = threading.RLock()  # Use RLock for reentrant locking
        self.completed_count = 0
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
        
        # Set App Icon
        try:
            icon_path = self.resource_path(os.path.join("assets", "icon.png"))
            if os.path.exists(icon_path):
                # Use ImageTk for window icon
                from PIL import ImageTk
                icon_img = ImageTk.PhotoImage(file=icon_path)
                self.wm_iconphoto(True, icon_img)
                # Also try setting it for macOS dock if possible (often requires packaging, but this helps window)
        except Exception as e:
            print(f"Warning: Could not set app icon: {e}")

        self.setup_ui()
        self.load_initial_config()
        self.update_ui_text() # Apply initial language
        
        if platform.system() == "Darwin":
            self.apply_mac_paste_fix(self.entry_key)
            self.apply_mac_paste_fix(self.entry_base)
            try: self.apply_mac_paste_fix_to_widget(self.combo_model._entry)
            except: pass

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

    def load_icons(self):
        self.icons = {}
        icon_names = ["start", "pause", "stop", "review", "folder", "document"]
        
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
                
                # For solid buttons (Start, Pause, Stop, Folder, Document, Review), use White icons
                if name in ["start", "pause", "stop", "folder", "document", "review"]:
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

    def paste_event_handler(self, event):
        try:
            clipboard = self.clipboard_get()
            event.widget.insert("insert", clipboard)
            return "break"
        except Exception: return None

    def setup_ui(self):
        # Configure grid layout (1x2)
        self.grid_columnconfigure(0, minsize=260, weight=0) # Enforce fixed sidebar width
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar (Left) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=260, corner_radius=0, fg_color=(Theme.BG_LIGHT, Theme.BG_DARK))
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False) # Prevent resizing based on content
        self.sidebar_frame.grid_rowconfigure(10, weight=1)

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

        # API Config
        self.lbl_key = ctk.CTkLabel(self.sidebar_frame, text=self.t("lbl_key"), anchor="w")
        self.lbl_key.grid(row=6, column=0, padx=20, pady=(10, 0), sticky="w")
        self.entry_key = ctk.CTkEntry(self.sidebar_frame, width=220)
        self.entry_key.grid(row=7, column=0, padx=20, pady=(5, 10))
        
        # Bind events for masking
        self.entry_key.bind("<FocusIn>", self._on_key_focus_in)
        self.entry_key.bind("<FocusOut>", self._on_key_focus_out)
        self.entry_key.bind("<KeyRelease>", self._on_key_release)

        # Provider & Model (Re-added as they were removed in the provided snippet but are essential)
        self.lbl_base = ctk.CTkLabel(self.sidebar_frame, text=self.t("lbl_base"), anchor="w", font=ctk.CTkFont(size=13, weight="normal"))
        self.lbl_base.grid(row=8, column=0, padx=16, pady=(12, 4), sticky="w")
        self.entry_base = ctk.CTkEntry(self.sidebar_frame, placeholder_text="https://...", height=32, corner_radius=8, width=228)
        self.entry_base.grid(row=9, column=0, padx=16, pady=(0, 16))

        self.lbl_provider = ctk.CTkLabel(self.sidebar_frame, text=self.t("lbl_provider"), anchor="w", font=ctk.CTkFont(size=13, weight="normal"))
        self.lbl_provider.grid(row=10, column=0, padx=16, pady=(12, 4), sticky="w")
        self.provider_var = ctk.StringVar(value="OpenAI")
        self.combo_provider = ctk.CTkComboBox(self.sidebar_frame, values=["OpenAI", "Gemini"], variable=self.provider_var, command=self.on_provider_change, height=32, corner_radius=8, width=228)
        self.combo_provider.grid(row=11, column=0, padx=16, pady=(0, 12))

        self.lbl_model = ctk.CTkLabel(self.sidebar_frame, text=self.t("lbl_model"), anchor="w", font=ctk.CTkFont(size=13, weight="normal"))
        self.lbl_model.grid(row=12, column=0, padx=16, pady=(12, 4), sticky="w")
        self.combo_model = ctk.CTkComboBox(self.sidebar_frame, values=["gemini-2.5-pro-maxthinking", "gpt-4o"], height=32, corner_radius=8, width=228)
        self.combo_model.set("gemini-2.5-pro-maxthinking")
        self.combo_model.grid(row=13, column=0, padx=16, pady=(0, 12))
        
        self.btn_check_model = ctk.CTkButton(self.sidebar_frame, text=self.t("btn_check_model"), command=self.check_models, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"), height=36, corner_radius=8, font=ctk.CTkFont(size=13), width=228)
        self.btn_check_model.grid(row=14, column=0, padx=16, pady=(8, 16))

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
        self.files_card.grid_columnconfigure(1, weight=1)

        self.lbl_resources = ctk.CTkLabel(self.files_card, text=self.t("lbl_resources"), font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_resources.grid(row=0, column=0, padx=20, pady=(16, 12), sticky="w")

        # Rubric
        self.btn_rubric = ctk.CTkButton(self.files_card, text=" " + self.t("btn_rubric"), image=self.icons.get("document"), command=self.load_rubric, width=160, height=36, corner_radius=8, font=ctk.CTkFont(size=13), fg_color=Theme.INFO, text_color="white", anchor="w")
        self.btn_rubric.grid(row=1, column=0, padx=20, pady=6, sticky="w")
        self.lbl_rubric_status = ctk.CTkLabel(self.files_card, text=self.t("status_not_selected"), text_color=("gray40", "gray60"), font=ctk.CTkFont(size=13))
        self.lbl_rubric_status.grid(row=1, column=1, padx=12, sticky="w")

        # Folder
        self.btn_folder = ctk.CTkButton(self.files_card, text=" " + self.t("btn_folder"), image=self.icons.get("folder"), command=self.select_folder, width=160, height=36, corner_radius=8, font=ctk.CTkFont(size=13), fg_color=Theme.INFO, text_color="white", anchor="w")
        self.btn_folder.grid(row=2, column=0, padx=20, pady=6, sticky="w")
        self.lbl_folder_status = ctk.CTkLabel(self.files_card, text=self.t("status_not_selected"), text_color=("gray40", "gray60"), font=ctk.CTkFont(size=13))
        self.lbl_folder_status.grid(row=2, column=1, padx=12, sticky="w")

        # Student List
        self.btn_list = ctk.CTkButton(self.files_card, text=" " + self.t("btn_list"), image=self.icons.get("document"), command=self.load_student_list, width=160, height=36, corner_radius=8, font=ctk.CTkFont(size=13), fg_color=Theme.INFO, text_color="white", anchor="w")
        self.btn_list.grid(row=3, column=0, padx=20, pady=(6, 16), sticky="w")
        self.lbl_list_status = ctk.CTkLabel(self.files_card, text=self.t("status_not_uploaded"), text_color=("gray40", "gray60"), font=ctk.CTkFont(size=13))
        self.lbl_list_status.grid(row=3, column=1, padx=12, pady=(6, 16), sticky="w")

        # 2. Dashboard / Controls
        self.dashboard_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.dashboard_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.dashboard_frame.grid_columnconfigure(0, weight=1)
        self.dashboard_frame.grid_columnconfigure(1, weight=1)

        # Controls
        self.controls_card = ctk.CTkFrame(self.dashboard_frame, corner_radius=12)
        self.controls_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        
        # Ultra Compact buttons: height 40, pady 5
        self.btn_start = ctk.CTkButton(self.controls_card, text=self.t("btn_start"), image=self.icons.get("start"), fg_color=Theme.SECONDARY, hover_color=Theme.SECONDARY_HOVER, text_color="#FFFFFF", text_color_disabled="#E0E0E0", height=40, font=ctk.CTkFont(size=14, weight="bold"), corner_radius=8, command=self.start_grading_thread, anchor="center")
        self.btn_start.pack(side="left", padx=8, pady=5, expand=True, fill="x")
        
        self.btn_pause = ctk.CTkButton(self.controls_card, text=self.t("btn_pause"), image=self.icons.get("pause"), fg_color=Theme.WARNING, hover_color=Theme.WARNING_HOVER, text_color="#FFFFFF", text_color_disabled="#E0E0E0", height=40, font=ctk.CTkFont(size=14, weight="bold"), corner_radius=8, state="disabled", command=self.toggle_pause, anchor="center")
        self.btn_pause.pack(side="left", padx=8, pady=5, expand=True, fill="x")
        
        self.btn_stop = ctk.CTkButton(self.controls_card, text=self.t("btn_stop"), image=self.icons.get("stop"), fg_color=Theme.DANGER, hover_color=Theme.DANGER_HOVER, text_color="#FFFFFF", text_color_disabled="#E0E0E0", height=40, font=ctk.CTkFont(size=14, weight="bold"), corner_radius=8, state="disabled", command=self.stop_grading, anchor="center")
        self.btn_stop.pack(side="left", padx=8, pady=5, expand=True, fill="x")

        self.btn_review = ctk.CTkButton(self.controls_card, text=self.t("btn_review"), image=self.icons.get("review"), fg_color=Theme.INFO, hover_color=Theme.PRIMARY_HOVER, text_color="#FFFFFF", height=40, font=ctk.CTkFont(size=14, weight="bold"), corner_radius=8, command=self.open_review_window, anchor="center")
        self.btn_review.pack(side="left", padx=8, pady=5, expand=True, fill="x")

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
            self.log(self.t("log_loaded_profile", profile=choice))
    
    def save_current_profile(self):
        """Save current settings as a profile"""
        # Get current settings
        # Use self.current_api_key if available, else get from entry
        api_key = getattr(self, "current_api_key", self.entry_key.get())
        # If the entry is currently masked, we must ensure we don't save the masked string
        if api_key.startswith("sk-") and "..." in api_key:
             # This is a safety check, but ideally current_api_key should always be correct
             # If we are in masked state, self.current_api_key holds the real key
             pass
        
        profile_data = {
            "api_key": api_key,
            "base_url": self.entry_base.get().strip(),
            "provider": self.provider_var.get(),
            "model": self.combo_model.get(),
            "rubric_path": getattr(self, "rubric_path", ""),
            "exam_folder": getattr(self, "exam_folder", ""),
            "student_list": getattr(self.student_manager, "student_file", "") if hasattr(self, "student_manager") else ""
        }
        
        # Ask for profile name
        dialog = ctk.CTkInputDialog(text=self.t("msg_enter_profile_name"), title=self.t("title_save_profile"))
        profile_name = dialog.get_input()
        
        if not profile_name or profile_name.strip() == "":
            return
            
        profile_name = profile_name.strip()

        # Save profile
        self.config_manager.save_profile(profile_name, profile_data)
        
        # Update dropdown
        self.combo_profile.configure(values=self.config_manager.get_profile_names())
        self.combo_profile.set(profile_name)
        
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
        if "rubric_path" in profile_data and profile_data["rubric_path"]:
            self.rubric_path = profile_data["rubric_path"]
            if os.path.exists(self.rubric_path):
                self.lbl_rubric_status.configure(text=os.path.basename(self.rubric_path), text_color=("green", "lightgreen"))
                # Parse rubric for answer key (in background)
                threading.Thread(target=self.parse_rubric_for_answers, daemon=True).start()
        
        if "exam_folder" in profile_data and profile_data["exam_folder"]:
            self.exam_folder = profile_data["exam_folder"]
            if os.path.exists(self.exam_folder):
                self.lbl_folder_status.configure(text=os.path.basename(self.exam_folder), text_color=("green", "lightgreen"))
        
        if "student_list" in profile_data and profile_data["student_list"]:
            student_path = profile_data["student_list"]
            if os.path.exists(student_path):
                count = self.student_manager.load_from_file(student_path)
                if count > 0:
                    self.lbl_list_status.configure(text=self.t("status_students", count=count), text_color=("green", "lightgreen"))


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
        self.btn_check_model.configure(text=self.t("btn_check_model"))
        
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
        self.btn_check_model.configure(state="disabled", text=self.t("checking"))
        def run_check():
            try:
                engine = AIGraderEngine(self.provider_var.get(), api_key, self.entry_base.get())
                models = engine.get_available_models()
                self.after(0, lambda: self.update_model_list(models))
            except Exception as e:
                err = str(e)
                self.after(0, lambda: messagebox.showerror(self.t("title_check_failed"), err))
            finally:
                self.after(0, lambda: self.btn_check_model.configure(state="normal", text=self.t("btn_check_model")))
        threading.Thread(target=run_check, daemon=True).start()

    def update_model_list(self, models):
        if not models: return
        self.combo_model.configure(values=models)
        self.combo_model.set(models[0])
        messagebox.showinfo(self.t("title_success"), self.t("check_success", count=len(models)))

    def log(self, message):
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{current_time}] {message}\n")
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
            
            # Parse rubric for answer key
            threading.Thread(target=self.parse_rubric_for_answers, daemon=True).start()
            
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

    def check_completion_status(self):
        """
        Strict 1-to-1 verification:
        For every image file in the folder:
        1. Identify Student (Room/Seat).
        2. Check if 'reports/{Room}-{Seat}.md' exists.
        3. Check if Student exists in '成绩汇总表.csv'.
        """
        if not self.exam_folder: return
        
        # 1. Get Images
        valid_extensions = ('.png', '.jpg', '.jpeg')
        try:
            images = [f for f in os.listdir(self.exam_folder) if f.lower().endswith(valid_extensions)]
            total_images = len(images)
        except Exception: return

        if total_images == 0: return

        self.log(self.t("log_verifying", total=total_images))

        # 2. Load CSV Data for quick lookup
        csv_data = set() # Stores (Room, Seat) tuples
        
        csv_names = ["成绩汇总表.csv", "Grade_Summary.csv"]
        csv_path = None
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
            except Exception as e:
                self.log(self.t("log_failed_csv", error=e))

        # 3. Verify 1-to-1
        missing_reports = []
        missing_csv = []
        missing_jsons = []
        failed_files = []
        
        reports_dir = os.path.join(self.exam_folder, "reports")
        failed_dir = os.path.join(self.exam_folder, "failed")
        
        # Use a thread to avoid blocking UI during verification of many files
        def verify_task():
            checked_count = 0
            for filename in images:
                checked_count += 1
                if checked_count % 50 == 0:
                    self.after(0, lambda c=checked_count: self.log(self.t("log_verified_progress", current=c, total=total_images)))

                # Get Student Info
                student_info, _ = self.student_manager.get_student_by_filename(filename)
                room = str(student_info.get('room', '未知'))
                seat = str(student_info.get('seat', '未知'))
                
                # Check Report (.md)
                md_name = f"{room}-{seat}.md"
                md_path = os.path.join(reports_dir, md_name)
                if not os.path.exists(md_path):
                    missing_reports.append(filename)
                
                # Check JSON (.json)
                json_name = f"{room}-{seat}.json"
                json_path = os.path.join(reports_dir, json_name)
                if not os.path.exists(json_path):
                    missing_jsons.append(filename)
                
                # Check CSV
                if (room, seat) not in csv_data:
                    missing_csv.append(filename)

            # Check Failed Folder
            if os.path.exists(failed_dir):
                try:
                    failed_files.extend([f for f in os.listdir(failed_dir) if f.lower().endswith(valid_extensions)])
                except: pass

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
                self.start_targeted_grading(list(missing_set))

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
        config_path = os.path.join(self.exam_folder, "layout_config.json")
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
        config_path = os.path.join(self.exam_folder, "layout_config.json")
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
        if self.template_confirmed:
            callback()
            return

        # Try load
        self.load_layout_config()
        if self.template_confirmed:
            callback()
            return

        # Need detection
        self.start_detection_thread(callback)

    def start_grading_thread(self):
        if not self.rubric_path or not self.exam_folder:
            messagebox.showerror(self.t("title_error"), self.t("msg_select_files"))
            return
        if not self.entry_key.get():
            messagebox.showerror(self.t("title_error"), self.t("msg_enter_key"))
            return
        self.save_current_config()
        
        self.ensure_layout_and_run(self._run_grading_process)

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
        
        threading.Thread(target=self.process_images, daemon=True).start()

    def start_detection_thread(self, callback):
        self.btn_start.configure(state="disabled")
        threading.Thread(target=self.run_detection, args=(callback,), daemon=True).start()

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
            grader = AIGraderEngine(self.provider_var.get(), self.entry_key.get(), self.entry_base.get(), self.combo_model.get())
            
            # Submit all detection tasks concurrently with 1 second stagger
            futures = []
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=sample_count)
            try:
                for i, fname in enumerate(sample_files):
                    # Log with filename
                    self.after(0, lambda i=i, fn=fname, sc=sample_count: self.log(self.t("msg_detecting", current=i+1, total=sc) + f" - {fn}"))
                    path = os.path.join(self.exam_folder, fname)
                    future = executor.submit(grader.detect_regions, path)
                    futures.append(future)
                    # Stagger by 1 second between starts
                    if i < len(sample_files) - 1:
                        time.sleep(1)
                
                # Wait for all detections to complete
                descriptions = []
                for future in concurrent.futures.as_completed(futures):
                    desc = future.result()
                    descriptions.append(desc)
            finally:
                executor.shutdown(wait=True)
            
            # 3. Consolidate
            self.after(0, lambda: self.log(self.t("msg_consolidating")))
            final_layout = grader.consolidate_layout(descriptions)
            
            # 4. Show Confirmation (on main thread)
            self.after(0, lambda: self.show_confirmation_dialog(final_layout, callback))
            
        except Exception as e:
            self.after(0, lambda: self.log(self.t("msg_detect_failed", error=str(e))))
            self.after(0, lambda: self.reset_ui_state())

    def show_confirmation_dialog(self, layout_description, callback):
        def on_confirm(new_desc):
            self.layout_description = new_desc
            self.template_confirmed = True
            self.save_layout_config() # Save config
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

    def stop_grading(self):
        if messagebox.askyesno(self.t("title_confirm"), self.t("msg_confirm_stop")):
            self.stop_event.set()
            self.pause_event.set() # Ensure threads can wake up to exit
            self.log(self.t("msg_stopping"))

    def write_summary_csv(self, data_dict):
        import csv
        
        is_en = (self.current_lang == "EN")
        
        # Smart Filename Selection: Prioritize existing files
        csv_en = "Grade_Summary.csv"
        csv_cn = "成绩汇总表.csv"
        path_en = os.path.join(self.exam_folder, csv_en)
        path_cn = os.path.join(self.exam_folder, csv_cn)
        
        if os.path.exists(path_en):
            csv_path = path_en
        elif os.path.exists(path_cn):
            csv_path = path_cn
        else:
            # Create based on current language
            csv_path = path_en if is_en else path_cn
            
        csv_filename = os.path.basename(csv_path)
        
        # Header Mappings
        header_map = {
            '考场': 'Room', '座号': 'Seat', '班级': 'Class', '姓名': 'Name', '考号': 'ID',
            '总分': 'Total Score', '信息一致性': 'Consistency', '匹配项数': 'Matches',
            'OCR姓名': 'OCR Name', 'OCR班级': 'OCR Class', 'OCR考场': 'OCR Room',
            'OCR座号': 'OCR Seat', 'OCR手写考号': 'OCR Written ID', 'OCR填涂考号': 'OCR Filled ID',
            '原始文件': 'Original File', '客观题': 'Objective Score',
            '客观题正确数': 'Objective Correct', '客观题总数': 'Objective Total',
            '主观题': 'Subjective Score', '复审状态': 'Review Status', '缺考标记': 'Absence Marker'
        }
        
        # Translate data_dict keys if EN
        final_data = {}
        if is_en:
            for k, v in data_dict.items():
                new_key = header_map.get(k, k)
                final_data[new_key] = v
        else:
            final_data = data_dict

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

        # Final Order: Priority -> Subjective Details -> OCR Info -> Original File
        headers = list(final_data.keys())
        sorted_headers = sort_csv_headers(headers)

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
            # Note: For simplicity in this grading context, if headers change, we append new columns
            # But DictWriter handles this by ignoring extras or raising error.
            # To fix "missing fields" in existing CSV, we should ideally rewrite the file if headers changed.
            # Here we implement a check: if sorted_headers != existing_headers, we assume schema change.
            
            mode = 'a'
            if file_exists and existing_headers != sorted_headers:
                # Schema changed! We need to handle this.
                # Strategy: Read all data, map to new schema, rewrite.
                try:
                    all_rows = []
                    with open(csv_path, 'r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        all_rows = list(reader)
                    
                    mode = 'w' # Rewrite mode
                    # We will write all old rows + new row
                except Exception as e:
                    self.log(f"Error updating CSV schema: {e}")
                    # Fallback to append (might cause issues but safer than data loss)
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
                md += f"| {label_s_ans} | " + " | ".join([str(item.get('student_answer', '')).center(4) for item in group]) + " |\n"
                
                # Row: Results
                results = [f"{'✅' if item.get('score', 0) > 0 else '❌'}".center(4) for item in group]
                md += f"| {label_result} | " + " | ".join(results) + " |\n"

                # Row: Correct answers
                md += f"| {label_c_ans} | " + " | ".join([str(item.get('standard_answer', '')).center(4) for item in group]) + " |\n"
            
            md += "\n"
        
        # --- 2. Subjective Questions ---
        if is_english:
            md += "\n### 2. Subjective Questions\n"
        else:
            md += "\n### 2. 主观题\n"
            
        sorted_keys = sorted(subjective_q.keys(), key=lambda x: int(x) if x.isdigit() else 999)
        
        for main_id in sorted_keys:
            items = subjective_q[main_id]
            main_total = sub_scores_dict.get(f"{main_id}", 0)
            
            for item in items:
                q_id = item.get('question_id', '')
                student_answer = item.get('student_answer', '')
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
        
        try:
            with open(self.rubric_path, 'r', encoding='utf-8') as f:
                rubric_text = f.read()
            
            self.log(self.t("log_extracting_answers"))
            
            # Initialize engine if not already done (might be needed if checking models hasn't run)
            # But usually engine is created in start_grading. 
            # Here we create a temporary one or check if we can reuse logic.
            # We need api_key and base_url.
            api_key = getattr(self, "current_api_key", self.entry_key.get())
            if not api_key: return
            
            engine = AIGraderEngine(self.provider_var.get(), api_key, self.entry_base.get(), self.combo_model.get())
            self.answer_key = engine.extract_answer_key(rubric_text)
            
            count = len(self.answer_key)
            self.log(self.t("log_answers_extracted", count=count))
            
        except Exception as e:
            self.log(f"Failed to extract answer key: {e}")

    def save_markdown(self, data, original_filename, db_student_info):
        exam_room = db_student_info.get('room', '未知')
        seat_no = db_student_info.get('seat', '未知')
        filename_prefix = f"{exam_room}-{seat_no}"
        
        # Generate Content
        md_content, sub_scores_dict, consistency_note, matches, obj_score_sum = self.generate_report_content(data, db_student_info)
        
        reports_dir = os.path.join(self.exam_folder, "reports")
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
            '信息一致性': consistency_note
        }
        summary_data.update(sub_scores_dict)
        
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

    def start_targeted_grading(self, target_files):
        # If target_files is None, it means we want to auto-detect missing files (Resume Mode)
        # But we want to show "Targeted Grading" UI state.
        
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
                    # Move to failed
                    failed_dir = os.path.join(self.exam_folder, "failed")
                    if not os.path.exists(failed_dir): os.makedirs(failed_dir)
                    shutil.move(image_path, os.path.join(failed_dir, filename))
                return False
            
            # Resolve Student Info
            student_info, _ = self.student_manager.get_student_by_filename(filename)
            
            # Save Report
            with self.write_lock:
                self.save_markdown(result, filename, student_info)
                
                # Log Saved Status
                self.after(0, lambda fn=filename: self.log(self.t("log_json_saved", filename=fn)))
                self.after(0, lambda fn=filename: self.log(self.t("log_report_saved", filename=fn)))
                
                # Increment counters AFTER successful completion (within lock)
                self.completed_count += 1
                self.session_completed_count += 1
            
            # If this was a retry, move the file from failed back to main folder
            if is_retry:
                try:
                    dest_main = os.path.join(self.exam_folder, filename)
                    shutil.move(image_path, dest_main)
                    self.after(0, lambda fn=filename: self.log(self.t("log_moved_back", filename=fn)))
                except Exception as e:
                    self.after(0, lambda fn=filename: self.log(self.t("log_move_failed", filename=fn, error=str(e))))
            
            # Update UI and log (outside lock)
            self.after(0, lambda: self.update_progress_ui())
            self.after(0, lambda fn=filename: self.log(self.t("log_file_done", filename=fn)))
            return True
            
        except Exception as e:
            err_str = str(e)
            self.after(0, lambda fn=filename, e=err_str: self.log(self.t("log_processing_error", filename=fn, error=e)))
            if not is_retry:
                failed_dir = os.path.join(self.exam_folder, "failed")
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
            # Actually, current_api_key should always be the real key if logic is correct.
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
            
            pending_files = []
            
            if target_files:
                # Targeted Mode: Only process specific files
                failed_dir = os.path.join(self.exam_folder, "failed")
                
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
                # Normal Mode: Resume logic
                for f in files:
                    # Check if markdown exists in reports folder
                    student_info, _ = self.student_manager.get_student_by_filename(f)
                    exam_room = student_info.get('room', '未知')
                    seat_no = student_info.get('seat', '未知')
                    md_name = f"{exam_room}-{seat_no}.md"
                    md_path = os.path.join(self.exam_folder, "reports", md_name)
                    
                    if not os.path.exists(md_path):
                        pending_files.append(f)
            
            # Check failed folder count
            failed_dir = os.path.join(self.exam_folder, "failed")
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
                
                self.after(0, lambda: self.log("🔄 Regenerating Summary CSV..."))
                self.regenerate_csv_from_jsons()
                
                # Final count verification
                self.after(0, lambda: self.log("📊 Verifying final counts..."))
                total_images = len([f for f in os.listdir(self.exam_folder) if f.lower().endswith(valid_extensions)])
                
                reports_dir = os.path.join(self.exam_folder, "reports")
                if os.path.exists(reports_dir):
                    json_count = len([f for f in os.listdir(reports_dir) if f.endswith('.json')])
                    md_count = len([f for f in os.listdir(reports_dir) if f.endswith('.md')])
                else:
                    json_count = md_count = 0
                
                csv_path = os.path.join(self.exam_folder, "成绩汇总表.csv")
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
            
        # 2. Update CSV (Re-generate whole CSV to be safe and simple)
        # This might be slow for huge batches, but ensures consistency.
        self.regenerate_csv_from_jsons()

    def regenerate_csv_from_jsons(self):
        reports_dir = os.path.join(self.exam_folder, "reports")
        if not os.path.exists(reports_dir): return
        
        json_files = [f for f in os.listdir(reports_dir) if f.endswith(".json")]
        all_summaries = []
        
        is_en = (self.current_lang == "EN")
        
        # Header Mappings
        # Key: Internal Key (CN), Value: Display Key (EN)
        header_map = {
            '考场': 'Room', '座号': 'Seat', '班级': 'Class', '姓名': 'Name', '考号': 'ID',
            '总分': 'Total Score', '信息一致性': 'Consistency', '匹配项数': 'Matches',
            'OCR姓名': 'OCR Name', 'OCR班级': 'OCR Class', 'OCR考场': 'OCR Room',
            'OCR座号': 'OCR Seat', 'OCR手写考号': 'OCR Written ID', 'OCR填涂考号': 'OCR Filled ID',
            '复审状态': 'Review Status', '缺考标记': 'Absence Marker', '确认缺考': 'Confirm Absence'
        }
        
        for jf in json_files:
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
                
                summary = {
                    '考场': db_info.get('room', '未知'), 
                    '座号': db_info.get('seat', '未知'), 
                    '班级': db_info.get('class', '未知'), 
                    '姓名': db_info.get('name', '未知'), 
                    '考号': db_info.get('id', '未知'),
                    '总分': data.get('total_score', 0),
                    '信息一致性': consistency_note,
                    '匹配项数': matches,
                    'OCR姓名': data.get('ocr_name', ''),
                    'OCR班级': data.get('ocr_class', ''),
                    'OCR考场': data.get('ocr_room', ''),
                    'OCR座号': data.get('ocr_seat', ''),
                    'OCR手写考号': data.get('ocr_id_written', ''),
                    'OCR填涂考号': data.get('ocr_id_filled', ''),
                    '复审状态': review_status,
                    '缺考标记': data.get('缺考标记', ''),
                    '确认缺考': data.get('confirm_absence', ''),
                    '客观题': obj_score_sum
                }
                
                # Translate Absence Markers if EN
                if is_en:
                    if summary.get('缺考标记') == '是': summary['缺考标记'] = 'Yes'
                    if summary.get('确认缺考') == '是': summary['确认缺考'] = 'Yes'
                    
                summary.update(sub_scores_dict)
                
                # If EN, translate keys in summary
                if is_en:
                    new_summary = {}
                    for k, v in summary.items():
                        new_key = header_map.get(k, k)
                        # Also translate consistency values if needed? 
                        # consistency_note is generated in generate_report_content which is hardcoded CN for now.
                        # Ideally generate_report_content should also be localized, but user asked for CSV mainly.
                        # Let's keep values as is for now unless requested.
                        new_summary[new_key] = v
                    all_summaries.append(new_summary)
                else:
                    all_summaries.append(summary)
        
        # Sort by Room/Seat
        def sort_key(x):
            try: 
                r = x.get('Room') if is_en else x.get('考场')
                s = x.get('Seat') if is_en else x.get('座号')
                return (int(r), int(s))
            except: return (999, 999)
        all_summaries.sort(key=sort_key)
        
        # Write CSV
        if not all_summaries: return
        
        import csv
        csv_filename = "Grade_Summary.csv" if is_en else "成绩汇总表.csv"
        csv_path = os.path.join(self.exam_folder, csv_filename)
        
        # Determine headers
        if is_en:
            base_headers = ['Room', 'Seat', 'Class', 'Name', 'ID', 'Total Score', 'Consistency', 'Matches', 'Review Status']
            ocr_headers = ['OCR Name', 'OCR Class', 'OCR Room', 'OCR Seat', 'OCR Written ID', 'OCR Filled ID']
        else:
            base_headers = ['考场', '座号', '班级', '姓名', '考号', '总分', '信息一致性', '匹配项数', '复审状态']
            ocr_headers = ['OCR姓名', 'OCR班级', 'OCR考场', 'OCR座号', 'OCR手写考号', 'OCR填涂考号']
        
        # Collect all dynamic keys (subjective scores)
        dynamic_keys = set()
        for s in all_summaries:
            for k in s.keys():
                if k not in base_headers and k not in ocr_headers:
                    dynamic_keys.add(k)
        
        # Sort dynamic keys
        def key_sort(k):
            if "_总分" in k:
                try: return (int(k.split('_')[0]), -1)
                except: return (999, -1)
            match = re.match(r"(\d+)\((\d+)\)", k)
            if match:
                return (int(match.group(1)), int(match.group(2)))
            if k.isdigit(): return (int(k), 0)
            return (999, 999)
            
        sorted_dynamic = sorted(list(dynamic_keys), key=key_sort)
        
        fieldnames = base_headers + sorted_dynamic + ocr_headers
        
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_summaries)

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