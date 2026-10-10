# ECV Tutor — 自适应学习系统 (Track D)

Demo-ready adaptive tutoring system: grounded RAG chat, adaptive assessment with a
Bayesian Knowledge Tracing (BKT) learner model, misconception diagnosis, learning
planner, flashcards, and a full RAGAS benchmark. Works **fully offline** by default
and lights up with LLM judging when an OpenAI-compatible relay is configured.

## Layout

```
server/   FastAPI backend (app/api, app/services/tutor, app/services/eval, ...)
web/      React + Vite desktop dashboard (src/components, src/utils/api.ts)
```

## Quick start

Backend:
```bash
cd server
# (optional) create .env from the template — see section below
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:
```bash
cd web
npm install
npm run dev        # http://localhost:5173, proxies /tutor -> 127.0.0.1:8000
```

## One-command demo bootstrap

`scripts/demo.ps1` (Windows) or `scripts/demo.sh` (macOS/Linux/WSL) gets the system
demo-ready in one go: ensures the backend is running, idempotently seeds the **REAL
bundled course materials** (Think Python 2e + MIT OCW 6.0001), warms up a base
「Demo 学生」 with scripted answers (a few deliberately wrong, so the misconception
judge and mastery curve already have data), then smoke-tests every learner-model
endpoint.

```bash
# Windows
powershell -ExecutionPolicy Bypass -File scripts\demo.ps1
# bash
bash scripts/demo.sh
```

Then open the dashboard, select the printed student id, and you can immediately demo:
ask a grounded question (with `[1][2]` citations that resolve to real page / slide /
video-timestamp references) → 「🧠 误解诊断」→ mastery sparkline → 「🔊 朗读总结」.
For RAGAS, run `POST /tutor/evaluate/full` (one multi-row call ~10–35s).

The pieces are also usable individually:
- `scripts/reset_seed_real.py` — wipe the demo DB + RAG store, re-ingest the real
  course from `server/demo_materials/materials-manifest.json`, rebuild FAISS once,
  and warm up the demo student.
- `scripts/seed_demo.py` — idempotent service-layer seeder for the real course.
- `scripts/warmup_student.py` — HTTP client for `POST /tutor/demo/warmup`, prints a summary.
- `POST /tutor/demo/warmup` — server-side scripted warmup (reads real answer keys from the
  store in-process, so no second DB writer and no leaked answers over the public API).

## Environment (`.env`)

Copy `server/.env.example` to `server/.env` and fill in values.
`.env` is git-ignored — **it holds API keys and must not be committed.**

| Variable | Purpose | Default / offline behavior |
| --- | --- | --- |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI-compatible chat relay | unset → offline templates |
| `LLM_TIMEOUT_SECONDS` | per-call timeout | 60 |
| `LANGFUSE_*` / `LANGFUSE_ENABLED` | tracing | off |
| `RAGAS_EMBED_MODEL` / `RAGAS_EMBED_DEVICE` | local embedding override for RAGAS | `all-MiniLM-L6-v2` on `cpu` |
| `TTS_VOICE` | Edge-TTS voice | `zh-CN-XiaoxiaoNeural` |

## RAGAS — all four metrics are real LLM judges

`/tutor/evaluate/full` runs `faithfulness`, `answer_relevancy`, `context_precision`
and `context_recall`. **There is no lexical fallback** — every metric is LLM-judged.
Because the relay does not serve OpenAI `/embeddings` (returns 403 /
`AttributeError: str has no attribute data`), embeddings come from a fully-offline
local MiniLM model (`AutoModel` + mean-pooling + L2 norm, lazy singleton cache,
`local_files_only=True`). Judge calls are `use_responses_api=False`/native for
compatibility with `openai` 3.3.x. Expect ~10–35s per multi-row call.

## High-impact features

- **LLM misconception judge (3c)** — `POST /tutor/misconceptions`. One call groups the
  student's wrong-answer samples and returns a concrete misconception label per topic
  (e.g. 「混淆了 def 定义与调用」). Falls back to a count-based report when the relay is off.
  Labels are merged into the assessment report.
- **Learner-model mastery curve (20% weight)** — every `submit_answer` appends the average
  BKT mastery to `student.mastery_traj`; `GET /tutor/mastery-trajectory/{id}` exposes it,
  and the dashboard renders it as a sparkline (real student + simulated profiles).
- **Voice coaching (6e)** — `POST /tutor/tts` (Edge TTS) returns MP3; dashboard has a
  「🔊 朗读总结」 button that reads back mastery + misconceptions.
- **Bilingual answers (6d)** — grounded-chat prompt replies in the language the student used.

## Demo materials & citation provenance (real-citations-first)

The demo knowledge base is grounded in **real, verifiable public course materials**,
not fabricated sample content. Every unit origin (`p.123` / `slide#7` /
`video@00:31:05`) resolves to a real file in `server/demo_materials/` plus a real
public URL.

| Bundled material | Source | License | Attribution |
| --- | --- | --- | --- |
| `thinkpython2.pdf` (Think Python, 2nd ed.) | [Green Tea Press](https://greenteapress.com/thinkpython2/thinkpython2.pdf) | CC BY-NC 3.0 | Allen B. Downey |
| `MIT6_0001F16_Lec1.pptx` + `Lec1–Lec6.pdf` (slides) | [MIT OCW 6.0001 Fall 2016](https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/) | CC BY-NC-SA 4.0 | Ana Bell, Eric Grimson, John Guttag |
| `MIT6_0001F16_Lec1_transcript.srt` (official captions, 927 cues) | [Internet Archive MIT6.0001F16](https://archive.org/details/MIT6.0001F16) | CC BY-NC-SA 4.0 | MIT OpenCourseWare |

The `server/demo_materials/materials-manifest.json` file is the machine-readable
provenance record: filename, original URL, license, and attribution for every
bundled file. `scripts/build_lec1_pptx.py` rebuilds the PPTX deck verbatim from the
official OCW PDF, so slide numbers stay verifiable against the original deck.

Every origin is resolvable through `GET /tutor/source/open` (Phase 3 wires it to the
PDF.js / video-seek viewers), and `server/tests/test_citation_resolve.py` fails the
build if any unit references a fabricated source, an out-of-range page, or a
timestamp beyond the real video length:

```bash
cd server && python -m pytest tests -q
# 5 passed — citations resolvable, no synthetic units
```

## New REST endpoints

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/tutor/misconceptions` | LLM misconception labels from wrong-answer samples |
| `GET` | `/tutor/mastery-trajectory/{student_id}` | per-answer mastery curve |
| `POST` | `/tutor/tts` | Edge-TTS MP3 for any text |
| `POST` | `/tutor/demo/warmup` | scripted warmup of 「Demo 学生」 (seeds + misconception + trajectory) |
| `GET` | `/tutor/report/{student_id}` | last stored assessment report |
| `POST` | `/tutor/evaluate/full` | full RAGAS + personalization benchmark |
| `GET` | `/tutor/source/open?unit_id=…` | resolve a citation to page/slide/video-timestamp + seek URL |
| `GET` | `/tutor/files?path=…` | serve a bundled course-material file (PDF/PPTX/SRT) to the browser viewer |

## Verified

- Backend: `py_compile` clean; app imports; BKT lowers mastery on errors; trajectory +
  misconception samples persist; Edge-TTS synthesizes audio.
- Frontend: `tsc --noEmit` passes.
- Offline RAGAS eval returns real scores (`faithfulness=0.5, answer_relevancy=1.0,
  context_precision=1.0, context_recall=1.0`) with `ragas_used=True`.