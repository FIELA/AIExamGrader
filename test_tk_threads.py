"""Tk objects are only finalized on the main thread: this Tcl 9 build does not pass calls from other threads to it."""
import gc
import tempfile
import threading
import time
import tkinter.font
import unittest
from pathlib import Path
from unittest.mock import patch

import customtkinter as ctk

from AutoGrader import App
from config_manager import ConfigManager


class TestGarbageCollection(unittest.TestCase):
    def test_widgets_freed_while_a_worker_runs_are_finalized_on_the_main_thread(self):
        threads = []
        finalize = tkinter.font.Font.__del__

        def spy(font):
            threads.append(threading.current_thread().name)
            finalize(font)

        thresholds = gc.get_threshold()
        with tempfile.TemporaryDirectory() as directory:
            with patch('AutoGrader.ConfigManager', return_value=ConfigManager(str(Path(directory) / 'config.json'))):
                app = App()
            app.withdraw()
            try:
                with patch.object(tkinter.font.Font, '__del__', spy):
                    # Like a review window closed just before a worker starts: its widgets, each with its own CTkFont,
                    # are left in reference cycles that no collection has looked at yet
                    automatic = gc.isenabled()
                    gc.disable()
                    frame = ctk.CTkFrame(app)
                    for i in range(20):
                        ctk.CTkLabel(frame, text=str(i)).pack()
                    frame.destroy()
                    del frame

                    def allocate():  # Like the export or a grading worker
                        if automatic:
                            gc.enable()  # Automatic collection as the app left it, so the next one starts in here
                        gc.set_threshold(50)  # Low enough that these allocations would start collections
                        for _ in range(100):
                            [[] for _ in range(100)]
                    worker = threading.Thread(target=allocate, name="worker")
                    worker.start()
                    worker.join()
                    self.assertEqual(threads, [])

                    end = time.time() + 3
                    while len(threads) < 20 and time.time() < end:
                        app.update()
                        time.sleep(0.02)
                self.assertGreaterEqual(len(threads), 20)
                self.assertEqual(set(threads), {threading.main_thread().name})
            finally:
                gc.set_threshold(*thresholds)
                app.destroy()


if __name__ == "__main__":
    unittest.main()
