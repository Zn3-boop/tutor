# Evaluation Results — Offline Lexical Probe

> **ragas_used: false** — All metrics below are from deterministic lexical probes, NOT RAGAS LLM-judge scores.

## Test Configuration

| Parameter | Value |
|-----------|-------|
| n_sessions | 2 |
| questions_per_session | 3 |
| seed | 42 |
| llm | false |
| ragas_used | **false** |

## Test Dataset

| Metric | Value |
|--------|-------|
| Total cases | 1190 |
| On-material | 1184 |
| Off-material | 6 |
| Topics covered | 11 (t_control, t_datatypes, t_dicts, t_exceptions, t_files, t_functions, t_lists, t_recursion, t_strings, t_tuples, t_variable) |

## RAG Metrics (Lexical Probes)

> ⚠️ These are **offline lexical probes** (word overlap / token matching), not RAGAS LLM-judge evaluations.
> - `faithfulness`: fraction of answer tokens found in retrieved contexts
> - `answer_relevancy`: fraction of question tokens found in answer
> - `context_precision/recall`: ID-based overlap with gold unit set

| Metric | Value |
|--------|-------|
| Faithfulness | 0.9151 |
| Answer Relevancy | 1.0000 |
| Context Precision | 0.0756 |
| Context Recall | 0.2141 |
| Refusal Rate | 1.0000 |
| Answered Cases | 540 |
| Golden Cases | 1182 |

## Assessment Metrics

| Metric | Value |
|--------|-------|
| Mastery Gain (avg) | +0.5315 |
| Question Repetition Rate (avg) | 0.0000 |

## How to Run True RAGAS Evaluation

To get real RAGAS LLM-judge scores, configure an LLM API key:

```bash
# In .env
LLM_API_KEY=your_zhipu_key
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
LLM_MODEL=glm-4-flash
```

Then call with `llm=true`:

```bash
curl -X POST http://127.0.0.1:8000/tutor/evaluate/full \
  -H "Content-Type: application/json" \
  -d '{"n_sessions":4,"questions_per_session":5,"seed":42,"llm":true}'
```

The response will include `ragas_used: true` and metrics computed by RAGAS with LLM judge.

## Reproducibility

- Seed: 42 (fixed via `random.seed(42)` in `evaluation.py:175`)
- Test set builder (`dataset.py`) is deterministic (no `random` calls)
- Results are reproducible given the same store state and seed

## Note on Lexical Probe Metrics

**The `eval_results_offline_probe.json` file contains results from the offline lexical probe mode (ragas_used=false).**

These metrics are **deterministic word-overlap and token-matching heuristics**, NOT RAGAS LLM-judge scores. 

| Metric | What It Measures | Limitation |
|--------|-----------------|------------|
| `faithfulness` (0.9154) | Fraction of answer tokens present in retrieved contexts | Does NOT verify semantic correctness |
| `answer_relevancy` (1.0) | Fraction of question tokens present in the answer | Does NOT verify answer accuracy |
| `context_precision` (0.0778) | Proportion of retrieved chunks that are in gold set | ID-based, not semantic |
| `context_recall` (0.2191) | Proportion of gold chunks that were retrieved | ID-based, not semantic |

For actual RAGAS LLM-judge metrics, run the evaluation with LLM support enabled:
```bash
curl -X POST http://127.0.0.1:8000/tutor/evaluate/full \
  -H "Content-Type: application/json" \
  -d '{"n_sessions":4,"questions_per_session":5,"seed":42,"llm":true}'
```
Results with `ragas_used: true` will be saved to `docs/eval_results_ragas.json`.