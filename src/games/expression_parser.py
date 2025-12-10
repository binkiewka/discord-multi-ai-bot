"""
Safe mathematical expression parser for the Countdown Numbers Game.
Uses Python's ast module to safely evaluate expressions without eval().
"""

import ast
import operator
import re
from typing import Dict, List, Optional, Tuple, Union
from collections import Counter


class ExpressionParser:
    """
    Safely parses and evaluates mathematical expressions.
    Only allows: +, -, *, / operators, integers, and parentheses.
    """

    # Mapping of AST operators to actual Python operators
    SAFE_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
    }

    # Characters allowed in expressions
    ALLOWED_CHARS = set('0123456789+-*/() ')

    def __init__(self):
        pass

    def sanitize(self, expression: str) -> str:
        """Remove any characters not in the allowed set."""
        return ''.join(c for c in expression if c in self.ALLOWED_CHARS)

    def extract_numbers(self, expression: str) -> List[int]:
        """
        Extract all numbers from an expression.
        Returns list of integers found in the expression.
        """
        # Find all number sequences in the expression
        number_strings = re.findall(r'\d+', expression)
        return [int(n) for n in number_strings]

    def validate_numbers(self, expression: str, available: List[int]) -> Tuple[bool, Optional[str]]:
        """
        Check if expression only uses available numbers (each once max).

        Args:
            expression: The mathematical expression
            available: List of available numbers to use

        Returns:
            Tuple of (is_valid, error_message or None)
        """
        used_numbers = self.extract_numbers(expression)
        available_counter = Counter(available)
        used_counter = Counter(used_numbers)

        # Check each used number
        for num, count in used_counter.items():
            if num not in available_counter:
                return False, f"Number **{num}** is not available"
            if count > available_counter[num]:
                return False, f"Number **{num}** used more times than available"

        return True, None

    def _safe_eval(self, node: ast.AST) -> Union[int, float]:
        """
        Recursively evaluate AST node with only allowed operations.

        Raises:
            ValueError: If an unsupported operation is encountered
        """
        # Handle numeric literals (Python 3.8+)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Only numeric values allowed")

        # Handle numeric literals (Python 3.7 and earlier)
        if isinstance(node, ast.Num):
            return node.n

        # Handle binary operations (+, -, *, /)
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self.SAFE_OPERATORS:
                raise ValueError(f"Operator not allowed: {op_type.__name__}")

            left = self._safe_eval(node.left)
            right = self._safe_eval(node.right)

            # Check for division by zero
            if op_type == ast.Div and right == 0:
                raise ValueError("Division by zero")

            return self.SAFE_OPERATORS[op_type](left, right)

        # Handle unary operations (negation)
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                return -self._safe_eval(node.operand)
            if isinstance(node.op, ast.UAdd):
                return self._safe_eval(node.operand)
            raise ValueError("Unsupported unary operator")

        # Handle parenthesized expressions (ast.Expression wrapper)
        if isinstance(node, ast.Expression):
            return self._safe_eval(node.body)

        raise ValueError("Invalid expression structure")

    def evaluate(self, expression: str) -> Tuple[bool, Optional[Union[int, float]], Optional[str]]:
        """
        Safely evaluate expression using AST parsing.

        Args:
            expression: The mathematical expression to evaluate

        Returns:
            Tuple of (success, result or None, error_message or None)
        """
        # Sanitize input
        clean_expr = self.sanitize(expression)

        if not clean_expr.strip():
            return False, None, "Empty expression"

        try:
            # Parse the expression into an AST
            tree = ast.parse(clean_expr, mode='eval')

            # Evaluate using our safe evaluator
            result = self._safe_eval(tree)

            return True, result, None

        except SyntaxError as e:
            return False, None, f"Invalid syntax: {str(e)}"
        except ValueError as e:
            return False, None, str(e)
        except Exception as e:
            return False, None, f"Evaluation error: {str(e)}"

    def parse_and_validate(self, expression: str, available_numbers: List[int]) -> Dict:
        """
        Complete validation and evaluation of an expression.

        Args:
            expression: The mathematical expression
            available_numbers: List of numbers the player can use

        Returns:
            Dictionary with:
            - valid: bool
            - result: int/float or None
            - error: str or None
            - numbers_used: list of numbers used
        """
        result = {
            'valid': False,
            'result': None,
            'error': None,
            'numbers_used': []
        }

        # Sanitize
        clean_expr = self.sanitize(expression)

        if not clean_expr.strip():
            result['error'] = "Empty expression"
            return result

        # Extract and validate numbers
        numbers_used = self.extract_numbers(clean_expr)
        result['numbers_used'] = numbers_used

        is_valid, error = self.validate_numbers(clean_expr, available_numbers)
        if not is_valid:
            result['error'] = error
            return result

        # Evaluate the expression
        success, eval_result, error = self.evaluate(clean_expr)

        if not success:
            result['error'] = error
            return result

        # Round to handle floating point issues, but keep as float if not whole
        if isinstance(eval_result, float):
            if eval_result == int(eval_result):
                eval_result = int(eval_result)

        result['valid'] = True
        result['result'] = eval_result

        return result
