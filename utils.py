# Copyright (c) 2025 JASim. Licensed under NCEL-Strict License v2.0.
# STRICT NON-COMMERCIAL USE ONLY. No AI/ML training, fine-tuning, or public distribution of Derivative Works.
# Modifications may only be shared as Patch Files.
# Public forks allowed solely for PRs (delete within 14 days after PR merged, rejected, or closed).
# Commercial licensing inquiries: nicofiela@outlook.com. See LICENSE file for full terms.

import re
import json

def clean_json_string(text: str) -> str:
    """
    Robustly extract JSON from a string.
    Finds the largest substring wrapped in {...} or [...]
    """
    text = text.strip()
    
    # Try to find the first '{' and the last '}'
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return text[start_idx:end_idx+1]
        
    # If no object found, try array
    start_idx = text.find('[')
    end_idx = text.rfind(']')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return text[start_idx:end_idx+1]

    # Fallback: simple cleanup
    if text.startswith("```json"): text = text[7:]
    elif text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    return text.strip()

def sort_csv_headers(headers: list) -> list:
    """
    Sort CSV headers based on a predefined priority list.
    Ensures consistent column order across the application.
    """
    priority = [
        # 1. Basic Info
        '考场', '座号', '班级', '姓名', '考号',
        'Room', 'Seat', 'Class', 'Name', 'ID',
        
        # 2. Status
        '复审状态', 'Review Status',
        '缺考标记', 'Absence Marker',
        '确认缺考', 'Confirm Absence',
        
        # 3. Scores
        '总分', 'Total Score',
        '客观题', 'Objective Score',
        '客观题正确数', 'Objective Correct',
        '客观题总数', 'Objective Total',
        '主观题', 'Subjective Score',
        
        # 4. Question Scores (Will be sorted naturally after these if not in list)
        # 5. Details (Info Consistency, Match Count)
        # 6. OCR Fields
    ]
    
    def natural_key(text):
        return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', text)]

    def header_sort_key(h):
        # 1. Priority List
        if h in priority:
            return (0, priority.index(h))
        
        # 3. Details (Explicitly move to end, before OCR)
        details_cols = ['信息一致性', 'Info Consistency', '匹配项数', 'Match Count']
        if h in details_cols:
            return (2, details_cols.index(h))
            
        # 4. OCR Fields (Move to very end)
        if h.startswith('OCR') or h.startswith('原始'):
            return (3, h)
            
        # 2. Questions (Everything else, e.g. "17", "18")
        # Use natural sort key for questions
        return (1, natural_key(h))
    
    return sorted(headers, key=header_sort_key)
