import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, CourseGraph, GraphNode, FlashcardsResponse, StudyPlanResponse } from '../utils/api';

interface Props { studentId: string; }

export default function StudyPlanPanel({ studentId }: Props) {
  const [graph, setGraph] = useState<CourseGraph | null>(null);
  const [cards, setCards] = useState<FlashcardsResponse | null>(null);
  const [plan, setPlan] = useState<StudyPlanResponse | null>(null);
  const [examDays, setExamDays] = useState(14);
  const [perWeek, setPerWeek] = useState(7);
  const [flipped, setFlipped] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const loadGraph = useCallback(async () => {
    try { setGraph(await api.graph(studentId)); } catch (e) { setErr(String(e)); }
  }, [studentId]);

  useEffect(() => { loadGraph(); }, [loadGraph]);

  const genCards = async () => {
    if (!studentId) { setErr('请先选择学生'); return; }
    setBusy(true); setErr(''); setFlipped(new Set());
    try { setCards(await api.flashcards(studentId, 10)); } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  const genPlan = async () => {
    if (!studentId) { setErr('请先选择学生'); return; }
    setBusy(true); setErr('');
    try { setPlan(await api.studyPlan(studentId, examDays, perWeek)); } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  const toggleCard = (i: number) => {
    setFlipped((prev) => { const s = new Set(prev); s.has(i) ? s.delete(i) : s.add(i); return s; });
  };

  return (
    <div className="panel">
      <h2>学习计划 · 课程图 · 复习卡片</h2>
      {err && <div className="error">{err}</div>}

      {/* 6a. course graph */}
      <div className="card">
        <h3>课程流程图 (topics → prerequisites)</h3>
        {graph && <CourseGraphSvg graph={graph} />}
        <div className="row">
          <button disabled={busy} onClick={loadGraph}>刷新课程图</button>
        </div>
      </div>

      {/* 6b. flashcards */}
      <div className="card">
        <h3>薄弱项复习卡片</h3>
        <div className="row">
          <button disabled={busy || !studentId} onClick={genCards}>生成复习卡片</button>
        </div>
        {cards && cards.ok && cards.cards.length > 0 && (
          <div className="flashgrid">
            {cards.cards.map((c, i) => (
              <div key={c.unit_id + i}
                className={'flashcard' + (flipped.has(i) ? ' flipped' : '')}
                onClick={() => toggleCard(i)}>
                {flipped.has(i)
                  ? <div className="back"><b>{c.back}</b><span className="meta">{c.topic_name} · {c.source_label}</span></div>
                  : <div className="front">{c.front}</div>}
              </div>
            ))}
          </div>
        )}
        {cards && cards.ok && cards.cards.length === 0 && <div className="meta">暂无可用卡片（请先摄入资料 / 上传课程）。</div>}
      </div>

      {/* 6c. study plan */}
      <div className="card">
        <h3>个性化学习计划</h3>
        <div className="row">
          <label>距考试 <input type="number" min={1} max={90} value={examDays} onChange={(e) => setExamDays(Number(e.target.value))} /> 天</label>
          <label>每周 <input type="number" min={1} max={35} value={perWeek} onChange={(e) => setPerWeek(Number(e.target.value))} /> 次练习</label>
          <button disabled={busy || !studentId} onClick={genPlan}>生成计划</button>
        </div>
        {plan && plan.ok && (
          <>
            <div className="meta">
              共 {plan.stats.total_activities} 次 = 学习 {plan.stats.learn_sessions} + 复习 {plan.stats.review_sessions}，覆盖 {plan.stats.covered_topics} 个主题
            </div>
            <div className="planlist">
              {plan.days.map((d) => (
                <div key={d.day} className="planrow">
                  <span className="day">Day {d.day}</span>
                  <span className="acts">
                    {d.activities.map((a, i) => (
                      <span key={i} className={'act ' + (a.action === '复习' ? 'review' : 'learn')}>
                        {a.topic_name}<em>{a.action}</em>
                        <small>{a.reason}</small>
                      </span>
                    ))}
</span>
                  <span className="meta">~{d.minutes}min</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
const W = 760, H = 300;

function CourseGraphSvg({ graph }: { graph: CourseGraph }) {
  const layout = useMemo(() => {
    const depth: Record<string, number> = {};
    graph.nodes.forEach((n) => { depth[n.id] = 0; });
    const byId: Record<string, GraphNode> = {};
    graph.nodes.forEach((n) => { byId[n.id] = n; });
    for (let pass = 0; pass < graph.nodes.length + 1; pass++) {
      let changed = false;
      graph.nodes.forEach((n) => {
        const deps = graph.edges.filter((e) => e.to === n.id);
        if (!deps.length) return;
        const d = Math.max(...deps.map((e) => (depth[e.from] ?? 0) + 1));
        if (depth[n.id] !== d) { depth[n.id] = d; changed = true; }
      });
      if (!changed) break;
    }
    const byCol: Record<number, GraphNode[]> = {};
    graph.nodes.forEach((n) => { (byCol[depth[n.id] ?? 0] = byCol[depth[n.id] ?? 0] || []).push(n); });
    const pos: Record<string, { x: number; y: number }> = {};
    let maxRow = 0;
    Object.entries(byCol).forEach(([col, arr]) => {
      arr.forEach((n, row) => {
        maxRow = Math.max(maxRow, row);
        pos[n.id] = { x: 90 + Number(col) * 170, y: 40 + row * 60 };
      });
    });
    const height = Math.max(H, 80 + (maxRow + 1) * 60);
    return { pos, height, byId };
  }, [graph]);

  const color = (m?: number | null) => {
    if (m == null) return '#8a93a6';
    if (m < 0.4) return '#e4584f';
    if (m < 0.7) return '#e0a53e';
    return '#3fb27f';
  };

  return (
    <svg width={W} height={layout.height} style={{ maxWidth: '100%' }}>
      <defs>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#b9c2d0" />
        </marker>
      </defs>
      {graph.edges.map((e, i) =>
        layout.pos[e.from] && layout.pos[e.to] ? (
          <line key={i} x1={layout.pos[e.from].x} y1={layout.pos[e.from].y}
            x2={layout.pos[e.to].x} y2={layout.pos[e.to].y}
            stroke="#b9c2d0" strokeWidth={1.6} markerEnd="url(#arrow)" />
        ) : null
      )}
      {graph.nodes.map((n) => {
        const p = layout.pos[n.id]; if (!p) return null;
        const c = color(n.mastery);
        return (
          <g key={n.id}>
            <circle cx={p.x} cy={p.y} r={18} fill={c} opacity={0.18} />
            <circle cx={p.x} cy={p.y} r={10} fill={c} />
            {n.mastery != null && (
              <text x={p.x} y={p.y + 14} textAnchor="middle" fontSize={10} fill={c} fontWeight={600}>
                {(n.mastery * 100).toFixed(0)}%
              </text>
            )}
          </g>
        );
      })}
      {graph.nodes.map((n) => {
        const p = layout.pos[n.id]; if (!p) return null;
        return (
          <text key={'t' + n.id} x={p.x} y={p.y + 36} textAnchor="middle" fontSize={12} fill="#2b3440" fontWeight={500}>
            {n.name}
          </text>
        );
      })}
    </svg>
  );
}