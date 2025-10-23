"""
Return Type Annotation Fixer

Automatically adds missing return type annotations to functions
"""

import ast
import re
from typing import Any


def detect_missing_return_types(code: str) -> list[dict[str, Any]]:
    """
    Detect functions missing return type annotations

    Args:
        code: Python source code

    Returns:
        List of functions missing return types with metadata
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    missing_functions = []

    class FunctionVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            # Check if return type annotation is missing
            if node.returns is None:
                # Determine if it's __init__ (should be -> None)
                should_be_none = node.name == "__init__"

                missing_functions.append({
                    "name": node.name,
                    "line": node.lineno - 1,  # 0-based for consistency
                    "is_async": False,
                    "should_be_none": should_be_none,
                })
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            # Check if return type annotation is missing
            if node.returns is None:
                missing_functions.append({
                    "name": node.name,
                    "line": node.lineno - 1,  # 0-based
                    "is_async": True,
                    "should_be_none": False,
                })
            self.generic_visit(node)

    visitor = FunctionVisitor()
    visitor.visit(tree)

    return missing_functions


def infer_return_type(code: str, function_name: str) -> str:
    """
    Try to infer the return type from function body

    Args:
        code: Python source code
        function_name: Name of the function

    Returns:
        Inferred return type or 'Any' if cannot infer
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "Any"

    class ReturnTypeFinder(ast.NodeVisitor):
        def __init__(self) -> None:
            self.return_values = []
            self.in_target_function = False
            self.has_bare_return = False

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if node.name == function_name:
                self.in_target_function = True
                self.generic_visit(node)
                self.in_target_function = False

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if node.name == function_name:
                self.in_target_function = True
                self.generic_visit(node)
                self.in_target_function = False

        def visit_Return(self, node: ast.Return) -> None:
            if self.in_target_function:
                if node.value is None:
                    self.has_bare_return = True
                else:
                    self.return_values.append(node.value)

    finder = ReturnTypeFinder()
    finder.visit(tree)

    # If no return statements or only bare returns, it's None
    if not finder.return_values:
        return "None"

    # Try to infer type from return values
    inferred_types = set()

    for ret_val in finder.return_values:
        if isinstance(ret_val, ast.Constant):
            if isinstance(ret_val.value, bool):
                inferred_types.add("bool")
            elif isinstance(ret_val.value, int):
                inferred_types.add("int")
            elif isinstance(ret_val.value, float):
                inferred_types.add("float")
            elif isinstance(ret_val.value, str):
                inferred_types.add("str")
            elif ret_val.value is None:
                inferred_types.add("None")
        elif isinstance(ret_val, ast.Dict):
            inferred_types.add("dict[str, Any]")
        elif isinstance(ret_val, ast.List):
            inferred_types.add("list[Any]")
        elif isinstance(ret_val, ast.Tuple):
            inferred_types.add("tuple[Any, ...]")
        elif isinstance(ret_val, ast.Name):
            if ret_val.id in ("True", "False"):
                inferred_types.add("bool")
            elif ret_val.id == "None":
                inferred_types.add("None")
        elif isinstance(ret_val, ast.Compare):
            # Comparison operations return bool
            inferred_types.add("bool")
        elif isinstance(ret_val, ast.BinOp):
            # Check if it's a comparison-like operation (e.g., n % 2 == 0)
            # For now, we can't easily infer the type from binary operations
            pass

    # If no types were inferred, return Any
    if not inferred_types:
        return "Any"

    # If we have consistent return types, use them
    if len(inferred_types) == 1:
        return inferred_types.pop()

    # Mixed returns or complex returns
    return "Any"


def add_return_type_annotations(code: str) -> str:
    """
    Add return type annotations to functions missing them

    Args:
        code: Python source code

    Returns:
        Code with added return type annotations
    """
    missing = detect_missing_return_types(code)
    if not missing:
        return code

    lines = code.split("\n")
    modified_lines = lines.copy()
    needs_any = False

    # Sort by line number in reverse to avoid offset issues
    for func_info in sorted(missing, key=lambda x: x["line"], reverse=True):
        func_name = func_info["name"]
        line_idx = func_info["line"]

        # Infer return type
        if func_info.get("should_be_none", False):
            return_type = "None"
        else:
            return_type = infer_return_type(code, func_name)
            if return_type == "Any":
                needs_any = True

        # Find the function definition line(s)
        # Handle multiline signatures
        func_line_idx = line_idx
        func_line = modified_lines[func_line_idx]

        # Check if this is a multiline signature
        paren_count = func_line.count("(") - func_line.count(")")
        end_idx = func_line_idx

        while paren_count > 0 and end_idx < len(modified_lines) - 1:
            end_idx += 1
            next_line = modified_lines[end_idx]
            paren_count += next_line.count("(") - next_line.count(")")

        # Find where to insert the return type
        if end_idx == func_line_idx:
            # Single line function signature
            if ":" in func_line and ")" in func_line:
                # Replace the closing parenthesis and colon with return type
                new_line = re.sub(r"\)(\s*):", f") -> {return_type}:", func_line)
                modified_lines[func_line_idx] = new_line
        else:
            # Multiline signature - add return type on the last line
            last_line = modified_lines[end_idx]
            if ":" in last_line and ")" in last_line:
                new_line = re.sub(r"\)(\s*):", f") -> {return_type}:", last_line)
                modified_lines[end_idx] = new_line

    # Check if Any is used in return types
    code_with_types = "\n".join(modified_lines)
    if "Any" in code_with_types and "from typing import" in code:
        for i, line in enumerate(modified_lines):
            if line.startswith("from typing import") and "Any" not in line:
                # Extract imports
                match = re.match(r"from typing import (.+)", line)
                if match:
                    imports = match.group(1).strip()
                    new_imports = f"{imports}, Any"
                    modified_lines[i] = f"from typing import {new_imports}"
                    break
    elif "Any" in code_with_types and "from typing import" not in code:
        # Add new typing import
        # Find position after imports
        import_end = 0
        for i, line in enumerate(modified_lines):
            if line.startswith("import ") or line.startswith("from "):
                import_end = i + 1
            elif line.strip() and not line.startswith("#"):
                break

        modified_lines.insert(import_end, "from typing import Any")
        if import_end > 0:
            modified_lines.insert(import_end + 1, "")

    return "\n".join(modified_lines)


def fix_return_type_annotations(code: str) -> str:
    """
    Main function to fix return type annotations

    Args:
        code: Python source code

    Returns:
        Code with fixed return type annotations
    """
    return add_return_type_annotations(code)


def fix_file_return_types(file_path: str) -> bool:
    """
    Fix return type annotations in a specific file

    Args:
        file_path: Path to Python file

    Returns:
        True if file was modified, False otherwise
    """
    try:
        with open(file_path) as f:
            original_code = f.read()

        fixed_code = fix_return_type_annotations(original_code)

        if fixed_code != original_code:
            with open(file_path, "w") as f:
                f.write(fixed_code)
            return True
        return False
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return False
