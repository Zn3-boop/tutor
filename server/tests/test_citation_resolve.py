"""Citation resolvability regression tests (Phase 1: real-citations-first).

These tests lock in the "Knowledge Base & Grounding" criterion: every content
Unit shipped in the demo knowledge base must resolve to a REAL source file and
a valid page / slide / video-timestamp range. Fabricated references fail here.

They assume the demo DB has been seeded with the REAL course (Think Python 2e +
MIT OCW 6.0001): run ``python scripts/seed_demo.py`` after resetting
``server/app/data/tutor/tutor_db.json``.
"""

from __future__ import annotations

import json
import os
import re

from app.services.tutor.citations import resolve_citation
from app.services.tutor.store import get_tutor_store

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEMO_DIR = os.path.join(SERVER_DIR, "demo_materials")
MANIFEST_PATH = os.path.join(DEMO_DIR, "materials-manifest.json")

_REAL_PREFIXES = ("Think Python", "MIT 6.0001")
_INGESTABLE = ("pdf", "pptx", "transcript")

TS_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")


def _manifest() -> dict:
    assert os.path.exists(MANIFEST_PATH), f"manifest missing: {MANIFEST_PATH}"
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _real_sources(store):
    return [s for s in store.list_sources()
            if s.get("title", "").startswith(_REAL_PREFIXES)]


def test_manifest_is_consistent() -> None:
    """Every ingestable entry has a real file on disk; no ingestable file in
    demo_materials is orphaned outside the manifest."""
    manifest = _manifest()
    entries = manifest["materials"]
    assert len(entries) >= 8, "manifest lost materials"
    filenames = {e["filename"] for e in entries}
    assert len(filenames) == len(entries), "duplicate filenames in manifest"
    for entry in entries:
        path = os.path.join(DEMO_DIR, entry["filename"])
        assert os.path.exists(path), f"manifest file missing: {entry['filename']}"
        assert entry.get("url"), f"missing source url: {entry['filename']}"
        assert entry.get("license"), f"missing license: {entry['filename']}"
        assert entry.get("attribution"), f"missing attribution: {entry['filename']}"
    on_disk = {f for f in os.listdir(DEMO_DIR)
               if f.lower().endswith((".pdf", ".pptx", ".srt", ".docx", ".vtt"))
               and not f.startswith(".")}
    orphans = on_disk - filenames
    assert not orphans, f"ingestable files not listed in manifest: {sorted(orphans)}"


def test_real_sources_exist_on_disk() -> None:
    """Every REAL source recorded in the DB points to a file that exists and is
    declared in the manifest."""
    manifest = _manifest()
    declared = {e["filename"] for e in manifest["materials"]}
    store = get_tutor_store()
    real = _real_sources(store)
    assert real, "no REAL course sources found - was the fallback synthetic seed used?"
    for source in real:
        path = source.get("path", "")
        assert path, f"source without path: {source.get('title')}"
        assert os.path.exists(path), f"source file missing: {path}"
        basename = os.path.basename(path)
        assert basename in declared, f"{basename} not declared in the manifest"


def test_every_real_unit_origin_resolves() -> None:
    """Every unit of every REAL source resolves to an openable, in-range
    reference (p.N / slide#N / video@HH:MM:SS) with a working URL."""
    store = get_tutor_store()
    real_ids = {s["source_id"] for s in _real_sources(store)}
    resolved = 0
    for unit in store.list_units():
        if unit.get("source_id") not in real_ids:
            continue
        origin = unit.get("origin", {}) or {}
        label = origin.get("label", "")
        assert label, f"unit {unit['unit_id']} has no origin label"
        res = resolve_citation(store, unit_id=unit["unit_id"])
        assert res["ok"], f"resolve failed for unit {unit['unit_id']}: {res}"
        assert res["origin_label"] == label
        kind = res["kind"]
        if kind == "pdf":
            assert res["page"] is not None and res["total_pages"], res
            assert 1 <= res["page"] <= res["total_pages"], res
            assert res["open_url"].endswith(f"#page={res['page']}"), res
        elif kind == "slides":
            assert res["slide"] is not None and res["total_slides"], res
            assert 1 <= res["slide"] <= res["total_slides"], res
            assert res["open_url"].endswith(f"#slide={res['slide']}"), res
        elif kind == "video":
            if origin.get("timestamp"):
                assert TS_RE.match(origin["timestamp"]), origin
                assert res["seconds"] is not None and res["seconds"] >= 0, res
                assert res["video_url"].startswith("http") and "#t=" in res["video_url"], res
                assert res["youtube_url"].startswith("https://www.youtube.com"), res
            else:
                assert label.startswith("video#"), label
                assert res["viewer"] == "transcript", res
        assert res["file_exists"], res
        resolved += 1
    assert resolved > 200, f"expected hundreds of real units, got {resolved}"


def test_no_synthetic_units_in_demo_db() -> None:
    """Guard against regressing to the fabricated demo course: every unit must
    belong to a REAL source."""
    store = get_tutor_store()
    titles = {s["source_id"]: s.get("title", "") for s in store.list_sources()}
    for unit in store.list_units():
        title = titles.get(unit.get("source_id", ""), "")
        assert title.startswith(_REAL_PREFIXES), f"synthetic unit leak: {title}"


def test_transcript_cues_are_real_and_bounded() -> None:
    """Timestamped transcript origins must be within the real Lecture 1 video
    duration (2585.96 s / 43:06 per the official Internet Archive stream)."""
    store = get_tutor_store()
    video_sources = [s for s in store.list_sources() if s.get("kind") == "video"]
    assert video_sources, "no video/transcript source seeded"
    max_seen = 0
    for unit in store.list_units():
        if unit.get("source_id") not in {s["source_id"] for s in video_sources}:
            continue
        ts = (unit.get("origin", {}) or {}).get("timestamp", "")
        if not ts:
            continue
        assert TS_RE.match(ts), f"malformed timestamp: {ts!r}"
        h, m, s = (int(x) for x in ts.split(":"))
        secs = h * 3600 + m * 60 + s
        max_seen = max(max_seen, secs)
        assert secs <= 2586 + 10, f"timestamp beyond video length: {ts}"
    assert max_seen > 2400, f"suspiciously short transcript: last cue {max_seen}s"

