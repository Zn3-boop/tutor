# ECV-Tutor — Personalized Tutoring & Adaptive Learning

> Hackathon Track D: AI-Powered Personalized Tutoring System with Source-Grounded RAG, BKT Adaptive Assessment, and Offline-First Design.

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (React + Vite)                │
│  Upload │ Diagnostic │ Chat │ Quiz │ Graph │ Cards │ WQ  │
└──────────────────────┬──────────────────────────────────┘
                       │ /tutor API
┌──────────────────────┴──────────────────────────────────┐
│                  FastAPI Backend (Python)                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ RAG      │ │ BKT      │ │Assessment│ │ Planning  │   │
│  │ Retriever│ │ Learner  │ │ Generator│ │ Scheduler │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                 │
│  │ Grounding│ │ Citations│ │  Store   │                 │
│  │ (Source) │ │ (溯源)   │ │ (JSON)   │                 │
│  └──────────┘ └──────────┘ └──────────┘                 │
└─────────────────────────────────────────────────────────┘
```

## ✨ Core Features

| Feature | Description |
|---------|-------------|
| **Source-Grounded RAG** | Every answer cites specific source units (page/slide/timestamp), no hallucination |
| **BKT Adaptive Assessment** | Bayesian Knowledge Tracing per-topic mastery, difficulty adapts to learner level |
| **Offline-First Questions** | Cloze-MCQs generated from course material with verifiable answer keys — no LLM needed |
| **Course Knowledge Graph** | Force-directed visualization with mastery color coding (red/yellow/green) |
| **Flashcard Review** | Weakness-driven cards with spaced repetition, batch review & memorization tracking |
| **Wrong Question Notebook** | Auto-recorded on wrong answer, filter by topic, one-click retest |
| **Personalized Study Plan** | Weak-first scheduling with prerequisite ordering & forgetting curve review spacing |
| **Multimodal Ingestion** | PDF, PPTX, DOCX, video keyframe extraction, timestamped transcripts |
| **Misconception Analysis** | LLM judge identifies specific conceptual misunderstandings from error patterns |
| **TTS Read-Aloud** | Edge-TTS for quiz feedback and report narration |

## 🚀 Local Deployment

### Prerequisites

- Python 3.11+
- Node.js 20+
- (Optional) CUDA GPU for VLM — runs fully without it

### Backend Setup

```bash
cd server
pip install -r requirements.txt
python -m app.main  # starts on http://127.0.0.1:8000
```

### Frontend Setup

```bash
cd web
npm install
npm run dev  # starts on http://localhost:5173 (proxies /tutor → backend)
```

### Seed Demo Data

```bash
curl -X POST http://127.0.0.1:8000/tutor/ingest/seed-demo
```

Or use the dashboard's "知识库 / 上传" tab → "Seed Demo Course" button.

## 🧪 Testing

```bash
cd server
python -m pytest tests -v
```

### Test Coverage

- `test_assessment.py` — cloze generation, difficulty mapping, answer verification, wrong-question recording
- `test_planning.py` — topological sort, study plan, flashcards, course graph, wrong-question CRUD
- `test_e2e_pipeline.py` — full pipeline: diagnostic → quiz → submit → report → plan → graph → retest
- `test_grounding.py` — source grounding, citation resolution
- `test_knowledge.py` — knowledge base ingestion
- `test_learner.py` — BKT learner model
- `test_citation_resolve.py` — citation resolution, source integrity, transcript cues
- `test_error_analyzer.py` — misconception classification, error pattern detection
- `test_graph_enhancer.py` — course graph enhancement, prerequisite validation
- `test_ragas_diagnostic.py` — RAGAS metric diagnostics, evaluation runner

**Result**: 108/108 passed ✅

## 📊 Evaluation Results

> Full details in [docs/EVALUATION_SUMMARY.md](docs/EVALUATION_SUMMARY.md) and [docs/eval_results.md](docs/eval_results.md)

### QA Test Set (v2.0, `server/tests/test_set.json`)

> **Honest rebuild**: the earlier 1283-case set contained 1183 "kb-derived"
> cases where query == expected answer (tautological self-validation). Those
> were removed from the QA benchmark and demoted to a dedicated retrieval
> self-check set (`server/tests/retrieval_selfcheck.json`). Numbers below come
> only from real, independent questions.

| Metric | Value | Note |
|--------|-------|------|
| **QA Test Cases** | **238** | 140 on-material + 98 off-material |
| **On-material composition** | 118 LLM bank + 10 builtin + 1 synthesis + 1 bilingual comparison + 10 bilingual factual | Query ≠ answer everywhere |
| **Retrieval self-check cases** | 1172 | query = unit first sentence (recall@k probe only, not QA) |
| **Faithfulness** | ~0.917 | **Lexical probe** (`ragas_used: false`) |
| **Answer Relevancy** | **1.000** | Keyword overlap (not semantic) |
| **Context Precision** | 0.073 | Lexical probe (BM25-only limitation) |
| **Context Recall** | 0.205 | Lexical probe (BM25-only limitation) |
| **Refusal Rate** | **96.94%** | 95/98 off-material queries correctly refused |
| **Cognitive Diagnosis** | **71.4%** | Error classification accuracy |
| **Adversarial Robustness** | **92.5%** | Pass rate against adversarial attacks |
| **Unit Tests** | **108/108** | All passing |
| **Mastery Gain (avg)** | **+0.426** | Simulated student mastery improvement (BKT) |

### Known Limitations (Honest Disclosure)

- Context Precision/Recall (0.073/0.205) are **lexical probes**, not RAGAS LLM-judge scores — clearly labeled `ragas_used: false`
- **RAGAS LLM-judge attempt**: a real judge run (`server/run_ragas_judge.py`, seed 42) was executed on sampled v2.0 cases; the judge model returned degenerate all-zero faithfulness/context scores, the guard rejected the run and fell back to lexical probes (`docs/eval_results_ragas_judge.json`, `ragas_used: false`). A valid LLM-judge pass is not part of this submission — public RAG metrics are **offline lexical probes only**.
- BM25-only retrieval (no GPU embedding model); enabling vector search + LLM-judge would yield higher scores
- **VLM/OCR (1d)**: implemented and **真跑验证** — a small batch (2 PDFs, 6 embedded figures) was captioned via the configured cloud vision API and the captions were written into the KB as `【图表】` units (`docs/vlm_small_batch_report.json`, 6 units). Default is cloud-API-enabled (`VLM_ENABLED=true`); the local Qwen2.5-VL-3B model cannot load on this machine's CPU memory budget, so full-course VLM ingestion is not enabled by default.

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Pydantic, sentence-transformers (all-MiniLM-L6-v2), FAISS |
| Frontend | React 18, TypeScript, Vite, react-force-graph-2d, pdfjs-dist |
| AI/ML | BKT (Bayesian Knowledge Tracing), RAG (hybrid BM25+vector), LangFuse observability |
| Storage | JSON file store (zero-config, hackathon-friendly) |

## 📋 Project Highlights

1. **Offline-First**: Core quiz generation, BKT updates, study planning all run without LLM or network
2. **Verifiable Answers**: Every cloze-MCQ answer strictly exists in the source material
3. **No Hallucination**: RAG answers cite specific source units; refusal when off-material
4. **Adaptive Difficulty**: Questions automatically target the learner's weakest topics at appropriate difficulty
5. **Forgetting Curve**: Study plan spaces reviews at 1/3/7/14/30 day intervals
6. **Full Pipeline**: Ingest → Diagnose → Quiz → Report → Plan → Review — all wired end-to-end
7. **Honest Evaluation**: `ragas_used` flag in every eval result — offline lexical probes clearly labeled, never passed off as RAGAS LLM-judge scores