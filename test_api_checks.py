"""Run diagnostic callbacks with a real Tk event loop and no network."""
import threading
import unittest
from unittest.mock import Mock, patch
import customtkinter as ctk
from AutoGrader import App
from grader_engine import AIGraderEngine


class TestApiChecks(unittest.TestCase):
    def setUp(self):
        self.app = App.__new__(App)
        ctk.CTk.__init__(self.app)
        self.app.withdraw()
        self.app.t = lambda key, **kw: key + str(kw)
        self.app.current_api_key = 'test-key'
        self.app.entry_key = ctk.CTkEntry(self.app)
        self.app.entry_base = ctk.CTkEntry(self.app)
        self.app.combo_model = ctk.CTkComboBox(self.app, values=['test-model'])
        self.app.provider_var = ctk.StringVar(value='Gemini')
        self.app.btn_test_connection = ctk.CTkButton(self.app)
        self.app.btn_get_models = ctk.CTkButton(self.app)
        self.callback_errors = []
        self.app.report_callback_exception = lambda *args: self.callback_errors.append(args)

    def tearDown(self):
        self.app.destroy()

    def check_result(self, method, failing=False):
        app = self.app
        button = app.btn_test_connection if method == 'test_connection' else app.btn_get_models
        main_thread = threading.get_ident()
        result = []
        def delivered(*args, **kwargs):
            self.assertEqual(threading.get_ident(), main_thread)
            self.assertEqual(button.cget('state'), 'normal')
            result.append(args)
            app.quit()
        engine = Mock()
        engine.get_available_models.return_value = ['test-model']
        if failing:
            engine.test_connection.side_effect = RuntimeError('diagnostic failure')
            engine.get_available_models.side_effect = RuntimeError('diagnostic failure')
        original_after = app.after
        def main_thread_after(*args):
            self.assertEqual(threading.get_ident(), main_thread, 'Tk scheduled from worker')
            return original_after(*args)
        app.after = main_thread_after
        with patch('AutoGrader.AIGraderEngine', return_value=engine), patch('AutoGrader.messagebox.showinfo', side_effect=delivered), patch('AutoGrader.messagebox.showerror', side_effect=delivered):
            app.after(0, getattr(app, method))
            watchdog = app.after(3000, app.quit)
            app.mainloop()
            app.after_cancel(watchdog)
        self.assertEqual(len(result), 1)
        self.assertFalse(self.callback_errors)
        if failing:
            self.assertIn('diagnostic failure', str(result))

    def test_connection_success(self):
        self.check_result('test_connection')

    def test_connection_error(self):
        self.check_result('test_connection', failing=True)

    def test_models_success(self):
        self.check_result('check_models')

    def test_models_error(self):
        self.check_result('check_models', failing=True)

    def test_timeout_restores_button_and_ignores_late_result(self):
        app = self.app
        released = threading.Event()
        finished = threading.Event()
        success = Mock()
        def blocked():
            released.wait(2)
            finished.set()
        with patch('AutoGrader.time.monotonic', side_effect=[0, 36]), patch('AutoGrader.messagebox.showerror') as error:
            app._run_api_check(app.btn_test_connection, 'btn_test_connection', blocked, success)
            app.after(200, app.quit)
            app.mainloop()
            self.assertEqual(app.btn_test_connection.cget('state'), 'normal')
            error.assert_called_once()
        released.set()
        self.assertTrue(finished.wait(1))
        app.update()
        success.assert_not_called()


class TestProbeLimits(unittest.TestCase):
    def test_gemini_no_retry_and_deadline(self):
        engine = AIGraderEngine.__new__(AIGraderEngine)
        engine.provider = 'Gemini'
        engine.gemini_model = Mock()
        engine.test_connection(timeout=7)
        self.assertEqual(engine.gemini_model.generate_content.call_args.kwargs['request_options'], {'timeout': 7, 'retry': None})

    def test_openai_no_retry_and_deadline(self):
        engine = AIGraderEngine.__new__(AIGraderEngine)
        engine.provider = 'OpenAI'
        engine.model_name = 'test-model'
        engine.client = Mock()
        engine.test_connection(timeout=7)
        engine.client.with_options.assert_called_once_with(timeout=7, max_retries=0)


if __name__ == '__main__':
    unittest.main()
