"""Fix operations on potentially None values to prevent runtime errors."""

import ast
from pathlib import Path
import re


class NoneOperationFixer:
    """Fixes operations that could fail when values are None."""

    @staticmethod
    def fix_content(content: str) -> str:
        """Fix None operations in the given content."""
        if not content.strip():
            return content

        try:
            tree = ast.parse(content)
        except SyntaxError:
            # If we can't parse, return unchanged
            return content

        # Analyze and fix the AST
        fixer = NoneOperationTransformer()
        fixed_tree = fixer.visit(tree)
        ast.fix_missing_locations(fixed_tree)

        # Convert back to source code
        try:
            import astor
            return astor.to_source(fixed_tree)
        except ImportError:
            # Fallback to regex-based fixing if astor not available
            return NoneOperationFixer._regex_fix(content)

    @staticmethod
    def _regex_fix(content: str) -> str:
        """Fallback regex-based fixing."""
        lines = content.split("\n")
        result_lines = []

        # Track variables that might be None
        none_vars = set()

        for i, line in enumerate(lines):
            # Detect variables that might be None from type annotations
            # Handle both function params and variable annotations
            if "def " in line and "|" in line:
                # Extract parameter names that can be None
                params = re.findall(
                    r"(\w+):\s*[\w\[\]]+\s*\|\s*None",
                    line,
                )
                none_vars.update(params)

            # Check for operations on potentially None variables
            modified = False
            for var in none_vars:
                # Look for binary operations with the variable
                # Also check for chained attributes
                patterns = [
                    (rf"\b{var}\.", "attr"),  # Chained attributes
                    (rf"\b{var}\s*\*", "*"),
                    (rf"\b{var}\s*\+", "+"),
                    (rf"\b{var}\s*-", "-"),
                    (rf"\s*-\s*{var}", "rsub"),  # Right-side subtraction
                    (rf"\b{var}\s*/", "/"),
                    (rf"\s*/\s*{var}", "rdiv"),  # Right-side division
                ]

                for pattern, op in patterns:
                    if re.search(pattern, line) and "if" not in line:
                        # Check if already guarded (look back up to 3 lines)
                        already_guarded = False
                        for j in range(max(0, i-3), i):
                            if f"if {var} is None:" in lines[j]:
                                already_guarded = True
                                break
                        if already_guarded:
                            break

                        # Add guard before the operation
                        indent = len(line) - len(line.lstrip())
                        spaces = " " * indent

                        # Determine default value based on operation
                        if op == "attr":
                            # For chained attributes, always return Decimal(0)
                            default = "Decimal(0)"
                        elif op in ["*", "/", "rdiv"]:
                            # Check if it's int or Decimal context
                            if "int" in line:
                                default = "0"
                            else:
                                default = "Decimal(0)"
                        elif op == "+":
                            # For addition, find the other operand
                            match = re.search(rf"{var}\s*\+\s*(\w+)", line)
                            if match:
                                default = match.group(1)
                            else:
                                default = "0"
                        elif op == "-":
                            # For subtraction, return the left operand
                            match = re.search(
                                rf"(\w+)\s*-\s*{var}", line,
                            )
                            if match:
                                default = match.group(1)
                            else:
                                default = "0"
                        elif op == "rsub":
                            # For right-side subtraction, return left operand
                            match = re.search(rf"(\w+)\s*-\s*{var}", line)
                            if match:
                                default = match.group(1)
                            else:
                                default = "total"
                        else:
                            default = "0"

                        # If it's a return statement, add guard before
                        if line.strip().startswith("return"):
                            guard = f"{spaces}if {var} is None:"
                            ret = f"{spaces}    return {default}"
                            result_lines.append(guard)
                            result_lines.append(ret)
                            result_lines.append(line)
                            modified = True
                            break
                        # If it's an assignment, convert to ternary
                        is_assignment = "=" in line
                        is_not_def = not line.strip().startswith("def")
                        if is_assignment and is_not_def:
                            parts = line.split("=", 1)
                            if len(parts) == 2:
                                lhs = parts[0]
                                rhs = parts[1].strip()
                                # Determine default for ternary based on type
                                if "int" in lines[i-1] or "int" in lines[i-2]:
                                    ternary_default = "0"
                                else:
                                    ternary_default = default
                                condition = f"{var} is not None"
                                new_line = (
                                    f"{lhs}= {rhs} if {condition} else "
                                    f"{ternary_default}"
                                )
                                result_lines.append(new_line)
                                modified = True
                                break

            if not modified:
                result_lines.append(line)

        return "\n".join(result_lines)

    @staticmethod
    def fix_file(file_path: str) -> None:
        """Fix None operations in a single file."""
        with open(file_path) as f:
            content = f.read()

        fixed_content = NoneOperationFixer.fix_content(content)

        if fixed_content != content:
            with open(file_path, "w") as f:
                f.write(fixed_content)

    @staticmethod
    def get_files_with_none_operation_errors() -> list[str]:
        """Get list of files that have None operation errors."""
        # These files were identified from mypy output
        return [
            "app/engine/backtest/backtest_engine.py",
            "app/engine/features/engine.py",
            "app/engine/features/feature_service.py",
            "app/engine/paper/paper_broker.py",
            "app/engine/plugins/plugin_manager.py",
        ]

    @staticmethod
    def fix_all() -> None:
        """Fix all files with None operation errors."""
        files = NoneOperationFixer.get_files_with_none_operation_errors()
        fixed_count = 0

        for file_path in files:
            if Path(file_path).exists():
                print(f"Fixing None operations in {file_path}")
                NoneOperationFixer.fix_file(file_path)
                fixed_count += 1

        print(f"Fixed {fixed_count} files")


