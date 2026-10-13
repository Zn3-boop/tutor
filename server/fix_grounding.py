"""Idempotent repair for app/services/tutor/grounding.py (Windows-safe UTF-8).

History: a previous public export mangled the off-material detection block
(mis-escaped \\b words, literal \\u escapes, broken indentation). A first repair
already inserted a clean, compilable block on disk. This script is safe to run
at any time:

  1. If the file already compiles AND already defines ``_is_off_material``, it
     prints ``FIXED: Syntax OK (idempotent)`` and exits without touching anything.
  2. Otherwise it reconstructs ONLY the off-material section (identified by
     text anchors, not line numbers), then verifies with py_compile.

Run from server/:  python fix_grounding.py
"""
from __future__ import annotations

import io
import os
import re
import shutil
import sys

# Windows default console codepage is GBK; force UTF-8 so Chinese messages in
# this script and in grounding.py do not crash ``print`` / ``open()``.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PATH = r"d:/ecv-tutor/server/app/services/tutor/grounding.py"

# The canonical, validated "off-material" block that must be present.
CLEAN_SECTION = '''\
# Off-material detection: explicit flag for queries clearly outside course scope
_OFF_MATERIAL_PATTERNS = [
    r"\\b(capital of|population of|weather in|recipe for|how to cook|how to fix)\\b",
    r"\\b(who wrote|who painted|who composed)\\b",
    r"\\b(olympics|world cup|nba|fifa)\\b",
    r"\\b(bitcoin|crypto|stock price|invest)\\b",
    r"\\b(iphone|android|tech review)\\b",
]
# Additional off-material patterns for Chinese queries
_OFF_MATERIAL_PATTERNS_ZH = [
    r"法国的首都是",
    r"怎么从零开始煮",
    r"荷马史诗的作者",
    r"骑自行车链条",
    r"东京今天天气",
    r"投资比特币",
    r"世界杯冠军",
    r"火星人口",
]
_OFF_MATERIAL_RE_ZH = re.compile("|".join(_OFF_MATERIAL_PATTERNS_ZH))
_OFF_MATERIAL_RE = re.compile("|".join(_OFF_MATERIAL_PATTERNS), re.IGNORECASE)


def _is_off_material(query: str) -> tuple[bool, str]:
    """Detect if a query is clearly off-material based on lexical patterns.

    Returns (is_off, reason) tuple. This is a fast pre-filter before retrieval.
    """
    # Check Chinese patterns first
    if _OFF_MATERIAL_RE_ZH.search(query):
        return True, "该问题涉及课程范围外的主题（如地理、历史、体育、投资等），系统已自动识别并拒绝回答。"
    # Check English patterns
    if _OFF_MATERIAL_RE.search(query):
        return True, "该问题涉及课程范围外的主题（如地理、历史、体育、投资等），系统已自动识别并拒绝回答。"
    return False, ""


'''

def _read(path: str) -> str:
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


def _compile_ok(path: str) -> bool:
    import py_compile
    try:
        py_compile.compile(path, doraise=True)
        return True
    except py_compile.PyCompileError:
        return False


def _has_marker(text: str) -> bool:
    return re.search(r"\ndef _is_off_material", text or "") is not None


def _strip_mangled_blocks(text: str) -> str:
    """Remove every mangled/historical off-material section from ``text``.

    Anchors: each block starts at a line beginning with
    ``# Off-material detection`` and ends right before the next section
    (refuse reason, citation label, or the def that follows the block).
    """
    pattern = re.compile(
        r"# Off-material detection.*?(?=\ndef _extract_citation_label|\n_REFUSE_REASON = |\ndef _stem)",
        re.S,
    )
    cleaned, n = pattern.subn(
        lambda m: m.group(0).splitlines()[0] + "\n" if m.group(0).startswith("# Off-material") else "",
        text,
    )
    return cleaned


def repair() -> int:
    if not os.path.exists(PATH):
        print(f"STILL BROKEN: {PATH} not found")
        return 1

    text = _read(PATH)
    if _compile_ok(PATH) and _has_marker(text):
        print("FIXED: Syntax OK (idempotent skip — off-material block already present)")
        return 0

    # Preserve the original once before any attempt.
    backup = PATH + ".bak"
    if not os.path.exists(backup):
        try:
            shutil.copy2(PATH, backup)
        except OSError as exc:  # pragma: no cover - defensive
            print(f"warning: could not create backup {backup}: {exc}")

    text = _strip_mangled_blocks(text)

    # Insert the canonical block right before the refuse-reason sentinel if it
    # exists (the historical location), else before the citation-label helper.
    anchor = text.find("_REFUSE_REASON = (")
    if anchor == -1:
        anchor = text.find("def _extract_citation_label(")
    if anchor == -1:
        anchor = len(text)
    text = text[:anchor] + CLEAN_SECTION + text[anchor:]

    with io.open(PATH, "w", encoding="utf-8") as f:
        f.write(text)

    if _compile_ok(PATH):
        print("FIXED: Syntax OK")
        return 0
    print("STILL BROKEN: repaired file does not compile")
    return 1


if __name__ == "__main__":
    raise SystemExit(repair())