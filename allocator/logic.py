"""Allocation algorithms: which blocks go in which container.

Containers are filled one at a time. Each one gets the heaviest combination
of the remaining blocks that fits its weight limit (and block-count limit),
found exactly with a 0/1 knapsack when that is fast enough and greedily
otherwise. An optional balancing pass then evens out the loads without
changing which blocks are shipped.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from allocator.blockfile import Block

ContainerMap = dict[int, dict[str, list[str] | float]]

# Cap DP work so we fall back to greedy on very large inputs.
_DP_WORK_LIMIT = 50_000_000

# Default limit for a whole run, in seconds.
DEFAULT_TIME_LIMIT = 10.0

# Upper bound on balancing moves, as a safety net. Each move strictly reduces
# the spread, so the pass always ends well before this in practice.
_MAX_BALANCE_MOVES = 5_000


def _scale(weight: float) -> int:
    """Weights are handled internally in hundredths, as integers."""
    return int(round(weight * 100))


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


@dataclass
class AllocationResult:
    """The outcome of a run, with everything the results window needs."""

    containers: list[list[Block]]
    unplaced: list[Block]
    capacity: float
    max_blocks: int | None = None
    balanced: bool = False
    # False if any container was filled by the greedy fallback, so the
    # result is good but not guaranteed to be the best possible.
    exact: bool = True
    notes: list[str] = field(default_factory=list)

    @staticmethod
    def total(blocks: Sequence[Block]) -> float:
        return round(sum(w for _, w in blocks), 2)

    @property
    def container_totals(self) -> list[float]:
        return [self.total(c) for c in self.containers]

    @property
    def placed_count(self) -> int:
        return sum(len(c) for c in self.containers)

    @property
    def placed_weight(self) -> float:
        return round(sum(self.container_totals), 2)

    @property
    def unplaced_weight(self) -> float:
        return self.total(self.unplaced)

    @property
    def utilisation(self) -> float:
        """Share of the used containers' combined limit that is filled (0–1)."""
        if not self.containers or self.capacity <= 0:
            return 0.0
        return self.placed_weight / (self.capacity * len(self.containers))

    def to_container_map(self) -> ContainerMap:
        return {
            i: {"blocks": [b for b, _ in blocks], "total_weight": self.total(blocks)}
            for i, blocks in enumerate(self.containers, start=1)
        }


# --------------------------------------------------------------------------
# Filling one container
# --------------------------------------------------------------------------


def find_best_subset_dp(
    blocks: Sequence[Block], capacity: float, max_blocks: int | None = None
) -> tuple[list[Block], float]:
    """Find the optimal subset of blocks via 0/1 knapsack DP (numpy-backed).

    Maximises total weight subject to capacity, optionally constrained to at
    most `max_blocks` blocks. Weights are scaled by 100 to work in integers."""
    n = len(blocks)
    if n == 0 or capacity <= 0:
        return [], 0.0
    if max_blocks is not None and max_blocks <= 0:
        return [], 0.0

    cap_scaled = _scale(capacity)
    if cap_scaled <= 0:
        return [], 0.0
    weights_scaled = np.array([_scale(b[1]) for b in blocks], dtype=np.int64)

    use_count_dim = max_blocks is not None and max_blocks < n

    result: list[Block] = []
    if not use_count_dim:
        # Standard 0/1 knapsack. dp[j] = best scaled weight at capacity j.
        dp = np.zeros(cap_scaled + 1, dtype=np.int64)
        chosen = np.zeros((n + 1, cap_scaled + 1), dtype=bool)

        for i in range(1, n + 1):
            ws = int(weights_scaled[i - 1])
            if ws > cap_scaled:
                continue
            candidate = np.full(cap_scaled + 1, -1, dtype=np.int64)
            candidate[ws:] = dp[: cap_scaled + 1 - ws] + ws
            take = candidate > dp
            chosen[i] = take
            dp = np.where(take, candidate, dp)

        j = cap_scaled
        for i in range(n, 0, -1):
            if chosen[i, j]:
                result.append(blocks[i - 1])
                j -= int(weights_scaled[i - 1])
    else:
        # Add a block-count dimension. dp[k, j] = best scaled weight using at
        # most k blocks at capacity j.
        assert max_blocks is not None
        K = max_blocks + 1
        dpk = np.zeros((K, cap_scaled + 1), dtype=np.int64)
        chosenk = np.zeros((n + 1, K, cap_scaled + 1), dtype=bool)

        for i in range(1, n + 1):
            ws = int(weights_scaled[i - 1])
            if ws > cap_scaled:
                continue
            new_dp = dpk.copy()
            for k in range(1, K):
                candidate = np.full(cap_scaled + 1, -1, dtype=np.int64)
                candidate[ws:] = dpk[k - 1, : cap_scaled + 1 - ws] + ws
                take = candidate > new_dp[k]
                chosenk[i, k] = take
                new_dp[k] = np.where(take, candidate, new_dp[k])
            dpk = new_dp

        # Best k is the one that achieves the highest total at full capacity.
        best_k = int(np.argmax(dpk[:, cap_scaled]))

        j = cap_scaled
        k = best_k
        for i in range(n, 0, -1):
            if k > 0 and chosenk[i, k, j]:
                result.append(blocks[i - 1])
                j -= int(weights_scaled[i - 1])
                k -= 1

    total_weight = sum(block[1] for block in result)
    return result, total_weight


