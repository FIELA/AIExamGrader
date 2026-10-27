"""After a sheet's first review, the review window shows its result for a few seconds before moving on."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from AutoGrader import App
from config_manager import ConfigManager
from review_window import ReviewWindow
from translations import TRANSLATIONS


class TestReviewCountdown(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.exam = root / "exam"
        (self.exam / "成功归档").mkdir(parents=True)
        (self.exam / "阅卷报告").mkdir()
        for name, review_count in (("IMG_0001", 1), ("IMG_0002", 0), ("IMG_0003", 0)):
            Image.new("RGB", (8, 8), "white").save(self.exam / "成功归档" / f"{name}.jpg")
            details = [{"question_id": "1", "type": "客观题", "score": 3, "max_score": 3, "student_answer": "A"},
                       {"question_id": "17(1)", "type": "主观题", "score": 4, "max_score": 6}]
            report = {"original_filename": f"{name}.jpg", "total_score": 7, "review_count": review_count, "details": details,
                      "db_student_info": {"id": "", "name": "张三", "class": "701", "room": "", "seat": ""}}
            (self.exam / "阅卷报告" / f"{name}.json").write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
        with patch('AutoGrader.ConfigManager', return_value=ConfigManager(str(root / 'config.json'))):
            self.app = App()
        self.app.withdraw()
        self.app.exam_folder = str(self.exam)
        self.review = ReviewWindow(self.app, str(self.exam), self.app.student_manager, self.app.on_review_save,
                                   lang='CN', translations=TRANSLATIONS)
        self.review.update()

    def tearDown(self):
        if self.review.winfo_exists():
            self.review.destroy()
        self.app.destroy()
        self.tmp.cleanup()

    def sheet(self):
        return Path(self.review.image_files[self.review.current_index]).stem

    def review_count(self, name):
        return json.loads((self.exam / "阅卷报告" / f"{name}.json").read_text(encoding='utf-8'))['review_count']

    def wait(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.review.update()
            time.sleep(0.02)

    def test_first_review_shows_the_result_then_moves_on(self):
        self.assertEqual(self.sheet(), "IMG_0002")  # The first sheet not yet reviewed
        self.review.ADVANCE_DELAY = 2
        self.review.confirm_all_and_next()
        self.assertEqual((self.sheet(), self.review_count("IMG_0002")), ("IMG_0002", 1))
        self.assertEqual(self.review.btn_confirm_all.cget('text'), "⏳ 2 秒后下一份")
        self.assertIn("已复审", self.review.lbl_status.cget('text'))
        self.wait(1.2)
        self.assertEqual((self.sheet(), self.review.btn_confirm_all.cget('text')), ("IMG_0002", "⏳ 1 秒后下一份"))
        self.wait(1.2)
        self.assertEqual(self.sheet(), "IMG_0003")
        self.assertIsNone(self.review.advance_job)

    def test_second_review_moves_on_at_once(self):
        self.review.current_index = 0
        self.review.load_current_student()
        self.review.confirm_all_and_next()
        self.assertEqual((self.sheet(), self.review_count("IMG_0001")), ("IMG_0002", 2))
        self.assertIsNone(self.review.advance_job)

    def test_clicking_again_moves_on_without_saving_twice(self):
        self.review.confirm_all_and_next()
        self.review.confirm_all_and_next()  # Within the 3-second guard: ignored
        self.assertEqual(self.sheet(), "IMG_0002")
        self.review.last_confirm_time -= 3.5
        self.review.confirm_all_and_next()
        self.assertEqual((self.sheet(), self.review_count("IMG_0002")), ("IMG_0003", 1))

    def test_typing_or_going_back_keeps_the_sheet(self):
        for stay in (lambda: self.review.event_generate("<KeyPress>", keysym="a", when="now"), self.review.prev_step):
            with self.subTest(stay=stay):
                self.review.ADVANCE_DELAY = 1
                self.review.last_confirm_time = 0
                self.review.current_index = self.review.image_files.index(next(f for f in self.review.image_files if "IMG_0002" in f))
                self.review.load_current_student()
                self.review.current_data['review_count'] = 0
                self.review.confirm_all_and_next()
                self.assertIsNotNone(self.review.advance_job)
                stay()
                self.wait(1.5)
                self.assertIsNone(self.review.advance_job)
                self.assertIn(self.sheet(), ("IMG_0002", "IMG_0001"))  # Back on the first step goes to the previous sheet
                self.assertFalse(self.review.btn_confirm_all.cget('text').startswith("⏳"))

    def test_back_from_the_last_step_stays_on_the_sheet(self):
        self.review.current_step_index = len(self.review.steps) - 1
        self.review.load_step_ui()
        self.review.ADVANCE_DELAY = 1
        self.review.confirm_all_and_next()
        self.review.prev_step()
        self.wait(1.5)
        self.assertEqual((self.sheet(), self.review.current_step_index), ("IMG_0002", len(self.review.steps) - 2))
        self.assertIsNone(self.review.advance_job)

    def test_closing_during_the_countdown(self):
        self.review.confirm_all_and_next()
        with patch.object(self.app, 'report_callback_exception') as errors:
            self.review.on_close()
            end = time.time() + 1.5
            while time.time() < end:
                self.app.update()
                time.sleep(0.02)
        errors.assert_not_called()
        self.assertFalse(self.review.winfo_exists())


if __name__ == "__main__":
    unittest.main()
