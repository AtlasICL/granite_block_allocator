import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from allocator import APP_NAME, settings
from allocator.settings import (
    InputError,
    Settings,
    load_settings,
    parse_capacity,
    parse_container_count,
    parse_max_blocks,
    save_settings,
)


class TestParsing(unittest.TestCase):
    def test_container_count(self):
        self.assertEqual(parse_container_count(" 4 "), 4)
        self.assertEqual(parse_container_count("3.0"), 3)
        for bad, fragment in [
            ("", "Enter the number"),
            ("abc", "whole number"),
            ("2.5", "whole number"),
            ("0", "at least 1"),
            ("-1", "at least 1"),
        ]:
            with self.subTest(text=bad), self.assertRaises(InputError) as cm:
                parse_container_count(bad)
            self.assertIn(fragment, str(cm.exception))

    def test_capacity_accepts_decimal_comma(self):
        self.assertEqual(parse_capacity("28"), 28.0)
        self.assertEqual(parse_capacity("27,5"), 27.5)
        for bad, fragment in [
            ("", "Enter the max weight"),
            ("lots", "must be a number"),
            ("0", "more than 0"),
        ]:
            with self.subTest(text=bad), self.assertRaises(InputError) as cm:
                parse_capacity(bad)
            self.assertIn(fragment, str(cm.exception))

    def test_max_blocks(self):
        self.assertIsNone(parse_max_blocks("No limit"))
        self.assertIsNone(parse_max_blocks("no limit"))
        self.assertIsNone(parse_max_blocks(""))
        self.assertEqual(parse_max_blocks("3"), 3)
        for bad in ("x", "0"):
            with self.subTest(text=bad), self.assertRaises(InputError):
                parse_max_blocks(bad)


class TestPersistence(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "sub" / "settings.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_round_trip(self):
        original = Settings(
            container_count="5",
            capacity="27.5",
            max_blocks="3",
            balance=True,
            last_file="/x/blocks.csv",
            last_dir="/x",
        )
        self.assertTrue(save_settings(original, self.path))
        self.assertEqual(load_settings(self.path), original)

    def test_missing_file_gives_defaults(self):
        self.assertEqual(load_settings(self.path), Settings())

    def test_corrupt_file_gives_defaults(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(load_settings(self.path), Settings())
        self.path.write_text("[1, 2]", encoding="utf-8")
        self.assertEqual(load_settings(self.path), Settings())

    def test_wrong_types_and_unknown_keys_are_ignored(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps({"capacity": 28, "balance": "yes", "container_count": "3", "colour": "red"}),
            encoding="utf-8",
        )
        loaded = load_settings(self.path)
        self.assertEqual(loaded.capacity, "")
        self.assertFalse(loaded.balance)
        self.assertEqual(loaded.container_count, "3")

    def test_save_failure_returns_false(self):
        blocker = Path(self._tmp.name) / "file"
        blocker.write_text("x")
        self.assertFalse(save_settings(Settings(), blocker / "settings.json"))

    def test_settings_path_per_platform(self):
        with (
            mock.patch.object(settings.sys, "platform", "win32"),
            mock.patch.dict(settings.os.environ, {"APPDATA": "/appdata"}),
        ):
            self.assertEqual(settings.settings_path(), Path("/appdata") / APP_NAME / "settings.json")
        with mock.patch.object(settings.sys, "platform", "darwin"):
            self.assertIn("Application Support", str(settings.settings_path()))
        with (
            mock.patch.object(settings.sys, "platform", "linux"),
            mock.patch.dict(settings.os.environ, {"XDG_CONFIG_HOME": "/cfg"}),
        ):
            self.assertEqual(settings.settings_path(), Path("/cfg") / APP_NAME / "settings.json")


if __name__ == "__main__":
    unittest.main()
