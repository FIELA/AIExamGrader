import unittest
import json
import os
import copy
from datetime import datetime
from review_window import ReviewWindow
import customtkinter as ctk

# Mock ReviewWindow to test logic without GUI
class MockReviewWindow:
    def __init__(self):
        self.current_data = {
            "total_score": 70,
            "confirm_absence": "",
            "details": [
                {"question_id": "1", "score": 3},
                {"question_id": "2", "score": 0}
            ],
            "db_student_info": {"room": "01", "seat": "01"}
        }
        self.original_data = copy.deepcopy(self.current_data)
        self.chk_absence_var = ctk.BooleanVar(value=False)
        self.reports_dir = "."
        self.on_save_callback = None
        self.parent_app = None

    # Copy the logic from save_to_disk (only the diff part)
    def calculate_diff(self):
        # Simulate update from UI
        is_confirmed = self.chk_absence_var.get()
        self.current_data['confirm_absence'] = '是' if is_confirmed else ''
        
        if not hasattr(self, 'original_data'):
             self.original_data = copy.deepcopy(self.current_data)
             
        changes = []
        
        # Check Total Score
        old_score = self.original_data.get('total_score', 0)
        new_score = self.current_data.get('total_score', 0)
        if old_score != new_score:
            changes.append(f"Total Score: {old_score} -> {new_score}")
            
        # Check Confirm Absence
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
            else:
                changes.append(f"Q{q_id} Added")
                
        if changes:
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "changes": changes,
                "user": "Reviewer"
            }
            if 'review_logs' not in self.current_data:
                self.current_data['review_logs'] = []
            self.current_data['review_logs'].append(log_entry)
            
            # Update original_data for next save
            self.original_data = copy.deepcopy(self.current_data)
            return True
        return False

class TestReviewLogs(unittest.TestCase):
    def test_log_creation(self):
        window = MockReviewWindow()
        
        # 1. Modify Score
        window.current_data['total_score'] = 75
        window.current_data['details'][0]['score'] = 5 # Hack: max score ignored for test
        
        has_changes = window.calculate_diff()
        self.assertTrue(has_changes)
        
        logs = window.current_data.get('review_logs', [])
        self.assertEqual(len(logs), 1)
        self.assertIn("Total Score: 70 -> 75", logs[0]['changes'])
        self.assertIn("Q1 Score: 3 -> 5", logs[0]['changes'])
        
        # 2. Modify Absence
        window.chk_absence_var.set(True)
        has_changes = window.calculate_diff()
        self.assertTrue(has_changes)
        
        logs = window.current_data.get('review_logs', [])
        self.assertEqual(len(logs), 2)
        self.assertIn("Confirm Absence: '' -> '是'", logs[1]['changes'])
        
        # 3. No Change
        has_changes = window.calculate_diff()
        self.assertFalse(has_changes)
        self.assertEqual(len(logs), 2)

if __name__ == '__main__':
    unittest.main()
