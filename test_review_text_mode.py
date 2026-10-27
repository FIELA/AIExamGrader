"""Text mode of the review window: editing an answer must not undo choices that are not confirmed yet."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from AutoGrader import App
from config_manager import ConfigManager
from review_window import ReviewWindow
from translations import TRANSLATIONS

ROSTER = [{'id': '', 'name': '张三', 'class': '701', 'room': '', 'seat': ''},
          {'id': '', 'name': '李四', 'class': '701', 'room': '', 'seat': ''}]


class TestReviewTextMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.exam = root / "exam"
        (self.exam / "成功归档").mkdir(parents=True)
        (self.exam / "阅卷报告").mkdir()
        Image.new("RGB", (8, 8), "white").save(self.exam / "成功归档" / "IMG_0001.jpg")
        details = [{"question_id": "1", "type": "客观题", "student_answer": "A", "standard_answer": "A", "score": 3, "max_score": 3},
                   {"question_id": "2", "type": "客观题", "student_answer": "B", "standard_answer": "C", "score": 0, "max_score": 3},
                   {"question_id": "17(1)", "type": "主观题", "score": 2, "max_score": 6}]
        report = {"original_filename": "IMG_0001.jpg", "total_score": 5, "details": details, "ocr_name": "李思", "ocr_class": "",
                  "db_student_info": {"id": "未知", "name": "未知", "class": "未知", "room": "", "seat": ""},
                  "student_match": {"method": "unmatched", "candidates": []}}
        self.report = self.exam / "阅卷报告" / "IMG_0001.json"
        self.report.write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
        with patch('AutoGrader.ConfigManager', return_value=ConfigManager(str(root / 'config.json'))):
            self.app = App()
        self.app.withdraw()
        self.app.exam_folder = str(self.exam)
        self.app.student_manager.students = [dict(s) for s in ROSTER]
        self.review = ReviewWindow(self.app, str(self.exam), self.app.student_manager, self.app.on_review_save,
                                   lang='CN', translations=TRANSLATIONS)
        self.review.toggle_view_mode()  # Text mode
        self.review.update()

    def tearDown(self):
        if self.review.winfo_exists():
            self.review.destroy()
        self.app.destroy()
        self.tmp.cleanup()

    def test_changing_an_answer_keeps_the_chosen_student_and_typed_scores(self):
        self.assertEqual(self.review.view_mode, 'no_image')
        chosen = ReviewWindow.student_display(ROSTER[1])
        self.review.combo_student.set(chosen)
        entry = self.review.sub_entries['17(1)'][0]
        entry.delete(0, "end")
        entry.insert(0, "5")

        self.review.on_obj_answer_change('2', 'C')  # Picking an answer in the objective table

        self.assertEqual(self.review.combo_student.get(), chosen)
        self.assertEqual(self.review.sub_entries['17(1)'][0].get(), "5")
        self.review.confirm_all_and_next()
        saved = json.loads(self.report.read_text(encoding='utf-8'))
        self.assertEqual((saved['db_student_info']['name'], saved['student_match']['method']), ('李四', 'manual'))
        scores = {item['question_id']: (item.get('student_answer'), item['score']) for item in saved['details']}
        self.assertEqual(scores, {'1': ('A', 3), '2': ('C', 3), '17(1)': (None, 5)})
        self.assertEqual(saved['total_score'], 11)


if __name__ == "__main__":
    unittest.main()
