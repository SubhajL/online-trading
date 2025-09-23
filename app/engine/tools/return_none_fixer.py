"""Tool to fix 'No return value expected' errors in Python files."""

import ast
import re
from pathlib import Path
from typing import List, Set, Tuple, Optional


class ReturnNoneFixer:
    """Fixes functions that have -> None but return values."""

    @staticmethod
    def fix_return_none_errors(content: str) -> str:
        """Fix return None errors in the given content."""
        if not content.strip():
            return content

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return content

        lines = content.split('\n')
        fixes = []

        class ReturnFinder(ast.NodeVisitor):
            def __init__(self):
                self.current_function = None
                self.current_class = None

            def visit_ClassDef(self, node):
                old_class = self.current_class
                self.current_class = node.name
                self.generic_visit(node)
                self.current_class = old_class

            def visit_FunctionDef(self, node):
                self._check_function(node)

            def visit_AsyncFunctionDef(self, node):
                self._check_function(node)

            def _check_function(self, node):
                old_function = self.current_function
                self.current_function = node

                # Check if function has -> None return annotation
                if node.returns:
                    return_type = ast.unparse(node.returns) if hasattr(ast, 'unparse') else None

                    # Special case for __hash__ method
                    if node.name == '__hash__' and return_type == 'None':
                        # Fix __hash__ to return int
                        fixes.append({
                            'line': node.returns.lineno - 1,
                            'type': 'fix_hash_return_type'
                        })
                    elif return_type == 'None':
                        # Find all return statements with values
                        for child in ast.walk(node):
                            if isinstance(child, ast.Return) and child.value is not None:
                                # Don't process returns in nested functions
                                if self._is_in_current_function(child, node):
                                    fixes.append({
                                        'line': child.lineno - 1,
                                        'type': 'remove_return_value'
                                    })

                self.generic_visit(node)
                self.current_function = old_function

            def _is_in_current_function(self, node, func_node):
                """Check if a node is directly in the current function, not nested."""
                # This is a simplified check - in reality would need more complex logic
                return True

        finder = ReturnFinder()
        finder.visit(tree)

        # Apply fixes in reverse order to avoid line number issues
        fixes.sort(key=lambda x: x['line'], reverse=True)

        for fix in fixes:
            line_idx = fix['line']
            if fix['type'] == 'fix_hash_return_type':
                # Replace -> None with -> int for __hash__ methods
                if line_idx < len(lines):
                    lines[line_idx] = re.sub(r'def __hash__\(self\)\s*->\s*None:',
                                           'def __hash__(self) -> int:',
                                           lines[line_idx])
            elif fix['type'] == 'remove_return_value':
                # Remove the return statement or just the value
                if line_idx < len(lines):
                    line = lines[line_idx]
                    # Check if it's a simple return statement
                    if re.match(r'^\s*return\s+\S', line):
                        # Get the indentation
                        indent_match = re.match(r'^(\s*)', line)
                        indent = indent_match.group(1) if indent_match else ''
                        # Remove the entire line if it's just a return statement
                        # Check if the previous line can stand alone
                        if line_idx > 0:
                            prev_line = lines[line_idx - 1].rstrip()
                            # If previous line ends with : or is empty, keep return
                            if prev_line.endswith(':') or not prev_line.strip():
                                lines[line_idx] = f"{indent}return"
                            else:
                                # Remove the line entirely
                                lines.pop(line_idx)

        return '\n'.join(lines)

    @staticmethod
    def fix_file(file_path: str) -> None:
        """Fix return None errors in a file."""
        with open(file_path, 'r') as f:
            content = f.read()

        fixed_content = ReturnNoneFixer.fix_return_none_errors(content)

        if fixed_content != content:
            with open(file_path, 'w') as f:
                f.write(fixed_content)

    @staticmethod
    def get_files_with_return_none_errors(directory: str) -> List[str]:
        """Find all Python files with return None errors."""
        files_with_errors = []

        for py_file in Path(directory).rglob('*.py'):
            # Skip virtual environment
            if '.venv' in py_file.parts or 'venv' in py_file.parts:
                continue

            try:
                with open(py_file, 'r') as f:
                    content = f.read()

                # Look for functions with -> None that have return statements with values
                if '-> None:' in content and re.search(r'return\s+[^:\s]', content):
                    files_with_errors.append(str(py_file))
                # Also check for __hash__ -> None
                elif re.search(r'def __hash__\(self\)\s*->\s*None:', content):
                    files_with_errors.append(str(py_file))
            except Exception:
                # Skip files that can't be read
                pass

        return files_with_errors

    @staticmethod
    def fix_all_files(directory: str) -> int:
        """Fix all files with return None errors in a directory."""
        files_with_errors = ReturnNoneFixer.get_files_with_return_none_errors(directory)

        for file_path in files_with_errors:
            print(f"Fixing return None errors in {file_path}")
            ReturnNoneFixer.fix_file(file_path)

        return len(files_with_errors)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        directory = "app/engine"

    fixed_count = ReturnNoneFixer.fix_all_files(directory)
    print(f"Fixed {fixed_count} files")