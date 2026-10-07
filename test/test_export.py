import csv
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from allocator.export import (
    NOT_PLACED,
    settings_line,
    summary_line,
    to_clipboard_text,
    to_csv,
    to_html,
)
from allocator.logic import AllocationResult


def _result(**overrides) -> AllocationResult:
    values = dict(
        containers=[[("6017", 13.1), ("0612", 9.9)], [("A<1>", 20.0)]],
        unplaced=[("7315", 19.63)],
        capacity=25.0,
        max_blocks=3,
    )
    values.update(overrides)
    return AllocationResult(**values)


class TestCsv(unittest.TestCase):
    def test_rows_and_bom(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "out.csv"
            to_csv(_result(), path)
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "Excel needs the UTF-8 BOM")
            rows = list(csv.reader(raw.decode("utf-8-sig").splitlines()))
        self.assertEqual(rows[0], ["Container", "BlockNo", "Weight", "Container total"])
        self.assertEqual(rows[1], ["1", "6017", "13.10", "23.00"])
        self.assertEqual(rows[2], ["1", "0612", "9.90", "23.00"])
        self.assertEqual(rows[3], ["2", "A<1>", "20.00", "20.00"])
        self.assertEqual(rows[4], [NOT_PLACED, "7315", "19.63", ""])
        self.assertEqual(len(rows), 5)

    def test_clipboard_is_tab_separated(self):
        lines = to_clipboard_text(_result()).splitlines()
        self.assertEqual(lines[0], "Container\tBlockNo\tWeight\tContainer total")
        self.assertEqual(lines[1], "1\t6017\t13.10\t23.00")


class TestSummaries(unittest.TestCase):
    def test_summary_line(self):
        self.assertEqual(
            summary_line(_result()),
            "2 containers · 3 of 4 blocks placed · 43.00 loaded · 86.0% of capacity used",
        )

    def test_summary_line_with_nothing_placed(self):
        line = summary_line(_result(containers=[], unplaced=[("x", 99.0)]))
        self.assertEqual(line, "0 containers · 0 of 1 blocks placed · 0.00 loaded")

    def test_settings_line(self):
        self.assertEqual(
            settings_line(_result(), 4),
            "4 containers available · max weight 25 · max 3 blocks each · each container filled in turn",
        )
        self.assertEqual(
            settings_line(_result(max_blocks=None, balanced=True)),
            "max weight 25 · no block limit · loads spread evenly",
        )


class TestHtml(unittest.TestCase):
    def test_loading_sheet_contents(self):
        html = to_html(_result(), "blocks.csv", 2, datetime(2026, 10, 7, 9, 30), auto_print=False)
        self.assertIn("Container loading sheet", html)
        self.assertIn("07 Oct 2026, 09:30", html)
        self.assertIn("blocks.csv", html)
        self.assertIn("Container 1", html)
        self.assertIn("Container 2", html)
        self.assertIn("Not placed", html)
        self.assertIn("0612", html)
        self.assertIn("92.0% full", html)
        self.assertNotIn("window.print()", html.split("<button")[0])
        self.assertNotIn("addEventListener('load'", html)

    def test_block_numbers_are_escaped(self):
        html = to_html(_result(), auto_print=False)
        self.assertIn("A&lt;1&gt;", html)
        self.assertNotIn("A<1>", html)

    def test_notes_are_shown_and_print_starts_automatically(self):
        html = to_html(_result(notes=["Quick method used."]))
        self.assertIn("Quick method used.", html)
        self.assertIn("addEventListener('load'", html)


if __name__ == "__main__":
    unittest.main()
