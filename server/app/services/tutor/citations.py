"""Citation resolution.

Turns a content Unit's ORIGIN (``p.123`` / ``slide#7`` / ``video@00:31:05``)
into a viewer-actionable reference backed by a real file on disk and/or a real
public URL, so every citation in the tutor UI can be "opened" and verified.
"""

from __future__ import annotations

import os
import re
from typing import Any

_TS_RE = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})")
_PAGE_LABEL_RE = re.compile(r"[pP]\.(\d+)")
_SLIDE_LABEL_RE = re.compile(r"slide(?:#| )(\d+)", re.IGNORECASE)
_VIDEO_LABEL_RE = re.compile(r"video#(\d+)", re.IGNORECASE)


def _doc_page_count(path: str) -> int | None:
    try:
        import fitz  # type: ignore
        doc = fitz.open(path)  # type: ignore[attr-defined]
        try:
            return doc.page_count
        finally:
            doc.close()
    except Exception:
        return None


def _slide_count(path: str) -> int | None:
    try:
        from pptx import Presentation  # type: ignore
        prs = Presentation(path)
        return len(prs.slides)
    except Exception:
        return None


def _seconds(ts: str) -> int | None:
    m = _TS_RE.search(ts or "")
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))


def _proxy_url(path: str, fragment: str = "") -> str:
    """Browser-openable URL for a local file, served by the /tutor/files proxy.

    Returns a relative URL (the web frontend runs behind the same origin / Vite
    proxy), e.g. ``/tutor/files?path=...%23page=39#page=39``. Kept as a plain
    ``#page=`` fragment so PDF.js and in-browser viewers seek directly.
    """
    from urllib.parse import quote
    qs = quote(path, safe="")
    return f"/tutor/files?path={qs}" + (f"#{fragment}" if fragment else "")


def resolve_citation(store, *, source_id: str = "", unit_id: str = "",
                     origin_label: str = "") -> dict[str, Any]:
    """Resolve one unit origin into an openable reference dict.

    Accepts either an explicit ``unit_id`` or a ``source_id`` + ``origin_label``
    pair (as carried on RAG retrieval chunks).
    """
    unit: dict | None = None
    if unit_id:
        unit = store.get_unit(unit_id)
    elif source_id and origin_label:
        for u in store.list_units(source_id=source_id):
            if (u.get("origin", {}) or {}).get("label") == origin_label:
                unit = u
                break
    if not unit:
        return {"ok": False, "error": "unit not found"}

    source = store.get_source(unit.get("source_id", ""))
    if not source:
        return {"ok": False, "error": "source not found"}

    origin = unit.get("origin", {}) or {}
    label = origin.get("label", "")
    kind = source.get("kind", "")
    path = source.get("path", "") or ""
    base: dict[str, Any] = {
        "ok": True,
        "unit_id": unit["unit_id"],
        "source_id": source["source_id"],
        "source_title": source.get("title", ""),
        "kind": kind,
        "origin_label": label,
        "file": path,
        "file_exists": bool(path and os.path.exists(path)),
    }

    if kind == "pdf":
        page = origin.get("page")
        if page is None:
            m = _PAGE_LABEL_RE.search(label)
            page = int(m.group(1)) if m else None
        total = _doc_page_count(path) if path else None
        base.update({"viewer": "pdf", "page": page, "total_pages": total})
        if path and page:
            base["open_url"] = _proxy_url(path, f"page={page}")
        return base

    if kind == "slides":
        slide = origin.get("slide")
        if slide is None:
            m = _SLIDE_LABEL_RE.search(label)
            slide = int(m.group(1)) if m else None
        total = _slide_count(path) if path else None
        base.update({"viewer": "slides", "slide": slide, "total_slides": total})
        if path and slide:
            base["open_url"] = _proxy_url(path, f"slide={slide}")
        return base

    if kind == "video":
        ts = origin.get("timestamp", "") or ""
        secs = _seconds(ts) if ts else None
        meta = source.get("meta", {}) or {}
        video_url = meta.get("video_url", "")
        yt_id = meta.get("video_id", "")
        out: dict[str, Any] = {
            **base,
            "viewer": "video",
            "timestamp": ts,
            "seconds": secs,
            "paragraph_index": origin.get("index", 0),
        }
        if video_url:
            out["video_url"] = video_url + (f"#t={secs}" if secs is not None else "")
        if yt_id:
            out["youtube_url"] = (
                f"https://www.youtube.com/watch?v={yt_id}"
                + (f"&t={secs}" if secs is not None else "")
            )
        if not ts:
            idx = origin.get("index")
            if idx is None:
                m = _VIDEO_LABEL_RE.search(label)
                idx = (int(m.group(1)) - 1) if m else 0
            out["paragraph_index"] = idx
            out["viewer"] = "transcript"
        return out

    # Any other kind (textbook text etc.): fall back to the transcript viewer.
    base.update({"viewer": "transcript", "paragraph_index": origin.get("index", 0)})
    return base