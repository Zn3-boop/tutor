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

> Full details in [docs/EVALUATION_SUMMARY.md](docs/EVALUATION_SUMMARY.md)

| Metric | Value | Note |
|--------|-------|------|
| **Test Cases** | **1283** | 1185 on-material + 98 off-material (39 domains × 2 languages) |
| **Faithfulness** | **0.917** | Lexical probe (ragas_used: false) |
| **Answer Relevancy** | **1.000** | Keyword overlap |
| **Refusal Rate** | **96.94%** | 95/98 off-material queries correctly refused |
| **Cognitive Diagnosis** | **71.4%** | Error classification accuracy |
| **Adversarial Robustness** | **92.5%** | Pass rate against adversarial attacks |
| **Unit Tests** | **108/108** | All passing |
| **Mastery Gain (avg)** | **+0.426** | Simulated student mastery improvement |

### Known Limitations (Honest Disclosure)

- Context Precision/Recall (0.073/0.205) are **lexical probes**, not RAGAS LLM-judge scores — clearly labeled `ragas_used: false`
- BM25-only retrieval (no GPU embedding model); enabling vector search + LLM-judge would yield higher scores
- VLM/OCR optional, requires GPU, disabled by default

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