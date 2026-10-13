import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, CourseGraph, GraphNode, FlashcardsResponse, StudyPlanResponse } from '../utils/api';
import { Button, Card, Input } from './ui';

interface Props { studentId: string; onOpenGraph?: () => void; }

export default function StudyPlanPanel({ studentId, onOpenGraph }: Props) {
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
    <Card title="学习计划 · 课程图 · 复习卡片">
      {err && <div className="error">{err}</div>}

      {/* 6a. course graph */}
      <Card title="课程流程图 (topics → prerequisites)">
        {graph && <CourseGraphSvg graph={graph} />}
        <div className="row">
          <Button size="sm" variant="secondary" disabled={busy} onClick={loadGraph}>🔄 刷新课程图</Button>
        </div>
      </Card>

      {/* 6b. flashcards */}
      <Card title="薄弱项复习卡片">
        <div className="row">
          <Button size="sm" disabled={busy || !studentId} onClick={genCards}>🎴 生成复习卡片</Button>
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
      </Card>

      {/* 6c. study plan */}
      <Card title="个性化学习计划">
        <div className="row">
          <label className="flex items-center gap-1.5 text-sm text-slate-600">距考试
            <Input type="number" min={1} max={90} value={examDays} onChange={(e) => setExamDays(Number(e.target.value))} className="w-24" /> 天
          </label>
          <label className="flex items-center gap-1.5 text-sm text-slate-600">每周
            <Input type="number" min={1} max={35} value={perWeek} onChange={(e) => setPerWeek(Number(e.target.value))} className="w-24" /> 次练习
          </label>
          <Button size="sm" disabled={busy || !studentId} onClick={genPlan}>🎯 生成计划</Button>
          {onOpenGraph && (
            <Button size="sm" variant="secondary" onClick={() => onOpenGraph()}>🗺 打开交互图谱</Button>
          )}
        </div>
        {plan && plan.ok && (
          <>
            <div className="meta">
              共 {plan.stats.total_activities} 次 = 学习 {plan.stats.learn_sessions} + 复习 {plan.stats.review_sessions}，覆盖 {plan.stats.covered_topics} 个主题
            </div>
            <div className="planlist">
              {plan.days.map((d) => (
                <div key={d.day} className="planrow" style={{ alignItems: 'flex-start' }}>
                  <span className="day">Day {d.day}</span>
                  <div className="acts" style={{ flexDirection: 'column', gap: '6px' }}>
                    {d.activities.map((a, i) => (
                      <div key={i} className={'act ' + (a.action === '复习' ? 'review' : a.action === '学习' ? 'learn' : 'goal')} style={{ padding: '8px 12px', fontSize: 13, lineHeight: 1.5 }}>
                        <div style={{ fontWeight: 600, marginBottom: 4 }}>
                          {a.topic_name} · <em>{a.action}</em>
                        </div>
                        {a.learning_goal && <div className="meta" style={{ color: '#047857', marginBottom: 2 }}>🎯 学习目标: {a.learning_goal}</div>}
                        {a.materials && <div className="meta" style={{ marginBottom: 2 }}>📚 教材材料: {a.materials}</div>}
                        {a.exercise && <div className="meta" style={{ marginBottom: 2 }}>✏️ 练习任务: {a.exercise}</div>}
                        {a.review_requirement && <div className="meta" style={{ marginBottom: 2 }}>🔄 复习要求: {a.review_requirement}</div>}
                        <div className="meta" style={{ marginTop: 4, fontStyle: 'italic' }}>{a.reason}</div>
                      </div>
                    ))}
                  </div>
                  <span className="meta" style={{ flexShrink: 0, marginTop: 4 }}>~{d.minutes}min</span>
                </div>
              ))}
            </div>
          </>
        )}
        </Card>
    </Card>
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
    if (m == null) return '#94A3B8';
    if (m < 0.4) return '#F87171';
    if (m < 0.7) return '#FB923C';
    return '#10B981';
  };

  return (
    <svg width={W} height={layout.height} style={{ maxWidth: '100%' }}>
      <defs>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#CBD5E1" />
        </marker>
      </defs>
      {graph.edges.map((e, i) =>
        layout.pos[e.from] && layout.pos[e.to] ? (
          <line key={i} x1={layout.pos[e.from].x} y1={layout.pos[e.from].y}
            x2={layout.pos[e.to].x} y2={layout.pos[e.to].y}
            stroke="#CBD5E1" strokeWidth={1.6} markerEnd="url(#arrow)" />
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
          <text key={'t' + n.id} x={p.x} y={p.y + 36} textAnchor="middle" fontSize={12} fill="#334155" fontWeight={500}>
            {n.name}
          </text>
        );
      })}
    </svg>
  );
}