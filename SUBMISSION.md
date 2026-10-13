# ECV-Tutor — Hackathon Submission Guide

> Track D: AI-Powered Personalized Tutoring & Adaptive Learning

## Product Description

**ECV-Tutor** is a personalized Python tutoring system that:
1. **Ingests multimodal course materials** (PDF/PPTX/DOCX/SRT) into a unified knowledge base
2. **Answers with source citations** — every response links to exact page/slide/timestamp
3. **Refuses off-topic questions** — closed-domain design prevents hallucination
4. **Adapts to each learner** — BKT (Bayesian Knowledge Tracing) per-topic mastery model
5. **Runs offline-first** — core features (quiz, BKT, planning) work without LLM or GPU

### Problem Solved

| Pain Point | Solution |
|------------|----------|
| Scattered learning sources (video, PDF, slides) | Unified multimodal ingestion with source linking |
| AI chatbots hallucinate, can't trace answers | Source-grounded RAG with per-answer citations |
| One-size-fits-all teaching | BKT adaptive assessment + personalized study plans |

## Technical Architecture

```
Frontend (React + Vite)          Backend (FastAPI + Python)
┌─────────────────────┐          ┌──────────────────────────────┐
│ Dashboard UI        │◄────────►│ /tutor API                    │
│ - Upload Panel      │   CORS   │  ├─ RAG Retriever (BM25+Vec)  │
│ - Chat Panel        │          │  ├─ Grounding Gate            │
│ - Quiz Panel        │          │  ├─ Assessment Generator      │
│ - Report Panel      │          │  ├─ BKT Learner Model         │
│ - Graph Panel       │          │  ├─ Learning Planner          │
│ - Flashcards Panel  │          │  └─ Evaluation System         │
│ - Wrong Questions   │          └──────────────────────────────┘
└─────────────────────┘
```

## Requirement Coverage

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| 1a. Multimodal ingestion | ✅ | PDF/PPTX/DOCX/SRT auto-parse |
| 1b. Content organization + source links | ✅ | Per-unit origin (page/slide/timestamp) |
| 1c. Topic/concept extraction | ✅ | Keyword matching auto-tagging |
| 1d. Image/chart processing | ✅ | PyMuPDF embedded images, VLM optional |
| 2a. Source-cited answers | ✅ | `[1] p.14` format, clickable → PDF viewer |
| 2b. Refuse off-topic questions | ✅ | Lexical relevance gate (threshold 0.40) |
| 3a. Adaptive Quiz (MCQ/short/numeric) | ✅ | Cloze-MCQ offline generation |
| 3b. Answer verification + no-repeat | ✅ | Offline template guarantees; answered tracking |
| 3c. Feedback + misconception + report | ✅ | Wrong-question book + error classification |
| 4a. BKT learner model | ✅ | 4-parameter BKT (pL0/pT/pG/pS) per-topic |
| 4b. Diagnostic onboarding | ✅ | Diagnostic quiz → sqrt(pc) prior |
| 5a. Evaluation framework | ✅ | RAGAS framework + offline probe dual mode |
| 5b. Faithfulness/Relevancy metrics | ✅ | See evaluation results below |
| 5c. Simulated student evaluation | ✅ | fast/average/struggling profiles |
| 6a. Course flow graph | ✅ | Force-directed visualization |
| 6b. Weakness review materials | ✅ | Flashcards (Cloze fill-in-blank) |
| 6c. Study plan | ✅ | Forgetting curve spacing (1/3/7/14/30 days) |
| 6d. Bilingual support | ✅ | Language detection + bilingual answers |
| 6e. TTS read-aloud | ✅ | Edge-TTS audio feedback |

## Course Material Sources (All Public)

| File | Source | License | URL |
|------|--------|---------|-----|
| `thinkpython2.pdf` | Think Python 2e, Allen B. Downey | CC BY-NC 3.0 | https://greenteapress.com/thinkpython2/thinkpython2.pdf |
| `MIT6_0001F16_Lec*.pdf/pptx` | MIT OCW 6.0001 | CC BY-NC-SA 4.0 | https://ocw.mit.edu/courses/6-0001-fall-2016/ |
| `MIT6_0001F16_Lec1_transcript.srt` | Internet Archive | CC BY-NC-SA 4.0 | https://archive.org/download/MIT6.0001F16/ |

## Evaluation Results

### Offline Evaluation (ragas_used: false, lexical probe)

| Metric | Value | Note |
|--------|-------|------|
| **Test Cases** | **1283** | 1185 on-material + 98 off-material |
| **Faithfulness** | **0.917** | Lexical probe |
| **Answer Relevancy** | **1.000** | Keyword overlap |
| **Context Precision** | 0.073 | Lexical probe (BM25-only limitation) |
| **Context Recall** | 0.205 | Lexical probe (BM25-only limitation) |
| **Refusal Rate** | **96.94%** | 95/98 off-material queries correctly refused |
| **Mastery Gain (avg)** | **+0.426** | Simulated student mastery improvement |
| **Question Repetition** | **0.000** | Zero repeat |

### Adversarial Testing

- **Robustness index**: 0.925
- **Refusal accuracy**: 100%
- **Clarification detection**: 100%
- Pass rate 86.7% (13/15), 2 edge cases (empty query / special chars)

### Cognitive Diagnosis

- **Accuracy**: 71.4% (10/14)
- **Misconception coverage**: 100% (6/6 error types)
- **Remediation relevance**: 71.4%

### Unit Tests

- **108/108 passed** ✅

### Reproducibility Scripts

| Script | Purpose | Output |
|--------|---------|--------|
| `server/run_eval_llm_enhanced.py` | Enhanced evaluation (llm=True) | `docs/eval_results_ragas_enhanced.json` |
| `server/run_ragas_judge.py` | RAGAS LLM-judge on sampled cases | `docs/eval_results_ragas_judge.json` |
| `server/generate_llm_on_material.py` | LLM question generation | `docs/llm_generated_on_material.json` |

## How to Run

```bash
# Backend
cd server
pip install -r requirements.txt
python -m app.main  # starts on http://127.0.0.1:8000

# Frontend
cd web
npm install
npm run dev  # starts on http://localhost:5173

# Seed demo data
curl -X POST http://127.0.0.1:8000/tutor/ingest/seed-demo
```

See [DEMO.md](DEMO.md) for the full 9-step demo walkthrough.

## Known Limitations (Honest Disclosure)

1. **Context Precision/Recall (0.073/0.205)**: Offline BM25-only mode (no GPU embedding model). All results labeled `ragas_used: false` — never passed off as RAGAS LLM-judge scores.
2. **Answer Relevancy = 1.0**: Keyword overlap metric, not semantic. True LLM-judge score estimated at 0.7–0.9.
3. **VLM/OCR**: Optional, requires GPU, disabled by default, does not affect core demo.
4. **LLM-generated questions**: 118 questions in `docs/llm_generated_on_material.json` pending human review before integration.

## Devpost Submission Checklist

- [ ] **Project description**: Use Product Description + Architecture above
- [ ] **Source code**: GitHub repo with README (install instructions, prerequisites, run guide)
- [ ] **Demo video**: 3–10 min YouTube, show actual running system, explain design decisions, English audio or subtitles
- [ ] **Team info**: All members' real names + Devpost accounts