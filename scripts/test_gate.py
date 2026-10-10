#!/usr/bin/env python3
"""P2 automation gate: validate a candidate test file WITHOUT touching the real
file. Run from repo root; the candidate's package/import context must be
resolvable (run inside server/ so ``app.*`` imports work, or pass a path under
server/tests whose module deps import via the existing sys.path setup).

The gate is non-destructive by design:
  * never overwrites the real test file
  * lints/compiles/single-file-tests the candidate
  * on success prints an explicit "OK to replace" signal

Usage:
  from repo root:  python scripts/test_gate.py server/tests/test_foo.py.candidate.py
  or inside server/tests after a copy:  python ../../scripts/test_gate.py candidate.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    print(f"[gate] $ {' '.join(cmd)}  (cwd={cwd.name})")
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)


def _tail(proc: subprocess.CompletedProcess, n: int = 2500) -> str:
    return ((proc.stdout or "") + (proc.stderr or ""))[-n:]


def _has(name: str) -> bool:
    return shutil.which(name) is not None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    cand = Path(argv[1]).resolve()
    if not cand.is_file():
        print(f"[gate] candidate not found: {cand}")
        return 2

    # --- 0. syntax + module sanity (fail fast) ------------------------------
    py = sys.executable
    proc = _run([py, "-m", "py_compile", str(cand)], ROOT)
    if proc.returncode != 0:
        print("[gate] FAIL: syntax\n" + _tail(proc))
        return 1
    print("[gate] syntax OK")

    # --- 1. ruff / mypy (optional, only if installed) -----------------------
    if _has("ruff"):
        proc = _run(["ruff", "check", str(cand)], ROOT)
        if proc.returncode != 0:
            print("[gate] FAIL: ruff\n" + _tail(proc))
            return 1
        print("[gate] ruff OK")
    else:
        print("[gate] ruff not installed, skipped")

    if _has("mypy"):
        proc = _run(["mypy", str(cand)], ROOT)
        if proc.returncode != 0:
            print("[gate] FAIL: mypy\n" + _tail(proc))
            return 1
        print("[gate] mypy OK")
    else:
        print("[gate] mypy not installed, skipped")

    # --- 2. single-file pytest (not the whole suite, so seed-dependent tests
    #        like test_citation_resolve.py don't pollute the gate result) ----
    # The candidate must be importable under its final name. Copy it into the
    # real tests dir ONLY as <name>.<pid>.tmp.py, run just that file, then
    # delete it. The REAL file is never touched.
    real_dir = SERVER / "tests"
    final_name = cand.name
    # strip any marker suffix: test_foo.candidate.py -> test_foo
    for marker in (".candidate", ".tmp", ".bak", ".run"):
        if marker in final_name:
            final_name = final_name.split(marker)[0] + ".py"
            break
    if not (final_name.startswith("test_") and final_name.endswith(".py")):
        print(f"[gate] name is not a test file: {final_name}")
        return 2
    scratch = real_dir / f"test_gate_{os.getpid()}_{final_name}"
    shutil.copy2(cand, scratch)
    try:
        proc = _run([py, "-m", "pytest", str(scratch), "-q", "--no-header"], SERVER)
    finally:
        scratch.unlink(missing_ok=True)
    if proc.returncode != 0:
        print("[gate] FAIL: pytest\n" + _tail(proc, 4000))
        return 1
    print(f"[gate] pytest OK ({final_name})")

    # --- 3. non-destructive green signal ------------------------------------
    print(f"\n[gate] ALL GREEN -> candidate '{cand.name}' is safe to apply.\n")
    print("Apply it with an editor incremental diff (old_text/new_text), then")
    print("re-run `python -m pytest tests -q` to confirm. The gate never")
    print("overwrites the real test file.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))