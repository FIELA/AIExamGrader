"""Exercise macOS shortcuts through the real application's Tk event bindings."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from AutoGrader import App
from config_manager import ConfigManager


@unittest.skipUnless(sys.platform == "darwin", "Requires macOS Aqua Tk")
class TestMacClipboard(unittest.TestCase):
    def test_paste_once_and_replace_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("AutoGrader.ConfigManager", return_value=ConfigManager(str(Path(directory) / "config.json"))):
                app = App()
            original = None
            try:
                app.update()
                try:
                    original = app.clipboard_get()
                except Exception:
                    pass
                for name in ("entry_key", "entry_base", "combo_model"):
                    with self.subTest(field=name):
                        entry = getattr(app, name)._entry
                        entry.focus_force()
                        app.update()
                        entry.delete(0, "end")
                        app.clipboard_clear()
                        app.clipboard_append("clipboard-test-123")
                        entry.event_generate("<Command-v>")
                        app.update()
                        self.assertEqual(entry.get(), "clipboard-test-123")
                        entry.event_generate("<Command-a>")
                        app.update()
                        self.assertTrue(entry.selection_present())
                        app.clipboard_clear()
                        app.clipboard_append("replacement-456")
                        entry.event_generate("<Command-v>")
                        app.update()
                        self.assertEqual(entry.get(), "replacement-456")
            finally:
                app.clipboard_clear()
                if original is not None:
                    app.clipboard_append(original)
                app.destroy()


if __name__ == "__main__":
    unittest.main()
