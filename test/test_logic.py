import sys
import unittest
from pathlib import Path
from unittest import mock

# Make the project root importable when running `python -m unittest discover -s test`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from allocator import logic
from allocator.logic import (
    assign_containers,
    find_best_subset,
    find_best_subset_dp,
    find_best_subset_greedy,
    load_blocks,
)

_RESOURCES = Path(__file__).resolve().parent / "resources"


def _assert_assignment_valid(test_case, blocks, capacity, count, max_blocks, assignments):
    """Shared invariants every valid ContainerMap must satisfy."""
    weight_by_blockno = {int(b[0]): float(b[1]) for b in blocks}
    seen_blocknos = []

    test_case.assertIsInstance(assignments, dict)
    test_case.assertLessEqual(len(assignments), count)

    for cid, info in assignments.items():
        test_case.assertIsInstance(cid, int)
        test_case.assertGreaterEqual(cid, 1)
        test_case.assertLessEqual(cid, count)
        test_case.assertIn("blocks", info)
        test_case.assertIn("total_weight", info)

        block_ids = info["blocks"]
        total = info["total_weight"]

        test_case.assertIsInstance(block_ids, list)
        test_case.assertLessEqual(total, capacity + 1e-9)

        if max_blocks is not None:
            test_case.assertLessEqual(len(block_ids), max_blocks)

        expected_total = 0.0
        for bid in block_ids:
            bid_int = int(bid)
            test_case.assertIn(bid_int, weight_by_blockno)
            expected_total += weight_by_blockno[bid_int]
            seen_blocknos.append(bid_int)

        test_case.assertAlmostEqual(total, expected_total, places=6)

    test_case.assertEqual(
        len(seen_blocknos),
        len(set(seen_blocknos)),
        "A block was assigned to more than one container",
    )


class TestLoadBlocks(unittest.TestCase):
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


class TestFindBestSubsetDp(unittest.TestCase):
    def test_empty_blocks_returns_empty(self):
        self.assertEqual(find_best_subset_dp([], 10.0), ([], 0.0))

    def test_zero_capacity_returns_empty(self):
        self.assertEqual(find_best_subset_dp([(1, 5.0)], 0.0), ([], 0.0))

    def test_negative_capacity_returns_empty(self):
        self.assertEqual(find_best_subset_dp([(1, 5.0)], -1.0), ([], 0.0))

    def test_zero_max_blocks_returns_empty(self):
        result, total = find_best_subset_dp([(1, 5.0), (2, 3.0)], 10.0, max_blocks=0)
        self.assertEqual(result, [])
        self.assertEqual(total, 0.0)

    def test_negative_max_blocks_returns_empty(self):
        result, total = find_best_subset_dp([(1, 5.0)], 10.0, max_blocks=-1)
        self.assertEqual(result, [])
        self.assertEqual(total, 0.0)

    def test_all_blocks_fit(self):
        blocks = [(1, 1.0), (2, 2.0), (3, 3.0)]
        result, total = find_best_subset_dp(blocks, 100.0)
        self.assertEqual(sorted(b[0] for b in result), [1, 2, 3])
        self.assertAlmostEqual(total, 6.0)

    def test_no_block_fits(self):
        blocks = [(1, 10.0), (2, 20.0), (3, 30.0)]
        result, total = find_best_subset_dp(blocks, 5.0)
        self.assertEqual(result, [])
        self.assertEqual(total, 0.0)

    def test_dp_finds_optimal_when_greedy_fails(self):
        # Greedy picks 6 then nothing else fits → total 6.
        # DP picks 5+5 = 10 (the optimum).
        blocks = [(1, 6.0), (2, 5.0), (3, 5.0)]
        result, total = find_best_subset_dp(blocks, 10.0)
        self.assertAlmostEqual(total, 10.0)
        self.assertEqual(sorted(b[0] for b in result), [2, 3])

    def test_respects_max_blocks_constraint(self):
        blocks = [(1, 3.0), (2, 3.0), (3, 3.0), (4, 3.0)]
        result, total = find_best_subset_dp(blocks, 12.0, max_blocks=2)
        self.assertEqual(len(result), 2)
        self.assertAlmostEqual(total, 6.0)

    def test_max_blocks_larger_than_n_treated_as_unconstrained(self):
        blocks = [(1, 6.0), (2, 5.0), (3, 5.0)]
        result_capped, total_capped = find_best_subset_dp(blocks, 10.0, max_blocks=100)
        result_none, total_none = find_best_subset_dp(blocks, 10.0, max_blocks=None)
        self.assertAlmostEqual(total_capped, total_none)
        self.assertAlmostEqual(total_capped, 10.0)

    def test_max_blocks_equal_to_n_means_unconstrained(self):
        blocks = [(1, 6.0), (2, 5.0), (3, 5.0)]
        result, total = find_best_subset_dp(blocks, 10.0, max_blocks=3)
        self.assertAlmostEqual(total, 10.0)

    def test_returned_total_matches_block_sum(self):
        blocks = [(1, 1.5), (2, 2.5), (3, 3.5), (4, 4.5)]
        result, total = find_best_subset_dp(blocks, 7.0)
        self.assertAlmostEqual(total, sum(b[1] for b in result))

    def test_result_does_not_exceed_capacity(self):
        blocks = [(1, 3.7), (2, 4.2), (3, 5.1), (4, 2.8), (5, 1.9)]
        capacity = 10.0
        result, total = find_best_subset_dp(blocks, capacity)
        self.assertLessEqual(sum(b[1] for b in result), capacity + 1e-9)
        self.assertLessEqual(total, capacity + 1e-9)

    def test_floating_point_weights(self):
        # Weights with two decimal places exercise the ×100 integer scaling.
        # Optimal at cap 0.7: pick 0.4 + 0.3 = 0.7 (greedy would pick 0.5 alone).
        blocks = [(1, 0.4), (2, 0.3), (3, 0.5)]
        result, total = find_best_subset_dp(blocks, 0.7)
        self.assertAlmostEqual(total, 0.7, places=6)
        self.assertEqual(sorted(b[0] for b in result), [1, 2])

    def test_single_block_fits(self):
        result, total = find_best_subset_dp([(42, 7.5)], 10.0)
        self.assertEqual(result, [(42, 7.5)])
        self.assertAlmostEqual(total, 7.5)

    def test_single_block_does_not_fit(self):
        result, total = find_best_subset_dp([(42, 20.0)], 10.0)
        self.assertEqual(result, [])
        self.assertEqual(total, 0.0)


