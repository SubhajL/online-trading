"""
Generic Type Parameter Fixer

Automatically adds missing type parameters to generic types like dict, list, tuple, etc.
"""

import ast
import re
from typing import Any

# Common generic types that need parameters
BUILTIN_GENERICS = {"dict", "list", "tuple", "set", "frozenset"}
TYPING_GENERICS = {
    "Dict",
    "List",
    "Tuple",
    "Set",
    "FrozenSet",
    "Deque",
    "DefaultDict",
    "OrderedDict",
    "Counter",
}
COLLECTIONS_GENERICS = {"deque", "defaultdict", "OrderedDict", "Counter"}
ASYNCIO_GENERICS = {"Task", "Future", "Queue"}
QUEUE_GENERICS = {"Queue", "PriorityQueue", "LifoQueue", "SimpleQueue"}
OTHER_GENERICS = {
    "Callable",
    "Optional",
    "Union",
    "Type",
    "Iterable",
    "Iterator",
    "Generator",
}

ALL_GENERICS = (
    BUILTIN_GENERICS
    | TYPING_GENERICS
    | COLLECTIONS_GENERICS
    | ASYNCIO_GENERICS
    | QUEUE_GENERICS
    | OTHER_GENERICS
)


def detect_missing_generic_parameters(code: str) -> list[dict[str, Any]]:
    """
    Detect generic types that are missing type parameters

    Args:
        code: Python source code

    Returns:
        List of generic types missing parameters with context
    """
    missing_generics = []
    lines = code.split("\n")

    for line_idx, line in enumerate(lines):
        # Skip comments and strings
        if line.strip().startswith("#") or '"""' in line or "'''" in line:
            continue

        # Look for generic types without brackets
        for generic_type in ALL_GENERICS:
            # Pattern to match bare generic type (not followed by [)
            # Must be word boundary to avoid matching partial names
            pattern = rf"\b{re.escape(generic_type)}\b(?!\s*\[)"

            for match in re.finditer(pattern, line):
                # Check context to avoid false positives
                start_pos = match.start()

                # Skip if it's part of an import statement (we don't parameterize imports)
                if "import" in line[:start_pos]:
                    continue

                # Skip if it's a class definition
                if re.match(r"^\s*class\s+" + generic_type, line):
                    continue

                # Skip if it's a function call (e.g., list(), dict())
                if (
                    match.end() < len(line)
                    and line[match.end() : match.end() + 1] == "("
                ):
                    continue

                # Determine context (return type, argument, variable annotation, etc.)
                context = "unknown"
                within_union = "Union[" in line and match.start() > line.find("Union[")
                within_optional = "Optional[" in line and match.start() > line.find(
                    "Optional[",
                )

                if "->" in line and match.start() > line.find("->"):
                    context = "return"
                elif ":" in line[: match.start()] and "=" not in line[: match.start()]:
                    context = "argument"
                elif ":" in line[: match.start()] and "=" in line[match.start() :]:
                    context = "variable"

                missing_generics.append(
                    {
                        "type_name": generic_type,
                        "line": line_idx,
                        "column": match.start(),
                        "context": context,
                        "within_union": within_union,
                        "within_optional": within_optional,
                        "full_line": line,
                    },
                )

    missing_generics.sort(
        key=lambda item: (item["line"], item["column"], item["type_name"]),
    )
    return missing_generics


