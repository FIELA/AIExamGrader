import customtkinter as ctk
import json
import tkinter as tk
from tkinter import messagebox

class StandardAnswerReviewDialog(ctk.CTkToplevel):
    def __init__(self, parent, initial_json, report_text, on_confirm):
        super().__init__(parent)
        self.on_confirm = on_confirm
        self.result_json = None
        
        self.title("标准答案确认 (Standard Answer Review)")
        self.geometry("800x600")
        
        # Make it modal
        self.transient(parent)
        self.grab_set()
        
        # Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # 1. Report Section
        self.lbl_report = ctk.CTkLabel(self, text="一致性分析报告 (Consistency Report):", font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_report.grid(row=0, column=0, sticky="w", padx=20, pady=(20, 5))
        
        self.txt_report = ctk.CTkTextbox(self, height=100)
        self.txt_report.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.txt_report.insert("1.0", report_text)
        self.txt_report.configure(state="disabled")
        
        # 2. JSON Editor Section
        self.lbl_json = ctk.CTkLabel(self, text="最终标准答案 (Final Answer Key - Editable):", font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_json.grid(row=2, column=0, sticky="w", padx=20, pady=(10, 5))
        
        self.txt_json = ctk.CTkTextbox(self)
        self.txt_json.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 20))
        
        # Pre-fill JSON
        formatted_json = json.dumps(initial_json, ensure_ascii=False, indent=4)
        self.txt_json.insert("1.0", formatted_json)
        
        # 3. Buttons
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.grid(row=4, column=0, sticky="ew", padx=20, pady=20)
        
        self.btn_confirm = ctk.CTkButton(self.btn_frame, text="确认并保存 (Confirm & Save)", command=self.confirm, fg_color="green")
        self.btn_confirm.pack(side="right", padx=10)
        
        self.btn_cancel = ctk.CTkButton(self.btn_frame, text="取消 (Cancel)", command=self.cancel, fg_color="gray")
        self.btn_cancel.pack(side="right", padx=10)
        
        self.protocol("WM_DELETE_WINDOW", self.cancel)

    def confirm(self):
        try:
            content = self.txt_json.get("1.0", "end").strip()
            self.result_json = json.loads(content)
            if self.on_confirm:
                self.on_confirm(self.result_json)
            self.destroy()
        except json.JSONDecodeError as e:
            messagebox.showerror("JSON Error", f"Invalid JSON format: {e}")

    def cancel(self):
        self.destroy()