class TestFindBestSubsetGreedy(unittest.TestCase):
    def test_empty_blocks_returns_empty(self):
        self.assertEqual(find_best_subset_greedy([], 10.0), ([], 0.0))

    def test_picks_heaviest_first(self):
        blocks = [(1, 1.0), (2, 5.0), (3, 3.0)]
        result, total = find_best_subset_greedy(blocks, 5.0)
        self.assertEqual(result, [(2, 5.0)])
        self.assertAlmostEqual(total, 5.0)

    def test_packs_multiple_when_capacity_allows(self):
        blocks = [(1, 1.0), (2, 5.0), (3, 3.0)]
        result, total = find_best_subset_greedy(blocks, 10.0)
        self.assertEqual(sorted(b[0] for b in result), [1, 2, 3])
        self.assertAlmostEqual(total, 9.0)

    def test_respects_capacity(self):
        blocks = [(i, float(i)) for i in range(1, 11)]
        result, total = find_best_subset_greedy(blocks, 15.0)
        self.assertLessEqual(total, 15.0 + 1e-9)
        self.assertLessEqual(sum(b[1] for b in result), 15.0 + 1e-9)

    def test_respects_max_blocks(self):
        blocks = [(i, 1.0) for i in range(1, 11)]
        result, total = find_best_subset_greedy(blocks, 100.0, max_blocks=3)
        self.assertLessEqual(len(result), 3)
        self.assertAlmostEqual(total, 3.0)

    def test_max_blocks_none_unconstrained(self):
        blocks = [(i, 1.0) for i in range(1, 6)]
        result, total = find_best_subset_greedy(blocks, 100.0)
        self.assertEqual(len(result), 5)
        self.assertAlmostEqual(total, 5.0)

    def test_dp_beats_greedy_on_known_case(self):
        # Documents that greedy is suboptimal here — DP would return total 10.0.
        blocks = [(1, 6.0), (2, 5.0), (3, 5.0)]
        result, total = find_best_subset_greedy(blocks, 10.0)
        self.assertAlmostEqual(total, 6.0)
        self.assertEqual([b[0] for b in result], [1])

    def test_no_block_fits(self):
        blocks = [(1, 10.0), (2, 20.0)]
        result, total = find_best_subset_greedy(blocks, 5.0)
        self.assertEqual(result, [])
        self.assertEqual(total, 0.0)


