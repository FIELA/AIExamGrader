# Copyright (c) 2025 JASim. Licensed under NCEL-Strict License v2.0.
# STRICT NON-COMMERCIAL USE ONLY. No AI/ML training, fine-tuning, or public distribution of Derivative Works.
# Modifications may only be shared as Patch Files.
# Public forks allowed solely for PRs (delete within 14 days after PR merged, rejected, or closed).
# Commercial licensing inquiries: nicofiela@outlook.com. See LICENSE file for full terms.

"""Name graded answer sheets after their students (Class-Name) once review is done; the scans stay backed up."""

import json
import os
import re

from report_files import record_image_name
from student_manager import REVIEW_METHODS, student_key

SHEET_NAME = '{班级}-{姓名}'  # e.g. 701-张三.jpg
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg')


def identity_confirmed(data):
    """The sheet's student is known and was either matched with certainty or confirmed in review."""
    student = data.get('db_student_info') or {}
    if student.get('name') in (None, '', '未知'):
        return False
    method = (data.get('student_match') or {}).get('method')
    return method not in REVIEW_METHODS or data.get('review_count', 0) > 0


def sheet_name(student, pattern=SHEET_NAME):
    """File name without extension for a student, e.g. 701-张三; separators left by empty fields are dropped."""
    fields = {'班级': student.get('class'), '姓名': student.get('name'), '考号': student.get('id'),
              '考场': student.get('room'), '座号': student.get('seat')}
    name = pattern.format(**{k: '' if v in (None, '未知') else str(v).strip() for k, v in fields.items()})
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name)  # Not allowed in file names
    return re.sub(r'([-_\s])[-_\s]+', r'\1', name).strip('-_ .')


def original_name(data, image_name=''):
    """Name the sheet was scanned, and backed up to the original files folder, with."""
    return os.path.basename(str(data.get('original_filename') or '')) or os.path.basename(image_name)


def find_graded_sheets(reports_dir, image_dirs):
    """(report JSON path, report data, image path or None) for every report; the image is looked for in image_dirs."""
    sheets = []
    if not reports_dir or not os.path.isdir(reports_dir):
        return sheets
    for report in sorted(os.listdir(reports_dir)):
        if not report.endswith('.json'):
            continue
        json_path = os.path.join(reports_dir, report)
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        image = record_image_name(data)
        # Older reports without that record are named after their image
        names = [image] if image else [os.path.splitext(report)[0] + ext for ext in IMAGE_EXTENSIONS]
        path = next((os.path.join(d, n) for n in names for d in image_dirs if d and os.path.isfile(os.path.join(d, n))), None)
        sheets.append((json_path, data, path))
    return sheets


def students_on_several_sheets(reports_dir):
    """{student key: [(report JSON path, report data), ...]} for each known student bound to more than one report."""
    groups = {}
    for json_path, data, _ in find_graded_sheets(reports_dir, []):
        student = data.get('db_student_info') or {}
        if student.get('name') not in (None, '', '未知'):
            groups.setdefault(student_key(student), []).append((json_path, data))
    return {key: sheets for key, sheets in groups.items() if len(sheets) > 1}


def sheet_label(data, image, t):
    """A sheet in a message, with its score and whether it was reviewed, e.g. 701-张三.jpg（54 分，未复审）."""
    score = data.get('total_score', '-')
    if isinstance(score, float) and score.is_integer():
        score = int(score)
    status = t('status_reviewed') if data.get('review_count', 0) else t('status_unreviewed')
    return t('sheet_label', file=image, score=score, status=status)
