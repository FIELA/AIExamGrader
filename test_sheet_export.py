"""Exporting graded sheets under their students' names without touching the originals."""
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import AutoGrader
from AutoGrader import App
from config_manager import ConfigManager
from sheet_export import NAME_PATTERNS, identity_confirmed, plan_export, sheet_name
from test_sheet_identity import FakeGrader, SheetApp
from test_student_matching import ROSTER, sheet
from review_window import ReviewWindow
from translations import TRANSLATIONS


class ExportApp(SheetApp):
    export_named_sheets = App.export_named_sheets


def student(name, klass, **fields):
    return dict({'id': '', 'name': name, 'class': klass, 'room': '', 'seat': ''}, **fields)


class TestNaming(unittest.TestCase):
    def test_sheet_names(self):
        zhang = student('张三', '701', id='23090828', room='01', seat='5')
        self.assertEqual({key: sheet_name(zhang, pattern) for key, pattern in NAME_PATTERNS.items()},
                         {'class_name': '701-张三', 'class_name_id': '701-张三-23090828', 'id_name': '23090828-张三', 'room_seat_name': '01-5-张三'})
        # Empty fields leave no stray separators; characters that file names cannot hold are replaced
        self.assertEqual(sheet_name(student('张三', '701'), NAME_PATTERNS['class_name_id']), '701-张三')
        self.assertEqual(sheet_name(student('张三', ''), NAME_PATTERNS['room_seat_name']), '张三')
        self.assertEqual(sheet_name(student('张三', '7/1:班'), NAME_PATTERNS['class_name']), '7_1_班-张三')
        self.assertEqual(sheet_name(student('张三', '未知'), NAME_PATTERNS['class_name']), '张三')

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

    def test_plan_names_and_suffixes(self):
        confirmed = {'student_match': {'method': 'class_name'}}
        sheets = [
            (dict(confirmed, db_student_info=student('张三', '701')), '/s/IMG_0001.jpg'),
            (dict(confirmed, db_student_info=student('张三', '701')), '/s/IMG_0002.jpg'),
            (dict(confirmed, db_student_info=student('Tom', '7A')), '/s/IMG_0003.png'),
            (dict(confirmed, db_student_info=student('tom', '7a')), '/s/IMG_0004.png'),
            ({'db_student_info': student('未知', '未知'), 'student_match': {'method': 'unmatched'}}, '/s/IMG_0005.jpg'),
            (dict(confirmed, db_student_info=student('李四', '701')), None),  # Image missing
        ]
        plan = plan_export(sheets, NAME_PATTERNS['class_name'], '待核对')
        self.assertEqual([(os.path.basename(path), name, ok) for path, name, ok, _ in plan], [
            ('IMG_0001.jpg', '701-张三.jpg', True),
            ('IMG_0002.jpg', '701-张三_1.jpg', True),
            ('IMG_0003.png', '7A-Tom.png', True),
            ('IMG_0004.png', '7a-tom_1.png', True),
            ('IMG_0005.jpg', '待核对-IMG_0005.jpg', False),
        ])


