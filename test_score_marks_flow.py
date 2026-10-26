"""
The scores written on the graded sheets, through the app's real paths: grading, review (also while the summary CSV
exists, when the review saves without the app's callback), steps in image mode, regrading, re-grading the objective
questions, the backups at the start of grading and the renaming once the review is finished.
"""
import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import DEFAULT, Mock, patch

from PIL import Image

import score_marks as sm
from AutoGrader import App
from config_manager import ConfigManager
from review_window import ReviewWindow
from score_marks_service import write_json_atomic
from test_score_marks import report, scan, template
from translations import TRANSLATIONS

ROSTER = [{'id': '', 'name': '张三', 'class': '701', 'room': '', 'seat': ''},
          {'id': '', 'name': '李四', 'class': '701', 'room': '', 'seat': ''}]
SHEETS = [('IMG_0001.jpg', 0, (3, 3, 2, 2)), ('IMG_0002.jpg', 1, (3, 0, 4, 1))]  # Scan, student, scores


def details(q1, q2, s1, s2):
    return report([('1', q1), ('2', q2)], [('17(1)', s1, 4), ('17(2)', s2, 4)])


class MarkedExam(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.exam = self.root / 'exam'
        self.originals, self.success = self.exam / '原始文件', self.exam / '成功归档'
        self.reports, self.data = self.exam / '阅卷报告', self.exam / '阅卷数据'
        for folder in (self.originals, self.success, self.reports, self.data):
            folder.mkdir(parents=True)
        for name, who, points in SHEETS:
            scan(self.originals / name, quality=90)
            shutil.copy2(self.originals / name, self.success / name)
            data = dict(details(*points), original_filename=name, db_student_info=dict(ROSTER[who]),
                        student_match={'method': 'class_name', 'candidates': []})
            write_json_atomic(self.reports / name.replace('.jpg', '.json'), data)
        self.template = template()
        self.template['ever_enabled'] = True
        write_json_atomic(self.data / 'score_marks.json', self.template)
        with patch('AutoGrader.ConfigManager', return_value=ConfigManager(str(self.root / 'config.json'))):
            self.app = App()
        self.app.withdraw()
        self.app.exam_folder = str(self.exam)
        self.app.student_manager.students = [dict(s) for s in ROSTER]
        self.service = self.app.score_marks
        self.messages = patch.multiple('review_window.messagebox', showinfo=DEFAULT, showerror=DEFAULT)
        self.dialogs = self.messages.start()

    def tearDown(self):
        self.messages.stop()
        self.service.drain(10)
        self.app.destroy()
        self.tmp.cleanup()

    def json_path(self, name):
        return str(self.reports / name.replace('.jpg', '.json'))

    def saved(self, name):
        return json.loads(Path(self.json_path(name)).read_text(encoding='utf-8'))

    def wait(self):
        self.assertTrue(self.service.drain(15))
        self.app.update()  # Main-thread messages: logs and refreshing the review

    def assert_marked_as_saved(self, name, archive=None):
        marker = sm.read_marker(self.success / (archive or name))
        self.assertIsNotNone(marker, f"{archive or name} has no scores")
        self.assertEqual(marker['scores'], sm.sheet_marks(self.saved(name), self.template).digest)
        self.assertEqual(sm.classify_archive(self.success / (archive or name), self.originals / name,
                                             sm.file_sha256(self.originals / name)), 'ours')

    def open_review(self, text_mode=True):
        review = ReviewWindow(self.app, str(self.exam), self.app.student_manager, self.app.on_review_save,
                              lang='CN', translations=TRANSLATIONS)
        if text_mode:
            review.toggle_view_mode()  # Text mode: the whole sheet is confirmed at once
        return review

    @staticmethod
    def confirm(review):
        review.last_confirm_time = 0
        review.confirm_all_and_next()
        if review.winfo_exists() and review.advance_job:
            review.advance_now()

    @staticmethod
    def type_score(review, qid, value):
        entry = review.sub_entries[qid][0]
        entry.delete(0, 'end')
        entry.insert(0, str(value))


class TestReview(MarkedExam):
    def test_confirming_with_the_summary_csv_present_redraws_the_sheet(self):
        self.app.regenerate_csv_from_jsons()  # The review then saves by itself, without the app's callback
        self.assertTrue(list(self.data.glob('*.csv')))
        with patch.object(self.app, 'on_review_save', wraps=self.app.on_review_save) as callback:
            review = self.open_review()
            callback.reset_mock()
            self.assertEqual(Path(review.image_files[review.current_index]).name, 'IMG_0001.jpg')
            self.type_score(review, '17(1)', 4)
            self.confirm(review)
            self.wait()
            callback.assert_not_called()
        self.assertEqual(self.saved('IMG_0001.jpg')['total_score'], 12)
        self.assert_marked_as_saved('IMG_0001.jpg')
        self.assertEqual(sm.file_sha256(self.originals / 'IMG_0001.jpg'),
                         sm.file_sha256(self.success.parent / '原始文件' / 'IMG_0001.jpg'))
        # Reviewing it again redraws it again
        review.destroy()
        review = self.open_review()
        review.current_index = [Path(f).name for f in review.image_files].index('IMG_0001.jpg')
        review.load_current_student()  # The review opens at the first sheet not reviewed yet
        self.type_score(review, '17(2)', 0)
        self.confirm(review)
        self.wait()
        self.assertEqual(self.saved('IMG_0001.jpg')['total_score'], 10)
        self.assert_marked_as_saved('IMG_0001.jpg')
        if review.winfo_exists():
            review.destroy()

    def test_steps_in_image_mode_save_and_redraw(self):
        review = self.open_review(text_mode=False)
        self.assertEqual(review.steps[review.current_step_index]['type'], 'info')
        review.next_step()  # Student
        review.next_step()  # Multiple choice
        self.assertEqual(review.steps[review.current_step_index]['type'], 'subj')
        self.type_score(review, '17(2)', 0)
        review.next_step()
        self.wait()
        self.assertEqual(self.saved('IMG_0001.jpg')['total_score'], 8)
        self.assert_marked_as_saved('IMG_0001.jpg')
        if review.winfo_exists():
            review.destroy()

    def test_a_review_that_cannot_be_saved_stays_on_the_sheet(self):
        review = self.open_review()
        with patch.object(self.service, 'commit_report', side_effect=OSError('read-only disk')):
            self.type_score(review, '17(1)', 4)
            self.confirm(review)
        self.wait()
        self.assertIn('read-only disk', self.dialogs['showerror'].call_args[0][1])
        self.assertEqual(Path(review.image_files[review.current_index]).name, 'IMG_0001.jpg')  # Still here
        self.assertEqual(review.current_data.get('review_count', 0), 0)
        self.assertFalse(review.current_data.get('review_logs'))
        self.assertEqual(self.saved('IMG_0001.jpg').get('review_count', 0), 0)
        self.assertIsNone(sm.read_marker(self.success / 'IMG_0001.jpg'))
        review.destroy()

    def test_finishing_the_review_renames_the_sheets_and_keeps_their_scores(self):
        self.app.regenerate_csv_from_jsons()
        review = self.open_review()
        for _ in SHEETS:
            self.confirm(review)
        self.wait()
        self.assertFalse(review.winfo_exists())
        for name, who, _ in SHEETS:
            archive = f"701-{ROSTER[who]['name']}.jpg"
            self.assertTrue((self.success / archive).is_file(), list(self.success.iterdir()))
            self.assert_marked_as_saved(name, archive)
        self.assertEqual(self.service.scan()['ok'], 2)
        message = self.dialogs['showinfo'].call_args[0][1]
        self.assertNotIn(TRANSLATIONS['CN']['msg_marks_hint_review_done'], message)


class TestAroundTheReview(MarkedExam):
    def pump(self, seconds=0.5):
        """Let the main loop run the work queued for it (logs, refreshing the review)."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.update()
            time.sleep(0.02)

    def test_the_review_shows_the_new_scores_once_drawn(self):
        review = self.open_review(text_mode=False)
        self.assertEqual(review.view_mode, 'image')
        before = review.current_image.tobytes()
        review.scale = 0.5
        review.redraw_image()
        review.canvas.xview_moveto(0.25)
        view = review.canvas.xview()[0]
        review.next_step()  # Each step saves the sheet; the teacher is still on it
        self.assertEqual(Path(review.image_files[review.current_index]).name, 'IMG_0001.jpg')
        self.assertTrue(self.service.drain(15))
        self.pump()
        self.assertNotEqual(review.current_image.tobytes(), before)
        with Image.open(self.success / 'IMG_0001.jpg') as shown:
            self.assertEqual(review.current_image.tobytes(), shown.convert(review.current_image.mode).tobytes())
        self.assertEqual(review.scale, 0.5)  # Zoom and scrolling stay where the teacher had them
        self.assertAlmostEqual(review.canvas.xview()[0], view, places=2)
        # Another sheet's scores being drawn does not change the sheet on screen
        shown_now = review.current_image.tobytes()
        self.service.commit_report(self.json_path('IMG_0002.jpg'), self.saved('IMG_0002.jpg'))
        self.assertTrue(self.service.drain(15))
        self.pump()
        self.assertEqual(review.current_image.tobytes(), shown_now)
        review.destroy()

    def test_the_scores_can_be_taken_off_again(self):
        self.service.scan()
        self.wait()
        with patch('AutoGrader.messagebox') as box:
            box.askyesno.return_value = True
            self.app.restore_marked_sheets()
            self.assertTrue(self.service.drain(15))
            self.pump()
        for name, _, _ in SHEETS:
            self.assertTrue(sm.files_equal(self.success / name, self.originals / name))
        self.assertIn('已恢复 2 张', box.showinfo.call_args[0][1])
        self.assertEqual(json.loads((self.data / 'score_marks.json').read_text(encoding='utf-8'))['status'], sm.DISABLED)

    def test_sheets_without_a_backup_are_backed_up_only_when_the_teacher_confirms(self):
        self.service.scan()
        self.wait()  # Both sheets marked
        shutil.copy2(self.originals / 'IMG_0002.jpg', self.success / 'IMG_0002.jpg')  # Restored by hand: unmarked
        for name, _, _ in SHEETS:
            (self.originals / name).unlink()
        with patch('AutoGrader.messagebox') as box:
            box.askyesno.return_value = False
            self.app.offer_legacy_backup()
            self.assertIn('IMG_0002.jpg', box.askyesno.call_args[0][1])
            self.assertNotIn('IMG_0001.jpg', box.askyesno.call_args[0][1])  # It carries scores: never a scan
            self.assertFalse((self.originals / 'IMG_0002.jpg').exists())
            box.askyesno.return_value = True
            self.app.offer_legacy_backup()
        self.assertTrue((self.originals / 'IMG_0002.jpg').exists())
        self.assertFalse((self.originals / 'IMG_0001.jpg').exists())

    def test_the_choice_made_before_grading_is_kept(self):
        for status in (sm.ENABLED, sm.PENDING, sm.DISABLED):
            write_json_atomic(self.data / 'score_marks.json', dict(self.template, status=status))
            went_on = Mock()
            with patch('AutoGrader.ScoreMarksDialog', side_effect=AssertionError('asked again')):
                self.app.ensure_score_marks_and_run(went_on)
            went_on.assert_called_once_with()
        write_json_atomic(self.data / 'score_marks.json', dict(self.template, status=sm.DRAFT))
        with patch('AutoGrader.ScoreMarksDialog') as dialog:
            self.app.ensure_score_marks_and_run(Mock())
        dialog.assert_called_once()  # A draft is opened again to be finished

    def test_grading_goes_on_if_the_positions_window_cannot_open(self):
        (self.data / 'score_marks.json').unlink()
        went_on = Mock()
        with patch('AutoGrader.ScoreMarksDialog', side_effect=RuntimeError('no display')):
            self.app.ensure_score_marks_and_run(went_on)
        went_on.assert_called_once_with()

    def test_sheets_graded_before_backups_can_still_be_samples(self):
        (self.data / 'score_marks.json').unlink()
        for name, _, _ in SHEETS:
            (self.originals / name).unlink()
        reports = self.service.reports()
        self.assertEqual(sorted(Path(p).name for p in self.app.score_marks_samples(reports)), ['IMG_0001.jpg', 'IMG_0002.jpg'])
        write_json_atomic(self.data / 'score_marks.json', self.template)  # Scores were written once: no longer
        self.assertEqual(self.app.score_marks_samples(reports), [])

    def test_finishing_without_positions_says_how_to_start(self):
        (self.data / 'score_marks.json').unlink()
        self.assertEqual(self.app.score_marks_after_review(), TRANSLATIONS['CN']['msg_marks_hint_review_done'])
        write_json_atomic(self.data / 'score_marks.json', self.template)
        self.assertEqual(self.app.score_marks_after_review(), '')


class TestRegrading(MarkedExam):
    def grader(self, scores):
        engine = Mock()
        engine.grade_exam.side_effect = lambda rubric, path, layout=None: dict(details(*scores), ocr_name='张三', ocr_class='701')
        return engine

    def test_regrading_grades_the_scan_and_redraws(self):
        self.service.scan()
        self.wait()
        self.assert_marked_as_saved('IMG_0001.jpg')
        self.app.grader_engine = self.grader((3, 3, 1, 1))
        self.app.read_rubric_text = lambda: 'rubric'
        ok, message = self.app.regrade_single_file(str(self.success / 'IMG_0001.jpg'))
        self.assertTrue(ok, message)
        graded = self.app.grader_engine.grade_exam.call_args[0][1]
        self.assertEqual(Path(graded), self.originals / 'IMG_0001.jpg')  # Never the image with scores on it
        self.wait()
        self.assertEqual(self.saved('IMG_0001.jpg')['total_score'], 8)
        self.assert_marked_as_saved('IMG_0001.jpg')

    def test_a_sheet_whose_scan_is_lost_is_not_regraded(self):
        self.service.scan()
        self.wait()
        (self.originals / 'IMG_0001.jpg').unlink()
        self.app.grader_engine = self.grader((3, 3, 1, 1))
        self.app.read_rubric_text = lambda: 'rubric'
        ok, message = self.app.regrade_single_file(str(self.success / 'IMG_0001.jpg'))
        self.assertFalse(ok)
        self.assertIn('IMG_0001.jpg', message)
        self.app.grader_engine.grade_exam.assert_not_called()

    def test_regrading_the_objective_questions_redraws(self):
        self.service.scan()
        self.wait()
        self.app.answer_key = {'1': 'B', '2': 'B'}
        for name, _, _ in SHEETS:  # Q1 was answered A on both sheets
            data = self.saved(name)
            for item in data['details']:
                item['student_answer'] = 'A' if item['question_id'] == '1' else 'B'
            write_json_atomic(self.json_path(name), data)
        with patch('AutoGrader.messagebox'):
            self.app.batch_regrade_objective(['1'])
            self.wait()
        self.assertEqual(self.saved('IMG_0001.jpg')['total_score'], 7)
        for name, _, _ in SHEETS:
            self.assert_marked_as_saved(name)

    def test_backups_never_take_an_image_with_scores(self):
        self.service.scan()
        self.wait()
        (self.originals / 'IMG_0001.jpg').unlink()  # The scan is lost
        (self.root / 'rubric.txt').write_text('rubric', encoding='utf-8')
        self.app.rubric_path, self.app.current_api_key = str(self.root / 'rubric.txt'), 'fake-test-key'
        logs = []
        self.app.log = logs.append
        with patch('AutoGrader.AIGraderEngine'), patch('AutoGrader.time.sleep'):
            self.app.process_images()
        self.app.update()
        self.assertFalse((self.originals / 'IMG_0001.jpg').exists())
        self.assertTrue(any('不能把成功归档中的图片当作原图备份' in line for line in logs), logs)


class TestFirstGrading(unittest.TestCase):
    def test_scores_are_written_once_the_first_report_confirms_the_guessed_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rubric = root / 'rubric.txt'
            rubric.write_text('synthetic rubric', encoding='utf-8')
            exam = root / 'exam'
            exam.mkdir()
            for name in ('01-01.jpg', '01-02.jpg'):
                scan(exam / name, quality=90)
            key = {'1': 'A', '2': 'B', '17(1)': '寒暖流交汇', '17(2)': '北'}
            engine = Mock()
            engine.extract_answer_key_concurrent.return_value = [key] * 3
            engine.consolidate_answer_keys.return_value = (key, 'consistent')
            engine.detect_regions.return_value = engine.consolidate_layout.return_value = 'layout'
            engine.grade_exam.side_effect = lambda rubric, path, layout=None: details(3, 0, 2, 1)
            with patch('AutoGrader.ConfigManager', return_value=ConfigManager(str(root / 'config.json'))):
                app = App()
            app.rubric_path, app.exam_folder, app.current_api_key = str(rubric), str(exam), 'fake-test-key'
            app.entry_key.insert(0, 'fake-test-key')
            asked, completed, errors = [], [], []

            def marks_dialog(master, t, tpl, samples, mode, on_done, **kwargs):
                self.assertIs(threading.current_thread(), threading.main_thread())
                asked.append((mode, tpl['items']['objective'], tpl['items']['subjective'], tpl['items']['source']))
                tpl['marks'] = dict(template()['marks'])  # Placed by the teacher
                on_done('enable', tpl)

            original_reset = app.reset_ui_state

            def reset():
                original_reset()
                completed.append(True)
                app.after(100, app.quit)
            app.reset_ui_state = reset
            try:
                with patch('AutoGrader.AIGraderEngine', return_value=engine), \
                        patch('standard_answer_dialog.StandardAnswerReviewDialog', side_effect=lambda p, k, r, cb: cb(k)), \
                        patch('AutoGrader.TemplateConfirmDialog', side_effect=lambda p, layout, cb: cb(layout)), \
                        patch('AutoGrader.ScoreMarksDialog', side_effect=marks_dialog), \
                        patch('AutoGrader.messagebox.showerror', side_effect=lambda *a: errors.append(str(a))), \
                        patch('AutoGrader.time.sleep'):
                    app.after(0, app.start_grading_thread)
                    watchdog = app.after(15000, app.quit)
                    app.mainloop()
                    app.after_cancel(watchdog)
                self.assertTrue(completed, 'grading never reached reset')
                self.assertFalse(errors, errors)
                self.assertEqual(asked, [('chain', ['1', '2'], ['17(1)', '17(2)'], 'answer_key')])
                self.assertTrue(app.score_marks.drain(15))
                saved = json.loads((exam / '阅卷数据' / 'score_marks.json').read_text(encoding='utf-8'))
                self.assertEqual(saved['status'], sm.ENABLED)  # Confirmed by the first report
                for name in ('01-01.jpg', '01-02.jpg'):
                    archive, original = exam / '成功归档' / name, exam / '原始文件' / name
                    self.assertTrue(archive.is_file() and original.is_file())
                    self.assertEqual(sm.classify_archive(archive, original, sm.file_sha256(original)), 'ours')
            finally:
                app.score_marks.drain(10)
                app.destroy()


if __name__ == '__main__':
    unittest.main()
