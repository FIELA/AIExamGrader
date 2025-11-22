import customtkinter as ctk
from PIL import Image, ImageTk
import os
import json
import csv
import tkinter as tk
from tkinter import messagebox
import threading

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
        
        self.load_file_list()
        self.setup_ui()
        
        # Check for saved progress
        self.progress_file = os.path.join(self.exam_folder, "review_progress.json")
        start_index = 0
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
                            pass
            except: pass
            
        self.current_index = start_index
        
        if self.image_files:
            self.load_current_student()
        else:
            messagebox.showinfo("Info", self.t("msg_no_images"))
            self.destroy()
            
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
            self.image_files = sorted([f for f in os.listdir(self.exam_folder) if f.lower().endswith(valid_extensions)])

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
        self.setup_ui()
        self.load_current_student()

    def setup_image_mode_ui(self):
        # --- Global Layout: Action Bar (Bottom) ---
        self.action_frame = ctk.CTkFrame(self, height=50)
        self.action_frame.pack(side="bottom", fill="x", padx=5, pady=5)
        
        self.btn_back = ctk.CTkButton(self.action_frame, text=self.t("btn_back"), width=100, command=self.prev_step, fg_color="gray")
        self.btn_back.pack(side="left", padx=5, pady=10)
        
        self.lbl_counter = ctk.CTkLabel(self.action_frame, text=self.t("lbl_student_counter", index=0, total=0))
        self.lbl_counter.pack(side="left", expand=True)
        
        self.btn_mode = ctk.CTkButton(self.action_frame, text=self.t("btn_text_mode"), width=100, command=self.toggle_view_mode, fg_color="#0F766E")
        self.btn_mode.pack(side="right", padx=5)

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
        
        self.btn_zoom_out = ctk.CTkButton(self.zoom_toolbar, text="➖", width=40, command=self.zoom_out)
        self.btn_zoom_out.pack(side="left", padx=5, pady=5)
        
        self.lbl_zoom = ctk.CTkLabel(self.zoom_toolbar, text="100%", width=60)
        self.lbl_zoom.pack(side="left", padx=5)
        
        self.btn_zoom_in = ctk.CTkButton(self.zoom_toolbar, text="➕", width=40, command=self.zoom_in)
        self.btn_zoom_in.pack(side="left", padx=5, pady=5)
        
        self.btn_reset = ctk.CTkButton(self.zoom_toolbar, text="↺ Reset", width=80, command=self.reset_zoom)
        self.btn_reset.pack(side="left", padx=10, pady=5)
        
        self.btn_left = ctk.CTkButton(self.zoom_toolbar, text="⬅ Left", width=80, command=self.scroll_to_left)
        self.btn_left.pack(side="left", padx=5, pady=5)
        
        self.btn_right = ctk.CTkButton(self.zoom_toolbar, text="➡ Right", width=80, command=self.scroll_to_right)
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
        
        self.btn_back = ctk.CTkButton(self.action_frame, text=self.t("btn_back"), width=100, command=self.prev_student, fg_color="gray")
        self.btn_back.pack(side="left", padx=5, pady=10)
        
        self.lbl_counter = ctk.CTkLabel(self.action_frame, text=self.t("lbl_student_counter", index=0, total=0))
        self.lbl_counter.pack(side="left", expand=True)
        
        self.btn_confirm_all = ctk.CTkButton(self.action_frame, text=self.t("btn_confirm_next"), width=150, command=self.confirm_all_and_next, fg_color="#106A38")
        self.btn_confirm_all.pack(side="right", padx=20, pady=10)
        
        self.btn_mode = ctk.CTkButton(self.action_frame, text=self.t("btn_image_mode"), width=100, command=self.toggle_view_mode, fg_color="#0F766E")
        self.btn_mode.pack(side="right", padx=5)

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
        
        self.subj_scroll = ctk.CTkScrollableFrame(self.right_panel, label_text="Subjective Review")
        self.subj_scroll.pack(fill="both", expand=True, padx=5, pady=5)

    # --- Navigation Methods ---
    def next_student(self):
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self.load_current_student()
        else:
            messagebox.showinfo("Done", self.t("msg_all_reviewed"))
            self.destroy()
            
    def prev_student(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_student()
        else:
            messagebox.showinfo("Info", self.t("msg_first_student"))

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
        self.lbl_counter.configure(text=f"Student {self.current_index + 1} / {len(self.image_files)}")
        
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
            csv_path = os.path.join(self.exam_folder, "成绩汇总表.csv")
            if os.path.exists(csv_path):
                try:
                    with open(csv_path, 'r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if str(row.get('考场')) == room and str(row.get('座号')) == seat:
                                try: csv_score = float(row.get('总分', 0))
                                except: pass
                                try: csv_obj_score = float(row.get('客观题', 0))
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
            
        # 3. Load Report Text
        md_name = f"{room}-{seat}.md"
        md_path = os.path.join(self.reports_dir, md_name)
        if os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                self.report_textbox.delete("1.0", "end")
                self.report_textbox.insert("1.0", f.read())
        else:
            self.report_textbox.delete("1.0", "end")
            self.report_textbox.insert("1.0", "No Report Generated")

        # 4. Generate Steps & Load UI
        self.generate_steps()
        
        if self.view_mode == 'image':
            self.current_step_index = 0
            self.load_step_ui()
        else:
            self.load_no_image_ui()

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
        self.entry_filter = ctk.CTkEntry(parent, placeholder_text="Type to search...")
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
        self.combo_student.set(current_val)
        self.combo_student.pack(anchor="w", pady=5)
        
        # --- Re-grade Button ---
        ctk.CTkButton(parent, text=self.t("btn_regrade"), fg_color="#7C3AED", command=self.trigger_regrade).pack(anchor="w", pady=10)
        
        if show_buttons:
            self.add_step_buttons(parent)

    def render_obj_step(self, parent, show_buttons=True):
        details = self.current_data.get('details', [])
        obj_items = [x for x in details if "客观" in x.get('type', '') or "选择" in x.get('type', '')]
        
        if obj_items:
            obj_score = sum(x.get('score', 0) for x in obj_items)
            obj_correct = len([x for x in obj_items if x.get('score', 0) > 0])
        else:
            obj_score = self.current_data.get('legacy_obj_score', 0)
            # Estimate correct count from score (assuming 3 pts per Q)
            obj_correct = int(obj_score / 3)
        
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x")
        
        # --- Logic: 16 Qs * 3 Pts ---
        ctk.CTkLabel(frame, text=self.t("lbl_correct_count")).pack(side="left")
        
        self.var_obj_count = tk.StringVar(value=str(obj_correct))
        self.combo_obj_count = ctk.CTkComboBox(frame, values=[str(i) for i in range(17)], width=70, variable=self.var_obj_count, command=self.on_obj_count_change)
        self.combo_obj_count.pack(side="left", padx=10)
        
        ctk.CTkLabel(frame, text=self.t("lbl_total_score")).pack(side="left", padx=(20, 0))
        
        self.var_obj_score = tk.StringVar(value=str(obj_score))
        self.entry_obj_score = ctk.CTkEntry(frame, width=60, textvariable=self.var_obj_score)
        self.entry_obj_score.pack(side="left", padx=10)
        
        # Bind Score Entry to update Count
        self.entry_obj_score.bind("<KeyRelease>", self.on_obj_score_change)
        
        if show_buttons:
            self.add_step_buttons(parent)

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
        # 1. Save Info
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
                    messagebox.showerror("Error", self.t("msg_score_error", qid=q_id, max=max_s))
                    return
                if val.is_integer(): val = int(val)
                
                for item in self.current_data.get('details', []):
                    if item.get('question_id') == q_id:
                        item['score'] = val
            except: return

        # 4. Recalculate Total
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
                        messagebox.showerror("Error", self.t("msg_score_error", qid=q_id, max=max_s))
                        return False
                    if val.is_integer(): val = int(val)
                    for item in self.current_data.get('details', []):
                        if item.get('question_id') == q_id:
                            item['score'] = val
                except: return False

        # Recalculate Total Score
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
                    self.after(0, lambda: messagebox.showinfo("Success", "Regrade complete! Reloading..."))
                    self.after(0, self.load_current_student)
                else:
                    self.after(0, lambda: messagebox.showerror("Error", f"Regrade failed: {msg}"))
            
            threading.Thread(target=run_regrade, daemon=True).start()
        else:
            messagebox.showerror("Error", "Regrade functionality not available.")

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
        
        # 1. Save to JSON
        room = str(self.current_data.get('db_student_info', {}).get('room', '未知'))
        seat = str(self.current_data.get('db_student_info', {}).get('seat', '未知'))
        json_name = f"{room}-{seat}.json"
        json_path = os.path.join(self.reports_dir, json_name)
        
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self.current_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving JSON: {e}")
            
        # 2. Update CSV (via callback)
        if self.on_save_callback:
            self.on_save_callback(self.current_data)

    def save_progress_to_file(self):
        try:
            data = {"current_index": self.current_index}
            with open(self.progress_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error saving progress: {e}")

    def on_close(self):
        # Auto-save on close
        self.save_progress_to_file()
        self.destroy()
