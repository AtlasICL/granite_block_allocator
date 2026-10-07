import sys
import tempfile
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from openpyxl import Workbook

from allocator.blockfile import (
    BlockFileError,
    find_duplicate_ids,
    load_blocks,
    normalise_header,
    parse_weight,
)

_RESOURCES = Path(__file__).resolve().parent / "resources"


class _TempFiles(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name: str, content: str | bytes) -> Path:
        path = self.dir / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def xlsx(self, name: str, rows) -> Path:
        wb = Workbook()
        ws = wb.active
        for row in rows:
            ws.append(row)
        path = self.dir / name
        wb.save(path)
        return path


class TestSampleFiles(unittest.TestCase):
    """The original loader tests, run against the sample files."""

    def test_loads_basic_csv(self):
        blocks = load_blocks(str(_RESOURCES / "example_blocks_2.csv"))
        self.assertEqual(len(blocks), 16)
        for b in blocks:
            self.assertIsInstance(b, tuple)
            self.assertEqual(len(b), 2)

    def test_ignores_extra_columns(self):
        blocks = load_blocks(str(_RESOURCES / "example_blocks.csv"))
        self.assertEqual(len(blocks), 100)
        for b in blocks:
            self.assertEqual(len(b), 2)

    def test_loads_csv_with_lots_of_extra_columns(self):
        blocks = load_blocks(str(_RESOURCES / "example_blocks_3.csv"))
        self.assertEqual(len(blocks), 56)
        for b in blocks:
            self.assertEqual(len(b), 2)

    def test_returns_correct_types(self):
        blocks = load_blocks(str(_RESOURCES / "tiny_dp_beats_greedy.csv"))
        self.assertEqual(len(blocks), 3)
        for b in blocks:
            self.assertIsInstance(b, tuple)
            int(b[0])
            self.assertIsInstance(float(b[1]), float)

    def test_loads_known_values(self):
        blocks = load_blocks(str(_RESOURCES / "tiny_dp_beats_greedy.csv"))
        weights = sorted(float(b[1]) for b in blocks)
        self.assertEqual(weights, [5.0, 5.0, 6.0])

    def test_missing_required_column_raises(self):
        with self.assertRaises(ValueError) as cm:
            load_blocks(str(_RESOURCES / "missing_weight_column.csv"))
        self.assertIn("Weight", str(cm.exception))

    def test_nan_weight_raises(self):
        with self.assertRaises(ValueError):
            load_blocks(str(_RESOURCES / "nan_values.csv"))

    def test_missing_file_raises(self):
        with self.assertRaises(ValueError):
            load_blocks(str(_RESOURCES / "this_file_does_not_exist.csv"))

    def test_empty_csv_returns_empty_list(self):
        blocks = load_blocks(str(_RESOURCES / "empty_blocks.csv"))
        self.assertEqual(blocks, [])


class TestHeaderMatching(_TempFiles):
    def test_normalise_header(self):
        cases = {
            "BlockNo": "blockno",
            " Block No ": "blockno",
            "block_no": "blockno",
            "BLOCK-NO": "blockno",
            "Block.No": "blockno",
            "Weight (t)": "weight",
            "weight [kg]": "weight",
            "WEIGHT": "weight",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalise_header(raw), expected)

    def test_column_names_are_case_insensitive(self):
        path = self.write("a.csv", "blockno,WEIGHT\n1,5\n")
        self.assertEqual(load_blocks(path), [("1", 5.0)])

    def test_accepts_common_alternative_names(self):
        for header in ("Block Number,Weight", "Block ID,Wt", "block_num,Weight (kg)"):
            with self.subTest(header=header):
                path = self.write("a.csv", f"{header}\n7,2.5\n")
                self.assertEqual(load_blocks(path), [("7", 2.5)])

    def test_messy_headers_sample_file(self):
        blocks = load_blocks(_RESOURCES / "messy_headers.csv")
        self.assertEqual(blocks, [("0612", 13.1), ("A-17", 15.1), ("6209", 16.7)])

    def test_missing_column_lists_the_columns_found(self):
        path = self.write("a.csv", "Block,L,H,Mass\n1,2,3,4\n")
        with self.assertRaises(BlockFileError) as cm:
            load_blocks(path)
        message = str(cm.exception)
        self.assertIn("BlockNo", message)
        for found in ("'Block'", "'L'", "'H'", "'Mass'"):
            self.assertIn(found, message)

    def test_ambiguous_columns_are_rejected(self):
        path = self.write("a.csv", "BlockNo,Weight,weight (kg)\n1,2,3\n")
        with self.assertRaises(BlockFileError) as cm:
            load_blocks(path)
        self.assertIn("More than one column", str(cm.exception))
        self.assertIn("'weight (kg)'", str(cm.exception))


