"""When review is done, graded sheets are renamed Class-Name where they are; the scans stay backed up in 原始文件.
A sheet with no name on it can be confirmed as 未署名 (unsigned) instead, and keeps its file name."""
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
from report_files import build_report_index
from review_window import NoStudentDialog, ReviewWindow
from sheet_naming import identity_confirmed, sheet_name
from test_sheet_identity import FakeGrader, SheetApp
from test_student_matching import ROSTER, sheet
from translations import TRANSLATIONS


class RenameApp(SheetApp):
    rename_reviewed_sheets = App.rename_reviewed_sheets


def student(name, klass, **fields):
    return dict({'id': '', 'name': name, 'class': klass, 'room': '', 'seat': ''}, **fields)


def files(folder):
    """Every image in a folder, with its bytes."""
    return {p.name: p.read_bytes() for p in Path(folder).iterdir() if p.is_file()}


class TestNaming(unittest.TestCase):
    def test_sheet_names(self):
        self.assertEqual(sheet_name(student('张三', '701', id='23090828', room='01', seat='5')), '701-张三')
        self.assertEqual(sheet_name(student('张三', '高二1班')), '高二1班-张三')
        # Empty fields leave no stray separators; characters that file names cannot hold are replaced
        self.assertEqual(sheet_name(student('张三', '')), '张三')
        self.assertEqual(sheet_name(student('张三', '未知')), '张三')
        self.assertEqual(sheet_name(student('张三', '7/1:班')), '7_1_班-张三')

    def test_confirmed_students(self):
        known = student('张三', '701')
        cases = [
            ({'db_student_info': known, 'student_match': {'method': 'class_name'}}, True),
            ({'db_student_info': known, 'student_match': {'method': 'manual'}}, True),
            ({'db_student_info': known}, True),  # Report from before match records
            ({'db_student_info': known, 'student_match': {'method': 'class_name_similar'}}, False),
            ({'db_student_info': known, 'student_match': {'method': 'class_name_similar'}, 'review_count': 1}, True),
            ({'db_student_info': student('未知', '未知'), 'student_match': {'method': 'ambiguous'}, 'review_count': 1}, False),
        ]
        for data, confirmed in cases:
            with self.subTest(data=data):
                self.assertEqual(identity_confirmed(data), confirmed)