class TestFindBestSubset(unittest.TestCase):
    def test_empty_returns_empty(self):
        self.assertEqual(find_best_subset([], 10.0), ([], 0.0))

    def test_zero_capacity_returns_empty(self):
        self.assertEqual(find_best_subset([(1, 5.0)], 0.0), ([], 0.0))

    def test_negative_capacity_returns_empty(self):
        self.assertEqual(find_best_subset([(1, 5.0)], -1.0), ([], 0.0))

    def test_uses_dp_for_small_inputs(self):
        # On small inputs, the dispatcher should pick DP and find the optimum.
        blocks = [(1, 6.0), (2, 5.0), (3, 5.0)]
        result, total = find_best_subset(blocks, 10.0)
        self.assertAlmostEqual(total, 10.0)
        self.assertEqual(sorted(b[0] for b in result), [2, 3])

    def test_falls_back_to_greedy_when_work_limit_exceeded(self):
        # Force the greedy branch by tightening _DP_WORK_LIMIT to 1.
        blocks = [(1, 6.0), (2, 5.0), (3, 5.0)]
        with mock.patch.object(logic, "_DP_WORK_LIMIT", 1):
            result, total = find_best_subset(blocks, 10.0)
        # Greedy is suboptimal on this input.
        self.assertAlmostEqual(total, 6.0)

    def test_result_invariants_hold_dp_path(self):
        blocks = [(i, float(i) * 0.5 + 1.0) for i in range(1, 11)]
        capacity = 7.5
        result, total = find_best_subset(blocks, capacity, max_blocks=4)
        self.assertLessEqual(total, capacity + 1e-9)
        self.assertLessEqual(len(result), 4)
        self.assertAlmostEqual(total, sum(b[1] for b in result))

    def test_result_invariants_hold_greedy_path(self):
        blocks = [(i, float(i) * 0.5 + 1.0) for i in range(1, 11)]
        capacity = 7.5
        with mock.patch.object(logic, "_DP_WORK_LIMIT", 1):
            result, total = find_best_subset(blocks, capacity, max_blocks=4)
        self.assertLessEqual(total, capacity + 1e-9)
        self.assertLessEqual(len(result), 4)
        self.assertAlmostEqual(total, sum(b[1] for b in result))


class TestAssignContainers(unittest.TestCase):
    def test_invalid_capacity_zero_raises(self):
        with self.assertRaises(ValueError):
            assign_containers([(1, 5.0)], 0.0, 1)

    def test_invalid_capacity_negative_raises(self):
        with self.assertRaises(ValueError):
            assign_containers([(1, 5.0)], -1.0, 1)

    def test_invalid_count_zero_raises(self):
        with self.assertRaises(ValueError):
            assign_containers([(1, 5.0)], 10.0, 0)

    def test_invalid_count_negative_raises(self):
        with self.assertRaises(ValueError):
            assign_containers([(1, 5.0)], 10.0, -2)

    def test_returns_dict_with_correct_structure(self):
        blocks = [(1, 5.0), (2, 3.0), (3, 8.0)]
        result = assign_containers(blocks, 10.0, 2)
        self.assertIsInstance(result, dict)
        for cid, info in result.items():
            self.assertIsInstance(cid, int)
            self.assertIn("blocks", info)
            self.assertIn("total_weight", info)
            self.assertIsInstance(info["blocks"], list)

    def test_container_ids_are_one_indexed(self):
        blocks = [(1, 5.0), (2, 3.0), (3, 8.0), (4, 2.0)]
        result = assign_containers(blocks, 10.0, 3)
        if result:
            self.assertEqual(min(result.keys()), 1)

    def test_no_block_assigned_twice(self):
        blocks = [(i, float(i % 7) + 1.0) for i in range(1, 21)]
        result = assign_containers(blocks, 10.0, 5)
        all_ids = []
        for info in result.values():
            all_ids.extend(int(b) for b in info["blocks"])
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_each_container_respects_capacity(self):
        blocks = [(i, float(i % 7) + 1.0) for i in range(1, 21)]
        capacity = 10.0
        result = assign_containers(blocks, capacity, 5)
        for info in result.values():
            self.assertLessEqual(info["total_weight"], capacity + 1e-9)

    def test_each_container_respects_max_blocks(self):
        blocks = [(i, 1.0) for i in range(1, 21)]
        result = assign_containers(blocks, 100.0, 5, max_blocks=3)
        for info in result.values():
            self.assertLessEqual(len(info["blocks"]), 3)

    def test_total_weights_match_block_sum(self):
        blocks = [(1, 5.0), (2, 3.0), (3, 8.0), (4, 2.5), (5, 4.5)]
        weight_by_id = {b[0]: b[1] for b in blocks}
        result = assign_containers(blocks, 10.0, 3)
        for info in result.values():
            expected = sum(weight_by_id[int(bid)] for bid in info["blocks"])
            self.assertAlmostEqual(info["total_weight"], expected, places=6)

    def test_stops_early_when_blocks_exhausted(self):
        # Two blocks, neither fits with the other → at most 2 containers used.
        blocks = [(1, 8.0), (2, 7.0)]
        result = assign_containers(blocks, 10.0, 5)
        self.assertLessEqual(len(result), 2)
        # Every input block should still be allocated.
        all_ids = {int(b) for info in result.values() for b in info["blocks"]}
        self.assertEqual(all_ids, {1, 2})

    def test_only_assigned_blocknos_appear(self):
        blocks = [(1, 5.0), (2, 3.0), (3, 8.0)]
        valid_ids = {b[0] for b in blocks}
        result = assign_containers(blocks, 10.0, 2)
        for info in result.values():
            for bid in info["blocks"]:
                self.assertIn(int(bid), valid_ids)

    def test_max_blocks_constraint_enforced_across_all_containers(self):
        blocks = [(i, 1.0) for i in range(1, 16)]
        result = assign_containers(blocks, 100.0, 5, max_blocks=2)
        for info in result.values():
            self.assertLessEqual(len(info["blocks"]), 2)
        all_ids = []
        for info in result.values():
            all_ids.extend(int(b) for b in info["blocks"])
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_does_not_mutate_input_list(self):
        blocks = [(1, 5.0), (2, 3.0), (3, 8.0)]
        original = list(blocks)
        assign_containers(blocks, 10.0, 2)
        self.assertEqual(blocks, original)

    def test_single_container_acts_like_find_best_subset(self):
        blocks = [(1, 6.0), (2, 5.0), (3, 5.0)]
        result = assign_containers(blocks, 10.0, 1)
        self.assertEqual(set(result.keys()), {1})
        self.assertAlmostEqual(result[1]["total_weight"], 10.0)
        self.assertEqual(sorted(int(b) for b in result[1]["blocks"]), [2, 3])


