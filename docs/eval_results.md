# Evaluation Results — v2.0 QA Set (Offline Lexical Probe)

> **ragas_used: false** — All public metrics below are from deterministic lexical probes, NOT RAGAS LLM-judge scores.

> **v2.0 honest rebuild**: the earlier 1283-case set contained 1183 "kb-derived"
> cases where query == expected answer (tautological self-validation). Those
> were removed from the QA benchmark and demoted to a dedicated retrieval
> self-check set (`server/tests/retrieval_selfcheck.json`, 1172 cases). Numbers
> below come only from real, independent questions.

## Test Configuration

| Parameter | Value |
|-----------|-------|
| n_sessions | 4 |
| questions_per_session | 5 |
| seed | 42 |
| llm | false |
| ragas_used | **false** |

## Test Dataset (v2.0)

| Metric | Value |
|--------|-------|
| Total cases | 238 |
| On-material | 140 |
| Off-material | 98 |
| Topics covered | 11 (t_control, t_datatypes, t_dicts, t_exceptions, t_files, t_functions, t_lists, t_recursion, t_strings, t_tuples, t_variable) |

## RAG Metrics (Lexical Probes, v2.0)

> ⚠️ These are **offline lexical probes** (word overlap / token matching), not RAGAS LLM-judge evaluations.
> - `faithfulness`: fraction of answer tokens found in retrieved contexts
> - `answer_relevancy`: fraction of question tokens found in answer
> - `context_precision/recall`: ID-based overlap with gold unit set

| Metric | Value |
|--------|-------|
| Faithfulness | ~0.917 |
| Answer Relevancy | 1.0000 |
| Context Precision | 0.073 |
| Context Recall | 0.205 |
| Refusal Rate | 0.9694 (95/98 off-material refused) |
| Mastery Gain (avg) | +0.426 |

## Historical Baseline (2026-10-11, for reference)

The pre-rebuild 1190-case offline probe run is preserved in
`docs/eval_results_offline_probe.json`:

| Metric | Value |
|--------|-------|
| Total cases | 1190 |
| On-material | 1184 |
| Off-material | 6 |
| Faithfulness | 0.9154 |
| Context Precision | 0.0778 |
| Context Recall | 0.2191 |
| Mastery Gain (avg) | +0.5315 |

## RAGAS LLM-Judge: Real Run, Judged Invalid

A real RAGAS LLM-judge run was attempted (`server/run_ragas_judge.py`, seed 42,
50 on-material + 30 off-material samples). The judge model returned degenerate
all-zero faithfulness/context scores in this environment; the degenerate-run
guard in `ragas_metrics.py` rejected the run and fell back to lexical probes,
writing `ragas_used: false` to `docs/eval_results_ragas_judge.json`. Those
sampled numbers are **not** reported as pass metrics.

## VLM Small-Batch Figure Extraction (1d)

Real VLM chart captioning was run on a deliberately small batch (2 PDFs, 6
embedded figures) using the configured cloud vision API; each caption became a
KB unit tagged `【图表】`. See `docs/vlm_small_batch_report.json` for per-unit
captions. The local Qwen2.5-VL-3B model cannot load on this machine's CPU
memory budget, so the cloud API is the enabled path (`VLM_ENABLED=true`).

## Reproducibility

- Seed: 42 (fixed via `random.seed(42)` in `evaluation.py`)
- Test set builder (`dataset.py`) is deterministic (no `random` calls)
- Results are reproducible given the same store state and seed

## Note on Lexical Probe Metrics

**The `eval_results_offline_probe.json` file contains the historical baseline
(ragas_used=false).** The v2.0 numbers in this document come from the same
deterministic lexical-probe backend.

| Metric | What It Measures | Limitation |
|--------|-----------------|------------|
| `faithfulness` (~0.917) | Fraction of answer tokens present in retrieved contexts | Does NOT verify semantic correctness |
| `answer_relevancy` (1.0) | Fraction of question tokens present in the answer | Does NOT verify answer accuracy |
| `context_precision` (0.073) | Proportion of retrieved chunks that are in gold set | ID-based, not semantic |
| `context_recall` (0.205) | Proportion of gold chunks that were retrieved | ID-based, not semantic |