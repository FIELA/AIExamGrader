import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image
from AutoGrader import App
from config_manager import ConfigManager
from grader_engine import AIGraderEngine


class TestGradingFlow(unittest.TestCase):
    def test_full_flow_in_isolated_folder(self):
        self.run_full_flow(pdf=False)

    def test_pdf_full_flow_converts_before_extracting_and_grading(self):
        self.run_full_flow(pdf=True)

    def run_full_flow(self, pdf):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rubric_text = 'Question 1: answer A, 1 point.'
            rubric = root / ('rubric.pdf' if pdf else 'rubric.txt')
            if pdf:
                with Image.new('RGB', (64, 64), 'white') as image:
                    image.save(rubric, 'PDF')
            else:
                rubric.write_text(rubric_text)
            exam = root / 'exam'
            exam.mkdir()
            Image.new('RGB', (32, 32), 'white').save(exam / '01-01.png')
            engine = Mock()
            engine.convert_rubric_pdf.return_value = rubric_text
            engine.extract_answer_key_concurrent.return_value = [{'1': 'A'}] * 3
            engine.consolidate_answer_keys.return_value = ({'1': 'A'}, 'consistent')
            engine.detect_regions.return_value = 'Question 1 in center'
            engine.consolidate_layout.return_value = 'Question 1 in center'
            engine.grade_exam.return_value = {'total_score': 1, 'details': [{'question_id': '1', 'score': 1, 'max_score': 1, 'type': '客观题', 'student_answer': 'A'}]}
            with patch('AutoGrader.ConfigManager', return_value=ConfigManager(str(root / 'config.json'))):
                app = App()
            app.rubric_path = str(rubric)
            app.exam_folder = str(exam)
            app.current_api_key = 'fake-test-key'
            app.entry_key.insert(0, 'fake-test-key')
            if pdf:
                old_data = exam / '阅卷数据'
                old_data.mkdir()
                (old_data / 'answer_key.json').write_text(json.dumps({'1': 'WRONG OLD KEY'}))
            errors = []
            confirmations = []
            completed = []
            app.report_callback_exception = lambda *args: errors.append(str(args))
            def answer_dialog(parent, key, report, callback):
                self.assertIs(threading.current_thread(), threading.main_thread())
                confirmations.append('answers')
                callback(key)
            def layout_dialog(parent, layout, callback):
                self.assertIs(threading.current_thread(), threading.main_thread())
                confirmations.append('layout')
                callback(layout)
            def marks_dialog(master, t, template, samples, mode, on_done, **kwargs):
                self.assertIs(threading.current_thread(), threading.main_thread())
                self.assertEqual(mode, 'chain')
                self.assertTrue(samples, 'the scans waiting to be graded are offered as samples')
                confirmations.append('marks')
                on_done('skip', template)  # Skipping writes no scores and asks again next time
            original_reset = app.reset_ui_state
            def reset():
                original_reset()
                completed.append(True)
                app.after(100, app.quit)
            app.reset_ui_state = reset
            try:
                with patch('AutoGrader.AIGraderEngine', return_value=engine), patch('standard_answer_dialog.StandardAnswerReviewDialog', side_effect=answer_dialog), patch('AutoGrader.TemplateConfirmDialog', side_effect=layout_dialog), patch('AutoGrader.ScoreMarksDialog', side_effect=marks_dialog), patch('AutoGrader.messagebox.showerror', side_effect=lambda *a: errors.append(str(a))):
                    app.after(0, app.start_grading_thread)
                    watchdog = app.after(12000, app.quit)
                    app.mainloop()
                    app.after_cancel(watchdog)
                self.assertTrue(completed, 'grading never reached reset')
                self.assertFalse(errors, str(errors))
                self.assertEqual(confirmations, ['answers', 'layout', 'marks'])
                self.assertFalse((exam / '阅卷数据' / 'score_marks.json').exists(), 'skipping saves no template')
                self.assertTrue((exam / '阅卷数据' / 'answer_key.json').is_file())
                self.assertTrue((exam / '阅卷数据' / 'layout_config.json').is_file())
                self.assertTrue((exam / '阅卷报告' / '01-01.json').is_file())
                self.assertTrue((exam / '阅卷报告' / '01-01.md').is_file())
                self.assertEqual(app.btn_start.cget('state'), 'normal')
                self.assertEqual(engine.grade_exam.call_args.args[0], rubric_text)
                if pdf:
                    engine.convert_rubric_pdf.assert_called_once()
                    self.assertLess(str(engine.mock_calls).index('convert_rubric_pdf'), str(engine.mock_calls).index('extract_answer_key_concurrent'))
                    self.assertTrue(list((exam / '阅卷数据' / 'rubric').glob('*.md')))
                    key_path = exam / '阅卷数据' / 'answer_key.json'
                    self.assertTrue(app._pdf_answer_key_matches(str(key_path)))
                    app.grader_engine = engine
                    success, message = app.regrade_single_file(str(exam / '成功归档' / '01-01.png'))
                    self.assertTrue(success, message)
                    self.assertEqual(engine.grade_exam.call_args.args[0], rubric_text)
                    engine.convert_rubric_pdf.assert_called_once()
                    with patch.object(app, '_start_targeted_grading', side_effect=lambda files: app.quit()) as targeted:
                        app.after(0, lambda: app.start_targeted_grading(['01-01.png']))
                        timer = app.after(3000, app.quit)
                        app.mainloop()
                        app.after_cancel(timer)
                        targeted.assert_called_once_with(['01-01.png'])
                    engine.extract_answer_key_concurrent.assert_called_once()
                    engine.convert_rubric_pdf.assert_called_once()
                    converted = next((exam / '阅卷数据' / 'rubric').glob('*.md'))
                    converted.write_text('Question 1: answer B, 1 point.')
                    self.assertFalse(app._pdf_answer_key_matches(str(key_path)))
                    calls = engine.grade_exam.call_count
                    success, message = app.regrade_single_file(str(exam / '成功归档' / '01-01.png'))
                    self.assertFalse(success)
                    self.assertIn('PDF', message)
                    self.assertEqual(engine.grade_exam.call_count, calls)
                else:
                    engine.convert_rubric_pdf.assert_not_called()
            finally:
                app.destroy()

    def test_pdf_conversion_failure_stops_the_pipeline_and_restores_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rubric = root / 'rubric.pdf'
            rubric.write_bytes(b'%PDF-synthetic')
            with patch('AutoGrader.ConfigManager', return_value=ConfigManager(str(root / 'config.json'))):
                app = App()
            app.rubric_path = str(rubric)
            app.exam_folder = str(root)
            app.current_api_key = 'fake-test-key'
            engine = Mock()
            engine.convert_rubric_pdf.side_effect = RuntimeError('synthetic PDF failure')
            continued = Mock()
            errors = []
            def failed(*args):
                self.assertIs(threading.current_thread(), threading.main_thread())
                errors.append(str(args))
                app.quit()
            try:
                with patch('AutoGrader.AIGraderEngine', return_value=engine), patch('AutoGrader.messagebox.showerror', side_effect=failed):
                    app.after(0, lambda: app.ensure_rubric_and_run(continued))
                    timer = app.after(3000, app.quit)
                    app.mainloop()
                    app.after_cancel(timer)
                self.assertEqual(len(errors), 1)
                self.assertIn('synthetic PDF failure', errors[0])
                continued.assert_not_called()
                self.assertEqual(app.btn_start.cget('state'), 'normal')
                self.assertEqual(app.btn_rubric.cget('state'), 'normal')
                self.assertFalse(list(root.rglob('*.md')))
                engine.extract_answer_key_concurrent.assert_not_called()
            finally:
                app.destroy()

    def test_extraction_error_reaches_main_thread_without_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rubric = root / 'rubric.txt'
            rubric.write_text('synthetic rubric')
            with patch('AutoGrader.ConfigManager', return_value=ConfigManager(str(root / 'config.json'))):
                app = App()
            app.rubric_path = str(rubric)
            app.exam_folder = str(root)
            app.current_api_key = 'test-key'
            engine = Mock()
            engine.extract_answer_key_concurrent.side_effect = TimeoutError('synthetic timeout')
            continued = Mock()
            received = []
            def error(*args):
                self.assertIs(threading.current_thread(), threading.main_thread())
                received.append(str(args))
                app.quit()
            try:
                with patch('AutoGrader.AIGraderEngine', return_value=engine), patch('AutoGrader.messagebox.showerror', side_effect=error):
                    app.after(0, lambda: app.ensure_answer_key_and_run(continued))
                    timer = app.after(3000, app.quit)
                    app.mainloop()
                    app.after_cancel(timer)
                self.assertEqual(len(received), 1)
                self.assertIn('synthetic timeout', received[0])
                continued.assert_not_called()
                self.assertFalse((root / '阅卷数据' / 'answer_key.json').exists())
            finally:
                app.destroy()

    def test_consolidation_failure_does_not_return_first_answer(self):
        engine = AIGraderEngine.__new__(AIGraderEngine)
        engine.provider = 'OpenAI'
        engine.model_name = 'fake'
        engine.client = Mock()
        engine.client.chat.completions.create.side_effect = TimeoutError('test timeout')
        with self.assertRaises(RuntimeError):
            engine.consolidate_answer_keys([{'1': 'A'}] * 3)

    def test_gemini_consolidation_uses_gemini(self):
        engine = AIGraderEngine.__new__(AIGraderEngine)
        engine.provider = 'Gemini'
        engine.gemini_model = Mock()
        engine.gemini_model.generate_content.return_value.text = json.dumps({'final_key': {'1': 'A'}, 'report': 'ok'})
        self.assertEqual(engine.consolidate_answer_keys([{'1': 'A'}] * 3)[0], {'1': 'A'})

if __name__ == '__main__':
    unittest.main()
