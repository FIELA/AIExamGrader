"""The review is finished only once every sheet is reviewed, and a student found on several sheets is pointed out;
the extra sheet can be taken out of the grades from the review instead of being deleted by hand.

As on 2026-10-17: a sheet named after its written exam number (114514.jpg) sorted before image00001.jpg and was never
opened, yet passing the last sheet said every student was reviewed. The teacher scanned that sheet again; the new scan
was graded for the same student with nothing in review saying so, and after one image was deleted by hand the grading
log still ended with "全部完成" while its counts disagreed."""
import csv
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import DEFAULT, patch

from PIL import Image

from AutoGrader import App
from config_manager import ConfigManager
from review_window import ReviewWindow
from translations import TRANSLATIONS

ROSTER = [{'id': '', 'name': name, 'class': '高三1班', 'room': '', 'seat': ''} for name in ('赵锦添', '李四', '王五', '孙七')]


class ReviewFolder(unittest.TestCase):
    # (report, image in 成功归档, name it was scanned with, roster index, review count, total score)
    sheets = []

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.exam = self.root / "exam"
        self.success, self.originals, self.reports = (self.exam / d for d in ("成功归档", "原始文件", "阅卷报告"))
        for folder in (self.success, self.originals, self.reports):
            folder.mkdir(parents=True)
        for i, (report, image, scanned, who, reviews, score) in enumerate(self.sheets):
            Image.new("RGB", (8, 8), (30 * i, 0, 0)).save(self.success / image)
            (self.originals / scanned).write_bytes((self.success / image).read_bytes())
            details = [{"question_id": "1", "type": "客观题", "student_answer": "A", "score": score, "max_score": 100}]
            data = {"original_filename": scanned, "db_student_info": dict(ROSTER[who]), "total_score": score, "details": details,
                    "student_match": {"method": "class_name", "candidates": []}}
            if image != scanned:
                data["renamed_filename"] = image
            if reviews:
                data["review_count"] = reviews
            (self.reports / report).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            (self.reports / report).with_suffix('.md').write_text(f"# {report}\n", encoding='utf-8')
        with patch('AutoGrader.ConfigManager', return_value=ConfigManager(str(self.root / 'config.json'))):
            self.app = App()
        self.app.withdraw()
        self.app.exam_folder = str(self.exam)
        self.app.student_manager.students = [dict(s) for s in ROSTER]
        self.messages = patch.multiple('review_window.messagebox', showinfo=DEFAULT, showerror=DEFAULT)
        self.dialogs = self.messages.start()

    def tearDown(self):
        self.messages.stop()
        self.app.destroy()
        self.tmp.cleanup()

    def open_review(self):
        review = ReviewWindow(self.app, str(self.exam), self.app.student_manager, self.app.on_review_save,
                              lang='CN', translations=TRANSLATIONS)
        review.toggle_view_mode()  # Text mode: the whole sheet is confirmed at once
        return review

    @staticmethod
    def current(review):
        return Path(review.image_files[review.current_index]).name

    @staticmethod
    def confirm(review):
        """Confirm & Next, then go on without waiting out the countdown a first review shows."""
        review.last_confirm_time = 0
        review.confirm_all_and_next()
        if review.winfo_exists() and review.advance_job:
            review.advance_now()

    def go_to(self, review, image):
        review.current_index = [Path(f).name for f in review.image_files].index(image)
        review.load_current_student()

    def run_grading(self):
        """Start Grading with nothing new to grade, as after a review; returns the log."""
        (self.root / 'rubric.txt').write_text('Question 1: answer A, 100 points.', encoding='utf-8')
        self.app.rubric_path, self.app.current_api_key = str(self.root / 'rubric.txt'), 'fake-test-key'
        logs = []
        self.app.log = logs.append
        with patch('AutoGrader.AIGraderEngine'), patch('AutoGrader.time.sleep'):
            self.app.process_images()
        self.app.update()  # Messages queued for the main thread
        return "\n".join(logs)


