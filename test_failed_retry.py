"""Failed scans must be retried from either archive name, and never count as finished."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from AutoGrader import App
from config_manager import ConfigManager
import score_marks
from test_sheet_identity import SheetApp


class RetryApp(SheetApp):
    process_images = App.process_images
    _verify_files_sync = App._verify_files_sync
    log_final_check = App.log_final_check
    regenerate_csv_from_jsons = App.regenerate_csv_from_jsons

    def ui_after(self, delay, callback, *args):
        if not delay:  # The post-batch review prompt is tested separately, without opening a window.
            callback(*args)

    def check_completion_status(self): pass
    def reset_ui_state(self): pass


class TestFailedRetry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def app(self, folder_lang='CN', ui_lang='CN'):
        exam = Path(self.tmp.name) / f'{self._testMethodName}-{folder_lang}-{ui_lang}'
        exam.mkdir()
        app = RetryApp(exam)
        app.current_lang = folder_lang
        for key in ('success', 'failed', 'reports', 'grading_data', 'original_files'):
            Path(app.get_folder_path(key)).mkdir()
        app.current_lang = ui_lang
        self.addCleanup(app.score_marks.drain, 10)
        return app

    def scan(self, app, name, folder='failed'):
        path = Path(app.get_folder_path(folder)) / name if folder else Path(app.exam_folder) / name
        Image.new('RGB', (8, 8), 'white').save(path)
        (Path(app.get_folder_path('original_files')) / name).write_bytes(path.read_bytes())
        return path

    def report(self, app, name, renamed=None):
        data = self.result()
        data['original_filename'] = name
        data['db_student_info'] = {'name': 'Test Student', 'class': 'Test Class', 'room': '', 'seat': ''}
        if renamed:
            data['renamed_filename'] = renamed
        path = Path(app.get_folder_path('reports')) / (Path(name).stem + '.json')
        path.write_text(json.dumps(data), encoding='utf-8')
        path.with_suffix('.md').write_text('test report', encoding='utf-8')
        app.regenerate_csv_from_jsons()
        return path

    @staticmethod
    def result():
        return {'total_score': 8, 'details': [{'question_id': '1', 'type': '客观题',
                'student_answer': 'A', 'score': 8, 'max_score': 8}]}

    def run_batch(self, app, results):
        grader = Mock()
        grader.grade_exam.side_effect = results
        app._create_grader = lambda: grader
        with patch('AutoGrader.time.sleep'):
            app.process_images()
        self.assertFalse(any('System Error' in line or '系统错误' in line for line in app.logs), app.logs)
        return grader, '\n'.join(app.logs)

    def csv_rows(self, app):
        name = '成绩汇总表.csv' if app.current_lang == 'CN' else 'Grade_Summary.csv'
        with (Path(app.get_folder_path('grading_data')) / name).open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))

    def test_verification_finds_failed_scans_with_an_empty_root_in_either_language(self):
        for folder_lang, ui_lang in [('CN', 'CN'), ('EN', 'EN'), ('CN', 'EN'), ('EN', 'CN')]:
            with self.subTest(folder_lang=folder_lang, ui_lang=ui_lang):
                app = self.app(folder_lang, ui_lang)
                self.scan(app, 'pending.jpg')
                self.assertEqual(app._verify_files_sync(), ([], [], [], ['pending.jpg']))

    def test_normal_start_retries_failed_archive_and_keeps_completed_reports(self):
        for folder_lang, ui_lang in [('CN', 'CN'), ('EN', 'EN'), ('CN', 'EN'), ('EN', 'CN')]:
            with self.subTest(folder_lang=folder_lang, ui_lang=ui_lang):
                app = self.app(folder_lang, ui_lang)
                self.scan(app, 'done.jpg', 'success')
                previous = self.report(app, 'done.jpg')
                saved = previous.read_bytes()
                pending = self.scan(app, 'pending.jpg')
                original = pending.read_bytes()
                grader, logs = self.run_batch(app, [self.result()])
                grader.grade_exam.assert_called_once()
                self.assertEqual(grader.grade_exam.call_args.args[1], str(pending))
                self.assertFalse(pending.exists())
                self.assertEqual((Path(app.get_folder_path('success')) / 'pending.jpg').read_bytes(), original)
                self.assertEqual(previous.read_bytes(), saved)
                self.assertEqual(len(self.csv_rows(app)), 2)
                self.assertIn(app.t('msg_finished'), logs)
                self.assertEqual(app._verify_files_sync(), ([], [], [], []))

    def test_retry_failure_stays_visible_and_never_says_finished(self):
        for lang in ('CN', 'EN'):
            with self.subTest(lang=lang):
                app = self.app(lang, lang)
                pending = self.scan(app, 'pending.jpg')
                for error in ({'error': 'synthetic failure'}, RuntimeError('synthetic transport failure')):
                    with self.subTest(error=error):
                        app.logs.clear()
                        grader, logs = self.run_batch(app, [error])
                        grader.grade_exam.assert_called_once()
                        self.assertTrue(pending.exists())
                        self.assertIn('pending.jpg', logs)
                        self.assertNotIn(app.t('msg_finished'), logs)
                        self.assertIn(app.t('msg_finished_problems', count=1), logs)
                        self.assertGreater(app.log_final_check(), 0)
                # A later normal start retries the retained file without moving it out by hand.
                app.logs.clear()
                grader, logs = self.run_batch(app, [self.result()])
                grader.grade_exam.assert_called_once()
                self.assertFalse(pending.exists())
                self.assertEqual(len(self.csv_rows(app)), 1)
                self.assertIn(app.t('msg_finished'), logs)

    def test_a_failed_scan_with_an_old_report_is_still_unfinished(self):
        app = self.app()
        self.scan(app, 'pending.jpg')
        self.report(app, 'pending.jpg')
        grader, logs = self.run_batch(app, [{'error': 'synthetic failure'}])
        grader.grade_exam.assert_called_once()
        self.assertNotIn(app.t('msg_finished'), logs)
        self.assertIn(app.t('msg_finished_problems', count=1), logs)
        self.assertIn('答题卡: 1, JSON: 1, Markdown: 1, CSV: 1', logs)

    def test_a_new_failure_is_retried_in_the_same_run(self):
        app = self.app()
        self.scan(app, 'new.jpg', folder=None)
        grader, logs = self.run_batch(app, [{'error': 'temporary failure'}, self.result()])
        self.assertEqual(grader.grade_exam.call_count, 2)
        self.assertEqual(Path(grader.grade_exam.call_args_list[0].args[1]).parent, Path(app.exam_folder))
        self.assertEqual(Path(grader.grade_exam.call_args_list[1].args[1]).parent, Path(app.get_folder_path('failed')))
        self.assertTrue((Path(app.get_folder_path('success')) / 'new.jpg').is_file())
        self.assertIn(app.t('msg_finished'), logs)

    def test_verification_checks_success_archive_and_respects_renamed_reports(self):
        app = self.app()
        self.scan(app, 'renamed.jpg', 'success')
        self.report(app, 'scan.jpg', renamed='renamed.jpg')
        self.assertEqual(app._verify_files_sync(), ([], [], [], []))
        (Path(app.get_folder_path('reports')) / 'scan.md').unlink()
        self.assertEqual(app._verify_files_sync(), (['renamed.jpg'], [], [], []))

    def test_a_missing_summary_is_rebuilt_without_regrading_completed_scans(self):
        app = self.app()
        self.scan(app, 'renamed.jpg', 'success')
        report = self.report(app, 'scan.jpg', renamed='renamed.jpg')
        saved = report.read_bytes()
        (Path(app.get_folder_path('grading_data')) / '成绩汇总表.csv').unlink()
        grader, logs = self.run_batch(app, [])
        grader.grade_exam.assert_not_called()
        self.assertEqual(report.read_bytes(), saved)
        self.assertEqual(len(self.csv_rows(app)), 1)
        self.assertIn(app.t('msg_finished'), logs)

    def test_completion_prompt_checks_archives_when_the_root_is_empty(self):
        app = self.app()
        self.scan(app, 'pending.jpg')
        app.handle_verification_result = Mock()
        with patch('AutoGrader.threading.Thread') as thread:
            thread.return_value.start.side_effect = lambda: thread.call_args.kwargs['target']()
            App.check_completion_status(app)
        app.handle_verification_result.assert_called_once_with(1, [], [], [], ['pending.jpg'])


class TestFailedRetryButton(unittest.TestCase):
    def test_start_button_uses_cached_configuration_and_retries_an_empty_roots_failed_scan(self):
        for succeeds in (True, False):
            with self.subTest(succeeds=succeeds), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                exam = root / 'exam'
                failed, originals, data = (exam / name for name in ('失败归档', '原始文件', '阅卷数据'))
                for folder in (failed, originals, data):
                    folder.mkdir(parents=True)
                Image.new('RGB', (8, 8), 'white').save(failed / 'pending.jpg')
                (originals / 'pending.jpg').write_bytes((failed / 'pending.jpg').read_bytes())
                rubric = root / 'rubric.txt'
                rubric.write_text('Question 1: A, 8 points.', encoding='utf-8')
                (data / 'answer_key.json').write_text(json.dumps({'1': 'A'}), encoding='utf-8')
                (data / 'layout_config.json').write_text(json.dumps({'layout_description': 'Question 1 in center'}))
                template = score_marks.new_template({'objective': ['1'], 'subjective': []}, 'CN', [8, 8])
                template['status'] = score_marks.DISABLED
                (data / 'score_marks.json').write_text(json.dumps(template), encoding='utf-8')
                with patch('AutoGrader.ConfigManager', return_value=ConfigManager(str(root / 'config.json'))):
                    app = App()
                app.withdraw()
                app.exam_folder, app.rubric_path = str(exam), str(rubric)
                app.entry_key.insert(0, 'synthetic-test-key')
                logs, errors, completed = [], [], []
                app.log = logs.append
                app.report_callback_exception = lambda *args: errors.append(str(args))
                reset = app.reset_ui_state

                def finish():
                    reset()
                    completed.append(True)
                    app.after(100, app.quit)

                app.reset_ui_state = finish
                grader = Mock()
                grader.grade_exam.return_value = TestFailedRetry.result() if succeeds else {'error': 'synthetic failure'}
                try:
                    with patch('AutoGrader.AIGraderEngine', return_value=grader), patch('AutoGrader.time.sleep'), \
                            patch('AutoGrader.messagebox.showerror', side_effect=lambda *args: errors.append(str(args))), \
                            patch('AutoGrader.messagebox.askyesno', return_value=False):
                        timer = app.after(8000, app.quit)
                        app.after(0, app.btn_start.invoke)
                        app.mainloop()
                        app.after_cancel(timer)
                    self.assertTrue(completed, 'The start-button pipeline did not finish')
                    self.assertFalse(errors, errors)
                    grader.grade_exam.assert_called_once()
                    self.assertEqual(grader.grade_exam.call_args.args[1], str(failed / 'pending.jpg'))
                    text = '\n'.join(logs)
                    self.assertIn('正在重试 1 个失败文件', text)
                    self.assertEqual(app.btn_start.cget('state'), 'normal')
                    if succeeds:
                        self.assertIn(app.t('msg_finished'), text)
                        self.assertFalse((failed / 'pending.jpg').exists())
                        self.assertTrue((exam / '成功归档' / 'pending.jpg').is_file())
                        self.assertIn('答题卡: 1, JSON: 1, Markdown: 1, CSV: 1', text)
                    else:
                        self.assertNotIn(app.t('msg_finished'), text)
                        self.assertIn(app.t('msg_finished_problems', count=1), text)
                        self.assertTrue((failed / 'pending.jpg').is_file())
                finally:
                    app.score_marks.drain(10)
                    app.destroy()


if __name__ == '__main__':
    unittest.main()