class TestExampleCsvFiles(unittest.TestCase):
    def test_example_csvs_load_without_error(self):
        for name in ("example_blocks.csv", "example_blocks_2.csv", "example_blocks_3.csv"):
            with self.subTest(file=name):
                blocks = load_blocks(str(_RESOURCES / name))
                self.assertGreater(len(blocks), 0)

    def test_example_blocks_assignment_valid(self):
        blocks = load_blocks(str(_RESOURCES / "example_blocks.csv"))
        capacity = 25.0
        count = 8
        result = assign_containers(blocks, capacity, count)
        _assert_assignment_valid(self, blocks, capacity, count, None, result)

    def test_example_blocks_assignment_with_max_blocks(self):
        blocks = load_blocks(str(_RESOURCES / "example_blocks.csv"))
        capacity = 50.0
        count = 5
        max_blocks = 3
        result = assign_containers(blocks, capacity, count, max_blocks=max_blocks)
        _assert_assignment_valid(self, blocks, capacity, count, max_blocks, result)

    def test_example_blocks_2_assignment_valid(self):
        blocks = load_blocks(str(_RESOURCES / "example_blocks_2.csv"))
        capacity = 30.0
        count = 4
        result = assign_containers(blocks, capacity, count)
        _assert_assignment_valid(self, blocks, capacity, count, None, result)

    def test_example_blocks_3_assignment_valid(self):
        blocks = load_blocks(str(_RESOURCES / "example_blocks_3.csv"))
        capacity = 40.0
        count = 6
        result = assign_containers(blocks, capacity, count)
        _assert_assignment_valid(self, blocks, capacity, count, None, result)

    def test_tiny_csv_round_trip(self):
        blocks = load_blocks(str(_RESOURCES / "tiny_dp_beats_greedy.csv"))
        result = assign_containers(blocks, 10.0, 1)
        self.assertEqual(set(result.keys()), {1})
        # DP path on this tiny input must achieve the optimum (10.0).
        self.assertAlmostEqual(result[1]["total_weight"], 10.0)

    def test_all_fit_csv_uses_one_container(self):
        blocks = load_blocks(str(_RESOURCES / "all_fit.csv"))
        capacity = 100.0
        result = assign_containers(blocks, capacity, 3)
        # All blocks fit in one container; later containers should be unused.
        self.assertIn(1, result)
        self.assertEqual(len(result[1]["blocks"]), 4)
        self.assertAlmostEqual(result[1]["total_weight"], 7.0)


if __name__ == "__main__":
    unittest.main()