class TestFinishingNeedsEverySheet(ReviewFolder):
    sheets = [
        ("114514.json", "114514.jpg", "image00031.jpg", 0, 0, 54),  # Named after its written exam number
        ("image00001.json", "image00001.jpg", "image00001.jpg", 1, 1, 40),
        ("image00002.json", "image00002.jpg", "image00002.jpg", 2, 0, 60),
        ("image00034.json", "image00034.jpg", "image00034.jpg", 3, 0, 63),
    ]

    def images(self):
        return sorted(image for _, image, *_ in self.sheets)

    def test_sheets_are_reviewed_in_the_order_they_were_scanned(self):
        # As the paper pile is: 114514.jpg was scanned as image00031.jpg, so it does not come first
        review = self.open_review()
        self.assertEqual([Path(f).name for f in review.image_files], ["image00001.jpg", "image00002.jpg", "114514.jpg", "image00034.jpg"])
        self.assertEqual(self.current(review), "image00002.jpg")  # The first sheet still to review
        review.destroy()

    def test_passing_the_last_sheet_opens_the_sheets_still_to_review(self):
        review = self.open_review()
        self.confirm(review)
        self.assertEqual(self.current(review), "114514.jpg")
        review.skip_student()
        review.skip_student()  # Past the last sheet, two sheets left unreviewed

        # Not finished: the first sheet still to review is opened, and the teacher is told what is left
        self.assertTrue(review.winfo_exists())
        self.assertEqual(self.current(review), "114514.jpg")
        message = self.dialogs['showinfo'].call_args.args[1]
        self.assertIn("还有 2 份答题卡未复审（第 3、4 份）", message)
        self.assertNotIn("所有学生复审完成", message)
        self.assertEqual(sorted(os.listdir(self.success)), self.images())  # Nothing renamed yet

        # Back from an earlier sheet, a first review goes on to the next sheet still to review
        self.go_to(review, "image00001.jpg")
        self.confirm(review)  # Reviewed again: the next sheet in order
        self.assertEqual(self.current(review), "image00002.jpg")
        self.go_to(review, "114514.jpg")
        self.confirm(review)
        self.assertEqual(self.current(review), "image00034.jpg")
        self.confirm(review)
        self.assertFalse(review.winfo_exists())
        self.assertIn("所有学生复审完成", self.dialogs['showinfo'].call_args.args[1])
        self.assertEqual(sorted(os.listdir(self.success)), ['高三1班-孙七.jpg', '高三1班-李四.jpg', '高三1班-王五.jpg', '高三1班-赵锦添.jpg'])

    def test_a_first_review_skips_sheets_already_reviewed(self):
        data = json.loads((self.reports / "114514.json").read_text(encoding='utf-8'))
        (self.reports / "114514.json").write_text(json.dumps(dict(data, review_count=1), ensure_ascii=False), encoding='utf-8')
        review = self.open_review()
        self.assertEqual(self.current(review), "image00002.jpg")
        self.confirm(review)
        self.assertEqual(self.current(review), "image00034.jpg")
        review.destroy()

    def test_closing_on_the_last_sheet_with_sheets_left_does_not_finish(self):
        review = self.open_review()
        self.go_to(review, "image00034.jpg")
        review.last_confirm_time = 0
        review.confirm_all_and_next()
        self.assertIsNotNone(review.advance_job)
        review.on_close()  # Closed while the last sheet's result is shown
        self.assertFalse(review.winfo_exists())
        self.dialogs['showinfo'].assert_not_called()
        self.assertEqual(sorted(os.listdir(self.success)), self.images())


