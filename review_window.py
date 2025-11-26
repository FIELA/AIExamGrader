import customtkinter as ctk
import shutil
from utils import clean_json_string, sort_csv_headers
from PIL import Image, ImageTk
import platform
import os
import json
import csv
import copy
from datetime import datetime
import tkinter as tk
from tkinter import messagebox
import threading
from theme import Theme

class ResumeDialog(ctk.CTkToplevel):
    def __init__(self, parent, title, message, btn_continue_text, btn_restart_text):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x200")
        self.resizable(False, False)
        
        self.result = None
        
        # Center window
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 200
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 100
        self.geometry(f"+{x}+{y}")
        
        # UI
        ctk.CTkLabel(self, text=message, font=("Arial", 14), wraplength=350).pack(pady=30, padx=20)
        
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        ctk.CTkButton(btn_frame, text=btn_restart_text, fg_color="gray", width=120, command=self.on_restart).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text=btn_continue_text, fg_color="#106A38", width=120, command=self.on_continue).pack(side="left", padx=10)
        
        self.transient(parent)
        self.grab_set()
        self.wait_window()
        
    def on_continue(self):
        self.result = True
        self.destroy()
        
    def on_restart(self):
        self.result = False
        self.destroy()

class ReviewWindow(ctk.CTkToplevel):
    def __init__(self, parent, exam_folder, student_manager, on_save_callback, lang="CN", translations=None):
        super().__init__(parent)
        
        self.lang = lang
        self.translations = translations if translations else {}
        
        self.title(self.t("review_title"))
        self.geometry("1400x900")
        
        self.parent_app = parent # Reference to AutoGrader for regrade
        self.exam_folder = exam_folder
        self.student_manager = student_manager
        self.on_save_callback = on_save_callback
        self.reports_dir = os.path.join(exam_folder, "reports")
        
        self.image_files = []
        self.current_index = 0
        self.current_data = None
        self.current_image = None
        self.photo_image = None
        
        # Step State
        self.steps = []
        self.current_step_index = 0
        
        # Zoom/Pan state
        self.scale = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.last_x = 0
        self.last_y = 0
        
        # View Mode: 'image' or 'no_image'
        self.view_mode = 'image'
        self.sub_entries = {}
        
        self.last_confirm_time = 0 # For debounce
        self.chk_absence_var = ctk.BooleanVar() # Variable for absence checkbox
        
        self.load_file_list()
        self.setup_ui()
        
        # Check for saved progress
        # Check for saved progress
        self.progress_file = os.path.join(self.exam_folder, "review_progress.json")
        
        # Default start index: First unreviewed student
        start_index = 0
        for i, f in enumerate(self.image_files):
            try:
                student_info, _ = self.student_manager.get_student_by_filename(f)
                room = str(student_info.get('room', '未知'))
                seat = str(student_info.get('seat', '未知'))
                json_path = os.path.join(self.reports_dir, f"{room}-{seat}.json")
                
                if os.path.exists(json_path):
                    with open(json_path, 'r', encoding='utf-8') as jf:
                        d = json.load(jf)
                        if d.get('review_count', 0) == 0:
                            start_index = i
                            break
            except: pass
            
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, "r") as f:
                    data = json.load(f)
                    saved_idx = data.get("current_index", 0)
                    if saved_idx > 0 and saved_idx < len(self.image_files):
                        # Custom Dialog
                        dialog = ResumeDialog(self, 
                                            self.t("msg_resume_title"), 
                                            self.t("msg_resume_body", index=saved_idx + 1),
                                            self.t("btn_continue"),
                                            self.t("btn_restart"))
                        if dialog.result:
                            start_index = saved_idx
                        else:
                            # If Restart chosen, force 0? Or keep unreviewed?
                            # Usually Restart means from beginning.
                            start_index = 0
            except: pass
            
        self.current_index = start_index
        
        if self.image_files:
            self.load_current_student()
        if not self.image_files:
            messagebox.showinfo(self.t("title_success"), self.t("msg_no_images"))
            self.destroy()
            return
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def t(self, key, **kwargs):
        """Translate helper"""
        text = self.translations.get(self.lang, {}).get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text

    def load_file_list(self):
        valid_extensions = ('.png', '.jpg', '.jpeg')
        if os.path.exists(self.exam_folder):
            all_files = sorted([f for f in os.listdir(self.exam_folder) if f.lower().endswith(valid_extensions)])
            self.image_files = []
            
            # Filter: Only include files with generated reports (JSON)
            for f in all_files:
                try:
                    student_info, _ = self.student_manager.get_student_by_filename(f)
                    room = str(student_info.get('room', '未知'))
                    seat = str(student_info.get('seat', '未知'))
                    
                    # Check JSON existence (primary data source)
                    # Check JSON existence (primary data source)
                    json_path = os.path.join(self.reports_dir, f"{room}-{seat}.json")
                    if os.path.exists(json_path):
                        self.image_files.append(f)
                except: pass
                
            # If no files found via JSON check, maybe fallback to all files?
            # User wants "only show completed", so strict filtering is better.
            if not self.image_files and all_files:
                # Fallback: If 0 reports found but images exist, maybe show all?
                # But user specifically asked for "only completed".
                # So we keep it empty if no reports.
                pass

    def setup_ui(self):
        # Clear existing widgets
        for widget in self.winfo_children():
            widget.destroy()
            
        if self.view_mode == 'image':
            self.setup_image_mode_ui()
        else:
            self.setup_no_image_mode_ui()
            
    def toggle_view_mode(self):
        self.view_mode = 'no_image' if self.view_mode == 'image' else 'image'
        self.update_idletasks() # Ensure pending events are processed
        self.setup_ui()
        self.load_current_student()

    def setup_image_mode_ui(self):
        # --- Global Layout: Action Bar (Bottom) ---
        self.action_frame = ctk.CTkFrame(self, height=50)
        self.action_frame.pack(side="bottom", fill="x", padx=5, pady=5)
        
        # --- Left Group ---
        self.btn_back = ctk.CTkButton(self.action_frame, text=self.t("btn_back"), width=40, command=self.prev_step, fg_color=Theme.TEXT_MUTED_LIGHT)
        self.btn_back.pack(side="left", padx=5, pady=10)
        
        self.lbl_counter = ctk.CTkLabel(self.action_frame, text=self.t("lbl_student_counter", index=0, total=0))
        self.lbl_counter.pack(side="left", padx=10)
        
        self.entry_search = ctk.CTkEntry(self.action_frame, placeholder_text=self.t("lbl_search_placeholder"), width=120)
        self.entry_search.pack(side="left", padx=10)
        self.entry_search.bind("<Return>", lambda e: self.search_student())
        
        # --- Center-Left Group ---
        self.lbl_status = ctk.CTkLabel(self.action_frame, text=self.t("lbl_status", status="--"), font=("Arial", 14, "bold"))
        self.lbl_status.pack(side="left", padx=20)
        
        self.btn_logs = ctk.CTkButton(self.action_frame, text=self.t("btn_logs"), image=self.parent_app.icons.get("document"), width=60, command=self.show_review_logs, fg_color=Theme.TEXT_MUTED_DARK)
        self.btn_logs.pack(side="left", padx=5)
        
        self.lbl_score = ctk.CTkLabel(self.action_frame, text=self.t("lbl_total_score_display", score="--"), font=("Arial", 14, "bold"), text_color="#2563EB")
        self.lbl_score.place(relx=0.5, rely=0.5, anchor="center")
        
        # --- Right Group (Packed from Right to Left) ---
        self.btn_confirm_all = ctk.CTkButton(self.action_frame, text=self.t("btn_confirm_next"), width=140, command=self.confirm_all_and_next, fg_color=Theme.SECONDARY, hover_color=Theme.SECONDARY_HOVER)
        self.btn_confirm_all.pack(side="right", padx=10, pady=10)
        
        self.btn_next_image = ctk.CTkButton(self.action_frame, text=self.t("btn_next_image"), width=40, command=self.skip_student, fg_color=Theme.WARNING, hover_color=Theme.WARNING_HOVER)
        self.btn_next_image.pack(side="right", padx=5, pady=10)
        
        self.btn_mode = ctk.CTkButton(self.action_frame, text=self.t("btn_text_mode"), width=80, command=self.toggle_view_mode, fg_color=Theme.INFO)
        self.btn_mode.pack(side="right", padx=5)
        
        self.chk_absence = ctk.CTkCheckBox(self.action_frame, text=self.t("chk_absence"), variable=self.chk_absence_var, command=self.on_absence_toggle)
        self.chk_absence.pack(side="right", padx=(0, 20))

        # --- Global Layout: Main Content (Top) ---
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(side="top", fill="both", expand=True, padx=5, pady=5)
        
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(1, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)
        
        # --- Left: Image Viewer ---
        self.image_frame = ctk.CTkFrame(self.main_frame, fg_color="gray10")
        self.image_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.image_frame.grid_rowconfigure(0, weight=1) 
        self.image_frame.grid_columnconfigure(0, weight=1)
        
        # 1. Canvas
        self.canvas = tk.Canvas(self.image_frame, bg="gray10", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        
        # 2. Scrollbars
        self.scroll_x = tk.Scrollbar(self.image_frame, orient="horizontal", command=self.canvas.xview)
        self.scroll_x.grid(row=1, column=0, sticky="ew")
        self.scroll_y = tk.Scrollbar(self.image_frame, orient="vertical", command=self.canvas.yview)
        self.scroll_y.grid(row=0, column=1, sticky="ns")
        
        self.canvas.configure(xscrollcommand=self.scroll_x.set, yscrollcommand=self.scroll_y.set)
        
        # 3. Zoom Toolbar
        self.zoom_toolbar = ctk.CTkFrame(self.image_frame, height=40, fg_color="gray20")
        self.zoom_toolbar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=2, pady=2)
        
        self.btn_zoom_out = ctk.CTkButton(self.zoom_toolbar, text=self.t("btn_zoom_out"), width=40, command=self.zoom_out)
        self.btn_zoom_out.pack(side="left", padx=5, pady=5)
        
        self.lbl_zoom = ctk.CTkLabel(self.zoom_toolbar, text=self.t("lbl_zoom", scale=100), width=60)
        self.lbl_zoom.pack(side="left", padx=5)
        
        self.btn_zoom_in = ctk.CTkButton(self.zoom_toolbar, text=self.t("btn_zoom_in"), width=40, command=self.zoom_in)
        self.btn_zoom_in.pack(side="left", padx=5, pady=5)
        
        self.btn_reset = ctk.CTkButton(self.zoom_toolbar, text=self.t("btn_reset_zoom"), width=80, command=self.reset_zoom)
        self.btn_reset.pack(side="left", padx=10, pady=5)
        
        self.btn_left = ctk.CTkButton(self.zoom_toolbar, text=self.t("btn_left"), width=80, command=self.scroll_to_left)
        self.btn_left.pack(side="left", padx=5, pady=5)
        
        self.btn_right = ctk.CTkButton(self.zoom_toolbar, text=self.t("btn_right"), width=80, command=self.scroll_to_right)
        self.btn_right.pack(side="left", padx=5, pady=5)
        
        # Bindings
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Enter>", lambda e: self.canvas.config(cursor="hand2"))
        self.canvas.bind("<Leave>", lambda e: self.canvas.config(cursor=""))

        # --- Right: Report & Controls ---
        self.right_panel = ctk.CTkFrame(self.main_frame)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        
        # CRITICAL: Pack Controls (Bottom) FIRST, then Report (Top, Expand)
        # 2. Verification Controls (Bottom, Fixed)
        self.controls_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.controls_frame.pack(side="bottom", fill="x", padx=5, pady=5)
        
        # Step Header
        self.lbl_step_header = ctk.CTkLabel(self.controls_frame, text="Step 1/3: Info", font=("Arial", 16, "bold"))
        self.lbl_step_header.pack(pady=(10, 5))
        
        # Dynamic Content Area
        self.step_content_frame = ctk.CTkFrame(self.controls_frame)
        self.step_content_frame.pack(fill="x", pady=5, padx=5)

        # 1. Report Viewer (Top, Expand)
        self.report_textbox = ctk.CTkTextbox(self.right_panel, font=("Courier", 12))
        self.report_textbox.pack(side="top", fill="both", expand=True, padx=5, pady=5)

    def setup_no_image_mode_ui(self):
        # --- Global Layout: Action Bar (Bottom) ---
        self.action_frame = ctk.CTkFrame(self, height=50)
        self.action_frame.pack(side="bottom", fill="x", padx=5, pady=5)
        
        # --- Left Group ---
        self.btn_back = ctk.CTkButton(self.action_frame, text=self.t("btn_back"), width=40, command=self.prev_student, fg_color="gray")
        self.btn_back.pack(side="left", padx=5, pady=10)
        
        self.lbl_counter = ctk.CTkLabel(self.action_frame, text=self.t("lbl_student_counter", index=0, total=0))
        self.lbl_counter.pack(side="left", padx=10)
        
        self.entry_search = ctk.CTkEntry(self.action_frame, placeholder_text=self.t("lbl_search_placeholder"), width=120)
        self.entry_search.pack(side="left", padx=10)
        self.entry_search.bind("<Return>", lambda e: self.search_student())
        
        # --- Center-Left Group ---
        self.lbl_status = ctk.CTkLabel(self.action_frame, text=self.t("lbl_status", status="--"), font=("Arial", 14, "bold"))
        self.lbl_status.pack(side="left", padx=20)
        
        self.btn_logs = ctk.CTkButton(self.action_frame, text=self.t("btn_logs"), width=60, command=self.show_review_logs, fg_color="#4B5563")
        self.btn_logs.pack(side="left", padx=5)
        
        # --- Right Group (Packed from Right to Left) ---
        self.btn_confirm_all = ctk.CTkButton(self.action_frame, text=self.t("btn_confirm_next"), width=140, command=self.confirm_all_and_next, fg_color="#106A38")
        self.btn_confirm_all.pack(side="right", padx=10, pady=10)
        
        # Total Score (Moved here, to the left of Confirm button)
        self.lbl_score = ctk.CTkLabel(self.action_frame, text=self.t("lbl_total_score_display", score="--"), font=("Arial", 16, "bold"), text_color="#2563EB")
        self.lbl_score.pack(side="right", padx=15)
        
        self.btn_next_image = ctk.CTkButton(self.action_frame, text=self.t("btn_next_image"), width=40, command=self.skip_student, fg_color="#D97706")
        self.btn_next_image.pack(side="right", padx=5, pady=10)
        
        self.btn_mode = ctk.CTkButton(self.action_frame, text=self.t("btn_image_mode"), width=80, command=self.toggle_view_mode, fg_color="#0F766E")
        self.btn_mode.pack(side="right", padx=5)
        
        self.chk_absence = ctk.CTkCheckBox(self.action_frame, text=self.t("chk_absence"), variable=self.chk_absence_var, command=self.on_absence_toggle)
        self.chk_absence.pack(side="right", padx=(0, 20))
        


        # --- Global Layout: Main Content (Top) ---
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(side="top", fill="both", expand=True, padx=5, pady=5)
        
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(1, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)
        
        # --- Left Panel ---
        self.left_panel = ctk.CTkFrame(self.main_frame)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # CRITICAL: Pack Info/Obj (Bottom) FIRST, then Report (Top, Expand)
        # 2. Info & Objective Frame (Bottom, Fixed)
        self.info_obj_frame = ctk.CTkFrame(self.left_panel)
        self.info_obj_frame.pack(side="bottom", fill="x", padx=5, pady=5)

        # 1. Report Viewer (Top, Expand)
        self.report_textbox = ctk.CTkTextbox(self.left_panel, font=("Courier", 12))
        self.report_textbox.pack(side="top", fill="both", expand=True, padx=5, pady=5)
        
        # --- Right Panel (Subjective) ---
        self.right_panel = ctk.CTkFrame(self.main_frame)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        
        self.subj_scroll = ctk.CTkScrollableFrame(self.right_panel, label_text=self.t("lbl_review_details"))
        self.subj_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Enable global mouse wheel scrolling
        self.setup_global_scroll()

    # --- Navigation Methods ---
    def next_student(self):
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self.load_current_student()
        else:
            messagebox.showinfo(self.t("title_success"), self.t("msg_all_reviewed"))
            self.destroy()
            
    def prev_student(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_student()
        else:
            messagebox.showinfo(self.t("title_success"), self.t("msg_first_student"))

    def skip_student(self):
        """Skip current student without saving"""
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self.load_current_student()
        else:
            messagebox.showinfo("Done", self.t("msg_all_reviewed"))
            self.destroy()

    def search_student(self):
        query = self.entry_search.get().strip().lower()
        if not query: return
        
        found_index = -1
        
        for idx, filename in enumerate(self.image_files):
            # We need to peek at student info without fully loading if possible, 
            # or just use the student_manager which should have it cached.
            student_info, _ = self.student_manager.get_student_by_filename(filename)
            
            name = str(student_info.get('name', '')).lower()
            sid = str(student_info.get('id', '')).lower()
            if sid.endswith('.0'): sid = sid[:-2] # Handle float conversion artifacts
            
            room = str(student_info.get('room', ''))
            seat = str(student_info.get('seat', ''))
            
            # Check matches
            if query in name or query in sid:
                found_index = idx
                break
            
            # Check Room-Seat exact match (e.g. "01-05") or loose match ("1-5")
            if "-" in query:
                try:
                    q_parts = query.split("-")
                    if len(q_parts) == 2:
                        q_room = int(q_parts[0])
                        q_seat = int(q_parts[1])
                        
                        s_room = int(room) if room.isdigit() else -1
                        s_seat = int(seat) if seat.isdigit() else -1
                        
                        if s_room == q_room and s_seat == q_seat:
                            found_index = idx
                            break
                except: pass
            
            if f"{room}-{seat}" == query:
                found_index = idx
                break
                
            # Check just seat if room is implicit? No, stick to explicit.
            
        if found_index != -1:
            self.current_index = found_index
            self.load_current_student()
            # Clear search? Maybe keep it.
        else:
            messagebox.showinfo(self.t("title_success"), self.t("msg_student_not_found"))

    # --- Image Logic ---
    def zoom_in(self):
        if self.scale < 5.0:
            self.scale *= 1.2
            self.redraw_image()
            
    def zoom_out(self):
        if self.scale > 0.1:
            self.scale /= 1.2
            self.redraw_image()
            
    def reset_zoom(self):
        self.scale = 0.27
        self.pan_x = 0
        self.pan_y = 0
        self.redraw_image()
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        
    def scroll_to_right(self):
        self.canvas.xview_moveto(1.0)

    def scroll_to_left(self):
        self.canvas.xview_moveto(0.0)

    def redraw_image(self):
        if not self.current_image: return
        
        # Update Label
        if hasattr(self, 'lbl_zoom'):
            self.lbl_zoom.configure(text=f"{int(self.scale * 100)}%")
        
        w, h = self.current_image.size
        new_w = int(w * self.scale)
        new_h = int(h * self.scale)
        
        img_resized = self.current_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.photo_image = ImageTk.PhotoImage(img_resized)
        
        self.canvas.delete("all")
        self.canvas.config(scrollregion=(0, 0, new_w, new_h))
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo_image)

    def show_placeholder(self, text):
        self.current_image = None
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        self.canvas.create_text(w//2, h//2, text=text, fill="white", font=("Arial", 16))

    def on_mouse_down(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def on_mouse_drag(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def on_mouse_wheel(self, event):
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def load_current_student(self):
        if not self.image_files: return
        
        filename = self.image_files[self.current_index]
        # Update Counter
        self.lbl_counter.configure(text=self.t("lbl_student_counter", index=self.current_index + 1, total=len(self.image_files)))
        
        

            
        # 1. Load Image (Only if in image mode)
        if self.view_mode == 'image':
            img_path = os.path.join(self.exam_folder, filename)
            if os.path.exists(img_path):
                self.current_image = Image.open(img_path)
                self.reset_zoom()
            else:
                self.show_placeholder(self.t("msg_no_images"))
            
        # 2. Resolve Student & Report
        student_info, _ = self.student_manager.get_student_by_filename(filename)
        room = str(student_info.get('room', '未知'))
        seat = str(student_info.get('seat', '未知'))
        
        json_name = f"{room}-{seat}.json"
        json_path = os.path.join(self.reports_dir, json_name)
        
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                self.current_data = json.load(f)
        else:
            # Legacy Support: Try to load from CSV
            csv_score = 0
            csv_obj_score = 0
            
            # Try both Chinese and English filenames
            csv_names = ["成绩汇总表.csv", "Grade_Summary.csv"]
            csv_path = None
            for name in csv_names:
                p = os.path.join(self.exam_folder, name)
                if os.path.exists(p):
                    csv_path = p
                    break
            
            if csv_path:
                try:
                    with open(csv_path, 'r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            # Handle localized headers
                            r_val = row.get('考场') or row.get('Room')
                            s_val = row.get('座号') or row.get('Seat')
                            
                            if str(r_val) == room and str(s_val) == seat:
                                try: 
                                    csv_score = float(row.get('总分') or row.get('Total Score', 0))
                                except: pass
                                try: 
                                    csv_obj_score = float(row.get('客观题') or row.get('Objective Score', 0))
                                except: pass
                                break
                except: pass

            self.current_data = {
                'total_score': csv_score,
                'ocr_name': '', 'ocr_class': '', 'ocr_room': '', 'ocr_seat': '',
                'ocr_id_written': '', 'ocr_id_filled': '',
                'db_student_info': student_info,
                'details': [], # Details missing in legacy
                'original_filename': filename,
                'legacy_obj_score': csv_obj_score
            }
            
        if 'original_filename' not in self.current_data or not self.current_data['original_filename']:
            self.current_data['original_filename'] = filename
            
        # Backup for Diff (Review Logs)
        self.original_data = copy.deepcopy(self.current_data)
            
        # Update Absence Checkbox
        # 1. Get Manual Confirmation
        is_confirmed_str = self.current_data.get('confirm_absence', '')
        
        # 2. Get Auto Detection
        is_absent = self.current_data.get('缺考标记') == '是' or self.current_data.get('Absence Marker') == '是'
        
        # Fallback to db_info if not in current_data
        if not is_absent:
            db_info = self.current_data.get('db_student_info', {})
            is_absent = db_info.get('is_absent', False)
            
        # 3. Set Checkbox State
        if is_confirmed_str:
            # If manually set, use that (handle both "Yes" and legacy "是")
            self.chk_absence_var.set(is_confirmed_str in ['Yes', '是'])
        else:
            # Default to auto detection
            self.chk_absence_var.set(is_absent)
            
        # 3. Load Report Text
        md_name = f"{room}-{seat}.md"
        md_path = os.path.join(self.reports_dir, md_name)

        
        if os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                self.report_textbox.delete("1.0", "end")
                self.report_textbox.insert("1.0", f.read())
        else:
            self.report_textbox.delete("1.0", "end")
            self.report_textbox.insert("1.0", f"No Report Generated\nPath: {md_path}")

        # Update Status Label (Now that current_data is loaded)
        review_count = self.current_data.get("review_count", 0)
        status_text = self.t("status_unreviewed")
        status_color = "red"
        
        if review_count == 1:
            status_text = self.t("status_reviewed")
            status_color = "green"
        elif review_count >= 2:
            status_text = self.t("status_second_review")
            status_color = "blue"
            
        if hasattr(self, 'lbl_status'):
            self.lbl_status.configure(text=self.t("lbl_status", status=status_text), text_color=status_color)
            
        self.update_score_display()
            


        # 4. Generate Steps & Load UI
        self.generate_steps()
        
        # 5. Start Confirm Countdown (Initialize timer first)
        self.start_confirm_timer()
        
        # 6. Load UI Initial State
        if self.view_mode == 'image':
            self.current_step_index = 0
            self.load_step_ui()
        else:
            self.load_no_image_ui()
        
    def start_confirm_timer(self):
        """Disable confirm button for 3 seconds to prevent accidental clicks"""
        if not hasattr(self, 'btn_confirm_all'): return
        
        self.btn_confirm_all.configure(state="disabled")
        self.confirm_timer_seconds = 3
        self.update_confirm_button_state()
        
    def update_confirm_button_state(self):
        if not hasattr(self, 'btn_confirm_all'): return
        
        # 1. Timer Logic
        if self.confirm_timer_seconds > 0:
            base_text = self.t("btn_confirm_next")
            self.btn_confirm_all.configure(text=f"{base_text} ({self.confirm_timer_seconds})")
            self.confirm_timer_seconds -= 1
            self.after(1000, self.update_confirm_button_state)
            return # Keep disabled while timer is running
            
        # 2. Timer Finished: Check Conditions
        target_text = self.t("btn_confirm_next")
        if self.btn_confirm_all.cget("text") != target_text:
            self.btn_confirm_all.configure(text=target_text)
        
        target_state = "disabled"
        if self.view_mode == 'image':
            # Image Mode: Enable if on last step OR absence confirmed
            is_absent = self.chk_absence_var.get()
            if self.current_step_index == len(self.steps) - 1 or is_absent:
                target_state = "normal"
        else:
            # Text Mode: Always enable after timer
            target_state = "normal"
            
        if self.btn_confirm_all.cget("state") != target_state:
            self.btn_confirm_all.configure(state=target_state)
            
    def on_absence_toggle(self):
        # Update button state immediately if timer is not running
        if self.confirm_timer_seconds <= 0:
            self.update_confirm_button_state()
        


    def update_score_display(self):
        if hasattr(self, 'lbl_score'):
            score = self.current_data.get('total_score', 0)
            self.lbl_score.configure(text=self.t("lbl_total_score_display", score=score))



    def generate_steps(self):
        self.steps = []
        # Step 1: Info
        self.steps.append({'type': 'info', 'title': self.t("lbl_step_info")})
        # Step 2: Objective
        self.steps.append({'type': 'obj', 'title': self.t("lbl_step_obj")})
        # Step 3+: Subjective Questions
        details = self.current_data.get('details', [])
        sub_items = [x for x in details if "客观" not in x.get('type', '') and "选择" not in x.get('type', '')]
        
        seen_mains = set()
        for item in sub_items:
            q_id = str(item.get('question_id', ''))
            import re
            match = re.match(r"(\d+)", q_id)
            main_id = match.group(1) if match else q_id
            
            if main_id not in seen_mains:
                seen_mains.add(main_id)
                self.steps.append({
                    'type': 'subj', 
                    'title': self.t("lbl_step_subj_q", qid=main_id),
                    'main_id': main_id,
                    'items': [x for x in sub_items if str(x.get('question_id')).startswith(main_id)]
                })

    def load_step_ui(self):
        # Only for Image Mode
        self.sub_entries = {}
        for widget in self.step_content_frame.winfo_children():
            widget.destroy()
            
        step = self.steps[self.current_step_index]
        self.lbl_step_header.configure(text=step['title'])
        
        self.auto_scroll_assets(step)
        
        # Temporarily point step_content_frame to the dynamic frame for shared render methods
        # (Already set in setup_image_mode_ui)
        
        if step['type'] == 'info':
            self.render_info_step(self.step_content_frame)
        elif step['type'] == 'obj':
            self.render_obj_step(self.step_content_frame)
        elif step['type'] == 'subj':
            self.render_subj_step(step, self.step_content_frame)
            
        # Update Confirm Button State (for Image Mode step restriction)
        self.update_confirm_button_state()

    def load_no_image_ui(self):
        # Populate Left Bottom: Info Only
        for widget in self.info_obj_frame.winfo_children(): widget.destroy()
        
        ctk.CTkLabel(self.info_obj_frame, text=self.t("lbl_info_header"), font=("Arial", 14, "bold")).pack(anchor="w", pady=5)
        self.render_info_step(self.info_obj_frame, show_buttons=False)
        
        # Populate Right: Objective & Subjective
        for widget in self.subj_scroll.winfo_children(): widget.destroy()
        
        # 1. Objective
        ctk.CTkLabel(self.subj_scroll, text=self.t("lbl_obj_header"), font=("Arial", 14, "bold")).pack(anchor="w", pady=(10, 5))
        self.render_obj_step(self.subj_scroll, show_buttons=False)
        
        ctk.CTkFrame(self.subj_scroll, height=2, fg_color="gray50").pack(fill="x", pady=10)
        
        # 2. Subjective
        ctk.CTkLabel(self.subj_scroll, text=self.t("lbl_subj_header"), font=("Arial", 14, "bold")).pack(anchor="w", pady=(10, 5))
        
        subj_steps = [s for s in self.steps if s['type'] == 'subj']
        self.sub_entries = {} # Reset
        
        for step in subj_steps:
            ctk.CTkLabel(self.subj_scroll, text=step['title'], font=("Arial", 12, "bold")).pack(anchor="w", pady=(10, 5))
            self.render_subj_step(step, self.subj_scroll, show_buttons=False)

    def auto_scroll_assets(self, step):
        if self.view_mode != 'image': return
        
        target_y = 0.0
        if step['type'] == 'info': target_y = 0.0
        elif step['type'] == 'obj': target_y = 0.15
        elif step['type'] == 'subj':
            try:
                mid = int(step.get('main_id', 0))
                target_y = 0.3 + (mid - 17) * 0.15
                if target_y > 0.9: target_y = 0.9
            except: target_y = 0.4
            
        self.canvas.yview_moveto(target_y)
        
        search_term = ""
        if step['type'] == 'info': search_term = "基本信息"
        elif step['type'] == 'obj': search_term = "客观题"
        elif step['type'] == 'subj': search_term = f"第 {step.get('main_id')} 题"
        
        if search_term:
            pos = self.report_textbox.search(search_term, "1.0")
            if pos: self.report_textbox.see(pos)

    def render_info_step(self, parent, show_buttons=True):
        db_info = self.current_data.get('db_student_info', {})
        
        # --- Search Filter ---
        ctk.CTkLabel(parent, text=self.t("lbl_filter")).pack(anchor="w")
        self.entry_filter = ctk.CTkEntry(parent, placeholder_text=self.t("lbl_filter"))
        self.entry_filter.pack(fill="x", pady=(0, 5))
        self.entry_filter.bind("<KeyRelease>", self.filter_student_list)
        
        # --- Student Dropdown ---
        ctk.CTkLabel(parent, text=self.t("lbl_select_student")).pack(anchor="w")
        
        # Format: Name | Class | ID | Room-Seat
        self.full_student_list = [
            f"{s['name']} | {s.get('class','')}班 | {s['id']} | {s.get('room','')}-{s.get('seat','')}" 
            for s in self.student_manager.students
        ]
        
        current_val = f"{db_info.get('name', '')} | {db_info.get('class','')}班 | {db_info.get('id', '')} | {db_info.get('room','')}-{db_info.get('seat','')}"
        
        self.combo_student = ctk.CTkComboBox(parent, values=self.full_student_list, width=400)
        
        # Try to find exact match to ensure consistent display
        match = next((s for s in self.full_student_list if current_val == s), None)
        if match:
            self.combo_student.set(match)
        else:
            self.combo_student.set(current_val)
            
        self.combo_student.pack(anchor="w", pady=5)
        
        # --- Re-grade Button ---
        ctk.CTkButton(parent, text=self.t("btn_regrade"), fg_color="#7C3AED", command=self.trigger_regrade).pack(anchor="w", pady=10)
        
        if show_buttons:
            self.add_step_buttons(parent)

    def render_obj_step(self, parent, show_buttons=True):
        details = self.current_data.get('details', [])
        obj_items = [x for x in details if "客观" in x.get('type', '') or "选择" in x.get('type', '')]
        
        # Sort by Question ID (numeric)
        def get_sort_key(item):
            qid = str(item.get('question_id', '0'))
            import re
            m = re.match(r"(\d+)", qid)
            return int(m.group(1)) if m else 999
        
        obj_items.sort(key=get_sort_key)
        
        # --- Summary Header ---
        if obj_items:
            obj_score = sum(x.get('score', 0) for x in obj_items)
            obj_correct = len([x for x in obj_items if x.get('score', 0) > 0])
        else:
            obj_score = self.current_data.get('legacy_obj_score', 0)
            obj_correct = int(obj_score / 3)
            
        header_frame = ctk.CTkFrame(parent, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(header_frame, text=self.t("lbl_correct_count")).pack(side="left")
        ctk.CTkLabel(header_frame, text=f"{obj_correct}", font=("Arial", 12, "bold")).pack(side="left", padx=5)
        
        ctk.CTkLabel(header_frame, text=self.t("lbl_total_score")).pack(side="left", padx=(20, 0))
        ctk.CTkLabel(header_frame, text=f"{obj_score}", font=("Arial", 12, "bold")).pack(side="left", padx=5)
        
        # --- Grid Layout for Questions ---
        grid_frame = ctk.CTkFrame(parent, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True)
        
        cols = 5
        for i, item in enumerate(obj_items):
            row = i // cols
            col = i % cols
            
            q_id = item.get('question_id', '?')
            stu_ans = item.get('student_answer', '')
            score = item.get('score', 0)
            
            # Display "-" for unanswered
            if not stu_ans:
                stu_ans = "-"
            
            # Color code
            score_color = "#106A38" if score > 0 else "#DC2626" # Green/Red
            if score == 0 and stu_ans == "-": score_color = "gray"
            
            card = ctk.CTkFrame(grid_frame, border_width=1, border_color="gray50")
            card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            
            # Q ID (Color coded, no punctuation)
            ctk.CTkLabel(card, text=f"{q_id}", font=("Arial", 12, "bold"), text_color=score_color).pack(pady=(5,0))
            
            # Dropdown for Student Answer
            answer_options = ["A", "B", "C", "D", "-"]
            combo = ctk.CTkComboBox(card, values=answer_options, width=50, height=28, 
                                   command=lambda choice, q=q_id: self.on_obj_answer_change(q, choice))
            combo.set(stu_ans)
            combo.pack(pady=(2, 5))
            
            # Score Display REMOVED as requested

        if show_buttons:
            self.add_step_buttons(parent)

    def on_obj_answer_change(self, q_id, new_ans):
        # Convert "-" to empty string internally
        if new_ans == "-":
            new_ans = ""
        else:
            new_ans = new_ans.strip().upper()
        
        details = self.current_data.get('details', [])
        
        changed = False
        for item in details:
            if str(item.get('question_id')) == str(q_id):
                old_ans = item.get('student_answer', '')
                if old_ans != new_ans:
                    item['student_answer'] = new_ans
                    item['manual_override'] = True # Flag as manually modified
                    
                    # Recalculate Score locally
                    std_ans = item.get('standard_answer', '')
                    if hasattr(self.parent_app, 'answer_key') and self.parent_app.answer_key:
                        std_ans = self.parent_app.answer_key.get(q_id, std_ans)
                    
                    max_score = item.get('max_score', 0)
                    if not max_score: max_score = 3 # Default fallback
                    
                    if new_ans and new_ans == std_ans:
                        item['score'] = max_score
                    else:
                        item['score'] = 0
                        
                    changed = True
                break
        
        if changed:
            # Recalculate totals
            self.recalculate_totals()
            # Refresh UI (to update colors/scores)
            if self.view_mode == 'image':
                self.load_step_ui()
            else:
                self.load_no_image_ui()

    def recalculate_totals(self):
        details = self.current_data.get('details', [])
        if not details: return
        
        sub_sum = sum(x.get('score', 0) for x in details)
        self.current_data['total_score'] = sub_sum
        self.update_score_display()

    def render_subj_step(self, step, parent, show_buttons=True):
        items = step['items']
        
        for item in items:
            q_id = item.get('question_id')
            score = item.get('score', 0)
            max_score = item.get('max_score', 0)
            
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=2)
            
            ctk.CTkLabel(row, text=self.t("lbl_q_score", qid=q_id, max=max_score), width=120, anchor="w").pack(side="left")
            
            entry = ctk.CTkEntry(row, width=60)
            entry.insert(0, str(score))
            entry.pack(side="left", padx=5)
            self.sub_entries[q_id] = (entry, max_score)
            
        if show_buttons:
            self.add_step_buttons(parent)

    def add_step_buttons(self, parent):
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(fill="x", pady=20)
        
        ctk.CTkButton(btn_frame, text=self.t("btn_correct"), fg_color="#106A38", width=120, command=self.next_step).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text=self.t("btn_confirm_edit"), fg_color="#D97706", width=120, command=self.next_step).pack(side="left", padx=10)

    def confirm_all_and_next(self):
        # Debounce check (3 seconds)
        import time
        now = time.time()
        if now - self.last_confirm_time < 3.0:
            return
        self.last_confirm_time = now
        
        selected_str = self.combo_student.get()
        try:
            parts = selected_str.split(" | ")
            name = parts[0]
            sid = parts[2]
            found = False
            for s in self.student_manager.students:
                if s['name'] == name and str(s['id']) == str(sid):
                    self.current_data['db_student_info'] = s
                    found = True
                    break
            if not found:
                self.current_data['db_student_info']['name'] = name
                self.current_data['db_student_info']['id'] = sid
        except: pass
        
        # 2. Save Obj
        try:
            new_score = float(self.entry_obj_score.get())
            if new_score.is_integer(): new_score = int(new_score)
            details = self.current_data.get('details', [])
            if details:
                current_obj_sum = sum(x.get('score', 0) for x in details if "客观" in x.get('type', '') or "选择" in x.get('type', ''))
                diff = new_score - current_obj_sum
                if diff != 0:
                    found = False
                    for item in details:
                        if "客观" in item.get('type', '') or "选择" in item.get('type', ''):
                            item['score'] += diff
                            found = True
                            break
                    if not found:
                         details.append({'question_id': 'Obj_Adj', 'type': '客观题修正', 'score': diff})
            else:
                self.current_data['legacy_obj_score'] = new_score
        except: pass
        
        # 3. Save Subj
        for q_id, (entry, max_s) in self.sub_entries.items():
            try:
                val = float(entry.get())
                if val > max_s:
                    messagebox.showerror(self.t("title_error"), self.t("msg_score_error", qid=q_id, max=max_s))
                    return
                if val.is_integer(): val = int(val)
                
                for item in self.current_data.get('details', []):
                    if item.get('question_id') == q_id:
                        item['score'] = val
            except: return

        # 4. Recalculate Total
        # 4. Recalculate Total
        if self.chk_absence_var.get():
            self.current_data['total_score'] = 0
            self.current_data['legacy_obj_score'] = 0
            for item in self.current_data.get('details', []):
                item['score'] = 0
        else:
            details = self.current_data.get('details', [])
            sub_sum = sum(x.get('score', 0) for x in details)
            legacy_obj = self.current_data.get('legacy_obj_score', 0)
            
            if not details:
                 self.current_data['total_score'] = legacy_obj
            else:
                 has_obj = any("客观" in x.get('type', '') for x in details)
                 if has_obj:
                     self.current_data['total_score'] = sub_sum
                 else:
                     self.current_data['total_score'] = sub_sum + legacy_obj
        
        self.save_to_disk()
        self.next_student()

    def save_current_step(self):
        # Implementation for save_current_step (needed for next_step/prev_step)
        # Note: This was also missing in the previous view, but confirm_all_and_next covers most logic.
        # However, next_step calls save_current_step.
        # I need to make sure save_current_step is defined or I refactor next_step.
        # Looking at previous code, save_current_step was defined.
        # Let's re-add it if it's missing, but wait, I see confirm_all_and_next.
        # The previous replace removed save_current_step too?
        # Let's check the view again.
        # Ah, I see confirm_all_and_next but I don't see save_current_step in the view output (450-537).
        # I need to restore save_current_step as well if it's used by next_step.
        # Yes, next_step calls self.save_current_step().
        
        step = self.steps[self.current_step_index]
        
        if step['type'] == 'info':
            selected_str = self.combo_student.get()
            try:
                parts = selected_str.split(" | ")
                name = parts[0]
                sid = parts[2]
                found = False
                for s in self.student_manager.students:
                    if s['name'] == name and str(s['id']) == str(sid):
                        self.current_data['db_student_info'] = s
                        found = True
                        break
                if not found:
                    self.current_data['db_student_info']['name'] = name
                    self.current_data['db_student_info']['id'] = sid
            except: pass
            
        elif step['type'] == 'obj':
            try:
                new_score = float(self.entry_obj_score.get())
                if new_score.is_integer(): new_score = int(new_score)
                details = self.current_data.get('details', [])
                if details:
                    current_obj_sum = sum(x.get('score', 0) for x in details if "客观" in x.get('type', '') or "选择" in x.get('type', ''))
                    diff = new_score - current_obj_sum
                    if diff != 0:
                        found = False
                        for item in details:
                            if "客观" in item.get('type', '') or "选择" in item.get('type', ''):
                                item['score'] += diff
                                found = True
                                break
                        if not found:
                             details.append({'question_id': 'Obj_Adj', 'type': '客观题修正', 'score': diff})
                else:
                    self.current_data['legacy_obj_score'] = new_score
            except: pass
            
        elif step['type'] == 'subj':
            for q_id, (entry, max_s) in self.sub_entries.items():
                try:
                    val = float(entry.get())
                    if val > max_s:
                        messagebox.showerror(self.t("title_error"), self.t("msg_score_error", qid=q_id, max=max_s))
                        return False
                    if val.is_integer(): val = int(val)
                    for item in self.current_data.get('details', []):
                        if item.get('question_id') == q_id:
                            item['score'] = val
                except: return False

        # Recalculate Total Score
        if self.chk_absence_var.get():
            self.current_data['total_score'] = 0
            self.current_data['legacy_obj_score'] = 0
            for item in self.current_data.get('details', []):
                item['score'] = 0
        else:
            details = self.current_data.get('details', [])
            sub_sum = sum(x.get('score', 0) for x in details)
            legacy_obj = self.current_data.get('legacy_obj_score', 0)
            
            if not details:
                 self.current_data['total_score'] = legacy_obj
            else:
                 has_obj = any("客观" in x.get('type', '') for x in details)
                 if has_obj:
                     self.current_data['total_score'] = sub_sum
                 else:
                     self.current_data['total_score'] = sub_sum + legacy_obj
        
        self.save_to_disk()
        return True

    def next_step(self):
        if not self.save_current_step(): return
        if self.current_step_index < len(self.steps) - 1:
            self.current_step_index += 1
            self.load_step_ui()
        else:
            self.next_student()

    def prev_step(self):
        if self.current_step_index > 0:
            self.current_step_index -= 1
            self.load_step_ui()
        else:
            self.prev_student()

    # --- Image Logic ---
    def zoom_in(self):
        if self.scale < 5.0:
            self.scale *= 1.2
            self.redraw_image()
            
    def zoom_out(self):
        if self.scale > 0.1:
            self.scale /= 1.2
            self.redraw_image()
            
    def reset_zoom(self):
        self.scale = 0.27
        self.pan_x = 0
        self.pan_y = 0
        self.redraw_image()
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        
    def scroll_to_right(self):
        self.canvas.xview_moveto(1.0)

    def scroll_to_left(self):
        self.canvas.xview_moveto(0.0)

    def redraw_image(self):
        if not self.current_image: return
        
        # Update Label
        if hasattr(self, 'lbl_zoom'):
            self.lbl_zoom.configure(text=f"{int(self.scale * 100)}%")
        
        w, h = self.current_image.size
        new_w = int(w * self.scale)
        new_h = int(h * self.scale)
        
        img_resized = self.current_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.photo_image = ImageTk.PhotoImage(img_resized)
        
        self.canvas.delete("all")
        self.canvas.config(scrollregion=(0, 0, new_w, new_h))
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo_image)

    def show_placeholder(self, text):
        self.current_image = None
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        self.canvas.create_text(w//2, h//2, text=text, fill="white", font=("Arial", 16))

    def on_mouse_down(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def on_mouse_drag(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def on_mouse_wheel(self, event):
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def filter_student_list(self, event=None):
        filter_text = self.entry_filter.get().lower()
        if not filter_text:
            self.combo_student.configure(values=self.full_student_list)
            return
            
        filtered = [s for s in self.full_student_list if filter_text in s.lower()]
        self.combo_student.configure(values=filtered)
        if filtered:
            self.combo_student.set(filtered[0])

    def trigger_regrade(self):
        # Call the parent app's regrade method
        if hasattr(self, 'parent_app') and hasattr(self.parent_app, 'regrade_single_file'):
            current_file = self.image_files[self.current_index]
            img_path = os.path.join(self.exam_folder, current_file)
            
            # Show loading
            self.btn_regrade = self.focus_get() # Hack to find button if needed, or just use direct ref if saved
            # Ideally we should disable the button
            
            def run_regrade():
                success, msg = self.parent_app.regrade_single_file(img_path)
                if success:
                    self.after(0, lambda: messagebox.showinfo(self.t("title_success"), self.t("msg_regrade_success")))
                    self.after(0, self.load_current_student)
                else:
                    self.after(0, lambda: messagebox.showerror(self.t("title_error"), self.t("msg_regrade_failed", error=msg)))
            
            threading.Thread(target=run_regrade, daemon=True).start()
        else:
            messagebox.showerror(self.t("title_error"), self.t("msg_regrade_unavailable"))

    # --- Helper for Obj Count Change ---
    def on_obj_count_change(self, choice):
        try:
            count = int(choice)
            score = count * 3
            self.var_obj_score.set(str(score))
        except: pass

    def on_obj_score_change(self, event=None):
        # Optional: Reverse update count if score matches a multiple of 3
        try:
            score = int(self.entry_obj_score.get())
            if score % 3 == 0:
                count = score // 3
                if 0 <= count <= 16:
                    self.var_obj_count.set(str(count))
        except: pass

    def save_to_disk(self):
        if not self.current_data: return
        
        self.update_score_display()
        
        # 1. Save to JSON
        room = str(self.current_data.get('db_student_info', {}).get('room', '未知'))
        seat = str(self.current_data.get('db_student_info', {}).get('seat', '未知'))
        json_name = f"{room}-{seat}.json"
        json_path = os.path.join(self.reports_dir, json_name)
        md_path = os.path.join(self.reports_dir, f"{room}-{seat}.md")
        
        # Increment Review Count
        current_count = self.current_data.get('review_count', 0)
        self.current_data['review_count'] = current_count + 1
        
        # Update Absence (store in English for data consistency)
        is_confirmed = self.chk_absence_var.get()
        self.current_data['confirm_absence'] = 'Yes' if is_confirmed else ''
        # self.current_data['缺考标记'] = '是' if is_absent else '' # Don't overwrite auto-detection
        
        # --- Calculate Diff & Update Logs ---
        if not hasattr(self, 'original_data'):
             self.original_data = copy.deepcopy(self.current_data)
             
        changes = []
        
        # Check Total Score
        old_score = self.original_data.get('total_score', 0)
        new_score = self.current_data.get('total_score', 0)
        if old_score != new_score:
            changes.append(f"Total Score: {old_score} -> {new_score}")
            
        # Check Confirm Absence (always log in English for data consistency)
        old_abs = self.original_data.get('confirm_absence', '')
        new_abs = self.current_data.get('confirm_absence', '')
        if old_abs != new_abs:
            changes.append(f"Confirm Absence: '{old_abs}' -> '{new_abs}'")
            
        # Check Question Details
        old_details = {item['question_id']: item for item in self.original_data.get('details', [])}
        new_details = {item['question_id']: item for item in self.current_data.get('details', [])}
        
        for q_id, new_item in new_details.items():
            old_item = old_details.get(q_id)
            if old_item:
                if old_item.get('score') != new_item.get('score'):
                    changes.append(f"Q{q_id} Score: {old_item.get('score')} -> {new_item.get('score')}")
                if old_item.get('student_answer') != new_item.get('student_answer'):
                    changes.append(f"Q{q_id} Answer: {old_item.get('student_answer')} -> {new_item.get('student_answer')}")
            else:
                changes.append(f"Q{q_id} Added")
                
        # Always log confirmation if no other changes but review count increased
        if not changes:
            changes.append("Review Confirmed")
                
        if changes:
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "changes": changes,
                "user": "Reviewer" # Placeholder for future user auth
            }
            if 'review_logs' not in self.current_data:
                self.current_data['review_logs'] = []
            self.current_data['review_logs'].append(log_entry)
            
            # Update original_data for next save
            self.original_data = copy.deepcopy(self.current_data)
            
        # ------------------------------------
        
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self.current_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving JSON: {e}")
        
        # 2. Regenerate Markdown file
        self.update_markdown_file(md_path)
        
        # 3. Update CSV row directly
        self.update_csv_row()
            
    def update_markdown_file(self, md_path):
        """Regenerate markdown file from current data"""
        if not self.current_data: return
        
        try:
            # Use parent's generate_report_content if available
            if hasattr(self.parent_app, 'generate_report_content'):
                db_info = self.current_data.get('db_student_info', {})
                md_content, _, _, _, _ = self.parent_app.generate_report_content(self.current_data, db_info)
                
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
        except Exception as e:
            print(f"Error updating markdown: {e}")
    
    def update_csv_row(self):
        """Update specific row in CSV file"""
        import csv
        
        try:
            # Determine CSV filename based on language
            is_en = (self.parent_app.current_lang == "EN") if hasattr(self.parent_app, 'current_lang') else False
            csv_filename = "Grade_Summary.csv" if is_en else "成绩汇总表.csv"
            csv_path = os.path.join(os.path.dirname(self.reports_dir), csv_filename)
            
            if not os.path.exists(csv_path):
                # If CSV doesn't exist, use callback to generate it
                if self.on_save_callback:
                    self.on_save_callback(self.current_data)
                return
            
            # Read existing CSV
            rows = []
            headers = []
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames
                rows = list(reader)
            
            if not headers: return
            
            # Ensure new columns exist in headers
            room_key = 'Room' if is_en else '考场'
            seat_key = 'Seat' if is_en else '座号'
            total_key = 'Total Score' if is_en else '总分'
            obj_score_key = 'Objective Score' if is_en else '客观题'
            obj_correct_key = 'Objective Correct' if is_en else '客观题正确数'
            obj_total_key = 'Objective Total' if is_en else '客观题总数'
            subj_score_key = 'Subjective Score' if is_en else '主观题'
            status_key = 'Review Status' if is_en else '复审状态'
            confirm_key = 'Confirm Absence' if is_en else '确认缺考'
            
            new_keys = [status_key, confirm_key, obj_score_key, obj_correct_key, obj_total_key, subj_score_key]
            for key in new_keys:
                if key not in headers:
                    headers.append(key)
            
            # Sort Headers using shared utility
            headers = sort_csv_headers(headers)
            
            # Helper to normalize values (remove leading zeros)
            
            # Helper to normalize values (remove leading zeros)
            def normalize(val):
                try:
                    return str(int(val))
                except:
                    return str(val).strip()

            # Find row to update
            db_info = self.current_data.get('db_student_info', {})
            target_room = normalize(db_info.get('room', ''))
            target_seat = normalize(db_info.get('seat', ''))
            
            room_key = 'Room' if is_en else '考场'
            seat_key = 'Seat' if is_en else '座号'
            
            row_found = False
            for row in rows:
                csv_room = normalize(row.get(room_key, ''))
                csv_seat = normalize(row.get(seat_key, ''))
                
                if csv_room == target_room and csv_seat == target_seat:
                    # Update scores
                    row[total_key] = str(self.current_data.get('total_score', 0))
                    
                    # Calculate objective stats
                    details = self.current_data.get('details', [])
                    obj_items = [x for x in details if "客观" in x.get('type', '') or "选择" in x.get('type', '')]
                    if obj_items:
                        obj_score = sum(x.get('score', 0) for x in obj_items)
                        obj_correct = len([x for x in obj_items if x.get('score', 0) > 0])
                        obj_total = len(obj_items)
                    else:
                        obj_score = self.current_data.get('legacy_obj_score', 0)
                        obj_correct = int(obj_score / 3) if obj_score > 0 else 0
                        obj_total = 16  # Default assumption
                    
                    row[obj_score_key] = str(obj_score)
                    row[obj_correct_key] = str(obj_correct)
                    row[obj_total_key] = str(obj_total)
                    
                    # Calculate Subjective Score
                    subj_score = self.current_data.get('total_score', 0) - obj_score
                    if subj_score < 0: subj_score = 0
                    row[subj_score_key] = str(subj_score)
                    
                    # Update Review Status
                    review_count = self.current_data.get('review_count', 0)
                    if review_count == 0:
                        status_str = ""
                    elif review_count == 1:
                        status_str = "Reviewed" if is_en else "已复审"
                    else:
                        status_str = "Second Review" if is_en else "已二次复审"
                        
                    row[status_key] = status_str
                    
                    # Update Confirm Absence
                    is_confirmed = self.current_data.get('confirm_absence') == '是'
                    if is_confirmed:
                        row[confirm_key] = 'Confirm Absence' if is_en else '确认缺考'
                    else:
                        row[confirm_key] = ''
                    
                    # Update subjective question scores
                    for item in details:
                        if "客观" not in item.get('type', '') and "选择" not in item.get('type', ''):
                            q_id = item.get('question_id', '')
                            if q_id in headers:
                                row[q_id] = str(item.get('score', 0))
                    
                    row_found = True
                    break
            
            # Write back to CSV
            if row_found:
                # Numeric Conversion for Excel
                for r in rows:
                    for k, v in r.items():
                        # Convert Room/Seat to int to remove leading zeros
                        if k in ['Room', 'Seat', '考场', '座号']:
                            try: r[k] = int(v)
                            except: pass
                        # Convert Scores/ID to numbers
                        elif k in ['ID', '考号', 'Total Score', '总分', 'Objective Score', '客观题', 
                                   'Subjective Score', '主观题', 'Objective Correct', '客观题正确数', 
                                   'Objective Total', '客观题总数']:
                            try:
                                if str(v).isdigit(): r[k] = int(v)
                                else:
                                    val = float(v)
                                    if val.is_integer(): r[k] = int(val)
                                    else: r[k] = val
                            except: pass
                with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(rows)

            else:
                # Silent failure or log to console only if needed, but user asked to cancel debug mode
                pass
                
        except PermissionError:
            messagebox.showerror(self.t("title_error"), self.t("msg_csv_permission_error") if hasattr(self, 't') else "CSV file is open. Please close it and try again.")
        except Exception as e:
            print(f"Error updating CSV: {e}")
            messagebox.showerror(self.t("title_error"), f"Failed to update CSV: {str(e)}")
            # Fallback to callback
            if self.on_save_callback:
                self.on_save_callback(self.current_data)


    def show_review_logs(self):
        """Show popup with review logs"""
        logs = self.current_data.get('review_logs', [])
        
        if not logs:
            messagebox.showinfo("Review Logs", "No review history found.")
            return
            
        # Helper for translation
        import re
        def translate_log(msg):
            is_cn = self.lang == "CN"
            
            if "Review Confirmed" in msg: 
                return "复审已确认" if is_cn else "Review Confirmed"
            
            # Total Score
            m = re.match(r"Total Score: (\d+) -> (\d+)", msg)
            if m: 
                return f"总分: {m.group(1)} -> {m.group(2)}" if is_cn else f"Total Score: {m.group(1)} -> {m.group(2)}"
            
            # Confirm Absence
            m = re.match(r"Confirm Absence: '(.+)' -> '(.+)'", msg)
            if m: 
                return f"确认缺考: '{m.group(1)}' -> '{m.group(2)}'" if is_cn else f"Confirm Absence: '{m.group(1)}' -> '{m.group(2)}'"
                
            # Question Score
            m = re.match(r"Q(.+) Score: (\d+) -> (\d+)", msg)
            if m:
                qid = m.group(1)
                v1 = m.group(2)
                v2 = m.group(3)
                
                if is_cn:
                    # Try to find question type
                    q_type = "第 " + qid + " 题"
                    details = self.current_data.get('details', [])
                    for item in details:
                        if str(item.get('question_id')) == qid:
                            if "客观" in item.get('type', '') or "选择" in item.get('type', ''):
                                q_type = "客观题"
                            break
                    return f"{q_type}得分: {v1} -> {v2}"
                else:
                    return f"Q{qid} Score: {v1} -> {v2}"
            
            # Question Added
            m = re.match(r"Q(.+) Added", msg)
            if m: 
                return f"第 {m.group(1)} 题 (新增)" if is_cn else f"Q{m.group(1)} Added"
            
            # Confirm Absence (alternative pattern)
            # Match: Confirm Absence: '' -> 'Yes' or similar
            m = re.match(r"Confirm Absence: '(.*)' -> '(.+)'", msg)
            if m:
                old_val = m.group(1)
                new_val = m.group(2)
                # Translate values based on language
                if is_cn:
                    # Translate English to Chinese
                    if old_val == "Yes": old_val = "是"
                    elif old_val == "": old_val = ""
                    if new_val == "Yes": new_val = "是"
                    elif new_val == "": new_val = ""
                    return f"确认缺考: '{old_val}' -> '{new_val}'"
                else:
                    # Keep English or translate Chinese to English
                    if old_val == "是": old_val = "Yes"
                    if new_val == "是": new_val = "Yes"
                    return f"Confirm Absence: '{old_val}' -> '{new_val}'"
            
            # Also handle simpler pattern without arrows
            m = re.match(r"Confirm Absence: (.+)", msg)
            if m:
                val = m.group(1)
                # Translate values based on language
                if is_cn:
                    if val == "Yes": val = "是"
                    elif val == "": val = ""
                    return f"确认缺考: {val}"
                else:
                    if val == "是": val = "Yes"
                    elif val == "": val = "No"
                    return f"Confirm Absence: {val}"
            
            return msg
            
        # Create Popup
        top = ctk.CTkToplevel(self)
        top.title(self.t("title_review_logs"))
        top.geometry("500x400")
        
        # Title
        student_name = self.current_data.get('db_student_info', {}).get('name', 'Unknown')
        lbl_title = ctk.CTkLabel(top, text=self.t("lbl_review_logs_title", name=student_name), font=("Arial", 16, "bold"))
        lbl_title.pack(pady=10)
        
        # Scrollable Frame
        scroll = ctk.CTkScrollableFrame(top)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Populate Logs (Reverse Order)
        for i, entry in enumerate(reversed(logs)):
            frame = ctk.CTkFrame(scroll)
            frame.pack(fill="x", pady=5)
            
            ts = entry.get('timestamp', 'Unknown Time')
            user = entry.get('user', 'Unknown User')
            if user == "Reviewer": user = self.t("lbl_reviewer")
            
            lbl_header = ctk.CTkLabel(frame, text=f"[{ts}] {user}", font=("Arial", 12, "bold"), anchor="w")
            lbl_header.pack(fill="x", padx=5, pady=2)
            
            for change in entry.get('changes', []):
                display_text = translate_log(change)
                lbl_change = ctk.CTkLabel(frame, text=f"  • {display_text}", anchor="w", text_color="gray")
                lbl_change.pack(fill="x", padx=5)

    def save_progress_to_file(self):
        try:
            data = {"current_index": self.current_index}
            with open(self.progress_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error saving progress: {e}")

    def setup_global_scroll(self):
        """Bind global mousewheel events to handle scrolling based on hover"""
        # Bind to the main window (self is the Toplevel)
        self.bind("<MouseWheel>", self.on_global_mousewheel)
        # Linux support
        self.bind("<Button-4>", self.on_global_mousewheel)
        self.bind("<Button-5>", self.on_global_mousewheel)

    def on_global_mousewheel(self, event):
        # Only handle if subj_scroll exists and is visible
        if not hasattr(self, 'subj_scroll') or not self.subj_scroll.winfo_viewable():
            return

        # Check if mouse is over subj_scroll
        x, y = self.winfo_pointerxy()
        try:
            widget = self.winfo_containing(x, y)
        except Exception:
            return

        if self.is_descendant(widget, self.subj_scroll):
            try:
                canvas = self.subj_scroll._parent_canvas
                if platform.system() == "Darwin":
                    canvas.yview_scroll(int(-1 * (event.delta)), "units")
                elif event.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.yview_scroll(1, "units")
                else:
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                return "break" # Stop propagation
            except Exception:
                pass

    def is_descendant(self, widget, ancestor):
        """Check if widget is a descendant of ancestor"""
        if not widget: return False
        curr = widget
        while curr:
            if curr == ancestor: return True
            try:
                curr = curr.master
            except AttributeError:
                break
        return False

    def on_close(self):
        # Auto-save on close
        self.save_progress_to_file()
        self.destroy()