class TestExport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.exam = Path(self.tmp.name) / "exam"
        self.exam.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def grade(self, sheets, lang="CN"):
        for i, name in enumerate(sheets):
            Image.new("RGB", (8, 8), (40 * i, 0, 0)).save(self.exam / name)
        app = ExportApp(self.exam, ROSTER)
        app.current_lang = lang
        grader = FakeGrader(sheets)
        for name in sheets:
            self.assertTrue(app.process_single_file(grader, "rubric", name, str(self.exam), False, 1), app.logs)
        return app

    def snapshot(self):
        """Every file outside the export folder, with its bytes."""
        return {str(p.relative_to(self.exam)): p.read_bytes() for p in self.exam.rglob('*')
                if p.is_file() and p.parts[len(self.exam.parts)] not in ('导出答题卡', 'exported_sheets')}

    def test_export_names_copies_and_lists_without_touching_originals(self):
        app = self.grade({"IMG_0001.jpg": sheet('张三', '701'), "IMG_0002.jpg": sheet('张三', '701'), "IMG_0003.jpg": sheet('王小名', '701'),
                          "IMG_0004.jpg": sheet('张五', '701'), "01-05缺.jpg": sheet('孙七', '702')})
        before = self.snapshot()
        dest, plan, missing = app.export_named_sheets('class_name')
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(missing, 0)
        dest = Path(dest)
        self.assertEqual(dest.parent, self.exam / "导出答题卡")
        self.assertEqual(sorted(os.listdir(dest)), ['701-张三.jpg', '701-张三_1.jpg', '702-孙七.jpg', '导出清单.csv',
                                                    '待核对-IMG_0003.jpg', '待核对-IMG_0004.jpg'])
        for path, name, _, _ in plan:
            self.assertEqual((dest / name).read_bytes(), Path(path).read_bytes(), name)
        with open(dest / '导出清单.csv', encoding='utf-8-sig') as f:
            rows = {r['导出文件']: r for r in csv.DictReader(f)}
        self.assertEqual([rows['702-孙七.jpg'][k] for k in ('状态', '班级', '姓名', '考号', '匹配方式', '原始文件', '当前文件')],
                         ['已确认', '702', '孙七', '23090828', '文件名考场座号', '01-05缺.jpg', '01-05缺.jpg'])
        self.assertEqual([rows['待核对-IMG_0003.jpg'][k] for k in ('状态', '姓名', '匹配方式')], ['待核对', '王小明', '班级+相近姓名(请核对)'])

        # Confirmed in review: the next export uses the student's name, in a new folder; the first stays as it was
        report = self.exam / "阅卷报告" / "IMG_0003.json"
        data = json.loads(report.read_text(encoding='utf-8'))
        data['review_count'] = 1
        report.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        before = self.snapshot()
        first = sorted(os.listdir(dest))
        second, plan, _ = app.export_named_sheets('room_seat_name')
        self.assertNotEqual(Path(second), dest)
        self.assertEqual(sorted(os.listdir(dest)), first)
        self.assertIn('王小明.jpg', os.listdir(second))
        self.assertIn('01-5-孙七.jpg', os.listdir(second))
        self.assertEqual(self.snapshot(), before)

    def test_older_reports_find_their_image_by_name(self):
        reports, success = self.exam / "阅卷报告", self.exam / "成功归档"
        reports.mkdir()
        success.mkdir()
        Image.new("RGB", (8, 8), "white").save(success / "05-01.png")
        (reports / "05-01.json").write_text(json.dumps({"db_student_info": student('赵六', '703')}, ensure_ascii=False), encoding='utf-8')
        (reports / "05-02.json").write_text(json.dumps({"db_student_info": student('钱九', '703')}, ensure_ascii=False), encoding='utf-8')
        dest, plan, missing = ExportApp(self.exam).export_named_sheets('class_name')
        self.assertEqual((sorted(os.listdir(dest)), missing), (['703-赵六.png', '导出清单.csv'], 1))

    def test_export_in_english(self):
        app = self.grade({"IMG_0001.jpg": sheet('张三', '701'), "IMG_0004.jpg": sheet('张五', '701')}, lang="EN")
        dest, plan, _ = app.export_named_sheets('class_name')
        self.assertEqual(Path(dest).parent.name, "exported_sheets")
        self.assertEqual(sorted(os.listdir(dest)), ['701-张三.jpg', 'CHECK-IMG_0004.jpg', 'export_list.csv'])
        with open(Path(dest) / 'export_list.csv', encoding='utf-8-sig') as f:
            self.assertEqual(next(csv.reader(f))[:3], ['Exported File', 'Status', 'Class'])


