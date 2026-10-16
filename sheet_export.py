# Copyright (c) 2025 JASim. Licensed under NCEL-Strict License v2.0.
# STRICT NON-COMMERCIAL USE ONLY. No AI/ML training, fine-tuning, or public distribution of Derivative Works.
# Modifications may only be shared as Patch Files.
# Public forks allowed solely for PRs (delete within 14 days after PR merged, rejected, or closed).
# Commercial licensing inquiries: nicofiela@outlook.com. See LICENSE file for full terms.

"""Name graded answer sheets after their students for export; the original images are never touched."""

import json
import os
import re

from report_files import record_image_name
from student_manager import REVIEW_METHODS

# Name formats offered when exporting
NAME_PATTERNS = {
    'class_name': '{班级}-{姓名}',
    'class_name_id': '{班级}-{姓名}-{考号}',
    'id_name': '{考号}-{姓名}',
    'room_seat_name': '{考场}-{座号}-{姓名}',
}
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg')


def identity_confirmed(data):
    """The sheet's student is known and was either matched with certainty or confirmed in review."""
    student = data.get('db_student_info') or {}
    if student.get('name') in (None, '', '未知'):
        return False
    method = (data.get('student_match') or {}).get('method')
    return method not in REVIEW_METHODS or data.get('review_count', 0) > 0


def sheet_name(student, pattern):
    """File name without extension for a student, e.g. 701-张三; separators left by empty fields are dropped."""
    fields = {'班级': student.get('class'), '姓名': student.get('name'), '考号': student.get('id'),
              '考场': student.get('room'), '座号': student.get('seat')}
    name = pattern.format(**{k: '' if v in (None, '未知') else str(v).strip() for k, v in fields.items()})
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name)  # Not allowed in file names
    return re.sub(r'([-_\s])[-_\s]+', r'\1', name).strip('-_ .')


def find_graded_sheets(reports_dir, image_dirs):
    """(report data, image path or None) for every report; the image is looked for in image_dirs."""
    sheets = []
    if not reports_dir or not os.path.isdir(reports_dir):
        return sheets
    for report in sorted(os.listdir(reports_dir)):
        if not report.endswith('.json'):
            continue
        try:
            with open(os.path.join(reports_dir, report), 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        image = record_image_name(data)
        # Older reports without that record are named after their image
        names = [image] if image else [os.path.splitext(report)[0] + ext for ext in IMAGE_EXTENSIONS]
        path = next((os.path.join(d, n) for n in names for d in image_dirs if d and os.path.isfile(os.path.join(d, n))), None)
        sheets.append((data, path))
    return sheets


def plan_export(sheets, pattern, check_prefix):
    """
    Export file name for each sheet that has an image: the student's name when the student is confirmed,
    otherwise '<check_prefix>-<image name>'. Repeated names get _1, _2 ... (ignoring letter case, as
    Windows and macOS do). Returns [(image path, export name, confirmed, report data)].
    """
    plan, used = [], set()
    for data, path in sheets:
        if not path:
            continue
        stem, ext = os.path.splitext(os.path.basename(path))
        confirmed = identity_confirmed(data)
        base = sheet_name(data.get('db_student_info') or {}, pattern) if confirmed else ''
        if not base:
            confirmed, base = False, f"{check_prefix}-{stem}"
        name, counter = f"{base}{ext}", 1
        while name.lower() in used:
            name = f"{base}_{counter}{ext}"
            counter += 1
        used.add(name.lower())
        plan.append((path, name, confirmed, data))
    return plan
