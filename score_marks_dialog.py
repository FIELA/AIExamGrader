# Copyright (c) 2025 JASim. Licensed under NCEL-Strict License v2.0.
# STRICT NON-COMMERCIAL USE ONLY. No AI/ML training, fine-tuning, or public distribution of Derivative Works.
# Modifications may only be shared as Patch Files.
# Public forks allowed solely for PRs (delete within 14 days after PR merged, rejected, or closed).
# Commercial licensing inquiries: nicofiela@outlook.com. See LICENSE file for full terms.

"""
Where each score is written, set once per exam on a sample scan (see score_marks). The marks are shown as the sheets
will get them: the same tables (question number, then the longest score it may show), font and size.
"""

import copy
import os
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

import score_marks as sm
from theme import Theme

CHAIN, MANAGE = 'chain', 'manage'  # Opened before grading starts, or from the main window
INK_WARNING = 0.12  # Share of dark pixels under a table above which it may cover writing (a printed line is less)
DEFAULT_ANCHOR = {sm.TOTAL: 'mm'}  # Others: the score ends where it is placed, left of the question number


def compact_ids(ids):
    """1–16 for consecutive numbers, else the ids themselves."""
    if ids and all(q.isdigit() for q in ids):
        numbers = sorted(int(q) for q in ids)
        if numbers == list(range(numbers[0], numbers[-1] + 1)) and len(numbers) > 2:
            return f"{numbers[0]}–{numbers[-1]}"
    return '、'.join(ids)


