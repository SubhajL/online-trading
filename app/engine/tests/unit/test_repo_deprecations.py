import os
import re


def test_no_utcnow_in_engine_sources():
    """Ensure datetime.utcnow() is not used in engine source files.

    This helps keep all timestamps timezone-aware. Tests may still reference
    utcnow in legacy cases, but production code should not.
    """
    pattern = re.compile(r"datetime\.utcnow\(")
    root = os.path.join(os.path.dirname(__file__), "..", "..")
    engine_dir = os.path.abspath(root)

    offenders: list[str] = []
    for base, _dirs, files in os.walk(engine_dir):
        # Skip virtualenvs and caches
        if ".venv" in base or "__pycache__" in base:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(base, f)
            # Skip tests themselves
            if os.sep + "tests" + os.sep in path:
                continue
            with open(path, "r", encoding="utf-8") as fh:
                txt = fh.read()
                if pattern.search(txt):
                    offenders.append(os.path.relpath(path, engine_dir))

    assert offenders == [], f"datetime.utcnow() found in: {offenders}"