def find_best_subset_greedy(
    blocks: Sequence[Block], capacity: float, max_blocks: int | None = None
) -> tuple[list[Block], float]:
    """Find a good subset of blocks quickly by adding the heaviest first.

    This is fast on any input size but may not find the optimal solution."""
    selected: list[Block] = []
    total_scaled = 0
    cap_scaled = _scale(capacity)
    for block in sorted(blocks, key=lambda b: b[1], reverse=True):
        if max_blocks is not None and len(selected) >= max_blocks:
            break
        ws = _scale(block[1])
        if total_scaled + ws <= cap_scaled:
            selected.append(block)
            total_scaled += ws
    return selected, sum(b[1] for b in selected)


def dp_is_feasible(n_blocks: int, capacity: float, max_blocks: int | None = None) -> bool:
    """Whether the exact method is small enough to run in reasonable time."""
    cap_scaled = _scale(capacity)
    count_dim = (max_blocks + 1) if (max_blocks is not None and max_blocks < n_blocks) else 1
    return n_blocks * (cap_scaled + 1) * count_dim <= _DP_WORK_LIMIT


def find_best_subset(
    blocks: Sequence[Block], capacity: float, max_blocks: int | None = None
) -> tuple[list[Block], float]:
    """Find the best subset of blocks that fits within capacity and max_blocks.
    Uses optimal DP when feasible, falling back to greedy on very large inputs."""
    if not blocks or capacity <= 0:
        return [], 0.0
    if dp_is_feasible(len(blocks), capacity, max_blocks):
        return find_best_subset_dp(blocks, capacity, max_blocks)
    return find_best_subset_greedy(blocks, capacity, max_blocks)


# --------------------------------------------------------------------------
# Balancing
# --------------------------------------------------------------------------


def balance_containers(
    containers: list[list[Block]], capacity: float, max_blocks: int | None = None
) -> list[list[Block]]:
    """Even out container loads by moving or swapping blocks between them.

    The set of shipped blocks doesn't change, and no container goes over its
    weight or block-count limit. Each step makes the move that most reduces
    the sum of squared loads, which narrows the gap between the heaviest and
    lightest containers, and stops when no move helps.
    """
    boxes = [list(c) for c in containers]
    cap = _scale(capacity)
    loads = [sum(_scale(w) for _, w in c) for c in boxes]

    def fits(j: int, extra_weight: int, extra_count: int) -> bool:
        if loads[j] + extra_weight > cap:
            return False
        return max_blocks is None or len(boxes[j]) + extra_count <= max_blocks

    for _ in range(_MAX_BALANCE_MOVES):
        best_gain = 0
        best_move: tuple[int, int, int, int | None] | None = None
        for i in range(len(boxes)):
            for j in range(len(boxes)):
                if loads[i] <= loads[j]:
                    continue
                before = loads[i] ** 2 + loads[j] ** 2
                for a, (_, wa) in enumerate(boxes[i]):
                    sa = _scale(wa)
                    # Move block a from i to j.
                    if fits(j, sa, 1):
                        gain = before - (loads[i] - sa) ** 2 - (loads[j] + sa) ** 2
                        if gain > best_gain:
                            best_gain, best_move = gain, (i, j, a, None)
                    # Swap block a (in i) with a lighter block b (in j).
                    for b, (_, wb) in enumerate(boxes[j]):
                        d = sa - _scale(wb)
                        if d <= 0 or not fits(j, d, 0):
                            continue
                        gain = before - (loads[i] - d) ** 2 - (loads[j] + d) ** 2
                        if gain > best_gain:
                            best_gain, best_move = gain, (i, j, a, b)
        if best_move is None:
            break
        i, j, a, swap_with = best_move
        block_a = boxes[i].pop(a)
        if swap_with is not None:
            block_b = boxes[j].pop(swap_with)
            boxes[i].append(block_b)
        boxes[j].append(block_a)
        loads[i] = sum(_scale(w) for _, w in boxes[i])
        loads[j] = sum(_scale(w) for _, w in boxes[j])
    return boxes


