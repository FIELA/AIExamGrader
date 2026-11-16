# Copyright (c) 2025 JASim. Licensed under NCEL-Strict License v2.0.
# STRICT NON-COMMERCIAL USE ONLY. No AI/ML training, fine-tuning, or public distribution of Derivative Works.
# Modifications may only be shared as Patch Files.
# Public forks allowed solely for PRs (delete within 14 days after PR merged, rejected, or closed).
# Commercial licensing inquiries: nicofiela@outlook.com. See LICENSE file for full terms.

"""Find an exam's resources in its folder: the rubric, the answer sheet folder and the student list usually sit together."""

import os

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg')
RUBRIC_EXTENSIONS = ('.txt', '.md', '.pdf')
ROSTER_EXTENSIONS = ('.xlsx', '.csv')

# Folders grading makes in an answer sheet folder, under either language's name
EXAM_SUBFOLDERS = {
    'grading_data': ['grading_data', '阅卷数据'],
    'original_files': ['original_files', '原始文件'],
    'reports': ['reports', '阅卷报告'],
    'success': ['success', '成功归档'],
    'failed': ['failed', '失败归档'],
    'removed': ['removed', '已移除'],  # Sheets taken out of the grades in review, e.g. scanned twice
}
APP_FOLDER_NAMES = frozenset(name for names in EXAM_SUBFOLDERS.values() for name in names)
APP_FILE_NAMES = frozenset({'成绩汇总表.csv', 'Grade_Summary.csv'})  # Summaries older versions kept beside the scans


def _entries(directory):
    try:
        with os.scandir(directory) as entries:
            return sorted(entries, key=lambda entry: entry.name)
    except OSError:
        return []


def is_answer_sheet_folder(path):
    """Scans are in it, or the folders grading made in it (graded scans move into those)."""
    return any(entry.is_dir() if entry.name in APP_FOLDER_NAMES else
               entry.name.lower().endswith(IMAGE_EXTENSIONS) and entry.is_file()
               for entry in _entries(path))


def find_exam_resources(directory):
    """What in directory could be each resource: {'exam_folder': [...], 'rubric': [...], 'student_list': [...]}."""
    found = {'exam_folder': [], 'rubric': [], 'student_list': []}
    for entry in _entries(directory):
        name = entry.name
        if name.startswith(('.', '~$')) or name in APP_FOLDER_NAMES or name in APP_FILE_NAMES:
            continue  # Hidden files, Office lock files, and what grading made
        if entry.is_dir():
            if is_answer_sheet_folder(entry.path):
                found['exam_folder'].append(entry.path)
        elif name.lower().endswith(RUBRIC_EXTENSIONS):
            found['rubric'].append(entry.path)
        elif name.lower().endswith(ROSTER_EXTENSIONS):
            found['student_list'].append(entry.path)
    return found


def located_in(path, directory):
    """Whether path (a file or folder) sits directly in directory."""
    return bool(path) and os.path.dirname(os.path.realpath(path)) == os.path.realpath(directory)