class TestStudentOnSeveralSheets(ReviewFolder):
    sheets = [
        ("114514.json", "高三1班-赵锦添.jpg", "image00031.jpg", 0, 0, 54),
        ("114514_1.json", "114514.jpg", "image1.jpg", 0, 0, 49),  # The same sheet, scanned again
        ("image00001.json", "高三1班-李四.jpg", "image00001.jpg", 1, 1, 40),
    ]

    def test_review_shows_the_students_other_sheet(self):
        review = self.open_review()
        self.go_to(review, "114514.jpg")
        self.assertIn("还有其他答题卡：高三1班-赵锦添.jpg（54 分，未复审）", review.lbl_other_sheets.cget('text'))
        self.go_to(review, "高三1班-赵锦添.jpg")
        self.assertIn("114514.jpg（49 分，未复审）", review.lbl_other_sheets.cget('text'))
        self.go_to(review, "高三1班-李四.jpg")
        self.assertIsNone(review.lbl_other_sheets)

        # Finishing the review says so again, as the summary now holds two scores for one student
        self.go_to(review, "114514.jpg")
        self.confirm(review)
        self.assertEqual(self.current(review), "高三1班-赵锦添.jpg")
        self.confirm(review)
        self.assertFalse(review.winfo_exists())
        message = self.dialogs['showinfo'].call_args.args[1]
        self.assertIn("所有学生复审完成", message)
        self.assertIn("赵锦添(高三1班) 有 2 份答题卡", message)


class TestGradingLogNamesProblems(ReviewFolder):
    sheets = [
        ("114514.json", "高三1班-赵锦添.jpg", "image00031.jpg", 0, 0, 54),
        ("114514_1.json", "高三1班-赵锦添_1.jpg", "image1.jpg", 0, 1, 57),
        ("image00001.json", "高三1班-李四.jpg", "image00001.jpg", 1, 1, 40),
    ]

    def test_a_run_with_a_missing_image_and_a_repeated_student_does_not_say_finished(self):
        (self.success / "高三1班-赵锦添.jpg").unlink()  # Deleted by hand in Finder, its report left behind
        text = self.run_grading()
        self.assertIn("赵锦添(高三1班) 对应了多张答题卡：高三1班-赵锦添.jpg（54 分，未复审）、高三1班-赵锦添_1.jpg（57 分，已复审）", text)
        self.assertIn("114514.json 记录的答题卡 高三1班-赵锦添.jpg 找不到", text)
        self.assertIn("答题卡: 2, JSON: 3, Markdown: 3, CSV: 3", text)
        self.assertIn("阅卷结束，但有 2 处需要处理", text)
        self.assertNotIn("全部完成", text)

    def test_a_clean_run_still_says_finished(self):
        for report in ("114514.json", "114514.md"):
            (self.reports / report).unlink()
        (self.success / "高三1班-赵锦添.jpg").unlink()
        text = self.run_grading()
        self.assertIn("答题卡: 2, JSON: 2, Markdown: 2, CSV: 2", text)
        self.assertIn("全部完成", text)
        self.assertNotIn("⚠️", text)


