"""Check physical function length, docstrings and names in maintained Python code."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAMEWORK_NAMES = {"setUp", "tearDown", "setUpClass", "tearDownClass", "setUpTestData"}


def source_files():
    """Select application, tests and tools; exclude generated migrations and venvs."""
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)
        if not any(
            part.startswith(".") or part == "migrations" for part in relative.parts
        ):
            yield path


def function_errors(node):
    """Count every physical line from def through its last statement, inclusively."""
    errors = []
    if node.end_lineno - node.lineno + 1 > 14:
        errors.append("function exceeds 14 physical lines")
    if node.name not in FRAMEWORK_NAMES and not re.fullmatch(
        r"[a-z_][a-z0-9_]*", node.name
    ):
        errors.append("function name is not snake_case")
    if not ast.get_docstring(node):
        errors.append("missing function docstring")
    return errors


def check_file(path):
    """Report source locations for all function violations."""
    problems = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for error in function_errors(node):
                problems.append(f"{path.relative_to(ROOT)}:{node.lineno}: {error}")
    return problems


def main():
    """Fail the check when maintained code violates the documented conventions."""
    problems = [problem for path in source_files() for problem in check_file(path)]
    print("\n".join(problems) if problems else "Conventions passed.")
    return bool(problems)


if __name__ == "__main__":
    raise SystemExit(main())
