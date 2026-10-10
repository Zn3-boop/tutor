# -*- coding: utf-8 -*-
"""Unit tests for document ingestion with small fixtures."""

import asyncio
import os
import sys
import tempfile

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from app.services.tutor.store import TutorStore
from app.services.tutor.knowledge import get_kb_ingestor, _split_srt, _split_transcript, _clean

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _make_store():
    return TutorStore(data_dir=tempfile.mkdtemp(prefix="test_kn_"))


def test_split_srt_with_timestamps():
    srt_text = """1
00:00:00,000 --> 00:00:03,000
Welcome to the introduction.

2
00:00:03,500 --> 00:00:07,000
Python variables store values.

3
00:00:07,500 --> 00:00:12,000
Lists are mutable sequences.
"""
    segments = _split_srt(srt_text)
    assert len(segments) == 3, f"Expected 3 segments, got {len(segments)}"
    ts, text = segments[0]
    assert ts == "00:00:00", f"Expected 00:00:00, got {ts}"
    assert "introduction" in text.lower()
    ts, text = segments[1]
    assert ts == "00:00:03"


def test_split_srt_empty_input():
    assert _split_srt("") == []
    assert _split_srt("   ") == []


def test_split_plain_transcript():
    text = "First paragraph about variables.\n\nSecond paragraph about lists.\n\nThird about functions."
    segments = _split_transcript(text)
    assert len(segments) >= 1
    for ts, seg_text in segments:
        assert _clean(seg_text), f"Empty segment found for timestamp {ts}"


def test_clean_function():
    assert _clean("  hello   world  ") == "hello world"
    assert _clean(" \t\nhello\tworld\n") == "hello world"
    assert _clean("") == ""
    assert _clean(None) == ""


def test_ingest_plain_text_transcript():
    store = _make_store()
    ing = get_kb_ingestor(store)
    transcript_path = os.path.join(FIXTURES_DIR, "test_plain_transcript.txt")

    async def _run():
        return await ing.ingest_transcript(
            title="Test Transcript",
            text=open(transcript_path, encoding="utf-8").read(),
            path=transcript_path,
        )

    result = asyncio.run(_run())
    assert result["ok"], f"Ingestion failed: {result.get('error')}"
    assert result["unit_count"] > 0, f"Expected units, got {result['unit_count']}"
    sources = store.list_sources()
    assert len(sources) == 1
    assert sources[0]["kind"] == "video"
    assert "Test Transcript" in sources[0]["title"]


def test_ingest_srt_transcript():
    store = _make_store()
    ing = get_kb_ingestor(store)
    srt_path = os.path.join(FIXTURES_DIR, "test_transcript.srt")

    async def _run():
        return await ing.ingest_transcript(
            title="Test SRT",
            text=open(srt_path, encoding="utf-8").read(),
            path=srt_path,
        )

    result = asyncio.run(_run())
    assert result["ok"], f"Ingestion failed: {result.get('error')}"
    assert result["unit_count"] > 0
    units = store.list_units()
    timestamps_found = []
    for unit in units:
        origin = unit.get("origin", {})
        ts = origin.get("timestamp", "")
        if ts:
            timestamps_found.append(ts)
    assert len(timestamps_found) > 0, "Expected some timestamped origins"


def test_ingest_pptx_slides():
    store = _make_store()
    ing = get_kb_ingestor(store)
    pptx_path = os.path.join(FIXTURES_DIR, "test_slides.pptx")

    async def _run():
        return await ing.ingest_pptx(path=pptx_path, title="Test Slides")

    result = asyncio.run(_run())
    assert result["ok"], f"Ingestion failed: {result.get('error')}"
    assert result["unit_count"] > 0, f"Expected units from PPTX, got {result['unit_count']}"
    units = store.list_units()
    slide_origins = [u for u in units if "slide" in (u.get("origin", {}) or {}).get("label", "").lower()]
    assert len(slide_origins) > 0, "Expected slide-labeled origins"


def test_ingest_pdf_text():
    store = _make_store()
    ing = get_kb_ingestor(store)
    pdf_path = os.path.join(FIXTURES_DIR, "test_text.pdf")

    async def _run():
        return await ing.ingest_pdf(path=pdf_path, title="Test PDF")

    result = asyncio.run(_run())
    assert result["ok"], f"Ingestion failed: {result.get('error')}"
    assert result["unit_count"] > 0, f"Expected units from PDF, got {result['unit_count']}"
    units = store.list_units()
    page_origins = [u for u in units if "p." in (u.get("origin", {}) or {}).get("label", "").lower()]
    assert len(page_origins) > 0, "Expected page-labeled origins"


def test_ingest_text_autotag():
    store = _make_store()
    ing = get_kb_ingestor(store)
    topics = {
        "t_var": {"topic_id": "t_var", "name": "Variables", "concepts": ["variable", "assignment"]},
        "t_list": {"topic_id": "t_list", "name": "Lists", "concepts": ["list", "append"]},
    }
    store.upsert_topic(topic_id="t_var", name="Variables", concepts=["variable", "assignment"], prerequisites=[])
    store.upsert_topic(topic_id="t_list", name="Lists", concepts=["list", "append"], prerequisites=[])

    async def _run():
        return await ing.ingest_text(
            title="Test Units",
            text="A variable is a name that refers to a value. "
                 "The append method adds an element to the end of a list. "
                 "Lists are mutable sequences of items in Python.",
            kind="text",
            topics=topics,
        )

    result = asyncio.run(_run())
    assert result["ok"], f"Ingestion failed: {result.get('error')}"
    units = store.list_units()
    assert len(units) > 0
    tagged = [u for u in units if u.get("topic_ids")]
    assert len(tagged) > 0, "Expected some units with autotagged topics"

    var_units = [u for u in units if "t_var" in u.get("topic_ids", [])]
    list_units = [u for u in units if "t_list" in u.get("topic_ids", [])]
    assert var_units, "Expected at least one unit tagged with t_var"
    assert list_units, "Expected at least one unit tagged with t_list"