class TestRemovingASheetScannedTwice(ReviewFolder):
    sheets = [
        ("114514.json", "高三1班-赵锦添.jpg", "image00031.jpg", 0, 0, 54),
        ("114514_1.json", "高三1班-赵锦添_1.jpg", "image1.jpg", 0, 1, 57),  # The same sheet scanned again, reviewed
        ("image00001.json", "高三1班-李四.jpg", "image00001.jpg", 1, 1, 40),
    ]

    def setUp(self):
        super().setUp()
        App.regenerate_csv_from_jsons(self.app)  # The summary as grading left it: three rows

    def summary_rows(self):
        with open(self.exam / "阅卷数据" / "成绩汇总表.csv", encoding='utf-8-sig') as f:
            return sorted(row['原始文件'] for row in csv.DictReader(f))

    def remove(self, review, answer=True):
        with patch('review_window.messagebox.askyesno', return_value=answer) as ask:
            review.btn_remove_sheet.invoke()
        return ask

    def test_the_sheet_and_its_report_leave_the_grades(self):
        moved = {"成功归档/高三1班-赵锦添.jpg": (self.success / "高三1班-赵锦添.jpg").read_bytes(),
                 "阅卷报告/114514.json": (self.reports / "114514.json").read_bytes(),
                 "阅卷报告/114514.md": (self.reports / "114514.md").read_bytes()}
        review = self.open_review()
        self.go_to(review, "高三1班-李四.jpg")
        self.assertIsNone(review.btn_remove_sheet)  # Offered only for a student on several sheets
        self.go_to(review, "高三1班-赵锦添.jpg")
        ask = self.remove(review)
        self.assertIn("高三1班-赵锦添.jpg（54 分，未复审）", ask.call_args.args[1])

        # Image and report move to 已移除/<time>/, laid out as in the exam folder, so moving them back restores the sheet
        self.assertEqual(sorted(os.listdir(self.success)), ['高三1班-李四.jpg', '高三1班-赵锦添_1.jpg'])
        self.assertEqual(sorted(os.listdir(self.reports)), ['114514_1.json', '114514_1.md', 'image00001.json', 'image00001.md'])
        [folder] = list((self.exam / "已移除").iterdir())
        self.assertEqual({str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob('*') if p.is_file()}, moved)
        self.assertIn("image00031.jpg", os.listdir(self.originals))  # The scan stays backed up
        self.assertEqual(self.summary_rows(), ['image00001.jpg', 'image1.jpg'])

        # The review goes on at the sheet that took its place, which has no other sheet now
        self.assertEqual([Path(f).name for f in review.image_files], ['高三1班-李四.jpg', '高三1班-赵锦添_1.jpg'])
        self.assertEqual(self.current(review), '高三1班-赵锦添_1.jpg')
        self.assertIsNone(review.lbl_other_sheets)
        review.destroy()

        # Grading and review leave the removed sheet alone
        text = self.run_grading()
        self.assertIn("答题卡: 2, JSON: 2, Markdown: 2, CSV: 2", text)
        self.assertIn("全部完成", text)
        self.assertNotIn("⚠️", text)
        again = self.open_review()
        self.assertEqual(len(again.image_files), 2)
        again.destroy()

    def test_cancelling_keeps_the_sheet(self):
        review = self.open_review()
        self.go_to(review, "高三1班-赵锦添.jpg")
        self.remove(review, answer=False)
        self.assertFalse((self.exam / "已移除").exists())
        self.assertEqual(sorted(os.listdir(self.success)), sorted(image for _, image, *_ in self.sheets))
        self.assertEqual(self.summary_rows(), ['image00001.jpg', 'image00031.jpg', 'image1.jpg'])
        self.assertEqual(self.current(review), '高三1班-赵锦添.jpg')
        review.destroy()

    def test_a_move_that_fails_puts_the_sheet_back(self):
        review = self.open_review()
        self.go_to(review, "高三1班-赵锦添.jpg")
        move = shutil.move

        def locked(src, dst):
            if str(src).endswith('114514.md'):
                raise PermissionError("report is open in another program")
            return move(src, dst)
        with patch('AutoGrader.shutil.move', side_effect=locked):
            self.remove(review)
        self.assertIn("report is open in another program", self.dialogs['showerror'].call_args.args[1])
        # Removed whole or not at all: the image and the report that had moved are back
        self.assertEqual(sorted(os.listdir(self.success)), sorted(image for _, image, *_ in self.sheets))
        self.assertTrue((self.reports / "114514.json").exists() and (self.reports / "114514.md").exists())
        self.assertFalse([p for p in (self.exam / "已移除").rglob('*') if p.is_file()])
        self.assertEqual(self.summary_rows(), ['image00001.jpg', 'image00031.jpg', 'image1.jpg'])
        self.assertEqual(self.current(review), '高三1班-赵锦添.jpg')
        review.destroy()

    def test_not_while_grading_runs(self):
        self.app.processing = True
        review = self.open_review()
        self.go_to(review, "高三1班-赵锦添.jpg")
        ask = self.remove(review)
        ask.assert_not_called()
        self.assertIn("阅卷正在进行", self.dialogs['showinfo'].call_args.args[1])
        self.assertFalse((self.exam / "已移除").exists())
        review.destroy()


if __name__ == "__main__":
    unittest.main()
