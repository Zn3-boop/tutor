"""Multimodal knowledge-base ingestion.

Converts raw course material (plain text, .docx textbook, .pptx slides, or a
video transcript) into content Units. Each Unit keeps its ORIGIN (page number /
slide number / video timestamp), is auto-tagged with topics/concepts, and is
indexed into the existing RAG service so it can be retrieved and cited.
"""

from __future__ import annotations

import os
import re
from typing import Any

from app.services.rag.service import get_rag_service
from app.services.tutor.store import TutorStore

try:  # python-docx is listed in requirements.txt
    from docx import Document as DocxDocument  # type: ignore
    HAS_DOCX = True
except Exception:  # pragma: no cover - optional
    HAS_DOCX = False

try:
    from pptx import Presentation  # type: ignore
    HAS_PPTX = True
except Exception:  # pragma: no cover - optional
    HAS_PPTX = False

try:  # PyMuPDF for PDF page text + embedded-image extraction
    import fitz  # type: ignore
    HAS_FITZ = True
except Exception:  # pragma: no cover - optional
    HAS_FITZ = False


def _clean(text: str) -> str:
    return re.sub(r"[ \t]+", " ", (text or "")).strip()


def _autotag(text: str, topics: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Keyword-match text against the topic graph -> (topic_ids, matched concepts)."""
    tid_hits: list[str] = []
    concepts: list[str] = []
    lower = text.lower()
    for tid, topic in topics.items():
        name = (topic.get("name") or "").lower()
        if name and name in lower:
            tid_hits.append(tid)
        for concept in topic.get("concepts", []):
            if concept and concept.lower() in lower:
                if concept not in concepts:
                    concepts.append(concept)
                if tid not in tid_hits:
                    tid_hits.append(tid)
    return tid_hits, concepts


_TS_RE = re.compile(r"\[?(\d{1,2}):(\d{2})(?::(\d{2}))?\]?")

_DEMO_MATERIALS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "demo_materials")
)
_MANIFEST_PATH = os.path.join(_DEMO_MATERIALS_DIR, "materials-manifest.json")


def _load_material_manifest() -> dict[str, Any] | None:
    """Load server/demo_materials/materials-manifest.json (provenance for every
    bundled real source: original URL, CC license, attribution)."""
    try:
        import json
        with open(_MANIFEST_PATH, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        return manifest if manifest.get("materials") else None
    except Exception:
        return None


def _safe_title(entry: dict[str, Any]) -> str:
    return (entry.get("title") or entry.get("filename") or "Course material").strip()


def _extract_pdf_text(path: str) -> str:
    if not HAS_FITZ:
        return ""
    try:
        doc = fitz.open(path)  # type: ignore[attr-defined]
        try:
            return "\n\n".join(
                p.get_text() for p in doc if p.get_text().strip()
            )
        finally:
            doc.close()
    except Exception:
        return ""
_SRT_TS_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,\\.](\d{3})\s*-->\s*\d{1,2}:\d{2}:\d{2}[,\\.]\d{3}"
)


def _split_srt(text: str) -> list[tuple[str, str]]:
    """Parse SubRip (.srt) captions into (start_timestamp, text) pairs.

    Returns real cue start times in ``HH:MM:SS`` so transcript units keep
    video@HH:MM:SS origins that resolve to the exact moment of the video.
    """
    segments: list[tuple[str, str]] = []
    blocks = re.split(r"\r?\n\s*\r?\n", (text or "").strip())
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        ts_line = next((l for l in lines if "-->" in l), "")
        m = _SRT_TS_RE.search(ts_line)
        body = [l for l in lines if "-->" not in l and not l.isdigit()]
        seg = _clean(" ".join(body))
        if not seg:
            continue
        if m:
            ts = f"{int(m.group(1)):02d}:{m.group(2)}:{m.group(3)}"
            segments.append((ts, seg))
        else:
            segments.append(("", seg))
    return segments


def _split_transcript(text: str) -> list[tuple[str, str]]:
    """Split a transcript into (timestamp, segment) pairs.

    Supports three real-world formats:
      - SRT captions with ``HH:MM:SS,mmm --> ...`` timing rows,
      - ``[HH:MM:SS]`` inline timestamps,
      - plain paragraph text (no timestamps) -> segments labelled video#N.
    """
    if "-->" in (text or ""):
        return _split_srt(text)
    lines = text.splitlines()
    segments: list[tuple[str, str]] = []
    current_ts = ""
    buf: list[str] = []
    for line in lines:
        m = _TS_RE.search(_clean(line))
        if m:
            if buf and current_ts:
                segments.append((current_ts, " ".join(buf)))
            h, mm, ss = m.group(1), m.group(2), m.group(3) or "00"
            current_ts = f"{int(h):02d}:{mm}:{ss}"
            rest = _TS_RE.sub("", line).strip().lstrip(":] ")
            buf = [rest]
        else:
            buf.append(_clean(line))
    if buf and current_ts:
        segments.append((current_ts, " ".join(buf)))
    if segments:
        return segments

    # Untimestamped transcript: split into paragraph-sized segments so a real
    # plain-text lecture transcript does not become one giant unit.
    paras = [p.strip() for p in re.split(r"\n\s*\n", (text or "").strip()) if p.strip()]
    if not paras:
        if (text or "").strip():
            return [("", text.strip())]
        return []
    out: list[tuple[str, str]] = []
    buf: list[str] = []
    buf_len = 0
    for para in paras:
        if buf and (buf_len + len(para) > 900):
            out.append(("", " ".join(buf)))
            buf, buf_len = [], 0
        buf.append(para)
        buf_len += len(para)
    if buf:
        out.append(("", " ".join(buf)))
    return out


def _split_units(text: str, max_len: int = 900) -> list[str]:
    """Split long text into units, breaking on markdown headings and size."""
    paras = [p for p in text.split("\n") if _clean(p)]
    units: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for p in paras:
        is_heading = p.lstrip().startswith("#")
        if is_heading or (buf and buf_len + len(p) > max_len):
            if buf:
                units.append("\n".join(buf))
                buf, buf_len = [], 0
        buf.append(p)
        buf_len += len(p)
    if buf:
        units.append("\n".join(buf))
    return units or ([text] if text.strip() else [])


# VLM 图表 caption 提示词：让模型用中文简洁描述图表/流程图/示意图
_VLM_PROMPT = (
    "请用简洁中文描述这张图中的关键内容，适合作为课堂复习笔记。"
    "如果是图表、流程图或示意图，请说明其结构和要点。只输出描述本身，不要解释过程。"
)


async def _vlm_caption(image: Any, prompt: str = _VLM_PROMPT) -> str:
    """Call the VLM to caption one image. Tries local → cloud, returns '' on all failures."""
    try:
        from app.services.vlm.provider import describe_image_fallback
        cap = await describe_image_fallback(prompt=prompt, image=image)
        return (cap or "").strip()
    except Exception:
        return ""


def _ocr_page(page: Any, lang: str = "ch", engine: str = "auto") -> str:
    """OCR a single PDF page when it has no extractable text (scanned image).

    Tries PyMuPDF built-in OCR first, then Tesseract as fallback.
    Returns extracted text or empty string. Never raises.
    """
    if not HAS_FITZ:
        return ""
    text = ""
    # Strategy 1: PyMuPDF built-in OCR (requires Tesseract data on system)
    if engine in ("auto", "tesseract", "pymupdf"):
        try:
            ocr_lang_map = {"ch": "chi_sim", "en": "eng", "ja": "jpn", "ko": "kor"}
            tess_lang = ocr_lang_map.get(lang, lang)
            tp = page.get_textpage(flags=fitz.TEXT_PRESERVE_WHITESPACE)
            if tp:
                text = _clean(tp.extractText())
            if not text:
                pix = page.get_pixmap(dpi=300)
                ocr_page = fitz.open("png", pix.tobytes())
                tp = ocr_page[0].get_textpage(flags=fitz.TEXT_PRESERVE_WHITESPACE)
                if tp:
                    text = _clean(tp.extractText())
                ocr_page.close()
            if text:
                return text
        except Exception:
            pass

    # Strategy 2: Tesseract via pytesseract (if installed)
    if engine in ("auto", "tesseract") and not text:
        try:
            import pytesseract  # type: ignore
            from PIL import Image

            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            ocr_lang_map = {"ch": "chi_sim+eng", "en": "eng", "ja": "jpn+eng", "ko": "kor+eng"}
            tess_lang = ocr_lang_map.get(lang, lang)
            text = _clean(pytesseract.image_to_string(img, lang=tess_lang))
        except Exception:
            pass

    return text


def _pptx_picture_blobs(slide: Any) -> list[bytes]:
    """Return raw bytes of every picture on a slide (best-effort, never raises)."""
    blobs: list[bytes] = []
    try:
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        for shape in slide.shapes:
            try:
                if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.PICTURE and hasattr(shape, "image"):
                    blob = shape.image.blob
                    if blob:
                        blobs.append(blob)
            except Exception:
                continue
    except Exception:
        pass
    return blobs



class KnowledgeBaseIngestor:
    """Ingests a piece of material into sources + units + RAG."""

    def __init__(self, store: TutorStore, rag=None):
        self.store = store
        self._rag = rag

    def _rag_service(self):
        return self._rag or get_rag_service()

    async def _index_unit(self, unit_id: str, text: str, source_type: str,
                          origin_label: str) -> str:
        res = await self._rag_service().index_document(
            text=text,
            doc_id=unit_id,
            doc_title=unit_id,
            source_type=source_type,
            source_url=origin_label,
        )
        return res.get("doc_id", "")

    async def ingest_text(self, *, title: str, text: str, kind: str = "text",
                          topics: dict[str, dict] | None = None,
                          chunk_size: int = 900) -> dict[str, Any]:
        topics = topics if topics is not None else self.store.list_topics_by_id()
        source = self.store.add_source(title=title, kind=kind)
        units_text = [t for _, t in _split_transcript(text)] if kind == "video" \
            else _split_units(text, chunk_size)
        created = []
        for i, chunk in enumerate(units_text):
            if not _clean(chunk):
                continue
            tid_hits, concepts = _autotag(chunk, topics)
            origin = {"index": i, "label": f"{kind}#{i + 1}"}
            unit = self.store.add_unit(
                source_id=source["source_id"], text=_clean(chunk),
                topic_ids=tid_hits, concepts=concepts, origin=origin,
            )
            chunk_doc = await self._index_unit(
                unit["unit_id"], chunk, "text", origin["label"])
            self.store._update("units", unit["unit_id"], {"chunk_id": chunk_doc})
            created.append(unit)
        return {"ok": True, "source_id": source["source_id"], "unit_count": len(created)}

    async def ingest_transcript(self, *, title: str, text: str,
                                topics: dict[str, dict] | None = None,
                                meta: dict | None = None,
                                path: str = "") -> dict[str, Any]:
        """Video lecture transcript (SRT / [HH:MM:SS] / plain text).

        ``meta`` may carry the real video URL / YouTube id so citations can
        resolve to the exact moment of the actual video. ``path`` (optional)
        records the local transcript file for citations to open as an artifact.
        """
        topics = topics if topics is not None else self.store.list_topics_by_id()
        source = self.store.add_source(title=title, kind="video",
                                       path=path, meta=meta or {})
        segments = _split_transcript(text)
        created = []
        for idx, (ts, seg) in enumerate(segments):
            if not _clean(seg):
                continue
            tid_hits, concepts = _autotag(seg, topics)
            unit = self.store.add_unit(
                source_id=source["source_id"], text=_clean(seg),
                topic_ids=tid_hits, concepts=concepts,
                origin={"timestamp": ts, "index": idx,
                        "label": f"video@{ts}" if ts else f"video#{idx + 1}"},
            )
            chunk_doc = await self._index_unit(
                unit["unit_id"], seg, "text", unit["origin"]["label"])
            self.store._update("units", unit["unit_id"], {"chunk_id": chunk_doc})
            created.append(unit)
        return {"ok": True, "source_id": source["source_id"], "unit_count": len(created)}

    async def ingest_video(
        self,
        *,
        path: str,
        title: str = "",
        topics: dict[str, dict] | None = None,
        interval_sec: float = 30.0,
        max_frames: int = 60,
    ) -> dict[str, Any]:
        """Extract keyframes from a video file using cv2, caption each with VLM,
        and create Units bound to video timestamps.

        Each keyframe becomes a Unit with origin ``video@HH:MM:SS``.
        If a transcript (.vtt / .srt / .txt) with the same stem exists beside the
        video, it is also ingested and merged under the same source.

        Args:
            path: Path to the video file.
            title: Source title (defaults to filename).
            topics: Topic graph for auto-tagging.
            interval_sec: Seconds between keyframes (default 30).
            max_frames: Maximum number of keyframes to extract (default 60).
        """
        try:
            import cv2  # type: ignore
        except ImportError:
            return {"ok": False, "error": "opencv-python-headless not installed; run: pip install opencv-python-headless"}
        if not os.path.exists(path):
            return {"ok": False, "error": f"file not found: {path}"}

        topics = topics if topics is not None else self.store.list_topics_by_id()
        source = self.store.add_source(
            title=title or os.path.basename(path), kind="video", path=path)

        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return {"ok": False, "error": f"cannot open video: {path}"}

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_interval = int(fps * interval_sec)
        created: list[dict[str, Any]] = []
        frame_idx = 0
        extracted = 0

        while frame_idx < total_frames and extracted < max_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break
            sec = frame_idx / fps
            ts = f"{int(sec // 3600):02d}:{int((sec % 3600) // 60):02d}:{int(sec % 60):02d}"
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            img_bytes = bytes(buf)
            cap_text = await _vlm_caption(img_bytes)
            unit_text = f"【关键帧 video@{ts}】"
            if cap_text:
                unit_text += f" {cap_text}"
            tid_hits, concepts = _autotag(unit_text, topics)
            unit = self.store.add_unit(
                source_id=source["source_id"], text=_clean(unit_text),
                topic_ids=tid_hits, concepts=concepts,
                origin={"timestamp": ts, "frame": frame_idx,
                        "label": f"video@{ts}"},
            )
            chunk_doc = await self._index_unit(
                unit["unit_id"], unit_text, "video", f"video@{ts}")
            self.store._update("units", unit["unit_id"], {"chunk_id": chunk_doc})
            created.append(unit)
            frame_idx += frame_interval
            extracted += 1

        cap.release()

        # Try to find and ingest a companion transcript
        stem = os.path.splitext(path)[0]
        transcript_text: str | None = None
        for ext in (".vtt", ".srt", ".txt"):
            tpath = stem + ext
            if os.path.exists(tpath):
                with open(tpath, "r", encoding="utf-8", errors="replace") as f:
                    transcript_text = f.read()
                break

        # No companion file → try Whisper auto-transcription
        whisper_info: dict[str, Any] = {}
        if not transcript_text:
            whisper_enabled = os.getenv(
                "WHISPER_ENABLED", "false"
            ).strip().lower() in ("true", "1", "yes")
            if whisper_enabled:
                try:
                    from app.services.tutor.transcriber import transcribe_video_async
                    whisper_result = await transcribe_video_async(path)
                    if whisper_result.get("ok") and whisper_result.get("transcript"):
                        transcript_text = whisper_result["transcript"]
                        whisper_info = {
                            "whisper_model": whisper_result.get("model", ""),
                            "whisper_backend": whisper_result.get("backend", ""),
                            "whisper_duration_s": whisper_result.get("duration_s", 0),
                        }
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Whisper transcription failed: {exc}"
                    )

        transcript_count = 0
        if transcript_text:
            t_segments = _split_transcript(transcript_text)
            for idx, (ts, seg) in enumerate(t_segments):
                if not _clean(seg):
                    continue
                tid_hits, concepts = _autotag(seg, topics)
                unit = self.store.add_unit(
                    source_id=source["source_id"], text=_clean(seg),
                    topic_ids=tid_hits, concepts=concepts,
                    origin={"timestamp": ts, "index": idx,
                            "label": f"video@{ts}" if ts else f"video#{idx + 1}"},
                )
                chunk_doc = await self._index_unit(
                    unit["unit_id"], seg, "text", unit["origin"]["label"])
                self.store._update("units", unit["unit_id"], {"chunk_id": chunk_doc})
                created.append(unit)
                transcript_count += 1

        return {
            "ok": True,
            "source_id": source["source_id"],
            "unit_count": len(created),
            "keyframes": extracted,
            "transcript_segments": transcript_count,
            **whisper_info,
        }

    async def ingest_docx(self, *, path: str = "",
                          topics: dict[str, dict] | None = None) -> dict[str, Any]:
        if not HAS_DOCX:
            return {"ok": False, "error": "python-docx not installed; run: pip install python-docx"}
        if not os.path.exists(path):
            return {"ok": False, "error": f"file not found: {path}"}
        try:
            doc = DocxDocument(path)
        except Exception as e:
            return {"ok": False, "error": f"docx parse failed: {e}"}
        topics = topics if topics is not None else self.store.list_topics_by_id()
        source = self.store.add_source(
            title=title or os.path.basename(path), kind="textbook",
            path=path, total_pages=max(1, len(doc.paragraphs) // 30))
        created = []
        char_acc = 0
        for i, para in enumerate(doc.paragraphs):
            ptext = _clean(para.text)
            if not ptext:
                continue
            char_acc += len(ptext)
            page = (char_acc // 2200) + 1
            tid_hits, concepts = _autotag(ptext, topics)
            unit = self.store.add_unit(
                source_id=source["source_id"], text=ptext,
                topic_ids=tid_hits, concepts=concepts,
                origin={"page": page, "paragraph": i, "label": f"p.{page}"},
            )
            chunk_doc = await self._index_unit(unit["unit_id"], ptext, "doc", f"p.{page}")
            self.store._update("units", unit["unit_id"], {"chunk_id": chunk_doc})
            created.append(unit)
        return {"ok": True, "source_id": source["source_id"], "unit_count": len(created)}

    async def ingest_pptx(self, *, path: str, title: str = "",
                          topics: dict[str, dict] | None = None) -> dict[str, Any]:
        if not HAS_PPTX:
            return {"ok": False,
                    "error": "python-pptx not installed; run: pip install python-pptx"}
        if not os.path.exists(path):
            return {"ok": False, "error": f"file not found: {path}"}
        try:
            prs = Presentation(path)
        except Exception as e:
            return {"ok": False, "error": f"pptx parse failed: {e}"}
        topics = topics if topics is not None else self.store.list_topics_by_id()
        source = self.store.add_source(
            title=title or os.path.basename(path), kind="slides",
            path=path, total_pages=len(prs.slides))
        created = []
        for i, slide in enumerate(prs.slides, start=1):
            texts = []
            if slide.shapes:
                for shape in slide.shapes:
                    if getattr(shape, "has_text_frame", False):
                        t = _clean(shape.text_frame.text)
                        if t:
                            texts.append(t)
            slide_text = "\n".join(texts)
            # Caption each embedded picture and bind it to the current slide
            fig_caps: list[str] = []
            for blob in _pptx_picture_blobs(slide):
                cap = await _vlm_caption(blob)
                if cap:
                    fig_caps.append(cap)
            if fig_caps:
                slide_text += "\n\n" + "\n".join(f"【图】{c}" for c in fig_caps)
            if not slide_text:
                continue
            tid_hits, concepts = _autotag(slide_text, topics)
            unit = self.store.add_unit(
                source_id=source["source_id"], text=slide_text,
                topic_ids=tid_hits, concepts=concepts,
                origin={"slide": i, "label": f"slide#{i}", "figures": len(fig_caps)},
            )
            chunk_doc = await self._index_unit(unit["unit_id"], slide_text, "doc", f"slide#{i}")
            self.store._update("units", unit["unit_id"], {"chunk_id": chunk_doc})
            created.append(unit)
        return {"ok": True, "source_id": source["source_id"], "unit_count": len(created)}

    async def ingest_pdf(self, *, path: str, title: str = "",
                         topics: dict[str, dict] | None = None,
                         ocr_fallback: bool = True) -> dict[str, Any]:
        """Parse a PDF page by page; each page becomes a Unit bound to its page
        number. Embedded images are captioned by the VLM and their captions are
        kept with the page so citations retain the page reference.

        When a page has no extractable text (scanned image), OCR is attempted
        via PyMuPDF's built-in OCR or Tesseract as fallback.
        """
        if not HAS_FITZ:
            return {"ok": False, "error": "PyMuPDF not installed; run: pip install pymupdf"}
        if not os.path.exists(path):
            return {"ok": False, "error": f"file not found: {path}"}
        try:
            doc = fitz.open(path)  # type: ignore[attr-defined]
        except Exception as e:
            return {"ok": False, "error": f"pdf parse failed: {e}"}
        topics = topics if topics is not None else self.store.list_topics_by_id()
        source = self.store.add_source(
            title=title or os.path.basename(path), kind="pdf",
            path=path, total_pages=doc.page_count)
        ocr_lang = os.getenv("OCR_LANG", "ch")
        ocr_engine = os.getenv("OCR_ENGINE", "auto")
        created: list[dict[str, Any]] = []
        ocr_pages: list[int] = []
        try:
            for page_idx in range(doc.page_count):
                page = doc.load_page(page_idx)
                page_text = _clean(page.get_text())

                if not page_text and ocr_fallback:
                    page_text = _ocr_page(page, ocr_lang, ocr_engine)
                    if page_text:
                        ocr_pages.append(page_idx + 1)

                fig_caps: list[str] = []
                for img in page.get_images(full=True):
                    try:
                        pix = doc.extract_image(img[0])
                        data = pix.get("image")
                        if not data:
                            continue
                        w, h = pix.get("width", 0), pix.get("height", 0)
                        if w < 32 or h < 32:
                            continue
                        cap = await _vlm_caption(data)
                        if cap:
                            fig_caps.append(cap)
                    except Exception:
                        continue
                unit_text = page_text
                if fig_caps:
                    unit_text += "\n\n" + "\n".join(f"【图表】{c}" for c in fig_caps)
                if not _clean(unit_text):
                    continue
                page_num = page_idx + 1
                tid_hits, concepts = _autotag(unit_text, topics)
                origin = {"page": page_num, "label": f"p.{page_num}",
                          "figures": len(fig_caps)}
                if page_num in ocr_pages:
                    origin["ocr"] = True
                unit = self.store.add_unit(
                    source_id=source["source_id"], text=_clean(unit_text),
                    topic_ids=tid_hits, concepts=concepts, origin=origin,
                )
                chunk_doc = await self._index_unit(unit["unit_id"], unit_text, "pdf", origin["label"])
                self.store._update("units", unit["unit_id"], {"chunk_id": chunk_doc})
                created.append(unit)
        finally:
            try:
                doc.close()
            except Exception:
                pass
        result: dict[str, Any] = {"ok": True, "source_id": source["source_id"], "unit_count": len(created)}
        if ocr_pages:
            result["ocr_pages"] = ocr_pages
        return result

    async def seed_real_course(self) -> dict[str, Any]:
        """Ingest the bundled REAL public course materials listed in
        ``server/demo_materials/materials-manifest.json``:

          - Think Python, 2nd edition (Green Tea Press PDF, 244 pages)
          - MIT OCW 6.0001 Fall 2016 Lecture 1-6 slide decks
          - MIT 6.0001 Lecture 1 official SRT captions (real timestamps)

        Every unit's origin (``p.N`` / ``slide#N`` / ``video@HH:MM:SS``) is
        backed by a real file on disk plus a real, verifiable public URL.
        """
        if self._real_course_seeded():
            return {"ok": True, "skipped": True, "note": "real course already present"}
        topics = self._seed_topics()
        manifest = _load_material_manifest()
        if not manifest:
            return {"ok": False, "error": f"materials-manifest.json not found under {_DEMO_MATERIALS_DIR}"}
        results: list[dict[str, Any]] = []
        for entry in manifest["materials"]:
            ingest_as = entry.get("ingest_as", "")
            if ingest_as not in ("pdf", "pptx", "transcript"):
                continue  # reference/artifact entries are not ingested
            filename = entry["filename"]
            path = os.path.join(_DEMO_MATERIALS_DIR, filename)
            if not os.path.exists(path):
                results.append({"filename": filename, "ok": False, "error": "file missing"})
                continue
            try:
                if ingest_as == "pdf":
                    res = await self.ingest_pdf(path=path, title=_safe_title(entry), topics=topics)
                elif ingest_as == "pptx":
                    res = await self.ingest_pptx(path=path, title=_safe_title(entry), topics=topics)
                else:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext == ".srt":
                        with open(path, "r", encoding="utf-8", errors="replace") as fh:
                            text = fh.read()
                    else:
                        text = _extract_pdf_text(path)
                    res = await self.ingest_transcript(
                        title=_safe_title(entry), text=text, topics=topics,
                        path=path,
                        meta={
                            "video_id": entry.get("youtube_id", ""),
                            "video_url": entry.get("video_url", ""),
                            "source_url": entry.get("url", ""),
                            "license": entry.get("license", ""),
                            "attribution": entry.get("attribution", ""),
                        })
                results.append({"filename": filename, **res})
            except Exception as exc:
                results.append({"filename": filename, "ok": False, "error": str(exc)})
        ok = all(r.get("ok", False) for r in results)
        return {"ok": ok, "results": results, "topics": len(topics)}

    def _real_course_seeded(self) -> bool:
        for source in self.store.list_sources():
            title = source.get("title", "")
            if title.startswith(("Think Python", "MIT 6.0001")):
                return True
        return False

    async def seed_fallback_course(self) -> dict[str, Any]:
        """Fallback synthetic course used only when the real materials are absent
        (e.g. offline checkout without server/demo_materials committed).
        Kept because the original demo shipped fake content; never the default."""
        topics = self._seed_topics()
        demo_text = (
            "## What is a Variable\n"
            "A variable is a named memory location that stores a value. Assigning a value "
            "binds the name to it, e.g. x = 10.\n"
            "## Data Types\n"
            "Python has several data types: int for integers, float for decimals, str for "
            "text, and bool for True/False. The type() function returns an object's type.\n"
            "## Control Flow\n"
            "If statements branch execution on a condition. Comparisons use == != < > <= >=. "
            "While loops repeat while a condition holds; for loops iterate over sequences.\n"
            "## Functions\n"
            "A function is a reusable block named via def. It takes parameters and returns "
            "a result. Parameters are local; return sends a value back.\n"
            "## Lists\n"
            "A list is an ordered mutable sequence. append() adds an element, len() gives "
            "its length, and indexing starts at 0.\n"
            "## Dictionaries\n"
            "A dictionary maps keys to values. Access via d[key], check membership with in. "
            "Keys must be immutable."
        )
        text_res = await self.ingest_text(title="Intro to Python (Textbook)", text=demo_text,
                                          kind="textbook", topics=topics)
        video_seg = (
            "[00:00:00] Welcome. Today we define a function with the def keyword.\n"
            "[00:01:30] A function takes parameters and returns a value with return.\n"
            "[00:03:00] Default parameters and keyword arguments make calls flexible.\n"
            "[00:05:00] Recursion means a function calls itself until a base case.\n"
            "[00:07:00] Remember to always test functions with simple inputs."
        )
        vid_res = await self.ingest_transcript(title="Functions Lecture (Video)", text=video_seg,
                                               topics=topics)
        return {"ok": True, "textbook": text_res, "video": vid_res, "topics": len(topics)}

    def _seed_topics(self) -> dict[str, dict]:
        seed = [
            ("t_variable", "Variables", ["assignment", "variable", "name", "bind",
                                         "integer", "float", "mutable", "immutable"], []),
            ("t_datatypes", "Data Types", ["type", "str", "bool", "data type",
                                           "integer", "float", "boolean"], ["t_variable"]),
            ("t_strings", "Strings", ["string", "concatenation", "slice", "slicing",
                                      "index", "substring"], ["t_datatypes"]),
            ("t_control", "Control Flow", ["if", "while", "for", "comparison", "branch",
                                           "iteration", "loop", "elif", "else", "guess-and-check",
                                           "bisection"], ["t_datatypes"]),
            ("t_functions", "Functions", ["def", "return", "parameter", "argument",
                                          "function", "abstraction", "decomposition",
                                          "scope"], ["t_control"]),
            ("t_lists", "Lists", ["append", "indexing", "len", "list", "tuple",
                                  "mutable", "aliasing", "clone", "slice"], ["t_variable"]),
            ("t_dicts", "Dictionaries", ["key", "value", "membership", "dictionary",
                                         "hashable", "lookup"], ["t_variable"]),
            ("t_recursion", "Recursion", ["recursion", "recursive", "base case",
                                          "factorial", "divide and conquer"], ["t_functions"]),
        ]
        topics = {}
        for tid, name, concepts, pre in seed:
            self.store.upsert_topic(topic_id=tid, name=name,
                                    concepts=concepts, prerequisites=pre)
            topics[tid] = self.store.get_topic(tid)
        return topics


_ingestor: KnowledgeBaseIngestor | None = None


def get_kb_ingestor(store: TutorStore | None = None) -> KnowledgeBaseIngestor:
    global _ingestor
    if store is None:
        from app.services.tutor.store import get_tutor_store
        store = get_tutor_store()
    if _ingestor is None or _ingestor.store is not store:
        _ingestor = KnowledgeBaseIngestor(store=store)
    return _ingestor