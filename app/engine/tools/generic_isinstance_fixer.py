"""Fix parameterized generic isinstance() checks that cause runtime errors."""

import re
from pathlib import Path
from typing import List


class GenericIsinstanceFixer:
    """Fixes isinstance() checks with parameterized generics."""

    @staticmethod
    def fix_content(content: str) -> str:
        """Fix parameterized generic isinstance checks in the given content."""
        if not content.strip():
            return content

        # Pattern to match isinstance with parameterized generics
        # This handles dict[...], list[...], etc.
        # Use a more comprehensive pattern that handles nested brackets

        # Pattern for nested brackets: [^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*
        nested_brackets = r'[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*'
        type_names = r'(dict|list|set|tuple)'

        patterns = [
            # Multi-line isinstance (check first to avoid single-line match)
            (rf'isinstance\s*\(\s*\n\s*([^,]+?)\s*,\s*\n\s*{type_names}'
             rf'\[{nested_brackets}\]\s*\n\s*\)',
             r'isinstance(\n        \1,\n        \2\n    )'),
            # Union types with None
            (rf'isinstance\s*\(\s*([^,]+?)\s*,\s*{type_names}'
             rf'\[{nested_brackets}\]\s*\|\s*None\s*\)',
             r'isinstance(\1, \2) or \1 is None'),
            # Single-line isinstance with nested generics
            (rf'isinstance\s*\(\s*([^,]+?)\s*,\s*{type_names}'
             rf'\[{nested_brackets}\]\s*\)',
             r'isinstance(\1, \2)'),
        ]

        result = content
        for pattern, replacement in patterns:
            flags = re.MULTILINE | re.DOTALL
            result = re.sub(pattern, replacement, result, flags=flags)

        # Handle nested generics (e.g., list[dict[str, Any]])
        # Keep applying the patterns until no more changes
        max_iterations = 5
        for _ in range(max_iterations):
            prev_result = result
            # Don't apply Union pattern in loop
            for pattern, replacement in patterns[:2]:
                flags = re.MULTILINE | re.DOTALL
                result = re.sub(pattern, replacement, result, flags=flags)
            if result == prev_result:
                break

        return result

    @staticmethod
    def fix_file(file_path: str) -> None:
        """Fix generic isinstance checks in a single file."""
        with open(file_path, 'r') as f:
            content = f.read()

        fixed_content = GenericIsinstanceFixer.fix_content(content)

        if fixed_content != content:
            with open(file_path, 'w') as f:
                f.write(fixed_content)

    @staticmethod
    def get_files_with_generic_isinstance_errors() -> List[str]:
        """Get list of files that have generic isinstance errors."""
        # These files were identified from mypy output
        return [
            'app/engine/adapters/router_client/http_client.py',
            'app/engine/core/config_manager.py',
            'app/engine/ingest/binance_ws.py',
            'app/engine/news_funding_guards/guards.py',
        ]

    @staticmethod
    def fix_all() -> None:
        """Fix all files with generic isinstance errors."""
        files = (GenericIsinstanceFixer
                 .get_files_with_generic_isinstance_errors())
        fixed_count = 0

        for file_path in files:
            if Path(file_path).exists():
                print(f"Fixing generic isinstance in {file_path}")
                GenericIsinstanceFixer.fix_file(file_path)
                fixed_count += 1

        print(f"Fixed {fixed_count} files")


if __name__ == "__main__":
    # Fix all files when run directly
    GenericIsinstanceFixer.fix_all()