class TestRename(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.exam = Path(self.tmp.name) / "exam"
        self.exam.mkdir()
        self.success, self.originals, self.reports = (self.exam / d for d in ("成功归档", "原始文件", "阅卷报告"))

    def tearDown(self):
        self.tmp.cleanup()

    def grade(self, sheets, backup=True):
        """Grade the scans as a batch does: back each up to 原始文件, then grade it into 成功归档."""
        self.originals.mkdir()
        for i, name in enumerate(sheets):
            Image.new("RGB", (8, 8), (40 * i, 0, 0)).save(self.exam / name)
            if backup:
                shutil.copy2(self.exam / name, self.originals / name)
        app = RenameApp(self.exam, ROSTER)
        grader = FakeGrader(sheets)
        for name in sheets:
            self.assertTrue(app.process_single_file(grader, "rubric", name, str(self.exam), False, 1), app.logs)
        return app

    def report(self, name):
        return json.loads((self.reports / name).read_text(encoding='utf-8'))

    def edit_report(self, name, **fields):
        data = dict(self.report(name), **fields)
        (self.reports / name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def test_confirmed_sheets_are_renamed_where_they_are(self):
        app = self.grade({"IMG_0001.jpg": sheet('张三', '701'), "IMG_0002.jpg": sheet('张三', '701'), "IMG_0003.jpg": sheet('王小名', '701'),
                          "IMG_0004.jpg": sheet('张五', '701'), "01-05缺.jpg": sheet('孙七', '702')})
        scans = files(self.originals)
        self.assertEqual(app.rename_reviewed_sheets(), (3, 2))
        # A similar name still to be checked and an unclear sheet keep their names
        self.assertEqual(sorted(os.listdir(self.success)), ['701-张三.jpg', '701-张三_1.jpg', '702-孙七.jpg', 'IMG_0003.jpg', 'IMG_0004.jpg'])
        self.assertEqual(files(self.originals), scans)  # The backup is not touched
        # Each report records its sheet's new name, and the sheet is still its own scan
        index = build_report_index(str(self.reports))
        for image in os.listdir(self.success):
            data = json.loads(Path(index[image]).read_text(encoding='utf-8'))
            self.assertEqual((self.success / image).read_bytes(), scans[data['original_filename']], image)
        self.assertEqual(self.report('IMG_0001.json')['renamed_filename'], '701-张三.jpg')
        self.assertNotIn('renamed_filename', self.report('IMG_0003.json'))
        self.assertTrue(any('重命名 3 张' in line and '2 张学生未确认' in line for line in app.logs), app.logs)

        # Confirmed in a later review: that sheet is named too, and the others keep their names
        self.edit_report('IMG_0003.json', review_count=1)
        self.assertEqual(app.rename_reviewed_sheets(), (1, 1))
        self.assertEqual(sorted(os.listdir(self.success)), ['701-张三.jpg', '701-张三_1.jpg', '701-王小明.jpg', '702-孙七.jpg', 'IMG_0004.jpg'])
        self.assertEqual(app.rename_reviewed_sheets(), (0, 1))
        self.assertFalse([p for p in os.listdir(self.reports) if p.endswith('.tmp')])

    def test_a_scan_missing_from_the_backup_is_backed_up_first(self):
        app = self.grade({"IMG_0001.jpg": sheet('张三', '701')}, backup=False)
        scan = (self.success / 'IMG_0001.jpg').read_bytes()
        self.assertEqual(app.rename_reviewed_sheets(), (1, 0))
        self.assertEqual(files(self.originals), {'IMG_0001.jpg': scan})
        self.assertEqual((self.success / '701-张三.jpg').read_bytes(), scan)
        self.assertTrue(any('原始文件中没有 IMG_0001.jpg' in line for line in app.logs), app.logs)

    def test_two_sheets_that_swapped_students_swap_names(self):
        app = self.grade({"IMG_0001.jpg": sheet('张三', '701'), "IMG_0002.jpg": sheet('李四', '701')})
        app.rename_reviewed_sheets()
        # Review found the two the wrong way round
        for report, chosen in (('IMG_0001.json', ROSTER[2]), ('IMG_0002.json', ROSTER[0])):
            self.edit_report(report, db_student_info=dict(chosen, is_absent=False), student_match={'method': 'manual', 'candidates': []}, review_count=1)
        self.assertEqual(app.rename_reviewed_sheets(), (2, 0))
        self.assertEqual(sorted(os.listdir(self.success)), ['701-张三.jpg', '701-李四.jpg'])
        scans = files(self.originals)
        self.assertEqual((self.success / '701-李四.jpg').read_bytes(), scans['IMG_0001.jpg'])
        self.assertEqual((self.success / '701-张三.jpg').read_bytes(), scans['IMG_0002.jpg'])
        self.assertEqual(self.report('IMG_0001.json')['renamed_filename'], '701-李四.jpg')

    def test_a_report_that_cannot_be_saved_keeps_its_sheet_name(self):
        app = self.grade({"IMG_0001.jpg": sheet('张三', '701'), "IMG_0002.jpg": sheet('李四', '701')})
        before = self.report('IMG_0001.json')
        replace = os.replace

        def locked(src, dst):
            if dst.endswith('IMG_0001.json'):
                raise PermissionError("report is open in another program")
            return replace(src, dst)
        with patch('AutoGrader.os.replace', side_effect=locked):
            self.assertEqual(app.rename_reviewed_sheets(), (1, 0))
        self.assertEqual(sorted(os.listdir(self.success)), ['701-李四.jpg', 'IMG_0001.jpg'])
        self.assertEqual(self.report('IMG_0001.json'), before)
        self.assertFalse([p for p in os.listdir(self.reports) if p.endswith('.tmp')])
        self.assertTrue(any('IMG_0001.jpg 重命名为 701-张三.jpg 失败' in line for line in app.logs), app.logs)


    def test_a_sheet_marked_unsigned_stays_unsigned(self):
        app = self.grade({"IMG_0001.jpg": sheet('', '')})
        self.edit_report('IMG_0001.json', student_match={'method': 'unsigned', 'candidates': []}, review_count=1)
        marked = self.report('IMG_0001.json')
        self.assertEqual(app.rematch_students(), 0)  # Matching to the roster again leaves it alone
        self.assertEqual(self.report('IMG_0001.json'), marked)
        # Regraded, the model now reads a name: the teacher's mark still stands
        app.grader_engine = FakeGrader({"IMG_0001.jpg": sheet('张三', '701')})
        self.assertEqual(app.regrade_single_file(str(self.success / "IMG_0001.jpg")), (True, "Success"))
        data = self.report('IMG_0001.json')
        self.assertEqual((data['db_student_info']['name'], data['student_match']['method']), ('未知', 'unsigned'))
        self.assertIn('- **学生匹配**: 未署名', (self.reports / 'IMG_0001.md').read_text(encoding='utf-8'))
        self.assertEqual(app.rename_reviewed_sheets(), (0, 1))
        self.assertEqual(os.listdir(self.success), ['IMG_0001.jpg'])


class TestBackupAfterRenaming(unittest.TestCase):
    def test_a_renamed_sheet_is_not_backed_up_again(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exam = root / 'exam'
            for folder in ('成功归档', '原始文件', '阅卷报告'):
                (exam / folder).mkdir(parents=True)
            Image.new('RGB', (8, 8), 'white').save(exam / '原始文件' / 'IMG_0001.jpg')
            shutil.copy2(exam / '原始文件' / 'IMG_0001.jpg', exam / '成功归档' / '701-张三.jpg')
            Image.new('RGB', (8, 8), 'black').save(exam / '成功归档' / 'IMG_0009.jpg')  # Graded before scans were backed up
            report = {'original_filename': 'IMG_0001.jpg', 'renamed_filename': '701-张三.jpg', 'total_score': 1, 'details': [],
                      'db_student_info': student('张三', '701'), 'student_match': {'method': 'class_name', 'candidates': []}}
            (exam / '阅卷报告' / 'IMG_0001.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
            (root / 'rubric.txt').write_text('Question 1: answer A, 1 point.')
            with patch('AutoGrader.ConfigManager', return_value=ConfigManager(str(root / 'config.json'))):
                app = App()
            try:
                app.withdraw()
                app.exam_folder, app.rubric_path, app.current_api_key = str(exam), str(root / 'rubric.txt'), 'fake-test-key'
                with patch('AutoGrader.AIGraderEngine'):
                    app.process_images()  # The next grading run
                self.assertEqual(sorted(os.listdir(exam / '原始文件')), ['IMG_0001.jpg', 'IMG_0009.jpg'])
            finally:
                app.destroy()


class TestFinishingReview(unittest.TestCase):
    """The real review window: a student is required before confirming, and the last confirmation renames the sheets."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.exam = root / "exam"
        self.success, self.originals, self.reports = (self.exam / d for d in ("成功归档", "原始文件", "阅卷报告"))
        for folder in (self.success, self.originals, self.reports):
            folder.mkdir(parents=True)
        records = {"IMG_0001.jpg": (ROSTER[0], 'class_name'), "IMG_0002.jpg": (student('未知', '未知', id='未知'), 'unmatched')}
        for i, (name, (info, method)) in enumerate(records.items()):
            Image.new("RGB", (8, 8), (90 * i, 0, 0)).save(self.success / name)
            shutil.copy2(self.success / name, self.originals / name)
            details = [{"question_id": "1", "type": "客观题", "student_answer": "A", "score": 3, "max_score": 3}]
            report = {"original_filename": name, "db_student_info": dict(info), "student_match": {"method": method, "candidates": []},
                      "total_score": 3, "details": details}
            if name == "IMG_0001.jpg":
                report["review_count"] = 1  # Reviewed already, so the last sheet's confirmation finishes the review
            (self.reports / name.replace('.jpg', '.json')).write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
        with patch('AutoGrader.ConfigManager', return_value=ConfigManager(str(root / 'config.json'))):
            self.app = App()
        self.app.withdraw()
        self.app.exam_folder = str(self.exam)
        self.app.student_manager.students = [dict(s) for s in ROSTER]
        self.messages = patch.multiple('review_window.messagebox', showinfo=DEFAULT, showerror=DEFAULT)
        self.dialogs = self.messages.start()
        # The real 关闭 / 未署名 dialog, answered by its own buttons instead of waiting for a click
        self.asked, self.answer = [], 'close'

        def answer(dialog, *args):
            self.asked.append(dialog.winfo_children()[0].cget('text'))
            {'close': dialog.btn_close.invoke, 'unsigned': dialog.btn_unsigned.invoke, 'window': dialog.destroy}[self.answer]()
        self.dialog = patch.object(NoStudentDialog, 'wait_window', answer)
        self.dialog.start()

    def tearDown(self):
        self.dialog.stop()
        self.messages.stop()
        self.app.destroy()
        self.tmp.cleanup()

    def open_last_sheet(self, text_mode=False):
        review = ReviewWindow(self.app, str(self.exam), self.app.student_manager, self.app.on_review_save, lang='CN', translations=TRANSLATIONS)
        if text_mode:
            review.toggle_view_mode()
        review.current_index = len(review.image_files) - 1
        review.load_current_student()
        self.assertEqual(Path(review.image_files[review.current_index]).name, "IMG_0002.jpg")
        return review

    def saved(self, name='IMG_0002.json'):
        return json.loads((self.reports / name).read_text(encoding='utf-8'))

    def test_confirming_without_a_student_asks_for_one_then_the_last_sheet_renames(self):
        review = self.open_last_sheet(text_mode=True)
        review.confirm_all_and_next()
        self.assertEqual(self.asked, [self.app.t("msg_select_student_first")])
        self.assertNotIn('review_count', self.saved())  # Closed: not confirmed
        self.assertTrue(review.winfo_exists())
        self.assertEqual(Path(review.image_files[review.current_index]).name, "IMG_0002.jpg")

        review.combo_student.set(ReviewWindow.student_display(ROSTER[2]))  # 李四
        review.confirm_all_and_next()  # Right after choosing: no 3-second wait
        saved = self.saved()
        self.assertEqual((saved['db_student_info']['name'], saved['student_match']['method'], saved['review_count']), ('李四', 'manual', 1))
        self.assertEqual(len(self.asked), 1)
        self.dialogs['showinfo'].assert_not_called()  # A first review shows its result before moving on
        review.advance_now()

        self.assertFalse(review.winfo_exists())
        self.assertEqual(sorted(os.listdir(self.success)), ['701-张三.jpg', '701-李四.jpg'])
        self.assertEqual(sorted(os.listdir(self.originals)), ['IMG_0001.jpg', 'IMG_0002.jpg'])
        message = self.dialogs['showinfo'].call_args.args[1]
        self.assertIn("本次重命名 2 张", message)
        self.assertIn("原始文件", message)
        with open(self.exam / "阅卷数据" / "成绩汇总表.csv", encoding='utf-8-sig') as f:
            self.assertEqual(sorted(row['重命名文件'] for row in csv.DictReader(f)), ['701-张三.jpg', '701-李四.jpg'])
        # The renamed sheets open in review again, with a fresh start
        again = ReviewWindow(self.app, str(self.exam), self.app.student_manager, self.app.on_review_save, lang='CN', translations=TRANSLATIONS)
        self.assertEqual(sorted(Path(f).name for f in again.image_files), ['701-张三.jpg', '701-李四.jpg'])
        again.destroy()

    def test_the_student_step_needs_a_student_in_image_mode(self):
        review = self.open_last_sheet()
        self.assertEqual(review.current_step_index, 0)
        review.next_step()  # "✅ 正确" on the student step
        self.assertEqual((review.current_step_index, len(self.asked)), (0, 1))
        review.combo_student.set(ReviewWindow.student_display(ROSTER[2]))
        review.next_step()
        self.assertEqual(review.current_step_index, 1)
        # Confirming on the last step uses the student chosen on the first one, and finishes the review
        review.current_step_index = len(review.steps) - 1
        review.load_step_ui()
        review.confirm_all_and_next()
        self.assertEqual(len(self.asked), 1)
        self.assertFalse(review.winfo_exists())
        self.assertEqual(sorted(os.listdir(self.success)), ['701-张三.jpg', '701-李四.jpg'])

    def test_closing_the_dialog_window_is_close(self):
        self.answer = 'window'
        review = self.open_last_sheet(text_mode=True)
        review.confirm_all_and_next()
        self.assertEqual(len(self.asked), 1)
        self.assertNotIn('review_count', self.saved())
        self.assertIsNone(review.advance_job)
        review.destroy()

    def test_a_sheet_with_no_name_is_confirmed_as_unsigned(self):
        self.answer = 'unsigned'
        review = self.open_last_sheet(text_mode=True)
        review.confirm_all_and_next()
        saved = self.saved()
        self.assertEqual((saved['db_student_info']['name'], saved['student_match']['method'], saved['review_count']), ('未知', 'unsigned', 1))
        self.assertIn('- **学生匹配**: 未署名', (self.reports / 'IMG_0002.md').read_text(encoding='utf-8'))
        with open(self.exam / "阅卷数据" / "成绩汇总表.csv", encoding='utf-8-sig') as f:
            row = next(r for r in csv.DictReader(f) if r['原始文件'] == 'IMG_0002.jpg')
        self.assertEqual((row['匹配方式'], row['复审状态']), ('未署名', '已复审'))
        self.assertIsNotNone(review.advance_job)  # Shown for a moment, then the next sheet: here, the end of the review
        review.advance_now()
        self.assertFalse(review.winfo_exists())
        self.assertEqual(sorted(os.listdir(self.success)), ['701-张三.jpg', 'IMG_0002.jpg'])
        self.assertIn("1 张答题卡学生未确认或未署名", self.dialogs['showinfo'].call_args.args[1])

        # Reviewed again, the unsigned sheet is confirmed without asking
        again = ReviewWindow(self.app, str(self.exam), self.app.student_manager, self.app.on_review_save, lang='CN', translations=TRANSLATIONS)
        again.toggle_view_mode()
        again.current_index = [Path(f).name for f in again.image_files].index('IMG_0002.jpg')
        again.load_current_student()
        again.confirm_all_and_next()
        self.assertEqual(len(self.asked), 1)
        self.assertEqual((self.saved()['student_match']['method'], self.saved()['review_count']), ('unsigned', 2))
        if again.winfo_exists():
            again.destroy()

    def test_unsigned_on_the_student_step_goes_on_in_image_mode(self):
        self.answer = 'unsigned'
        review = self.open_last_sheet()
        review.next_step()
        self.assertEqual(review.current_step_index, 1)
        review.current_step_index = len(review.steps) - 1
        review.load_step_ui()
        review.confirm_all_and_next()  # Not asked again
        self.assertEqual(len(self.asked), 1)
        self.assertFalse(review.winfo_exists())
        self.assertEqual(self.saved()['student_match']['method'], 'unsigned')
        self.assertEqual(sorted(os.listdir(self.success)), ['701-张三.jpg', 'IMG_0002.jpg'])

    def test_closing_while_the_last_sheet_counts_down_finishes_the_review(self):
        review = self.open_last_sheet(text_mode=True)
        review.combo_student.set(ReviewWindow.student_display(ROSTER[2]))
        review.confirm_all_and_next()
        self.assertIsNotNone(review.advance_job)
        review.on_close()
        self.assertFalse(review.winfo_exists())
        self.assertEqual(sorted(os.listdir(self.success)), ['701-张三.jpg', '701-李四.jpg'])

    def test_sheets_are_not_renamed_while_grading_runs(self):
        self.app.processing = True
        (self.reports / 'IMG_0002.json').write_text(json.dumps(dict(self.saved(), review_count=1), ensure_ascii=False), encoding='utf-8')
        review = self.open_last_sheet(text_mode=True)
        review.skip_student()  # Past the last sheet, every sheet reviewed
        self.assertFalse(review.winfo_exists())
        self.assertEqual(sorted(os.listdir(self.success)), ['IMG_0001.jpg', 'IMG_0002.jpg'])
        self.assertIn("阅卷仍在进行", self.dialogs['showinfo'].call_args.args[1])


if __name__ == "__main__":
    unittest.main()
