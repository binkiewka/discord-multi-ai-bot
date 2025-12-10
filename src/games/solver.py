
import operator
import itertools
from typing import List, Tuple, Optional, Set

class CountdownSolver:
    """
    Solver for the Countdown Numbers Game.
    Finds a sequence of operations to reach a target number.
    """

    OPS = {
        '+': operator.add,
        '-': operator.sub,
        '*': operator.mul,
        '/': operator.floordiv # Integer division as per most countdown rules, but we check for remainder
    }

    def __init__(self):
        pass

    def solve(self, target: int, numbers: List[int]) -> Tuple[Optional[str], int]:
        """
        Find the expression that equals the target or is closest to it.
        
        Args:
            target: The target number to reach.
            numbers: List of available numbers.
            
        Returns:
            Tuple of (expression_string, result_value).
            expression_string is None if no solution found (shouldn't happen with 0 as worst case).
            result_value is the calculated value.
        """
        best_expression = None
        best_result = 0
        best_diff = target  # Initialize with max possible difference

        # We can try to solve this recursively.
        # Since N is small (6 numbers), we can try permutations/combinations?
        # A more efficient approach for Countdown is usually recursive search.
        
        # State: List of (value, expression_string)
        # Initial state: [(n, str(n)) for n in numbers]
        
        # We need to explore all ways to combine these.
        
        # Limit the search space if needed, but for 6 numbers it's usually fine.
        
        # To handle "closest" as well, we track the best found so far.
        
        def _recursive_solve(current_numbers: List[Tuple[int, str]]):
            nonlocal best_expression, best_result, best_diff
            
            # Check current numbers for closeness to target
            for val, expr in current_numbers:
                diff = abs(target - val)
                if diff < best_diff:
                    best_diff = diff
                    best_result = val
                    best_expression = expr
                    if best_diff == 0:
                        return True # Found exact match
            
            # If we have only one number left, we can't combine anymore
            if len(current_numbers) <= 1:
                return False

            # Try combining any two numbers
            # This is O(N^2) per step, where N decreases.
            for i in range(len(current_numbers)):
                for j in range(len(current_numbers)):
                    if i == j:
                        continue
                    
                    val1, expr1 = current_numbers[i]
                    val2, expr2 = current_numbers[j]
                    
                    # Optimization: Commutative ops, order by value to avoid duplicates?
                    # For + and *, order doesn't matter. For - and /, it does.
                    # To reduce search space:
                    # For +, *, allow if i < j (since we iterate all pairs, this covers one order)
                    # For -, allow if val1 > val2 (since negative results not allowed in traditional countdown)
                    # For /, allow if val1 % val2 == 0 and val2 != 0 and val2 != 1 (div 1 is useless)
                    
                    # Remaining numbers to pass to next step
                    remaining = [current_numbers[k] for k in range(len(current_numbers)) if k != i and k != j]
                    
                    # Try +
                    if i < j: # Commutative symmetry breaking
                        new_val = val1 + val2
                        if _recursive_solve(remaining + [(new_val, f"({expr1} + {expr2})")]): return True
                        
                    # Try *
                    if i < j: # Commutative symmetry breaking
                        # Optimization: x * 1 = x, useless step
                        if val1 != 1 and val2 != 1:
                            new_val = val1 * val2
                            if _recursive_solve(remaining + [(new_val, f"({expr1} * {expr2})")]): return True

                    # Try -
                    if val1 > val2: # Result must be positive
                        new_val = val1 - val2
                        # Optimization: x - y = z, if z is very small or already in set? Not strictly useless.
                        if _recursive_solve(remaining + [(new_val, f"({expr1} - {expr2})")]): return True
                        
                    # Try /
                    if val2 > 1 and val1 % val2 == 0: # Integer result, no div by 1
                        new_val = val1 // val2
                        if _recursive_solve(remaining + [(new_val, f"({expr1} / {expr2})")]): return True
            
            return False

        initial_state = [(n, str(n)) for n in numbers]
        _recursive_solve(initial_state)
        
        return best_expression, best_result
