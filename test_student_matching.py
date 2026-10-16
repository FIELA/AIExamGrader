"""Matching answer sheets to the roster by handwritten class and name, and the 缺 (absent) mark, run headless."""
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from AutoGrader import App
from report_files import record_image_name
from review_window import ReviewWindow
from student_manager import StudentManager, class_parts, same_class
from test_sheet_identity import FakeGrader, ReviewStub, SheetApp
from translations import TRANSLATIONS

ROSTER = [
    {'id': '', 'name': '张三', 'class': '701', 'room': '', 'seat': ''},
    {'id': '', 'name': '张四', 'class': '701', 'room': '', 'seat': ''},
    {'id': '', 'name': '李四', 'class': '701', 'room': '', 'seat': ''},
    {'id': '', 'name': '王小明', 'class': '701', 'room': '', 'seat': ''},
    {'id': '', 'name': '张三', 'class': '702', 'room': '', 'seat': ''},
    {'id': '23090828', 'name': '孙七', 'class': '702', 'room': '01', 'seat': '5'},
    {'id': '', 'name': '赵六', 'class': '703', 'room': '', 'seat': ''},
    {'id': '', 'name': '李西', 'class': '703', 'room': '', 'seat': ''},
    {'id': '', 'name': '阿依古丽·买买提', 'class': '703', 'room': '', 'seat': ''},
]


def sheet(name='', klass='', **fields):
    """OCR fields of a sheet without exam numbers unless given."""
    return dict({'ocr_name': name, 'ocr_class': klass, 'ocr_id_written': '', 'ocr_id_filled': ''}, **fields)


