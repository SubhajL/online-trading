"""
Argument Type Annotation Fixer

Automatically adds missing type annotations to function arguments
"""

import ast
import re
from typing import List, Dict, Any, Optional, Set


def detect_missing_argument_types(code: str) -> List[Dict[str, Any]]:
    """
    Detect functions with missing argument type annotations

    Args:
        code: Python source code

    Returns:
        List of functions with missing argument types
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    missing_functions = []

    class FunctionVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            missing_args = []
            has_args = False
            has_kwargs = False

            for arg in node.args.args:
                # Skip self and cls parameters
                if arg.arg in ('self', 'cls'):
                    continue
                # Check if argument has type annotation
                if arg.annotation is None:
                    missing_args.append(arg.arg)

            # Check for *args
            if node.args.vararg:
                if node.args.vararg.annotation is None:
                    has_args = True

            # Check for **kwargs
            if node.args.kwarg:
                if node.args.kwarg.annotation is None:
                    has_kwargs = True

            if missing_args or has_args or has_kwargs:
                missing_functions.append({
                    'name': node.name,
                    'line': node.lineno - 1,  # 0-based
                    'missing_args': missing_args,
                    'has_args': has_args,
                    'has_kwargs': has_kwargs,
                    'is_async': False
                })

            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            missing_args = []
            has_args = False
            has_kwargs = False

            for arg in node.args.args:
                if arg.arg in ('self', 'cls'):
                    continue
                if arg.annotation is None:
                    missing_args.append(arg.arg)

            if node.args.vararg and node.args.vararg.annotation is None:
                has_args = True

            if node.args.kwarg and node.args.kwarg.annotation is None:
                has_kwargs = True

            if missing_args or has_args or has_kwargs:
                missing_functions.append({
                    'name': node.name,
                    'line': node.lineno - 1,
                    'missing_args': missing_args,
                    'has_args': has_args,
                    'has_kwargs': has_kwargs,
                    'is_async': True
                })

            self.generic_visit(node)

    visitor = FunctionVisitor()
    visitor.visit(tree)

    return missing_functions


def infer_argument_type(code: str, function_name: str, arg_name: str) -> str:
    """
    Try to infer the argument type from its usage in the function

    Args:
        code: Python source code
        function_name: Name of the function
        arg_name: Name of the argument

    Returns:
        Inferred type or 'Any' if cannot infer
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 'Any'

    class ArgumentUsageFinder(ast.NodeVisitor):
        def __init__(self):
            self.in_target_function = False
            self.inferred_types = set()

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

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if self.in_target_function and isinstance(node.value, ast.Name):
                if node.value.id == arg_name:
                    # Check method names to infer type
                    if node.attr in ('upper', 'lower', 'strip', 'split', 'replace', 'startswith', 'endswith'):
                        self.inferred_types.add('str')
                    elif node.attr in ('append', 'extend', 'pop', 'remove'):
                        self.inferred_types.add('list')
                    elif node.attr in ('get', 'items', 'keys', 'values', 'update'):
                        self.inferred_types.add('dict')
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            if self.in_target_function:
                # Check if argument is used as a callable
                if isinstance(node.func, ast.Name) and node.func.id == arg_name:
                    self.inferred_types.add('callable')
                # Check for len() calls
                elif isinstance(node.func, ast.Name) and node.func.id == 'len':
                    if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == arg_name:
                        # Could be list, dict, str, etc.
                        pass
            self.generic_visit(node)

        def visit_Subscript(self, node: ast.Subscript) -> None:
            if self.in_target_function and isinstance(node.value, ast.Name):
                if node.value.id == arg_name:
                    # Being subscripted suggests dict or list
                    if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                        self.inferred_types.add('dict')
                    else:
                        # Could be list or dict
                        pass
            self.generic_visit(node)

        def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
            # f-string - check if our argument is used in it
            if self.in_target_function:
                for value in node.values:
                    if isinstance(value, ast.FormattedValue):
                        if isinstance(value.value, ast.Name) and value.value.id == arg_name:
                            self.inferred_types.add('str')
            self.generic_visit(node)

    finder = ArgumentUsageFinder()
    finder.visit(tree)

    # Determine type based on findings
    if 'str' in finder.inferred_types:
        return 'str'
    elif 'list' in finder.inferred_types:
        return 'list[Any]'
    elif 'dict' in finder.inferred_types:
        return 'dict[str, Any]'
    elif 'callable' in finder.inferred_types:
        return 'Callable[[], Any]'
    else:
        return 'Any'


