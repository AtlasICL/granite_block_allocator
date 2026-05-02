from typing import List, Tuple, Dict, Union, Optional
import numpy as np
import pandas as pd
import time

# Type alias for clarity
dBlock = Tuple[int, float]
ContainerMap = Dict[int, Dict[str, Union[List[int], float]]]

# Cap DP work so we fall back to greedy on very large inputs.
_DP_WORK_LIMIT = 50_000_000


def load_blocks(path: str) -> List[dBlock]:
    """Load CSV and return list of (BlockNo, Weight).
    Ensures the required columns exist and handles potential errors."""
    try:
        df = pd.read_csv(path)
        
        # Verify required columns exist
        required_cols = ['BlockNo', 'Weight']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Required column '{col}' not found in CSV file")
        
        # Check for invalid values
        if df['BlockNo'].isna().any():
            raise ValueError("CSV contains empty BlockNo values")
        if df['Weight'].isna().any():
            raise ValueError("CSV contains empty Weight values")
        
        return list(df[['BlockNo', 'Weight']].itertuples(index=False, name=None))
    except Exception as e:
        raise ValueError(f"Error loading CSV file: {str(e)}")


def find_best_subset_dp(blocks: List[dBlock], capacity: float, max_blocks: Optional[int] = None) -> Tuple[List[dBlock], float]:
    """Find the optimal subset of blocks via 0/1 knapsack DP (numpy-backed).

    Maximises total weight subject to capacity, optionally constrained to at
    most `max_blocks` blocks. Weights are scaled by 100 to work in integers."""
    n = len(blocks)
    if n == 0 or capacity <= 0:
        return [], 0.0
    if max_blocks is not None and max_blocks <= 0:
        return [], 0.0

    cap_scaled = int(round(capacity * 100))
    if cap_scaled <= 0:
        return [], 0.0
    weights_scaled = np.array(
        [int(round(b[1] * 100)) for b in blocks], dtype=np.int64
    )

    use_count_dim = max_blocks is not None and max_blocks < n

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

        result = []
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
        dp = np.zeros((K, cap_scaled + 1), dtype=np.int64)
        chosen = np.zeros((n + 1, K, cap_scaled + 1), dtype=bool)

        for i in range(1, n + 1):
            ws = int(weights_scaled[i - 1])
            if ws > cap_scaled:
                continue
            new_dp = dp.copy()
            for k in range(1, K):
                candidate = np.full(cap_scaled + 1, -1, dtype=np.int64)
                candidate[ws:] = dp[k - 1, : cap_scaled + 1 - ws] + ws
                take = candidate > new_dp[k]
                chosen[i, k] = take
                new_dp[k] = np.where(take, candidate, new_dp[k])
            dp = new_dp

        # Best k is the one that achieves the highest total at full capacity.
        best_k = int(np.argmax(dp[:, cap_scaled]))

        result = []
        j = cap_scaled
        k = best_k
        for i in range(n, 0, -1):
            if k > 0 and chosen[i, k, j]:
                result.append(blocks[i - 1])
                j -= int(weights_scaled[i - 1])
                k -= 1

    total_weight = sum(block[1] for block in result)
    return result, total_weight


def find_best_subset_greedy(blocks: List[dBlock], capacity: float, max_blocks: Optional[int] = None) -> Tuple[List[dBlock], float]:
    """Find a good subset of blocks using a greedy approach.
    This is more efficient but may not find the optimal solution."""
    # Sort blocks by weight/mass ratio in descending order for better greedy results
    sorted_blocks = sorted(blocks, key=lambda x: x[1], reverse=True)
    
    selected_blocks = []
    total_weight = 0.0
    
    # Try to find a good solution
    for block in sorted_blocks:
        # If adding this block doesn't exceed capacity
        if total_weight + block[1] <= capacity:
            # And doesn't exceed max_blocks (if specified)
            if max_blocks is None or len(selected_blocks) < max_blocks:
                selected_blocks.append(block)
                total_weight += block[1]
    
    return selected_blocks, total_weight


def find_best_subset(blocks: List[dBlock], capacity: float, max_blocks: Optional[int] = None) -> Tuple[List[dBlock], float]:
    """Find the best subset of blocks that fits within capacity and max_blocks constraint.
    Uses optimal DP when feasible, falling back to greedy on very large inputs."""
    if not blocks or capacity <= 0:
        return [], 0.0

    n = len(blocks)
    cap_scaled = int(round(capacity * 100))
    count_dim = (max_blocks + 1) if (max_blocks is not None and max_blocks < n) else 1
    work = n * (cap_scaled + 1) * count_dim

    if work <= _DP_WORK_LIMIT:
        return find_best_subset_dp(blocks, capacity, max_blocks)

    return find_best_subset_greedy(blocks, capacity, max_blocks)


def assign_containers(blocks: List[dBlock], capacity: float, count: int, max_blocks: Optional[int] = None) -> ContainerMap:
    """Pack blocks into `count` containers with optional max blocks per container limit."""
    # Input validation
    if capacity <= 0:
        raise ValueError("Container capacity must be greater than 0")
    if count <= 0:
        raise ValueError("Number of containers must be greater than 0")
    
    # Make a copy to avoid modifying the original
    remaining = blocks.copy()
    assignments: ContainerMap = {}
    
    # Track running time to prevent excessive computation
    start_time = time.time()
    timeout = 10.0  # 10 seconds max for the entire allocation
    
    for cid in range(1, count + 1):
        # Check timeout to prevent hanging
        if time.time() - start_time > timeout:
            # If we're timing out, process remaining containers with greedy approach
            while remaining and cid <= count:
                greedy_combo, greedy_total = find_best_subset_greedy(
                    remaining[:min(20, len(remaining))], capacity, max_blocks
                )
                if not greedy_combo:
                    break
                    
                assignments[cid] = {
                    'blocks': [b[0] for b in greedy_combo],
                    'total_weight': greedy_total
                }
                for b in greedy_combo:
                    remaining.remove(b)
                cid += 1
            break
            
        if not remaining:
            break
            
        combo, total = find_best_subset(remaining, capacity, max_blocks)
        
        assignments[cid] = {
            'blocks': [b[0] for b in combo],
            'total_weight': total
        }
        
        for b in combo:
            remaining.remove(b)
    
    return assignments