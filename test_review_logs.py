# Copyright (c) 2025 JASim. Licensed under NCEL-Strict License v2.0.
# STRICT NON-COMMERCIAL USE ONLY. No AI/ML training, fine-tuning, or public distribution of Derivative Works.
# Modifications may only be shared as Patch Files.
# Public forks allowed solely for PRs (delete within 14 days after PR merged, rejected, or closed).
# Commercial licensing inquiries: nicofiela@outlook.com. See LICENSE file for full terms.

"""Each review save logs what changed, through the review window's real save, without opening a window."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from review_window import ReviewWindow


class Var:
    """Stands in for the absence checkbox's Tk variable, which needs a window to exist."""
    def __init__(self, value=False):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class LogStub:
    """Runs ReviewWindow.save_to_disk on a report in a temporary folder."""
    save_to_disk = ReviewWindow.save_to_disk

    def __init__(self, json_path, data):
        self.parent_app = None
        self.current_json_path = str(json_path)
        self.reports_dir = str(json_path.parent)
        self.current_data = data
        self.original_data = copy.deepcopy(data)
        self.chk_absence_var = Var(False)
        self.image_files, self.current_index, self.report_index = [], 0, {}

    def update_score_display(self): pass
    def update_markdown_file(self, md_path): pass
    def update_csv_row(self): pass


class TestReviewLogs(unittest.TestCase):
    def test_log_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            json_path = Path(folder) / "01-01.json"
            data = {
                "total_score": 70,
                "confirm_absence": "",
                "details": [{"question_id": "1", "score": 3}, {"question_id": "2", "score": 0}],
                "db_student_info": {"room": "01", "seat": "01"},
            }
            json_path.write_text(json.dumps(data), encoding='utf-8')
            window = LogStub(json_path, data)

            def saved():
                return json.loads(json_path.read_text(encoding='utf-8'))

            # 1. Modify Score
            window.current_data['total_score'] = 75
            window.current_data['details'][0]['score'] = 5  # Hack: max score ignored for test
            self.assertTrue(window.save_to_disk())
            logs = saved()['review_logs']
            self.assertEqual(len(logs), 1)
            self.assertIn("Total Score: 70 -> 75", logs[0]['changes'])
            self.assertIn("Q1 Score: 3 -> 5", logs[0]['changes'])
            self.assertEqual(saved()['review_count'], 1)

            # 2. Modify Absence (stored in English for data consistency)
            window.chk_absence_var.set(True)
            self.assertTrue(window.save_to_disk())
            logs = saved()['review_logs']
            self.assertEqual(len(logs), 2)
            self.assertIn("Confirm Absence: '' -> 'Yes'", logs[1]['changes'])
            self.assertEqual(saved()['confirm_absence'], 'Yes')

            # 3. No Change: the confirmation itself is logged
            self.assertTrue(window.save_to_disk())
            logs = saved()['review_logs']
            self.assertEqual(len(logs), 3)
            self.assertEqual(logs[2]['changes'], ["Review Confirmed"])
            self.assertEqual(saved()['review_count'], 3)


if __name__ == '__main__':
    unittest.main()