def infer_generic_parameters(
    code: str, type_name: str, function_name: str | None, line_num: int,
) -> str:
    """
    Try to infer the generic parameters based on usage

    Args:
        code: Python source code
        type_name: Name of the generic type (e.g., 'dict', 'list')
        function_name: Name of the function if applicable
        line_num: Line number where the type appears

    Returns:
        Inferred parameters as a string (e.g., '[str, Any]')
    """
    # Default parameters for each generic type
    defaults = {
        "dict": "[Any, Any]",
        "Dict": "[Any, Any]",
        "list": "[Any]",
        "List": "[Any]",
        "tuple": "[Any, ...]",
        "Tuple": "[Any, ...]",
        "set": "[Any]",
        "Set": "[Any]",
        "frozenset": "[Any]",
        "FrozenSet": "[Any]",
        "deque": "[Any]",
        "Deque": "[Any]",
        "defaultdict": "[Any, Any]",
        "DefaultDict": "[Any, Any]",
        "OrderedDict": "[Any, Any]",
        "Counter": "[Any]",
        "Queue": "[Any]",
        "PriorityQueue": "[Any]",
        "LifoQueue": "[Any]",
        "SimpleQueue": "[Any]",
        "Task": "[Any]",
        "Future": "[Any]",
        "Callable": "[..., Any]",
        "Type": "[Any]",
        "Iterable": "[Any]",
        "Iterator": "[Any]",
        "Generator": "[Any, None, None]",
    }

    # Try to parse the code and look for return statements or usage
    try:
        tree = ast.parse(code)

        # For dict/Dict types, try to infer from dict literals
        if type_name.lower() == "dict" and function_name:

            class DictInferrer(ast.NodeVisitor):
                def __init__(self):
                    self.in_target_function = False
                    self.key_types = set()
                    self.value_types = set()

                def visit_FunctionDef(self, node):
                    if node.name == function_name:
                        self.in_target_function = True
                        self.generic_visit(node)
                        self.in_target_function = False

                def visit_AsyncFunctionDef(self, node):
                    if node.name == function_name:
                        self.in_target_function = True
                        self.generic_visit(node)
                        self.in_target_function = False

                def visit_Return(self, node):
                    if self.in_target_function and node.value:
                        if isinstance(node.value, ast.Dict):
                            for key in node.value.keys:
                                if isinstance(key, ast.Constant):
                                    if isinstance(key.value, str):
                                        self.key_types.add("str")
                                    elif isinstance(key.value, int):
                                        self.key_types.add("int")
                            # For mixed values, use Any
                            if node.value.values:
                                self.value_types.add("Any")
                    self.generic_visit(node)

            inferrer = DictInferrer()
            inferrer.visit(tree)

            if inferrer.key_types:
                key_type = "str" if "str" in inferrer.key_types else "Any"
                return f"[{key_type}, Any]"

        # For list/List types, try to infer from list literals
        elif type_name.lower() == "list" and function_name:

            class ListInferrer(ast.NodeVisitor):
                def __init__(self):
                    self.in_target_function = False
                    self.element_types = set()

                def visit_FunctionDef(self, node):
                    if node.name == function_name:
                        self.in_target_function = True
                        self.generic_visit(node)
                        self.in_target_function = False

                def visit_Return(self, node):
                    if self.in_target_function and node.value:
                        if isinstance(node.value, ast.List):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant):
                                    if isinstance(elt.value, int):
                                        self.element_types.add("int")
                                    elif isinstance(elt.value, str):
                                        self.element_types.add("str")
                                    elif isinstance(elt.value, float):
                                        self.element_types.add("float")
                    self.generic_visit(node)

            inferrer = ListInferrer()
            inferrer.visit(tree)

            if inferrer.element_types:
                if len(inferrer.element_types) == 1:
                    return f"[{inferrer.element_types.pop()}]"

        # For tuple/Tuple types
        elif type_name.lower() == "tuple" and function_name:

            class TupleInferrer(ast.NodeVisitor):
                def __init__(self):
                    self.in_target_function = False
                    self.tuple_types = []

                def visit_FunctionDef(self, node):
                    if node.name == function_name:
                        self.in_target_function = True
                        self.generic_visit(node)
                        self.in_target_function = False

                def visit_Return(self, node):
                    if self.in_target_function and node.value:
                        if isinstance(node.value, ast.Tuple):
                            types = []
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant):
                                    if isinstance(elt.value, int):
                                        types.append("int")
                                    elif isinstance(elt.value, str):
                                        types.append("str")
                                    else:
                                        types.append("Any")
                                else:
                                    types.append("Any")
                            if types:
                                self.tuple_types = types
                    self.generic_visit(node)

            inferrer = TupleInferrer()
            inferrer.visit(tree)

            if inferrer.tuple_types:
                return f"[{', '.join(inferrer.tuple_types)}]"

    except Exception:
        pass

    # Return default parameters
    return defaults.get(type_name, "[Any]")