def add_argument_type_annotations(code: str) -> str:
    """
    Add type annotations to function arguments

    Args:
        code: Python source code

    Returns:
        Code with added argument type annotations
    """
    missing = detect_missing_argument_types(code)
    if not missing:
        return code

    lines = code.split('\n')
    modified_lines = lines.copy()
    needed_imports = set()

    # Process functions in reverse order to avoid line offset issues
    for func_info in sorted(missing, key=lambda x: x['line'], reverse=True):
        func_name = func_info['name']
        missing_args = func_info['missing_args']
        line_idx = func_info['line']

        # Find the function definition
        func_start_idx = line_idx
        func_line = modified_lines[func_start_idx]

        # Check if multiline function signature
        if func_line.rstrip().endswith(',') or '(' in func_line and ')' not in func_line:
            # Find the end of the function signature
            paren_count = func_line.count('(') - func_line.count(')')
            end_idx = func_start_idx

            while paren_count > 0 and end_idx < len(modified_lines) - 1:
                end_idx += 1
                next_line = modified_lines[end_idx]
                paren_count += next_line.count('(') - next_line.count(')')

            # Process each line in the function signature
            for idx in range(func_start_idx, end_idx + 1):
                line = modified_lines[idx]
                new_line = line

                # Add annotations to missing arguments
                for arg in missing_args:
                    # Infer type
                    arg_type = infer_argument_type(code, func_name, arg)
                    if arg_type == 'Any':
                        needed_imports.add('Any')
                    elif 'Callable' in arg_type:
                        needed_imports.add('Callable')
                        needed_imports.add('Any')

                    # Add type annotation
                    # Match argument with optional whitespace
                    pattern = rf'\b{re.escape(arg)}\b(?!\s*[:=])'
                    replacement = f'{arg}: {arg_type}'
                    new_line = re.sub(pattern, replacement, new_line)

                # Handle *args and **kwargs
                if func_info['has_args']:
                    new_line = re.sub(r'\*(\w+)(?![\s:*])', r'*\1: Any', new_line)
                    needed_imports.add('Any')
                if func_info['has_kwargs']:
                    # More specific regex to avoid double replacement
                    new_line = re.sub(r'\*\*(\w+)(?!:)(?=\))', r'**\1: Any', new_line)
                    needed_imports.add('Any')

                modified_lines[idx] = new_line
        else:
            # Single line function signature
            new_line = func_line

            for arg in missing_args:
                arg_type = infer_argument_type(code, func_name, arg)
                if arg_type == 'Any':
                    needed_imports.add('Any')
                elif 'Callable' in arg_type:
                    needed_imports.add('Callable')
                    needed_imports.add('Any')

                pattern = rf'\b{re.escape(arg)}\b(?!\s*[:=])'
                replacement = f'{arg}: {arg_type}'
                new_line = re.sub(pattern, replacement, new_line)

            if func_info['has_args']:
                new_line = re.sub(r'\*(\w+)(?![\s:*])', r'*\1: Any', new_line)
                needed_imports.add('Any')
            if func_info['has_kwargs']:
                new_line = re.sub(r'\*\*(\w+)(?!:)(?=\))', r'**\1: Any', new_line)
                needed_imports.add('Any')

            modified_lines[func_start_idx] = new_line

    # Add necessary imports
    if needed_imports:
        import_added = False
        typing_line_idx = -1

        # Check for existing typing imports
        for i, line in enumerate(modified_lines):
            if line.startswith('from typing import'):
                typing_line_idx = i
                match = re.match(r'from typing import (.+)', line)
                if match:
                    existing_imports = set(imp.strip() for imp in match.group(1).split(','))
                    new_imports = existing_imports | needed_imports
                    new_import_str = ', '.join(sorted(new_imports))
                    modified_lines[i] = f'from typing import {new_import_str}'
                    import_added = True
                break

        if not import_added:
            # Add new typing import
            import_str = ', '.join(sorted(needed_imports))
            import_line = f'from typing import {import_str}'

            # Find position to insert
            insert_idx = 0
            has_imports = False
            for i, line in enumerate(modified_lines):
                if line.startswith(('import ', 'from ')):
                    has_imports = True
                    insert_idx = i + 1
                elif has_imports and line.strip() and not line.startswith('#'):
                    break

            if has_imports:
                # Insert after other imports
                modified_lines.insert(insert_idx, import_line)
                if insert_idx < len(modified_lines) - 1 and modified_lines[insert_idx + 1].strip():
                    modified_lines.insert(insert_idx + 1, '')
            else:
                # Insert at beginning after docstring if present
                if modified_lines[0].strip().startswith('"""'):
                    # Find end of docstring
                    for i in range(1, len(modified_lines)):
                        if '"""' in modified_lines[i]:
                            modified_lines.insert(i + 1, '')
                            modified_lines.insert(i + 2, import_line)
                            modified_lines.insert(i + 3, '')
                            break
                else:
                    modified_lines.insert(0, import_line)
                    modified_lines.insert(1, '')

    return '\n'.join(modified_lines)


def fix_argument_type_annotations(code: str) -> str:
    """
    Main function to fix argument type annotations

    Args:
        code: Python source code

    Returns:
        Code with fixed argument type annotations
    """
    return add_argument_type_annotations(code)


def fix_file_argument_types(file_path: str) -> bool:
    """
    Fix argument type annotations in a specific file

    Args:
        file_path: Path to Python file

    Returns:
        True if file was modified, False otherwise
    """
    try:
        with open(file_path, 'r') as f:
            original_code = f.read()

        fixed_code = fix_argument_type_annotations(original_code)

        if fixed_code != original_code:
            with open(file_path, 'w') as f:
                f.write(fixed_code)
            return True
        return False
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return False