# --------------------------------------------------------------------------
# Filling all containers
# --------------------------------------------------------------------------


def _top_up(
    containers: list[list[Block]],
    remaining: list[Block],
    capacity: float,
    max_blocks: int | None,
    lightest_first: bool,
) -> None:
    """Add any leftover block that still fits somewhere (heaviest first)."""
    cap = _scale(capacity)
    for block in sorted(remaining, key=lambda b: b[1], reverse=True):
        order = list(range(len(containers)))
        if lightest_first:
            order.sort(key=lambda i: AllocationResult.total(containers[i]))
        for i in order:
            c = containers[i]
            if max_blocks is not None and len(c) >= max_blocks:
                continue
            if sum(_scale(w) for _, w in c) + _scale(block[1]) <= cap:
                c.append(block)
                remaining.remove(block)
                break


def allocate(
    blocks: Sequence[Block],
    capacity: float,
    count: int,
    max_blocks: int | None = None,
    balance: bool = False,
    time_limit: float = DEFAULT_TIME_LIMIT,
) -> AllocationResult:
    """Pack blocks into up to `count` containers.

    Args:
        blocks: ``(BlockNo, Weight)`` pairs.
        capacity: Weight limit of each container.
        count: Number of containers available.
        max_blocks: Optional limit on blocks per container.
        balance: Spread the shipped blocks evenly across the containers
            instead of filling each one as full as possible in turn.
        time_limit: Seconds after which remaining containers are filled with
            the greedy method so the app never hangs.
    """
    if capacity <= 0:
        raise ValueError("Container capacity must be greater than 0")
    if count <= 0:
        raise ValueError("Number of containers must be greater than 0")
    if max_blocks is not None and max_blocks <= 0:
        raise ValueError("Max blocks per container must be at least 1")

    position: dict[Block, int] = {}
    for i, b in enumerate(blocks):
        position.setdefault(b, i)

    remaining: list[Block] = list(blocks)
    containers: list[list[Block]] = []
    exact = True
    notes: list[str] = []
    deadline = time.monotonic() + time_limit
    timed_out = False

    for _ in range(count):
        if not remaining:
            break
        if not timed_out and time.monotonic() > deadline:
            timed_out = True
            notes.append(
                f"The run passed {time_limit:g} seconds, so the last containers "
                "were filled with the quick method."
            )
        if timed_out or not dp_is_feasible(len(remaining), capacity, max_blocks):
            combo, _ = find_best_subset_greedy(remaining, capacity, max_blocks)
            exact = False
        else:
            combo, _ = find_best_subset_dp(remaining, capacity, max_blocks)
        if not combo:
            # Nothing left fits in an empty container, so it won't fit later.
            break
        containers.append(combo)
        for b in combo:
            remaining.remove(b)

    if not exact and not timed_out:
        notes.append(
            "The job was too large to solve exactly, so the quick method was "
            "used. The result is usually close to the best but isn't guaranteed."
        )

    _top_up(containers, remaining, capacity, max_blocks, lightest_first=balance)

    if balance:
        containers += [[] for _ in range(count - len(containers))]
        containers = balance_containers(containers, capacity, max_blocks)
        _top_up(containers, remaining, capacity, max_blocks, lightest_first=True)
        containers = [c for c in containers if c]
        containers.sort(key=AllocationResult.total, reverse=True)

    for c in containers:
        c.sort(key=lambda b: position[b])
    remaining.sort(key=lambda b: position[b])

    return AllocationResult(
        containers=containers,
        unplaced=remaining,
        capacity=capacity,
        max_blocks=max_blocks,
        balanced=balance,
        exact=exact,
        notes=notes,
    )


def assign_containers(
    blocks: Sequence[Block], capacity: float, count: int, max_blocks: int | None = None
) -> ContainerMap:
    """Pack blocks into `count` containers; returns ``{id: {blocks, total_weight}}``.

    Kept for compatibility. New code should use :func:`allocate`, which also
    reports the blocks that weren't placed."""
    return allocate(blocks, capacity, count, max_blocks).to_container_map()