def add_generic_type_parameters(code: str) -> str:
    """
    Add type parameters to generic types

    Args:
        code: Python source code

    Returns:
        Code with added generic type parameters
    """
    missing = detect_missing_generic_parameters(code)
    if not missing:
        return code

    lines = code.split("\n")
    modified_lines = lines.copy()
    needs_any = False

    # Group by line number and process in reverse order
    lines_to_process = {}
    for item in missing:
        line_idx = item["line"]
        if line_idx not in lines_to_process:
            lines_to_process[line_idx] = []
        lines_to_process[line_idx].append(item)

    # Process each line with missing generics
    for line_idx in sorted(lines_to_process.keys(), reverse=True):
        items = sorted(
            lines_to_process[line_idx], key=lambda x: x["column"], reverse=True,
        )
        line = modified_lines[line_idx]

        for item in items:
            type_name = item["type_name"]

            # Try to infer parameters
            func_name = None
            if item["context"] == "return":
                # Extract function name from the line above
                for i in range(line_idx - 1, max(0, line_idx - 10), -1):
                    func_match = re.match(r"^\s*(?:async\s+)?def\s+(\w+)", lines[i])
                    if func_match:
                        func_name = func_match.group(1)
                        break

            params = infer_generic_parameters(code, type_name, func_name, line_idx)

            # Add the parameters
            pattern = rf"\b{re.escape(type_name)}\b"

            # Find all matches and replace from right to left
            matches = list(re.finditer(pattern, line))
            for match in reversed(matches):
                if match.start() == item["column"]:
                    line = line[: match.end()] + params + line[match.end() :]
                    if "Any" in params:
                        needs_any = True
                    break

        modified_lines[line_idx] = line

    # Add Any import if needed
    if needs_any:
        import_added = False

        # Check for existing typing imports
        for i, line in enumerate(modified_lines):
            if line.startswith("from typing import") and "Any" not in line:
                match = re.match(r"from typing import (.+)", line)
                if match:
                    imports = match.group(1).strip()
                    new_imports = f"{imports}, Any"
                    modified_lines[i] = f"from typing import {new_imports}"
                    import_added = True
                    break

        if not import_added:
            # Add new typing import
            insert_idx = 0
            has_imports = False

            for i, line in enumerate(modified_lines):
                if line.startswith(("import ", "from ")):
                    has_imports = True
                    insert_idx = i + 1
                elif has_imports and line.strip() and not line.startswith("#"):
                    break

            if has_imports:
                modified_lines.insert(insert_idx, "from typing import Any")
                if (
                    insert_idx < len(modified_lines) - 1
                    and modified_lines[insert_idx + 1].strip()
                ):
                    modified_lines.insert(insert_idx + 1, "")
            # Add at the beginning
            elif modified_lines[0].strip().startswith('"""'):
                # Find end of docstring
                for i in range(1, len(modified_lines)):
                    if '"""' in modified_lines[i]:
                        modified_lines.insert(i + 1, "")
                        modified_lines.insert(i + 2, "from typing import Any")
                        modified_lines.insert(i + 3, "")
                        break
            else:
                modified_lines.insert(0, "from typing import Any")
                modified_lines.insert(1, "")

    return "\n".join(modified_lines)


def fix_generic_type_parameters(code: str) -> str:
    """
    Main function to fix generic type parameters

    Args:
        code: Python source code

    Returns:
        Code with fixed generic type parameters
    """
    return add_generic_type_parameters(code)


def fix_file_generic_types(file_path: str) -> bool:
    """
    Fix generic type parameters in a specific file

    Args:
        file_path: Path to Python file

    Returns:
        True if file was modified, False otherwise
    """
    try:
        with open(file_path) as f:
            original_code = f.read()

        fixed_code = fix_generic_type_parameters(original_code)

        if fixed_code != original_code:
            with open(file_path, "w") as f:
                f.write(fixed_code)
            return True
        return False
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return False
