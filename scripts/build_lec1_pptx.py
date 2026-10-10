"""Build the derived MIT 6.0001 Lecture 1 PPTX deck from the official OCW PDF.

MIT OCW publishes the 6.0001 slides only as PDF, but the prototype needs a real
.pptx to exercise the slide-deck ingestion pipeline. This script rebuilds the
deck with python-pptx: every PDF page becomes one slide whose text is extracted
VERBATIM from the official PDF, so ``slide#N`` citations remain verifiable
against the original deck (slide N == PDF page N).

Run from the repo root:
    python scripts/build_lec1_pptx.py
"""

from __future__ import annotations

import os

DEMO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server", "demo_materials"))
PDF_PATH = os.path.join(DEMO_DIR, "MIT6_0001F16_Lec1.pdf")
OUT_PATH = os.path.join(DEMO_DIR, "MIT6_0001F16_Lec1.pptx")
MAX_LINES_PER_SLIDE = 26
MAX_CHARS_PER_LINE = 80


def main() -> None:
    import fitz  # type: ignore
    from pptx import Presentation  # type: ignore
    from pptx.util import Inches, Pt

    doc = fitz.open(PDF_PATH)
    page_count = doc.page_count
    prs = Presentation()  # default 4:3 blank
    blank = prs.slide_layouts[6]
    for page in doc:
        slide = prs.slides.add_slide(blank)
        lines = [l.strip() for l in page.get_text().splitlines() if l.strip()][:MAX_LINES_PER_SLIDE]
        tb = slide.shapes.add_textbox(Inches(0.4), Inches(0.4), Inches(9.2), Inches(6.6))
        tf = tb.text_frame
        tf.word_wrap = True
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = line[:MAX_CHARS_PER_LINE]
            p.font.size = Pt(16)
            p.space_after = Pt(4)
    doc.close()
    prs.save(OUT_PATH)
    print(f"built {OUT_PATH} with {len(prs.slides)} slides (source PDF pages = {page_count})")


if __name__ == "__main__":
    main()
