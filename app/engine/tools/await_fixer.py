"""Fix await operations on potentially non-awaitable values."""

from pathlib import Path
import re


class AwaitFixer:
    """Fixes await operations that might fail with non-coroutine values."""

    @staticmethod
    def fix_content(content: str) -> str:
        """Fix await compatibility issues in the given content."""
        if not content.strip():
            return content

        lines = content.split("\n")
        result_lines: list[str] = []
        counter = 1

        for i, line in enumerate(lines):
            # Check for await on Redis operations
            if "await" in line and "_redis" in line:
                modified = AwaitFixer._fix_redis_await(
                    line,
                    lines,
                    i,
                    result_lines,
                    counter,
                )
                if modified:
                    counter += 1
                    continue

            result_lines.append(line)

        return "\n".join(result_lines)

    @staticmethod
    def _fix_redis_await(
        line: str,
        lines: list[str],
        line_idx: int,
        result_lines: list[str],
        counter: int,
    ) -> bool:
        """Fix a Redis await operation."""
        # Get indentation from the original line
        indent = len(line) - len(line.lstrip())
        spaces = " " * indent

        # Handle counter for unique variable names
        suffix = "" if counter == 1 else str(counter)

        # Pattern 1: variable = await self._redis.method(...)
        match = re.match(
            r"(\s*)(\w+)\s*=\s*await\s+(self\._redis\.\w+\([^)]*\))",
            line,
        )
        if match:
            var_name = match.group(2)
            redis_call = match.group(3)
            result_lines.append(f"{spaces}_result{suffix} = {redis_call}")
            has_await = f"hasattr(_result{suffix}, '__await__')"
            await_expr = f"await _result{suffix} if {has_await} else _result{suffix}"
            result_lines.append(f"{spaces}{var_name} = {await_expr}")
            return True

        # Pattern 2: await self._redis.method(...) without assignment
        match = re.match(
            r"(\s*)await\s+(self\._redis\.\w+\([^)]*\))",
            line,
        )
        if match:
            redis_call = match.group(2)
            result_lines.append(f"{spaces}_result{suffix} = {redis_call}")
            has_await = f"hasattr(_result{suffix}, '__await__')"
            await_expr = f"await _result{suffix} if {has_await} else _result{suffix}"
            result_lines.append(f"{spaces}{await_expr}")
            return True

        # Pattern 3: Complex expressions like len(await self._redis.keys(...))
        match = re.match(
            r"(\s*)(.+?)\(await\s+(self\._redis\.\w+\([^)]*\))\)",
            line,
        )
        if match:
            prefix = match.group(2)
            redis_call = match.group(3)
            result_lines.append(f"{spaces}_result{suffix} = {redis_call}")
            has_await = f"hasattr(_result{suffix}, '__await__')"
            await_expr = f"await _result{suffix} if {has_await} else _result{suffix}"
            result_lines.append(f"{spaces}_awaited{suffix} = {await_expr}")
            result_lines.append(f"{spaces}{prefix}(_awaited{suffix})")
            return True

        return False

    @staticmethod
    def fix_file(file_path: str) -> None:
        """Fix await compatibility issues in a single file."""
        with open(file_path) as f:
            content = f.read()

        fixed_content = AwaitFixer.fix_content(content)

        if fixed_content != content:
            with open(file_path, "w") as f:
                f.write(fixed_content)

    @staticmethod
    def get_files_with_await_errors() -> list[str]:
        """Get list of files that have await compatibility errors."""
        # Only Redis adapter has these specific errors
        return [
            "app/engine/adapters/redis/redis_adapter.py",
        ]

    @staticmethod
    def fix_all() -> None:
        """Fix all files with await compatibility errors."""
        files = AwaitFixer.get_files_with_await_errors()
        fixed_count = 0

        for file_path in files:
            if Path(file_path).exists():
                print(f"Fixing await compatibility in {file_path}")
                AwaitFixer.fix_file(file_path)
                fixed_count += 1

        print(f"Fixed {fixed_count} files")


if __name__ == "__main__":
    # Fix all files when run directly
    AwaitFixer.fix_all()
