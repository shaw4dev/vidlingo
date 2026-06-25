"""CLI: validate LessonPackage files. Exit 0 if all valid, 1 otherwise.

Usage:
    python -m app.content.validate path/to/package.json [more.json ...]
"""

from __future__ import annotations

import sys

from app.content.validator import validate_file


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m app.content.validate <package.json> [...]", file=sys.stderr)
        return 2

    failed = 0
    for path in argv:
        errors = validate_file(path)
        if errors:
            failed += 1
            print(f"FAIL  {path}")
            for e in errors:
                print(f"    - {e}")
        else:
            print(f"OK    {path}")

    if failed:
        print(f"\n{failed} of {len(argv)} package(s) invalid.", file=sys.stderr)
        return 1
    print(f"\nAll {len(argv)} package(s) valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
