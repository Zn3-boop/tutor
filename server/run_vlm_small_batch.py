"""Run a real, deliberately small VLM chart-extraction batch.

Inputs: two bundled MIT PDFs with six embedded figures in total.
Outputs: six captioned KB units and docs/vlm_small_batch_report.json.
The cloud provider is configured in server/.env; VLM_ENABLED is required.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import fitz

from app.services.tutor.knowledge import KnowledgeBaseIngestor, _autotag, _vlm_caption
from app.services.tutor.store import get_tutor_store

ROOT = Path(__file__).resolve().parent.parent
MATERIALS = ROOT / "server" / "demo_materials"
REPORT = ROOT / "docs" / "vlm_small_batch_report.json"
TARGETS = [
    MATERIALS / "MIT6_0001F16_Lec1.pdf",
    MATERIALS / "MIT6_0001F16_Lec2.pdf",
]


async def main() -> None:
    if os.getenv("VLM_ENABLED", "").strip().lower() != "true":
        raise SystemExit("VLM_ENABLED must be true; refusing to create a non-VLM report")

    store = get_tutor_store()
    title = "MIT 6.0001 figures — VLM small-batch captions"
    existing = next((s for s in store.list_sources() if s.get("title") == title), None)
    if existing:
        print("already ran:", existing["source_id"])
        print("report:", REPORT)
        return

    source = store.add_source(
        title=title,
        kind="pdf-figures",
        path="server/demo_materials/MIT6_0001F16_Lec1.pdf;MIT6_0001F16_Lec2.pdf",
        total_pages=6,
        meta={"vlm_enabled": True, "batch": "1d", "model": os.getenv("VLM_CLOUD_MODEL", "")},
    )
    topics = store.list_topics_by_id()
    ingestor = KnowledgeBaseIngestor(store)
    results = []

    for pdf_path in TARGETS:
        doc = fitz.open(str(pdf_path))
        for page_idx in range(doc.page_count):
            page = doc.load_page(page_idx)
            page_num = page_idx + 1
            page_text = (page.get_text() or "").strip()
            for image_no, img in enumerate(page.get_images(full=True), start=1):
                pix = doc.extract_image(img[0])
                width, height, data = pix.get("width", 0), pix.get("height", 0), pix.get("image")
                if not data or width < 48 or height < 48:
                    continue
                caption = (await _vlm_caption(data)).strip()
                if not caption:
                    print("caption failed:", pdf_path.name, page_num, image_no)
                    continue
                text = f"【图表】{caption}\n来源页：{pdf_path.name} p.{page_num}"
                if page_text:
                    text += f"\n\n页面文字上下文：{page_text[:1200]}"
                topic_ids, concepts = _autotag(text, topics)
                unit = store.add_unit(
                    source_id=source["source_id"], text=text,
                    topic_ids=topic_ids, concepts=concepts,
                    origin={"page": page_num, "label": f"p.{page_num}",
                            "figures": 1, "vlm": True, "image_index": image_no,
                            "file": pdf_path.name},
                )
                chunk_id = await ingestor._index_unit(
                    unit["unit_id"], text, "pdf-figure", f"{pdf_path.name}#p.{page_num}")
                store._update("units", unit["unit_id"], {"chunk_id": chunk_id})
                results.append({
                    "unit_id": unit["unit_id"], "file": pdf_path.name,
                    "page": page_num, "width": width, "height": height,
                    "caption": caption,
                })
                print(unit["unit_id"], pdf_path.name, f"p.{page_num}", caption)
        doc.close()

    report = {"ok": bool(results), "source_id": source["source_id"],
              "vlm_enabled": True, "unit_count": len(results),
              "model": os.getenv("VLM_CLOUD_MODEL", ""), "results": results}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("ok", "unit_count", "source_id", "model")}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
