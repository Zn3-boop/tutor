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
- **Expected metrics** (Enhanced evaluation, 1283 test cases):
  - Faithfulness: ~0.917
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
| VLM errors in log | Normal — VLM disabled by default, not needed for demo |
| Port 8000 already in use | Kill existing process: `lsof -ti:8000 \| xargs kill` |

---

## 📦 Demo Materials

- **Think Python 2e** (PDF, ~240 pages) — bundled in `server/demo_materials/`
- **MIT OCW 6.0001 Slides** (PPTX) — bundled
- **Official SRT Transcript** — bundled with timestamps
- All materials are public/CC-licensed