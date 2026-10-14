# ECV-Tutor — Demo Script for Judges

> Step-by-step demo walkthrough for Devpost submission review.

## 🎬 Demo Setup (2 minutes)

1. **Start Backend**
   ```bash
   cd server && pip install -r requirements.txt && python -m app.main
   ```
2. **Start Frontend**
   ```bash
   cd web && npm install && npm run dev
   ```
3. **Open Dashboard**: http://localhost:5173
4. **Seed Demo Course**: Click "知识库 / 上传" → "Seed Demo Course" (loads Think Python PDF + MIT OCW slides + SRT transcript)
5. **Create Demo Student**: Click "+ 新建学生" → name "Demo 学生"

---

## 📋 Demo Steps

### Step 1: 入学诊断 (2 min)
- Tab: **入学诊断**
- Select topics → Click "开始诊断"
- Answer 4-6 questions (mix correct/wrong)
- Click "完成诊断" → View initial mastery report
- **Highlight**: BKT mastery initialized from diagnostic priors

### Step 2: Tutor 聊天 + RAG 溵源 (2 min)
- Tab: **Tutor 聊天**
- Ask: "What is a variable in Python?"
- **Highlight**: Answer cites specific source (page/slide), click citation → Source Drawer opens with PDF viewer at exact page
- Ask off-topic: "What is the weather today?"
- **Highlight**: Refusal with reason "off-material" — no hallucination

### Step 3: Quiz + 自适应难度 (2 min)
- Tab: **Quiz**
- Click "生成测验" → Answer questions
- **Highlight**: Questions target weakest topics first, difficulty adapts (easy→medium→hard)
- After answering, note mastery delta per topic

### Step 4: 测评报告 (1 min)
- Tab: **测评报告**
- Click "加载报告"
- **Highlight**: Weak topics list, misconception labels, mastery sparkline trajectory

### Step 5: 课程图谱 ⭐ NEW (2 min)
- Tab: **课程图谱**
- **Highlight**: Force-directed graph with mastery color coding
  - 🔴 Red = weak (< 40%)
  - 🟡 Yellow = learning (40-70%)
  - 🟢 Green = mastered (> 70%)
- Hover nodes → see topic name, mastery %, concepts
- Drag nodes to rearrange, scroll to zoom

### Step 6: 闪卡复习 ⭐ NEW (1 min)
- Tab: **闪卡复习**
- Click "生成闪卡" → Click cards to flip
- **Highlight**: Front = cloze sentence, Back = answer + citation
- Click "已记住" to mark memorized
- Navigate batches with "上一批/下一批"

### Step 7: 错题本 ⭐ NEW (2 min)
- Tab: **错题本**
- **Highlight**: Auto-recorded wrong answers with:
  - Your answer vs correct answer
  - Associated knowledge points
  - Filter by topic dropdown
- Click "标记已解决" on a wrong question
- Click "一键重测错题" → Answer retest quiz
- **Highlight**: Retest only covers topics from unresolved wrong questions

### Step 8: 学习计划 (1 min)
- Tab: **学习计划**
- Set exam days = 14, sessions/week = 7
- Click "生成计划"
- **Highlight**: Weak topics scheduled first, prerequisites respected, forgetting curve review spacing (1/3/7/14/30 days)

### Step 9: 系统评测 (1 min)
- Tab: **系统评测**
- Click "运行模拟评测"
- **Highlight**: Multi-profile mastery trajectories, faithfulness/repetition metrics
- **Expected metrics** (Enhanced evaluation, v2.0 QA set — 238 test cases: 140 on-material + 98 off-material):
  - Faithfulness: ~0.917 (lexical probe)
  - Refusal Rate: ~96.94% (95/98 off-material queries refused)
  - Mastery Gain: +0.426 avg across simulated students
  - Adversarial Robustness: 92.5%
  - Cognitive Diagnosis: 71.4%
  - Unit Tests: 108/108 passed
