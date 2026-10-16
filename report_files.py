# Copyright (c) 2025 JASim. Licensed under NCEL-Strict License v2.0.
# STRICT NON-COMMERCIAL USE ONLY. No AI/ML training, fine-tuning, or public distribution of Derivative Works.
# Modifications may only be shared as Patch Files.
# Public forks allowed solely for PRs (delete within 14 days after PR merged, rejected, or closed).
# Commercial licensing inquiries: nicofiela@outlook.com. See LICENSE file for full terms.

"""Find and name each answer sheet's report so that two sheets never share one report file."""

import json
import os


def record_image_name(data):
    """Image a report belongs to: the renamed file if the sheet was renamed, otherwise the original file."""
    return os.path.basename(str(data.get('renamed_filename') or data.get('original_filename') or ''))


def report_owner(json_path):
    """Image recorded in a report JSON; '' for older reports without that record; None if missing or unreadable."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return record_image_name(data) if isinstance(data, dict) else None


def build_report_index(reports_dir):
    """Map each image name to the report JSON that records it."""
    index = {}
    if reports_dir and os.path.isdir(reports_dir):
        for name in sorted(os.listdir(reports_dir)):
            if name.endswith('.json'):
                path = os.path.join(reports_dir, name)
                owner = report_owner(path)
                if owner:
                    index.setdefault(owner, path)
    return index


def candidate_prefixes(student_info, image_name):
    """Report names a sheet may have: Room-Seat when known, then the image's own name."""
    room = str(student_info.get('room', '')).strip()
    seat = str(student_info.get('seat', '')).strip()
    prefixes = []
    if room and seat and '未知' not in (room, seat):
        prefixes.append(f"{room}-{seat}")
    prefixes.append(os.path.splitext(os.path.basename(image_name))[0])
    return prefixes


def find_report(reports_dir, image_name, prefixes, index=None):
    """
    Return the report JSON path for image_name, or None.
    A report that records a different image is never returned; older reports
    without that record are still found by name.
    """
    image_name = os.path.basename(image_name)
    if index is None:
        index = build_report_index(reports_dir)
    if image_name in index:
        return index[image_name]
    for prefix in prefixes:
        path = os.path.join(reports_dir, f"{prefix}.json")
        if report_owner(path) in ('', image_name):  # Also covers reports written after the index was built
            return path
    return None


def unique_report_prefix(reports_dir, prefix, image_name):
    """Return prefix, or a variant of the image's name, that does not hold another sheet's report."""
    image_name = os.path.basename(image_name)

    def free(candidate):
        return report_owner(os.path.join(reports_dir, f"{candidate}.json")) in (None, '', image_name)

    if free(prefix):
        return prefix
    stem = os.path.splitext(image_name)[0] or prefix
    candidate, counter = stem, 1
    while not free(candidate):
        candidate = f"{stem}_{counter}"
        counter += 1
    return candidate


def unique_filename(filename, folders, current_path=None):
    """Return filename, or filename with _1, _2 ... added, so that no other file in folders has that name."""
    stem, ext = os.path.splitext(filename)
    current = os.path.abspath(current_path) if current_path else None

    def taken(candidate):
        for folder in folders:
            if not folder:
                continue
            path = os.path.join(folder, candidate)
            if os.path.exists(path) and os.path.abspath(path) != current:
                return True
        return False

    candidate, counter = filename, 1
    while taken(candidate):
        candidate = f"{stem}_{counter}{ext}"
        counter += 1
    return candidate