class TestValues(_TempFiles):
    def test_block_numbers_keep_leading_zeros_and_text(self):
        path = self.write("a.csv", "BlockNo,Weight\n0612,1\nA-17,2\n 6017 ,3\n")
        self.assertEqual([b for b, _ in load_blocks(path)], ["0612", "A-17", "6017"])

    def test_blank_rows_are_skipped(self):
        path = self.write("a.csv", "\nBlockNo,Weight\n1,5\n,\n\n2,6\n,,\n")
        self.assertEqual(load_blocks(path), [("1", 5.0), ("2", 6.0)])

    def test_semicolon_excel_export(self):
        blocks = load_blocks(_RESOURCES / "excel_semicolon_export.csv")
        self.assertEqual(blocks, [("6017", 13.1), ("6131", 15.1), ("0612", 9.85)])

    def test_windows_code_page_file(self):
        data = "BlockNo;Weight;Notes\r\n6017;13,1;Ön yüz\r\n".encode("cp1252")
        path = self.write("a.csv", data)
        self.assertEqual(load_blocks(path), [("6017", 13.1)])

    def test_tab_separated(self):
        path = self.write("a.tsv", "BlockNo\tWeight\n1\t4.5\n")
        self.assertEqual(load_blocks(path), [("1", 4.5)])

    def test_quoted_decimal_comma_in_comma_separated_file(self):
        path = self.write("a.csv", 'BlockNo,Weight\n1,"13,1"\n')
        self.assertEqual(load_blocks(path), [("1", 13.1)])

    def test_problems_are_reported_with_row_numbers(self):
        path = self.write("a.csv", "BlockNo,Weight\n1,5\n2,\n,7\n4,heavy\n5,-1\n6,0\n")
        with self.assertRaises(BlockFileError) as cm:
            load_blocks(path)
        message = str(cm.exception)
        self.assertIn("5 rows have problems", message)
        self.assertIn("Row 3 (block 2): Weight is empty", message)
        self.assertIn("Row 4: BlockNo is empty", message)
        self.assertIn("Row 5 (block 4): 'heavy' is not a number", message)
        self.assertIn("Row 6 (block 5): Weight must be more than 0", message)

    def test_long_problem_lists_are_summarised(self):
        rows = "\n".join(f"{i},x" for i in range(20))
        path = self.write("a.csv", f"BlockNo,Weight\n{rows}\n")
        with self.assertRaises(BlockFileError) as cm:
            load_blocks(path)
        self.assertIn("…and 15 more", str(cm.exception))

    def test_short_rows_are_reported_not_crashed_on(self):
        path = self.write("a.csv", "BlockNo,Notes,Weight\n1,x\n")
        with self.assertRaises(BlockFileError) as cm:
            load_blocks(path)
        self.assertIn("Weight is empty", str(cm.exception))

    def test_completely_empty_file(self):
        path = self.write("a.csv", "")
        self.assertEqual(load_blocks(path), [])

    def test_header_only(self):
        self.assertEqual(load_blocks(_RESOURCES / "empty_blocks.csv"), [])


class TestParseWeight(unittest.TestCase):
    def test_valid(self):
        cases = {
            "13.1": 13.1,
            "13,1": 13.1,
            " 7 ": 7.0,
            "1.234,5": 1234.5,
            "1,234.5": 1234.5,
            ".5": 0.5,
            "-2": -2.0,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertAlmostEqual(parse_weight(text), expected)

    def test_invalid(self):
        for text in ("", "abc", "13.1 t", "1,2,3", "1..2", "nan", "inf"):
            with self.subTest(text=text):
                self.assertIsNone(parse_weight(text))


class TestExcel(_TempFiles):
    def test_reads_first_sheet(self):
        path = self.xlsx(
            "blocks.xlsx",
            [["Block No", "Weight (t)"], [6017, 13.1], ["0612", 9.85], [None, None], [6209, 16]],
        )
        self.assertEqual(load_blocks(path), [("6017", 13.1), ("0612", 9.85), ("6209", 16.0)])

    def test_reports_excel_row_numbers(self):
        path = self.xlsx("blocks.xlsx", [["BlockNo", "Weight"], [1, 5], [2, "n/a"]])
        with self.assertRaises(BlockFileError) as cm:
            load_blocks(path)
        self.assertIn("Row 3 (block 2): 'n/a' is not a number", str(cm.exception))

    def test_text_weights_in_excel(self):
        path = self.xlsx("blocks.xlsx", [["BlockNo", "Weight"], ["1", "13,1"]])
        self.assertEqual(load_blocks(path), [("1", 13.1)])

    def test_corrupt_workbook(self):
        path = self.write("broken.xlsx", b"not really a workbook")
        with self.assertRaises(BlockFileError) as cm:
            load_blocks(path)
        self.assertIn("could not be read as an Excel workbook", str(cm.exception))

    def test_old_xls_is_explained(self):
        path = self.write("old.xls", b"\xd0\xcf\x11\xe0")
        with self.assertRaises(BlockFileError) as cm:
            load_blocks(path)
        self.assertIn(".xlsx", str(cm.exception))


class TestMisc(_TempFiles):
    def test_missing_file(self):
        with self.assertRaises(BlockFileError) as cm:
            load_blocks(self.dir / "nope.csv")
        self.assertIn("could not be found", str(cm.exception))

    def test_block_file_error_is_a_value_error(self):
        # Callers that catch ValueError keep working.
        self.assertTrue(issubclass(BlockFileError, ValueError))

    def test_find_duplicate_ids(self):
        blocks = [("1", 1.0), ("2", 2.0), ("1", 3.0), ("3", 1.0), ("2", 2.0)]
        self.assertEqual(find_duplicate_ids(blocks), ["1", "2"])
        self.assertEqual(find_duplicate_ids([("1", 1.0)]), [])


if __name__ == "__main__":
    unittest.main()
