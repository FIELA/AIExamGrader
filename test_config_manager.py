"""Configuration persistence across macOS bundle launches and working directories."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from config_manager import ConfigManager


class TestConfigPaths(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.home = self.root / "user"
        self.home.mkdir()
        self.cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.cwd)
        self.target = self.home / "Library/Application Support/AIExamGrader/config.json"

    def packaged_mac(self):
        self.enterContext(patch.object(sys, "platform", "darwin"))
        self.enterContext(patch.object(sys, "frozen", True, create=True))
        self.enterContext(patch.object(Path, "home", return_value=self.home))

    def test_bundle_uses_user_directory_even_when_launched_from_root(self):
        self.packaged_mac()
        os.chdir("/")
        manager = ConfigManager()
        self.assertEqual(Path(manager.config_path), self.target)
        self.assertFalse(self.target.exists())

    def test_saved_profile_survives_relaunch_from_another_directory(self):
        self.packaged_mac()
        manager = ConfigManager()
        profile = {"provider": "OpenAI", "model": "synthetic-model", "api_key": "fake-key"}
        manager.save_profile("synthetic-profile", profile)
        manager.set("language", "EN")
        os.chdir("/")
        reopened = ConfigManager()
        self.assertEqual(reopened.load_profile("synthetic-profile"), profile)
        self.assertEqual(reopened.get_last_used(), "synthetic-profile")
        self.assertEqual(reopened.get("language"), "EN")
        self.assertEqual(json.loads(self.target.read_text())["profiles"]["synthetic-profile"], profile)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)

    def test_explicit_path_takes_precedence_and_creates_parent(self):
        self.packaged_mac()
        explicit = self.root / "custom/config.json"
        manager = ConfigManager(explicit)
        manager.set("language", "EN")
        self.assertEqual(ConfigManager(explicit).get("language"), "EN")
        self.assertFalse(self.target.exists())

    def test_source_mode_keeps_existing_working_directory_config(self):
        self.enterContext(patch.object(sys, "frozen", False, create=True))
        legacy = self.root / "config.json"
        legacy.write_text(json.dumps({"language": "EN"}))
        manager = ConfigManager()
        self.assertEqual(manager.get("language"), "EN")
        manager.set("language", "CN")
        self.assertEqual(json.loads(legacy.read_text())["language"], "CN")

    def test_non_mac_bundle_keeps_existing_path(self):
        self.enterContext(patch.object(sys, "platform", "win32"))
        self.enterContext(patch.object(sys, "frozen", True, create=True))
        self.assertEqual(ConfigManager().config_path, "config.json")

    def test_bundle_does_not_overwrite_or_import_unrelated_cwd_config(self):
        self.packaged_mac()
        legacy = self.root / "config.json"
        original = json.dumps({"api_key": "unrelated-fake-key"}).encode()
        legacy.write_bytes(original)
        manager = ConfigManager()
        self.assertIsNone(manager.get("api_key"))
        manager.set("language", "CN")
        self.assertEqual(legacy.read_bytes(), original)
        self.assertTrue(self.target.exists())


if __name__ == "__main__":
    unittest.main()
