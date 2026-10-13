## Dataset Sources and Methodology

> **Important**: This evaluation dataset strictly follows the "closed-domain tutoring system" design principle.

### 1. Data Source Composition

#### 1.1 On-Material Questions (In-Scope)

**NEVER directly copy from external datasets**. Our on-material test questions consist of two parts:

- **Hand-Written Core Samples** (_BUILTIN_ON_MATERIAL_QUERIES)
  - Manually designed based on Python programming fundamentals
  - Covers 11 topics: variables, datatypes, functions, lists, dicts, control flow, exceptions, recursion, strings, tuples, files
  - Each question is linked to specific course units (chunk_id)
  - Answers are directly extracted from the course knowledge base

- **RAGAS TestsetGenerator / LLM Auto-Generated** (P1 - Completed)
  - Automatically generates diverse questions from course knowledge base content using LLM (glm-5.3-flash)
  - Includes factual, conceptual, and procedural question types
  - 118 questions generated (72 English + 46 Chinese), covering all 8 topics
  - Saved to `llm_generated_on_material.json` for human review before integration
  - Tagged with topic_ids, difficulty labels, and expected_doc_ids

#### 1.2 Off-Material Questions (Out-of-Scope)

**Partially referenced from open-source RAG evaluation repos** (e.g., RAGAS, LangChain examples)

- **Purpose**: Only for testing **out-of-scope refusal capability**
- **Source Domains**:
  - Geography, Cooking, Finance, Healthcare, Sports, Repair
  - Astronomy/Physics, History, Education, Business, Art, Travel
  - Tech, Philosophy, Economics, Pets, Technology, Crafts, Gardening
  - Literature, Geology, Wellness, Music, Games

- **Bilingual Design**: Each domain has paired English + Chinese samples
  - Total: 39 domains × 2 languages = 78 independent queries (zero duplicates)
  - Combined with _OFF_MATERIAL_QUERIES_EXTENDED: 20 additional pairs (10 domains × 2 languages)
  - Grand total: 98+ off-material test cases

### 2. Why Not Use Public Benchmark Datasets?

This is a **closed-domain personalized tutoring system**. Public QA benchmarks (HotpotQA, TriviaQA, CMRC, SQuAD, etc.) contain questions unrelated to our course materials. If we used them as on-material test cases:

1. Those questions **do not exist in our knowledge base**, breaking our source-grounded RAG pipeline
2. Our **learner model cannot track progress** on external topics
3. **Refusal rate would artificially drop**, falsely suggesting the system is hallucinating

We use public out-of-domain queries **only for refusal capability testing**. Our on-material test set is built from our own course content: hand-written core samples + auto-generated questions via RAGAS TestsetGenerator derived from our lecture/textbook chunks.

### 3. Evaluation Metric Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Refusal Rate** | ≥95% | Percentage of off-material queries correctly refused (98+ samples) |
| **Faithfulness** | ≥0.85 | RAGAS LLM-judge or lexical probe |
| **Context Recall** | ≥0.80 | Ratio of retrieved golden chunks |
| **Context Precision** | ≥0.75 | Ratio of relevant retrieved chunks |
| **Answer Relevancy** | ≥0.80 | Coverage of question keywords in answer |
| **Cognitive Diagnosis Accuracy** | ≥70% | Error classification accuracy |
| **Adversarial Robustness** | ≥60% | Pass rate against adversarial attacks |

### 4. Data Augmentation Strategy

1. **Bilingual Testing**: Mixed language queries for cross-lingual robustness
2. **Synthesis Queries**: Multi-unit reasoning questions
3. **KB-Derived**: Auto-generated from first sentences of course units
4. **Adversarial Attacks**: Empty queries, special characters, leading questions

### 5. Reproducibility Guarantee

- **Seed**: 42 (fixed random seed)
- **Persistence**: Test results saved to `tests/test_set.json`
- **Versioning**: Enhanced-v1 format with timestamps

---

**References**:
- RAGAS Framework: https://github.com/explodinggradients/ragas
- LangChain Evaluation: https://python.langchain.com/docs/how_to/qa-tools-rag-evaluation