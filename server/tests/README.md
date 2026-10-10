# 测试套件（Phase 2）

所有测试用 `python -m pytest tests -q` 在 `server/` 下运行（CI 与本地相同）。

## 运行前置条件

- **`test_citation_resolve.py`** 和 **`test_grounding.py::test_grounding_no_hallucinated_citations`**
  需要已种子化的真实课程知识库（8 个源、1300+ units）。先执行：

  ```bash
  python scripts/reset_seed_real.py   # 或 python scripts/seed_demo.py
  ```

- 其余单元测试使用 `tempfile` 独立数据目录，**不依赖**种子数据，也不依赖
  外部 embedding 模型：`_get_embedding_model()` 在模型缺失时自动降级为
  BM25-only（见 `app/services/rag/store.py`），测试在无网、无模型、
  无 GPU 的 CI 环境可直接运行。

- 本仓库 `.env` 是可选的；`load_dotenv` 只在脚本中调用。测试不加载 `.env`，
  因此 CI 通过环境变量显式注入：`RAG_DEFER_FAISS_BUILD=true`、
  `RAG_AUTO_BUILD_FAISS=false`、`VLM_ENABLED=false`。

## 测试分类

| 文件 | 覆盖 | 是否需种子数据 |
| --- | --- | --- |
| `test_learner.py` | BKT 学习模型：clamp、先验、观测更新、最弱主题排序 | 否 |
| `test_grounding.py` | 离线相关性闸门（词干化/停用词/拒答）、无幻觉引用 | `no_hallucinated_citations` 需 |
| `test_knowledge.py` | 多模态 ingestion：纯文本/SRT/PPTX/PDF 小 fixture、自动打标 | 否 |
| `test_planning.py` | 拓扑排序（含环）、课程图谱、学习计划前置顺序、闪卡、掌握度摘要 | 否 |
| `test_assessment.py` | 离线 cloze-MCQ 构造、答案严格存在于原文、去重、公共题不泄露答案 | 否 |
| `test_citation_resolve.py` | 真实引用解析：PDF 页码 / 幻灯片 / 视频时间戳 → `source/open` | 是 |

## 关键设计（Phase 2 验收要点）

- **轻量 fixture**：`tests/fixtures/` 下的小型 `test_plain_transcript.txt`、
  `test_transcript.srt`、`test_slides.pptx`、`test_text.pdf` 由
  `scripts/gen_test_files.py` 生成，避免在单测中加载真实大教材。
- **真实模型仅走集成路径**：`reset_seed_real.py` 才会触发 FAISS/embedding；
  单元测试通过 BM25-only 降级保持无模型可运行。
- **答案不泄露**：`generate_quiz` 返回给前端的 `questions` 经
  `_public_question()` 脱敏（无 `answer` 键），测试从
  `store.get_question()` 读取完整题目校验“答案严格存在于原文、干扰项 ≠ 答案”。