class TestExportDialog(unittest.TestCase):
    """Export from the real review window: its button, the dialog, the background copy and the prompt after the last sheet."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.exam = root / "exam"
        (self.exam / "成功归档").mkdir(parents=True)
        (self.exam / "阅卷报告").mkdir()
        records = {"IMG_0001.jpg": (student('张三', '701', id='1001'), 'class_name'), "IMG_0002.jpg": (student('未知', '未知'), 'unmatched')}
        for name, (info, method) in records.items():
            Image.new("RGB", (8, 8), "white").save(self.exam / "成功归档" / name)
            report = {"original_filename": name, "db_student_info": info, "student_match": {"method": method, "candidates": []}, "total_score": 5, "details": []}
            (self.exam / "阅卷报告" / name.replace('.jpg', '.json')).write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
        with patch('AutoGrader.ConfigManager', return_value=ConfigManager(str(root / 'config.json'))):
            self.app = App()
        self.app.withdraw()
        self.app.exam_folder = str(self.exam)
        dialogs = self.dialogs = []

        class Capture(AutoGrader.ExportSheetsDialog):
            def __init__(self, *args):
                super().__init__(*args)
                dialogs.append(self)
        self.capture = patch('AutoGrader.ExportSheetsDialog', Capture)
        self.capture.start()

    def tearDown(self):
        self.capture.stop()
        self.app.destroy()
        self.tmp.cleanup()

    def open_review(self):
        return ReviewWindow(self.app, str(self.exam), self.app.student_manager, self.app.on_review_save, lang='CN', translations=TRANSLATIONS)

    def test_nothing_to_export_and_grading_running(self):
        with patch('AutoGrader.messagebox.showinfo') as info:
            self.app.exam_folder = ""
            self.app.open_export_dialog()
            self.app.exam_folder, self.app.processing = str(self.exam), True
            self.app.open_export_dialog()
        self.assertEqual([c.args[1] for c in info.call_args_list], [self.app.t("msg_export_nothing"), self.app.t("msg_export_busy")])
        self.assertEqual(self.dialogs, [])

    def test_review_button_previews_and_exports(self):
        answers = []

        def ask(title, message, **kwargs):
            answers.append(message)
            self.app.after(0, self.app.quit)
            return False
        review = self.open_review()
        with patch('AutoGrader.messagebox.askyesno', side_effect=ask):
            review.btn_export.invoke()
            dialog = self.dialogs[0]
            self.assertIs(dialog.master, review)
            self.assertIn("共 2 张：1 张按学生命名；1 张学生未确认", dialog.lbl_summary.cget('text'))
            self.assertEqual(dialog.lbl_examples.cget('text'), "例：701-张三.jpg、待核对-IMG_0002.jpg")
            dialog.combo_pattern.set("考号-姓名")
            dialog.update_preview()
            self.assertEqual(dialog.lbl_examples.cget('text'), "例：1001-张三.jpg、待核对-IMG_0002.jpg")
            dialog.btn_confirm.invoke()
            watchdog = self.app.after(10000, self.app.quit)
            self.app.mainloop()
            self.app.after_cancel(watchdog)
        self.assertEqual(len(answers), 1, "export did not finish")
        exports = os.listdir(self.exam / "导出答题卡")
        self.assertEqual(len(exports), 1)
        self.assertEqual(sorted(os.listdir(self.exam / "导出答题卡" / exports[0])), ['1001-张三.jpg', '导出清单.csv', '待核对-IMG_0002.jpg'])
        self.assertIn("已导出 2 张答题卡", self.app.log_box.get('1.0', 'end'))
        review.destroy()

    def test_confirming_the_last_sheet_offers_export(self):
        review = self.open_review()
        review.current_index = len(review.image_files) - 1
        review.load_current_student()
        with patch('review_window.messagebox.askyesno', return_value=True) as ask:
            review.confirm_all_and_next()
        self.assertIn("现在按学生导出命名答题卡吗", ask.call_args.args[1])
        self.assertFalse(review.winfo_exists())
        self.assertEqual(len(self.dialogs), 1)


if __name__ == "__main__":
    unittest.main()
