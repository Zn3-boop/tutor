#!/usr/bin/env python3
"""P0: backup a test file (with date) so an AI rewrite can be diff-restored.

Usage:
    python scripts/backup_test.py server/tests/test_grounding.py
    python scripts/backup_test.py server/tests            # entire dir
"""
import os
import shutil
import sys
from datetime import datetime


def backup(path: str) -> str:
    path = os.path.abspath(path)
    if os.path.isdir(path):
        suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = f"{path}.bak.{suffix}"
        shutil.copytree(path, dst)
        return dst
    if not os.path.exists(path):
        raise SystemExit(f"[backup] not found: {path}")
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = f"{path}.{suffix}.bak"
    shutil.copy2(path, dst)
    return dst


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    dst = backup(sys.argv[1])
    print(f"[backup] OK -> {dst}")


if __name__ == "__main__":
    main()