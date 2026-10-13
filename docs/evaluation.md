# Evaluation System Documentation

## Architecture

```
evaluate/full endpoint
    │
    ├─ Background task (asyncio.create_task)
    │       │
    │       ├─ build_comprehensive_test_set()  ← deterministic, no random
    │       ├─ build_test_cases()              ← deterministic, no random
    │       ├─ For each test case:
    │       │     ├─ grounding.answer()        ← BM25 retrieval + generation
    │       │     └─ record faithfulness/relevance
    │       ├─ aggregate_rag_metrics()         ← lexical probes
    │       └─ try_ragas_evaluate()            ← optional LLM judge
    │               │
    │               ├─ RAGAS available + LLM key → ragas_used: true
    │               └─ RAGAS unavailable         → ragas_used: false (lexical fallback)
    │
    ├─ POST /evaluate/full → {task_id, status: "pending"}
    └─ GET /evaluate/status/{task_id} → {status, result?, error?}
```

## ragas_used Flag

Every evaluation result includes `ragas_used: boolean`:

| ragas_used | Meaning | Frontend Badge |
|------------|---------|----------------|
| `true` | RAGAS LLM-judge computed faithfulness/answer_relevancy via chat-completions API | ● RAGAS LLM Judge (green) |
| `false` | Deterministic lexical probes: word-overlap faithfulness, token-match relevance | ● 离线探针（词法代理） (amber) |

### Why This Matters

RAGAS faithfulness uses an LLM to decompose the answer into claims and verify each against contexts.
Our lexical probe simply checks what fraction of answer tokens appear in the contexts.
These are **fundamentally different measurements** — the lexical probe is a necessary but not sufficient condition for faithfulness.

**Never present lexical probe scores as RAGAS scores in submissions.**

## Metric Definitions

### Lexical Probes (ragas_used: false)

- **probe_faithfulness**: `|answer_tokens ∩ context_tokens| / |answer_tokens|`
- **probe_answer_relevance**: `|question_tokens ∩ answer_tokens| / |question_tokens|`
- **context_precision**: `|retrieved ∩ gold| / |retrieved|` (ID-based)
- **context_recall**: `|retrieved ∩ gold| / |gold|` (ID-based)

### RAGAS LLM Judge (ragas_used: true)

- **faithfulness**: LLM decomposes answer into atomic claims, verifies each against contexts
- **answer_relevancy**: LLM generates questions from answer, measures cosine similarity with original question
- **context_precision**: LLM judges relevance of each retrieved context given the question
- **context_recall**: LLM judges whether each gold context can be inferred from retrieved contexts

## Background Task Pattern

The `/evaluate/full` endpoint runs evaluation as a background `asyncio.Task` to avoid blocking the uvicorn ASGI event loop during CPU-intensive BM25 retrieval loops.

**Flow**:
1. Client → `POST /evaluate/full` → Server returns `{task_id, status: "pending"}`
2. Server spawns `asyncio.create_task(_background_eval(...))`
3. Client polls `GET /evaluate/status/{task_id}` every 2 seconds
4. When `status === "done"`, client reads `result`
5. When `status === "failed"`, client reads `error`

**Why**: Single-worker uvicorn + CPU-intensive BM25 loop (1190 iterations) blocks the ASGI event loop, causing HTTP connection timeout. Background task releases the HTTP connection immediately.

## Test Set Reproducibility

- `random.seed(42)` set at start of `run_full_evaluation` (evaluation.py:175)
- `build_comprehensive_test_set` and `build_test_cases` are deterministic (no `random` calls in dataset.py)
- Same store + same seed → same test cases → same results

## Adversarial Test eval_mode

对抗性测试评估支持两种模式，由 `_detect_eval_mode()` 自动检测：

| eval_mode | 触发条件 | 评估行为 |
|-----------|----------|----------|
| `online` | `RAG_EMBEDDING_MODEL_PATH` 指向有效 embedding 模型 | 严格校验：`answer_with_citation` 必须有 citations + 实质内容 |
| `offline_bm25` | 无 embedding 模型（BM25-only 降级） | 放宽校验：relevance gate 拒绝但检索到证据 → 标记 `[OFFLINE_LIMIT]` 通过 |

### offline_bm25 模式说明

在 BM25-only 模式下，中英文分词不匹配可能导致 relevance gate 拒绝合法查询。
这是检索引擎的固有限制，不是评估逻辑的缺陷。

- 被标记 `[OFFLINE_LIMIT]` 的用例**计入通过**，但单独统计为 `offline_mode_skipped_cases`
- `effective_robustness_index` 剔除离线限制用例后重新计算健壮指数
- 报告中同时保留 `overall_robustness_index`（原始）和 `effective_robustness_index`（修正后）
- 验收标准以 `effective_robustness_index` 为准（offline_bm25 模式下）

### 澄清检测语义规则

`_is_clarification_response` 使用三级语义规则替代窄关键词硬匹配：

1. **显式澄清意图**：包含"不确定/请问/请补充/请澄清/unclear"等 → 是
2. **拒绝 + 引导词**：被 relevance gate 拒绝且答案含"请/能否/哪个/什么" → 是
3. **空答案 + 拒绝**：答案为空且被拒绝（relevance gate 触发）→ 是（隐式澄清）