class TestResolveStudent(unittest.TestCase):
    def setUp(self):
        self.manager = StudentManager()
        self.manager.students = [dict(s) for s in ROSTER]

    def resolve(self, ocr, filename="IMG_0001.jpg"):
        student, match = self.manager.resolve_student(filename, ocr)
        return student['name'], student['class'], match['method']

    def test_class_and_name(self):
        for klass in ('701', '701班', '7(1)班', '七年级一班', '初一1班', '7 . 1', '0701'):
            with self.subTest(klass=klass):
                self.assertEqual(self.resolve(sheet('张三', klass)), ('张三', '701', 'class_name'))
        self.assertEqual(self.resolve(sheet('张三', '702')), ('张三', '702', 'class_name'))
        self.assertEqual(self.resolve(sheet('张 三', '701')), ('张三', '701', 'class_name'))
        self.assertEqual(self.resolve(sheet('阿依古丽•买买提', '703')), ('阿依古丽·买买提', '703', 'class_name'))

    def test_name_alone_when_only_one_student_has_it(self):
        self.assertEqual(self.resolve(sheet('李四', '')), ('李四', '701', 'name'))
        self.assertEqual(self.resolve(sheet('李四', 'None')), ('李四', '701', 'name'))
        self.assertEqual(self.resolve(sheet('赵六', '701')), ('赵六', '703', 'name'))  # Wrong class written

    def test_similar_name_within_the_class(self):
        self.assertEqual(self.resolve(sheet('王小名', '701')), ('王小明', '701', 'class_name_similar'))

    def test_unclear_sheets_offer_candidates(self):
        cases = {
            ('张三', ''): ['张三', '张三'],      # Same name in two classes, class unreadable
            ('张五', '701'): ['张三', '张四'],   # One character from two classmates
            ('李西', '701'): ['李四', '李西'],   # Misread classmate or the same name in another class
        }
        for (name, klass), candidates in cases.items():
            with self.subTest(name=name):
                student, match = self.manager.resolve_student("IMG_0001.jpg", sheet(name, klass))
                self.assertEqual((student['name'], match['method']), ('未知', 'ambiguous'))
                self.assertEqual([c['name'] for c in match['candidates']], candidates)
        student, match = self.manager.resolve_student("IMG_0001.jpg", sheet('孙八', '701'))
        self.assertEqual((student['name'], match['method'], [c['name'] for c in match['candidates']]), ('未知', 'unmatched', ['孙七']))
        for name in ('钱九', '张', '无', ''):
            with self.subTest(name=name):
                self.assertEqual(self.resolve(sheet(name, '701')), ('未知', '未知', 'unmatched'))

    def test_two_classmates_with_one_name(self):
        self.manager.students = [dict(ROSTER[0], id='1'), dict(ROSTER[0], id='2')]
        student, match = self.manager.resolve_student("IMG_0001.jpg", sheet('张三', '701'))
        self.assertEqual((student['name'], match['method'], len(match['candidates'])), ('未知', 'ambiguous', 2))

    def test_file_name_and_exam_numbers_come_first(self):
        self.assertEqual(self.resolve(sheet('张三', '701'), "1-5.jpg"), ('孙七', '702', 'filename'))
        self.assertEqual(self.resolve(sheet('张三', '701', ocr_id_filled='23090828')), ('孙七', '702', 'id_filled'))
        self.assertEqual(self.resolve(sheet('张三', '701', ocr_id_written='023090828')), ('孙七', '702', 'id_written'))
        self.assertEqual(self.resolve(sheet('张三', '701', ocr_room='1', ocr_seat='05')), ('孙七', '702', 'room_seat'))
        self.assertEqual(self.resolve(sheet('张三', '701', ocr_id_filled='99999999')), ('张三', '701', 'class_name'))

    def test_without_roster(self):
        self.assertEqual(StudentManager().resolve_student("IMG_0001.jpg", sheet('张三', '701'))[1]['method'], 'unmatched')

    def test_class_labels(self):
        labels = {'701': (7, 1), '701班': (7, 1), '7(1)班': (7, 1), '七年级一班': (7, 1), '初一1班': (7, 1), '初中一年级3班': (7, 3),
                  '高二3班': (11, 3), '0701': (7, 1), '3班': (None, 3), '十一班': (None, 11), '2023级1班': (2023, 1),
                  '实验班': None, '': None}
        for label, parts in labels.items():
            self.assertEqual(class_parts(label), parts, label)
        self.assertTrue(same_class('1班', '701'))
        self.assertTrue(same_class('实验班', '实验'))
        self.assertFalse(same_class('701', '702'))
        self.assertFalse(same_class('701', '801'))
        self.assertFalse(same_class('', '701'))


class ReviewWithCsv(ReviewStub):
    """Review stand-in that also updates the summary CSV and reads reports like the review window."""
    t = ReviewWindow.t
    update_csv_row = ReviewWindow.update_csv_row
    find_report_json = ReviewWindow.find_report_json
    report_student = ReviewWindow.report_student
    search_student = ReviewWindow.search_student

    def __init__(self, app, json_path):
        super().__init__(app, json_path)
        self.exam_folder = app.exam_folder
        self.lang, self.translations = 'CN', TRANSLATIONS
        self.on_save_callback = None
        self.image_files = [os.path.join(app.get_folder_path('success'), record_image_name(self.current_data))]


class TestMatchingFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.exam = Path(self.tmp.name) / "exam"
        self.exam.mkdir()
        self.reports = self.exam / "阅卷报告"
        self.success = self.exam / "成功归档"

    def tearDown(self):
        self.tmp.cleanup()

    def grade(self, sheets, students=ROSTER):
        for name in sheets:
            Image.new("RGB", (8, 8), "white").save(self.exam / name)
        app = SheetApp(self.exam, students)
        grader = FakeGrader(sheets)
        for name in sheets:
            self.assertTrue(app.process_single_file(grader, "rubric", name, str(self.exam), False, 1), app.logs)
        return app

    def summary_rows(self, filename="成绩汇总表.csv"):
        with open(self.exam / "阅卷数据" / filename, encoding='utf-8-sig') as f:
            return list(csv.DictReader(f))

    def report(self, name):
        return json.loads((self.reports / name).read_text(encoding='utf-8'))

    def test_sheets_without_exam_numbers_are_matched_by_class_and_name(self):
        app = self.grade({"IMG_0001.jpg": sheet('张三', '701'), "IMG_0002.jpg": sheet('李 四', '7(1)班'),
                          "IMG_0003.jpg": sheet('王小名', '701'), "IMG_0004.jpg": sheet('钱九', '701')})
        expected = {
            'IMG_0001.jpg': ('张三', '701', '班级+姓名', '一致'),
            'IMG_0002.jpg': ('李四', '701', '班级+姓名', '一致'),
            'IMG_0003.jpg': ('王小明', '701', '班级+相近姓名(请核对)', '不符'),
            'IMG_0004.jpg': ('未知', '未知', '未匹配名单(请复核)', '不符'),
        }
        written = {r['原始文件']: (r['姓名'], r['班级'], r['匹配方式'], r['信息一致性'][:2]) for r in app.csv_rows}
        self.assertEqual(written, expected)
        self.assertEqual(self.report('IMG_0003.json')['student_match']['method'], 'class_name_similar')
        self.assertIn('- **学生匹配**: 班级+相近姓名(请核对)', (self.reports / 'IMG_0003.md').read_text(encoding='utf-8'))

        App.regenerate_csv_from_jsons(app)
        rebuilt = {r['原始文件']: (r['姓名'], r['班级'], r['匹配方式'], r['信息一致性'][:2]) for r in self.summary_rows()}
        self.assertEqual(rebuilt, expected)
        app.current_lang = "EN"
        App.regenerate_csv_from_jsons(app)
        self.assertEqual(sorted(r['Match Method'] for r in self.summary_rows("Grade_Summary.csv")),
                         ['Class + name', 'Class + name', 'Class + similar name (check)', 'Not in roster (review)'])

        app.current_lang = "CN"
        app.log_student_matches()
        self.assertTrue(any("2 张已对应名单，2 张需核对；名单中 6 人没有答题卡" in line for line in app.logs), app.logs)

    def test_unclear_sheet_report_lists_candidates(self):
        self.grade({"IMG_0005.jpg": sheet('张五', '701')})
        self.assertIn("  - 候选: 张三(701) / 张四(701)", (self.reports / 'IMG_0005.md').read_text(encoding='utf-8'))

    def test_absent_mark_in_scan_name_reaches_the_summary(self):
        sheets = {"01-05缺.jpg": sheet('孙七', '702'), "IMG_0009缺.jpg": sheet('赵六', '703', ocr_id_filled='12345678'),
                  "IMG_0010.jpg": sheet('李四', '701')}
        app = self.grade(sheets)
        self.assertEqual(sorted(os.listdir(self.success)), ["01-05缺.jpg", "12345678.jpg", "IMG_0010.jpg"])
        expected = {'01-05缺.jpg': '是', 'IMG_0009缺.jpg': '是', 'IMG_0010.jpg': ''}
        self.assertEqual({r['原始文件']: r['缺考标记'] for r in app.csv_rows}, expected)
        App.regenerate_csv_from_jsons(app)
        self.assertEqual({r['原始文件']: r['缺考标记'] for r in self.summary_rows()}, expected)
        app.csv_rows.clear()
        App.regenerate_summary_csv(app)
        self.assertEqual({r['原始文件']: r['缺考标记'] for r in app.csv_rows}, expected)

    def test_regrade_updates_automatic_matches_but_keeps_a_teacher_choice(self):
        app = self.grade({"IMG_0003.jpg": sheet('王小名', '701')})
        image = str(self.success / "IMG_0003.jpg")
        app.grader_engine = FakeGrader({"IMG_0003.jpg": sheet('王小明', '701')})
        self.assertEqual(app.regrade_single_file(image), (True, "Success"))
        data = self.report('IMG_0003.json')
        self.assertEqual((data['db_student_info']['name'], data['student_match']['method']), ('王小明', 'class_name'))
        app.grader_engine = FakeGrader({"IMG_0003.jpg": sheet('张三', '701')})
        self.assertEqual(app.regrade_single_file(image), (True, "Success"))
        data = self.report('IMG_0003.json')
        self.assertEqual((data['db_student_info']['name'], data['student_match']['method']), ('张三', 'class_name'))

        data['db_student_info'] = dict(ROSTER[2])
        data['student_match'] = {'method': 'manual', 'candidates': []}
        (self.reports / 'IMG_0003.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        self.assertEqual(app.regrade_single_file(image), (True, "Success"))
        data = self.report('IMG_0003.json')
        self.assertEqual((data['db_student_info']['name'], data['student_match']['method']), ('李四', 'manual'))

    def test_summary_names_a_student_found_on_several_sheets(self):
        app = self.grade({"IMG_0001.jpg": sheet('张三', '701'), "IMG_0002.jpg": sheet('张三', '701')})
        app.log_student_matches()
        self.assertTrue(any("张三(701) 对应了多张答题卡：IMG_0001.jpg、IMG_0002.jpg" in line for line in app.logs), app.logs)

    def test_review_choice_is_recorded_and_written_to_the_summary(self):
        app = self.grade({"IMG_0005.jpg": sheet('张五', '701'), "01-05缺.jpg": sheet('孙七', '702'), "IMG_0001.jpg": sheet('张三', '701')})
        App.regenerate_csv_from_jsons(app)
        with patch('review_window.messagebox.showerror', side_effect=AssertionError):
            # Confirming the automatic match keeps how it was found
            review = ReviewWithCsv(app, self.reports / "IMG_0001.json")
            review.bind_selected_student(ReviewWindow.student_display(ROSTER[0]))
            self.assertEqual(review.current_data['student_match']['method'], 'class_name')

            review = ReviewWithCsv(app, self.reports / "IMG_0005.json")
            self.assertEqual([c['name'] for c in review.current_data['student_match']['candidates']], ['张三', '张四'])
            review.bind_selected_student(ReviewWindow.student_display(ROSTER[1]))
            self.assertEqual(review.current_data['student_match']['method'], 'manual')
            review.save_to_disk()
            review.update_csv_row()

            # A seat student rebound to one without an ID or seat keeps the 缺 mark and clears the old ID and seat
            review = ReviewWithCsv(app, self.reports / "01-5.json")
            review.bind_selected_student(ReviewWindow.student_display(ROSTER[2]))
            self.assertTrue(review.current_data['db_student_info']['is_absent'])
            review.save_to_disk()
            review.update_csv_row()

        rows = {r['原始文件']: r for r in self.summary_rows()}
        self.assertEqual([rows['IMG_0005.jpg'][k] for k in ('姓名', '班级', '考号', '匹配方式')], ['张四', '701', '', '复核时选定'])
        self.assertEqual([rows['01-05缺.jpg'][k] for k in ('姓名', '考号', '考场', '座号', '匹配方式')], ['李四', '', '', '', '复核时选定'])
        self.assertEqual(self.report('01-5.json')['db_student_info']['name'], '李四')

    def test_review_search_finds_sheets_by_matched_name(self):
        app = self.grade({"IMG_0001.jpg": sheet('张三', '701'), "IMG_0002.jpg": sheet('李四', '701')})
        review = ReviewWithCsv(app, self.reports / "IMG_0001.json")
        review.image_files = [str(self.success / "IMG_0001.jpg"), str(self.success / "IMG_0002.jpg")]
        review.entry_search = type("Entry", (), {"get": lambda self: "李四"})()
        review.load_current_student = lambda: None
        with patch('review_window.messagebox.showinfo', side_effect=AssertionError("not found")):
            review.search_student()
        self.assertEqual(review.current_index, 1)


if __name__ == "__main__":
    unittest.main()