class NoneOperationTransformer(ast.NodeTransformer):
    """AST transformer to fix None operations."""

    def __init__(self):
        self.none_vars: set[str] = set()
        self.current_function = None

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Track function definitions and their parameters."""
        old_none_vars = self.none_vars.copy()
        old_function = self.current_function
        self.current_function = node

        # Find parameters that can be None
        for arg in node.args.args:
            if arg.annotation:
                if self._is_optional_type(arg.annotation):
                    self.none_vars.add(arg.arg)

        # Visit function body
        self.generic_visit(node)

        # Restore context
        self.none_vars = old_none_vars
        self.current_function = old_function
        return node

    def visit_BinOp(self, node: ast.BinOp):
        """Fix binary operations that might involve None."""
        self.generic_visit(node)

        # Check if left operand might be None
        left_name = self._get_name(node.left)
        if left_name and left_name in self.none_vars:
            # Need to guard this operation
            return self._create_guarded_binop(node, left_name)

        return node

    def _is_optional_type(self, annotation) -> bool:
        """Check if a type annotation indicates optional (can be None)."""
        # Handle Union types (e.g., Union[int, None] or int | None)
        is_binop = isinstance(annotation, ast.BinOp)
        is_bitor = isinstance(annotation.op, ast.BitOr) if is_binop else False
        if is_binop and is_bitor:
            # Check if right side is None
            is_const = isinstance(annotation.right, ast.Constant)
            is_none = annotation.right.value is None if is_const else False
            if is_const and is_none:
                return True
        return False

    def _get_name(self, node) -> str | None:
        """Get the name of a variable if it's a simple Name node."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            # Handle chained attributes like order.price
            base = self._get_name(node.value)
            return base
        return None

    def _create_guarded_binop(self, node: ast.BinOp, var_name: str):
        """Create a guarded version of a binary operation."""
        # Create: var_name is not None
        test = ast.Compare(
            left=ast.Name(id=var_name, ctx=ast.Load()),
            ops=[ast.IsNot()],
            comparators=[ast.Constant(value=None)],
        )

        # Determine default value based on operation
        if isinstance(node.op, (ast.Mult, ast.Div)):
            default = ast.Call(
                func=ast.Name(id="Decimal", ctx=ast.Load()),
                args=[ast.Constant(value="0")],
                keywords=[],
            )
        elif isinstance(node.op, ast.Add):
            # For addition, default to the other operand
            default = node.right
        else:
            default = ast.Constant(value=0)

        # Create: node if test else default
        return ast.IfExp(test=test, body=node, orelse=default)


if __name__ == "__main__":
    # Fix all files when run directly
    NoneOperationFixer.fix_all()