- **Key talking point**: All metrics use `ragas_used: false` (lexical probes), clearly labeled — we don't fake LLM-judge scores

---

## 🌟 Key Demo Highlights Checklist

- [ ] **Offline RAG 溯源**: Citation → Source Drawer → PDF at exact page
- [ ] **No Hallucination**: Off-topic question → Refusal
- [ ] **BKT Adaptive**: Weak topics get easier questions, mastery updates in real-time
- [ ] **Course Graph**: Force-directed + mastery color coding
- [ ] **Flashcards**: Flip, memorize, batch review
- [ ] **Wrong Question Notebook**: Auto-record, filter, retest
- [ ] **Study Plan**: Prerequisite ordering + forgetting curve
- [ ] **Misconception Analysis**: LLM-generated error pattern labels

---

## ⚠️ Common Demo Issues & Fixes

| Issue | Fix |
|-------|-----|
| "没有可用的课程主题" | Seed demo data first (Step 0) |
| Quiz shows 0 questions | Need more units — seed demo or upload materials |
| Source Drawer empty | Ensure PDF files exist in `server/demo_materials/` |
| Graph not rendering | Refresh page, check browser console for errors |
| VLM errors in log | Normal — VLM defaults to cloud API for the small-batch figure run; verify `VLM_ENABLED=true` in `server/.env` |
| Port 8000 already in use | Kill existing process: `lsof -ti:8000 \| xargs kill` |

---

## 📦 Demo Materials

- **Think Python 2e** (PDF, ~240 pages) — bundled in `server/demo_materials/`
- **MIT OCW 6.0001 Slides** (PPTX) — bundled
- **Official SRT Transcript** — bundled with timestamps
- All materials are public/CC-licensed

---

## 🎯 Level-2 录屏辅助器（一键证据包 · 真实后端驱动）

> 录屏前后跑一条命令，产出**可审计的真实后端证据包**，覆盖三个评分维度：
> 知识库与来源标注(20%)、个性化功能有效性(20%)、系统评估(15%)。
> 全部走真实 `rag.query` / BKT `LearnerModel` / `EvaluationRunner.run_full_evaluation`，非 mock。

```bash
cd server
python scripts/demo_l2_review.py
```

**产物**
- 终端人类可读报告（chat 引用 / BKT mastery 前后对比 / 评测指标分层）
- `eval_results/eval_results_l2_review.json` 完整证据包（`{rag_demo, bkt_demo, eval_summary}` 三节）

**评分维度 → 证据字段映射**

| 评分项 | 权重 | 证据出处（JSON sections） |
|---|---|---|
| 知识库与来源标注 | 20% | `rag_demo` — 课内题引用(citations/evidence/retrieval_meta) + 超纲题拒答(refuse_reason/off_material) |
| 个性化功能有效性 | 20% | `bkt_demo` — Demo 学生 BKT mastery 轨迹、per-topic mastery 读回(mastery/n_correct/n_wrong)、misconceptions |
| 系统评估 | 15% | `eval_summary` — faithfulness/context_precision/context_recall/refusal_rate/mastery_gain_avg/repetition + student_profiles/profile_trajectories |
| 用户体验与演示视频 | 15% | 配合上方 9 步手动演示脚本对 Dashboard 面板录屏 |

**录屏编排建议**：终端窗口依次展示 Section A/B/C 输出（真实数据），
同时浏览器操作 Dashboard 的 Chat / Quiz / 报告 / 图谱面板；两画面剪辑同段视频，
剪进去的不再是「演示者声称」，而是「系统当场跑出的数字」。

**已预置裁判入口（无需此脚本也能演示）**
- `POST /tutor/demo/warmup` — 复用/创建"Demo 学生"，脚本化答题 + LLM 误区判断，
  返回 trajectory + misconceptions（个性化面板打开即有数据）。
- 前端 `EvaluationPanel` −「运行评测」→ 后台任务轮询 → 分层指标卡片。