class ScoreMarksDialog(ctk.CTkToplevel):
    """
    Pick a position on the right, then click on the sample to place it; drag a red score to move it. on_done(action,
    template) runs after the window closes; action is enable, draft, disable or skip (CHAIN), or enable, draft,
    pause, restore or close (MANAGE).
    """

    def __init__(self, master, t, template, samples, mode, on_done, max_scores=None, locate=None, ui_after=None):
        super().__init__(master)
        self.t = t
        self.template = copy.deepcopy(template)
        self.template.setdefault('marks', {})
        self.samples = list(samples)
        self.mode = mode
        self.on_done = on_done
        self.max_scores = max_scores or {}
        self.locate = locate
        self.ui_after = ui_after or (lambda delay, callback, *args: self.after(delay, callback, *args))
        self.sample_index = 0
        self.sample = self.gray = None
        self.size = (1, 1)
        self.scale = 0.25
        self.selected = None
        self.drag = None  # (mark id, offset x, offset y) while a mark is dragged
        self.panning = False
        self.candidates = {}  # Positions the model suggested, for resetting
        self.done = False
        self.photos = {}
        self.fonts = {}
        self.tags = {}  # Mark id -> canvas tag: Tk reads parentheses in tags as search expressions, so 17(1) cannot be one
        self.font_path, self.font_missing = sm.font_problem(self.template['lang'])

        self.title(t("title_score_marks"))
        self.geometry("1320x860")
        self.minsize(1000, 640)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.build()
        self.protocol("WM_DELETE_WINDOW", lambda: self.finish('skip' if mode == CHAIN else 'close'))
        self.select(next(iter(sm.unplaced_marks(self.template)), None))
        if self.samples:
            self.load_sample(0)
        else:
            self.lbl_warn.configure(text=t("msg_marks_no_samples"))
        self.transient(master)
        self._jobs = [self.after(80, self.fit), self.after(120, self._grab)]

    def destroy(self):
        for job in getattr(self, '_jobs', []):
            try:
                self.after_cancel(job)  # Not to run on a closed window
            except tk.TclError:
                pass
        super().destroy()

    def _grab(self):
        try:
            self.grab_set()
        except tk.TclError:
            pass  # Not shown yet

    # --- Layout ---

    def build(self):
        t = self.t
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(left, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(bar, text="−", width=32, command=lambda: self.zoom(1 / 1.25)).pack(side="left")
        ctk.CTkButton(bar, text="+", width=32, command=lambda: self.zoom(1.25)).pack(side="left", padx=4)
        ctk.CTkButton(bar, text=t("btn_marks_fit"), width=60, command=self.fit).pack(side="left")
        ctk.CTkButton(bar, text=t("btn_marks_prev"), width=90,
                      command=lambda: self.load_sample(self.sample_index - 1)).pack(side="left", padx=(16, 4))
        self.lbl_sample = ctk.CTkLabel(bar, text="")
        self.lbl_sample.pack(side="left")
        ctk.CTkButton(bar, text=t("btn_marks_next"), width=90,
                      command=lambda: self.load_sample(self.sample_index + 1)).pack(side="left", padx=4)
        self.btn_locate = self.btn_reset = None
        if self.locate:
            self.btn_reset = ctk.CTkButton(bar, text=t("btn_marks_reset"), width=120, state="disabled",
                                           command=self.reset_candidates)
            self.btn_reset.pack(side="right")
            self.btn_locate = ctk.CTkButton(bar, text=t("btn_marks_locate"), width=110, command=self.run_locate)
            self.btn_locate.pack(side="right", padx=4)

        frame = tk.Frame(left)
        frame.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(frame, bg="#4B5563", highlightthickness=0)
        xs = tk.Scrollbar(frame, orient="horizontal", command=self.canvas.xview)
        ys = tk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<MouseWheel>", lambda e: self.zoom(1.1 if e.delta > 0 else 1 / 1.1))
        self.canvas.bind("<Button-4>", lambda e: self.zoom(1.1))
        self.canvas.bind("<Button-5>", lambda e: self.zoom(1 / 1.1))

        side = ctk.CTkFrame(self)
        side.grid(row=0, column=1, sticky="ns", padx=(5, 10), pady=10)
        actions = ctk.CTkFrame(side, fg_color="transparent")
        actions.pack(side="bottom", fill="x", padx=12, pady=12)
        enable_text = t("btn_marks_enable") if self.mode == CHAIN else t("btn_marks_save_write")
        self.btn_enable = ctk.CTkButton(actions, text=enable_text, fg_color=Theme.SECONDARY,
                                        hover_color=Theme.SECONDARY_HOVER, command=lambda: self.finish('enable'))
        self.btn_enable.pack(fill="x", pady=(0, 6))
        row = ctk.CTkFrame(actions, fg_color="transparent")
        row.pack(fill="x")
        muted = dict(fg_color=Theme.TEXT_MUTED_LIGHT, hover_color=Theme.TEXT_MUTED_DARK)
        ctk.CTkButton(row, text=t("btn_marks_draft"), width=104, command=lambda: self.finish('draft'), **muted).pack(side="left")
        if self.mode == CHAIN:
            ctk.CTkButton(row, text=t("btn_marks_disable"), width=104, command=lambda: self.finish('disable'),
                          **muted).pack(side="left", padx=6)
            ctk.CTkButton(row, text=t("btn_marks_skip"), width=104, command=lambda: self.finish('skip'),
                          **muted).pack(side="right")
        else:
            ctk.CTkButton(row, text=t("btn_marks_pause"), width=104, command=lambda: self.finish('pause'),
                          **muted).pack(side="left", padx=6)
            ctk.CTkButton(row, text=t("btn_close"), width=104, command=lambda: self.finish('close'),
                          **muted).pack(side="right")
            ctk.CTkButton(actions, text=t("btn_marks_restore"), fg_color=Theme.WARNING, hover_color=Theme.WARNING_HOVER,
                          command=lambda: self.finish('restore')).pack(fill="x", pady=(6, 0))

        ctk.CTkLabel(side, text=t("lbl_marks_intro"), wraplength=350, justify="left").pack(anchor="w", padx=12, pady=(12, 6))
        ctk.CTkLabel(side, text=t("lbl_marks_items"), font=("Arial", 13, "bold")).pack(anchor="w", padx=12)
        self.items_frame = ctk.CTkScrollableFrame(side, width=330, height=220)
        self.items_frame.pack(fill="x", padx=12, pady=(4, 4))
        self.lbl_objective = ctk.CTkLabel(side, text="", wraplength=350, justify="left")
        self.lbl_objective.pack(anchor="w", padx=12)
        self.lbl_source = ctk.CTkLabel(side, text="", wraplength=350, justify="left", text_color=Theme.TEXT_MUTED_LIGHT)
        self.lbl_source.pack(anchor="w", padx=12)

        edit = ctk.CTkFrame(side, fg_color="transparent")
        edit.pack(fill="x", padx=12, pady=(6, 2))
        self.entry_qid = ctk.CTkEntry(edit, width=80, placeholder_text=t("lbl_marks_qid"))
        self.entry_qid.pack(side="left")
        ctk.CTkButton(edit, text=t("btn_marks_add_question"), width=78,
                      command=lambda: self.add_item('subjective')).pack(side="left", padx=3)
        ctk.CTkButton(edit, text=t("btn_marks_add_objective"), width=78,
                      command=lambda: self.add_item('objective')).pack(side="left")
        ctk.CTkButton(edit, text=t("btn_marks_remove"), width=60, command=self.remove_item,
                      **muted).pack(side="left", padx=3)

        for key, label, low, high in (('size_question', "lbl_marks_size_question", 0.010, 0.040),
                                      ('size_total', "lbl_marks_size_total", 0.015, 0.060)):
            row = ctk.CTkFrame(side, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=(8, 0))
            ctk.CTkLabel(row, text=t(label), width=80, anchor="w").pack(side="left")
            slider = ctk.CTkSlider(row, from_=low, to=high, command=lambda v, k=key: self.set_size(k, v))
            slider.set(min(high, max(low, self.template[key])))
            slider.pack(side="left", fill="x", expand=True)
            setattr(self, f"slider_{key}", slider)

        row = ctk.CTkFrame(side, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(8, 0))
        ctk.CTkLabel(row, text=t("lbl_marks_lang"), width=80, anchor="w").pack(side="left")
        self.lang_switch = ctk.CTkSegmentedButton(row, values=["中文", "English"], command=self.set_lang)
        self.lang_switch.set("中文" if self.template['lang'] == 'CN' else "English")
        self.lang_switch.pack(side="left")

        self.lbl_warn = ctk.CTkLabel(side, text="", wraplength=350, justify="left", text_color=Theme.WARNING)
        self.lbl_warn.pack(anchor="w", padx=12, pady=(10, 0))

    # --- Sample and drawing ---

    def load_sample(self, index):
        if not self.samples:
            return
        self.sample_index = index % len(self.samples)
        path = self.samples[self.sample_index]
        try:
            image, _, _ = sm.open_normalized(path)
        except (OSError, ValueError) as e:
            self.lbl_warn.configure(text=str(e))
            return
        self.sample, self.gray = image.convert('RGB'), image.convert('L')
        self.size = self.sample.size
        self.lbl_sample.configure(text=self.t("lbl_marks_sample", name=os.path.basename(path),
                                              index=self.sample_index + 1, total=len(self.samples)))
        self.redraw()

    def fit(self):
        if not self.winfo_exists() or not self.sample:
            return
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w > 1 and h > 1:
            self.scale = min(w / self.size[0], h / self.size[1])
        self.redraw()

    def zoom(self, factor):
        self.scale = min(4.0, max(0.05, self.scale * factor))
        self.redraw()

    def redraw(self):
        if not self.sample:
            return
        width, height = max(1, int(self.size[0] * self.scale)), max(1, int(self.size[1] * self.scale))
        self.bg_photo = ImageTk.PhotoImage(self.sample.resize((width, height), Image.Resampling.BILINEAR))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_photo, tags=("bg",))
        self.canvas.configure(scrollregion=(0, 0, width, height))
        self.draw_marks()

    def font_at(self, px):
        if px not in self.fonts:
            self.fonts[px] = sm.load_font(self.font_path, px)
        return self.fonts[px]

    def label(self, mark_id):
        if mark_id == sm.TOTAL:
            return self.t("mark_label_total")
        if mark_id == sm.OBJECTIVE:
            return self.t("mark_label_objective")
        return (self.template['items'].get('labels') or {}).get(mark_id, mark_id)

    def boxes(self):
        texts = {m: v for m, v in sm.preview_texts(self.template, self.max_scores).items() if m in sm.required_marks(self.template)}
        return sm.mark_boxes(self.template, texts, self.size, self.font_path)

    def draw_marks(self):
        for tag in ("mark", "frame"):
            self.canvas.delete(tag)
        self.photos = {}
        boxes = self.boxes() if self.sample else []
        flagged = self.check(boxes)
        color = tuple(self.template['color'])
        for box in boxes:
            # As the sheets get it: the same table at the scale shown, where the sheets have it (kept inside the image)
            size = max(6, round(box.px * self.scale))
            image = sm.table_image(box.cells, size, self.font_at(size), color)
            self.photos[box.mark_id] = ImageTk.PhotoImage(image)
            left, top = box.box[0] * self.scale, box.box[1] * self.scale
            right, bottom = left + image.size[0], top + image.size[1]
            tag = self.tag_for(box.mark_id)
            self.canvas.create_image(left, top, anchor="nw", image=self.photos[box.mark_id], tags=("mark", tag))
            if box.mark_id == self.selected or box.mark_id in flagged:
                self.canvas.create_rectangle(left - 2, top - 2, right + 2, bottom + 2, width=2,
                                             outline="#2563EB" if box.mark_id == self.selected else Theme.WARNING,
                                             tags=("frame", tag))
        self.refresh_items()

    def tag_for(self, mark_id):
        return self.tags.setdefault(mark_id, f"m{len(self.tags)}")

    def check(self, boxes):
        """Warnings about the current sample; returns the marks to outline."""
        t, notes, flagged = self.t, [], set()
        unplaced = sm.unplaced_marks(self.template)
        if unplaced:
            notes.append(t("lbl_marks_warn_unplaced", ids='、'.join(self.label(m) for m in unplaced)))
        outside, overlaps = sm.layout_problems(boxes, self.size)
        if outside:
            notes.append(t("lbl_marks_warn_outside", ids='、'.join(self.label(m) for m in outside)))
            flagged.update(outside)
        if overlaps:
            notes.append(t("lbl_marks_warn_overlap", pairs='、'.join(f"{self.label(a)}/{self.label(b)}" for a, b in overlaps)))
            flagged.update(m for pair in overlaps for m in pair)
        inky = [b.mark_id for b in boxes if self.gray is not None and sm.ink_ratio(self.gray, b.box) > INK_WARNING]
        if inky:
            notes.append(t("lbl_marks_warn_ink", ids='、'.join(self.label(m) for m in inky)))
            flagged.update(inky)
        difference = self.template.get('pending_diff')
        if difference:
            notes.append(t("lbl_marks_warn_diff", only_template='、'.join(difference.get('only_template') or []) or '-',
                           only_report='、'.join(difference.get('only_report') or []) or '-'))
        if self.font_missing:
            notes.append(t("msg_marks_font_missing"))
        self.lbl_warn.configure(text='\n'.join(notes))
        return flagged

    def refresh_items(self):
        for widget in self.items_frame.winfo_children():
            widget.destroy()
        for mark_id in sm.required_marks(self.template):
            placed = mark_id in self.template['marks']
            text = self.label(mark_id) + ('' if placed else '  ' + self.t("lbl_marks_unplaced"))
            chosen = mark_id == self.selected
            ctk.CTkButton(self.items_frame, text=text, anchor="w", height=26,
                          fg_color=Theme.PRIMARY if chosen else ("gray85", "gray25"),
                          text_color="white" if chosen else (("gray10", "gray90") if placed else Theme.WARNING),
                          command=lambda m=mark_id: self.select(m)).pack(fill="x", pady=1)
        items = self.template['items']
        self.lbl_objective.configure(text=self.t("lbl_marks_objective_ids", ids=compact_ids(items.get('objective') or []) or '-'))
        self.lbl_source.configure(text=self.t("lbl_marks_source_key" if items.get('source') == 'answer_key'
                                              else "lbl_marks_source_reports"))

    # --- Editing ---

    def select(self, mark_id):
        self.selected = mark_id
        if self.sample:
            self.draw_marks()
        else:
            self.refresh_items()

    def canvas_point(self, event):
        return self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

    def mark_at(self, x, y):
        marks = {tag: mark_id for mark_id, tag in self.tags.items()}
        for item in reversed(self.canvas.find_overlapping(x - 1, y - 1, x + 1, y + 1)):
            for tag in self.canvas.gettags(item):
                if tag in marks and marks[tag] in self.template['marks']:
                    return marks[tag]
        return None

    def place(self, mark_id, x, y):
        """Put mark_id's anchor at canvas point (x, y)."""
        width, height = self.size[0] * self.scale, self.size[1] * self.scale
        pos = self.template['marks'].get(mark_id) or {'anchor': DEFAULT_ANCHOR.get(mark_id, 'rm')}
        pos = dict(pos, x=round(min(1.0, max(0.0, x / width)), 5), y=round(min(1.0, max(0.0, y / height)), 5))
        self.template['marks'][mark_id] = pos

    def on_press(self, event):
        if not self.sample:
            return
        x, y = self.canvas_point(event)
        mark_id = self.mark_at(x, y)
        if mark_id:
            pos = self.template['marks'][mark_id]
            self.drag = (mark_id, x - pos['x'] * self.size[0] * self.scale, y - pos['y'] * self.size[1] * self.scale)
            if mark_id != self.selected:
                self.select(mark_id)
            return
        if self.selected and self.selected not in self.template['marks']:
            self.place(self.selected, x, y)
            self.select(next(iter(sm.unplaced_marks(self.template)), self.selected))
            return
        self.panning = True
        self.canvas.scan_mark(event.x, event.y)

    def on_motion(self, event):
        if self.drag:
            mark_id, dx, dy = self.drag
            x, y = self.canvas_point(event)
            before = self.template['marks'][mark_id]
            old = (before['x'] * self.size[0] * self.scale, before['y'] * self.size[1] * self.scale)
            self.place(mark_id, x - dx, y - dy)
            after = self.template['marks'][mark_id]
            self.canvas.move(self.tag_for(mark_id), after['x'] * self.size[0] * self.scale - old[0],
                             after['y'] * self.size[1] * self.scale - old[1])
        elif self.panning:
            self.canvas.scan_dragto(event.x, event.y, gain=1)

    def on_release(self, event):
        if self.drag:
            self.drag = None
            self.draw_marks()  # Checks and outlines follow the new position
        self.panning = False

    def add_item(self, kind):
        """Add the typed question number as a sub-question or a multiple-choice question (moving it if listed)."""
        raw = self.entry_qid.get().strip()
        qid = sm.normalize_qid(raw)
        if not qid or qid in (sm.TOTAL, sm.OBJECTIVE):
            return
        items = self.template['items']
        for other in ('objective', 'subjective'):
            if qid in items[other]:
                items[other].remove(qid)
        items[kind] = sorted(items[kind] + [qid], key=sm.qid_sort_key)
        items.setdefault('labels', {})[qid] = raw
        if kind == 'objective':
            self.template['marks'].pop(qid, None)
        self.entry_qid.delete(0, "end")
        self.template.pop('pending_diff', None)
        self.select(qid if kind == 'subjective' else self.selected)

    def remove_item(self):
        """Remove the typed question number, or else the selected sub-question, from the list."""
        qid = sm.normalize_qid(self.entry_qid.get().strip()) or (self.selected if self.selected not in (sm.TOTAL, sm.OBJECTIVE) else '')
        if not qid:
            return
        items = self.template['items']
        for kind in ('objective', 'subjective'):
            if qid in items[kind]:
                items[kind].remove(qid)
        self.template['marks'].pop(qid, None)
        if not items['objective']:
            self.template['marks'].pop(sm.OBJECTIVE, None)
        self.entry_qid.delete(0, "end")
        self.template.pop('pending_diff', None)
        self.select(None if self.selected == qid else self.selected)

    def set_size(self, key, value):
        self.template[key] = round(float(value), 4)
        if self.sample:
            self.draw_marks()

    def set_lang(self, value):
        self.template['lang'] = 'CN' if value == "中文" else 'EN'
        self.font_path, self.font_missing = sm.font_problem(self.template['lang'])
        self.fonts = {}
        if self.sample:
            self.draw_marks()

    # --- Model suggestion ---

    def run_locate(self):
        if not (self.locate and self.samples):
            return
        self.btn_locate.configure(state="disabled", text=self.t("msg_marks_locating"))
        path, template, size, font_path = self.samples[self.sample_index], copy.deepcopy(self.template), self.size, self.font_path

        def work():
            try:
                boxes = self.locate(path, template)
                result = (sm.anchors_from_boxes(template, boxes, size, font_path), None)
            except Exception as e:  # Shown to the teacher, who can still place the marks by hand
                result = (None, str(e))
            self.ui_after(0, self.located, *result)
        threading.Thread(target=work, daemon=True).start()

    def located(self, candidates, error):
        if not self.winfo_exists():
            return
        self.btn_locate.configure(state="normal", text=self.t("btn_marks_locate"))
        if error:
            messagebox.showwarning(self.t("title_score_marks"), self.t("msg_marks_locate_failed", error=error), parent=self)
            return
        required = sm.required_marks(self.template)
        self.candidates = {m: p for m, p in candidates.items() if m in required}
        for mark_id, pos in self.candidates.items():
            self.template['marks'].setdefault(mark_id, dict(pos))  # Marks placed by hand stay where they are
        self.btn_reset.configure(state="normal" if self.candidates else "disabled")
        self.select(next(iter(sm.unplaced_marks(self.template)), self.selected))
        messagebox.showinfo(self.t("title_score_marks"), self.t("msg_marks_locate_done", found=len(self.candidates),
                                                               total=len(required)), parent=self)

    def reset_candidates(self):
        for mark_id, pos in self.candidates.items():
            self.template['marks'][mark_id] = dict(pos)
        self.draw_marks()

    # --- Closing ---

    def enable_blocker(self):
        """Why the template cannot be enabled yet, or None."""
        unplaced = sm.unplaced_marks(self.template)
        if unplaced:
            return self.t("lbl_marks_warn_unplaced", ids='、'.join(self.label(m) for m in unplaced))
        if not (self.template['items']['subjective'] or self.template['items']['objective']):
            return self.t("msg_marks_no_items")
        if self.font_missing:
            return self.t("msg_marks_font_missing")
        if not self.sample:
            return self.t("msg_marks_no_samples")
        return None

    def result(self):
        template = copy.deepcopy(self.template)
        if self.sample:
            path = self.samples[self.sample_index]
            template['reference'] = {'image': os.path.basename(path), 'sha256': sm.file_sha256(path), 'size': list(self.size)}
        return template

    def finish(self, action):
        if self.done:
            return
        if action == 'enable':
            reason = self.enable_blocker()
            if reason:
                messagebox.showwarning(self.t("title_score_marks"), self.t("msg_marks_enable_blocked", reason=reason),
                                       parent=self)
                return
        self.done = True
        template = self.result()
        self.destroy()
        self.on_done(action, template)
