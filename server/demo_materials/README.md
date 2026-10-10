# demo_materials

Optional directory. The **built-in demo course** (Python textbook + video-transcript
lecture over the 6-topic BKT graph) is seeded automatically by `POST /tutor/ingest/seed-demo`
and by `scripts/seed_demo.py`, so you don't *need* to add anything here.

If you want to show multimodal ingestion live, drop files in this folder and they'll
be picked up by `scripts/seed_demo.py` on the next (non-cached) run:

| File | Kind routed to |
|------|----------------|
| `*.pdf`  | ingest_pdf (PyMuPDF: text + embedded images) |
| `*.docx` | ingest_docx (python-docx textbook) |
| `*.pptx` | ingest_pptx (python-pptx slides) |
| `*.srt` / `*.vtt` / `*.txt` | ingest_transcript (video transcript, timestamps kept as unit origin) |

Use topic names from the graph (e.g. 变量/Variables, 函数/Functions) so auto-tagging works.