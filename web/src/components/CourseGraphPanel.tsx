import { useCallback, useEffect, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { api, CourseGraph, GraphNode, Topic } from '../utils/api';
import { Button, Card } from './ui';

interface Props { studentId: string; topics: Topic[]; }

const NODE_R = 8;

export default function CourseGraphPanel({ studentId }: Props) {
  const [graph, setGraph] = useState<CourseGraph | null>(null);
  const [hoverNode, setHoverNode] = useState<GraphNode | null>(null);
  const [err, setErr] = useState('');
  const [frozenNodes, setFrozenNodes] = useState<Set<string>>(new Set());
  const fgRef = useRef<any>();

  const loadGraph = useCallback(async () => {
    try {
      setGraph(await api.graph(studentId));
      setErr('');
    } catch (e) { setErr(String(e)); }
  }, [studentId]);

  useEffect(() => { loadGraph(); }, [loadGraph]);

  const masteryColor = (m?: number | null) => {
    if (m == null) return '#94A3B8';
    if (m < 0.4) return '#F87171';
    if (m < 0.7) return '#FB923C';
    return '#10B981';
  };

  const masteryLabel = (m?: number | null) => {
    if (m == null) return '未学习';
    if (m < 0.4) return '薄弱';
    if (m < 0.7) return '学习中';
    return '已掌握';
  };

  const graphData = graph ? {
    nodes: graph.nodes.map((n) => ({ ...n, id: n.id, val: 1 })),
    links: graph.edges.map((e) => ({ ...e, source: e.from, target: e.to })),
  } : { nodes: [], links: [] };

  const prerequisites = graph
    ? graph.edges
        .filter((e) => e.to && e.from)
        .reduce<Record<string, string[]>>((acc, e) => {
          (acc[e.to] = acc[e.to] || []).push(e.from);
          return acc;
        }, {})
    : {};

  const dependents = graph
    ? graph.edges
        .filter((e) => e.to && e.from)
        .reduce<Record<string, string[]>>((acc, e) => {
          (acc[e.from] = acc[e.from] || []).push(e.to);
          return acc;
        }, {})
    : {};

  const nodeById = graph
    ? graph.nodes.reduce<Record<string, GraphNode>>((acc, n) => { acc[n.id] = n; return acc; }, {})
    : {};

  const handleDragEnd = (node: any) => {
    if (node?.id) {
      setFrozenNodes((prev) => new Set(prev).add(node.id));
    }
  };

  const handleDoubleClick = () => {
    setFrozenNodes(new Set());
    if (fgRef.current) {
      fgRef.current.d3ReheatSimulation();
    }
  };

  // ---- custom canvas painters: permanent node + edge annotations ----------
  const paintNode = (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const r = NODE_R * Math.max(node.val ?? 1, 1);
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = node.color || masteryColor(node.mastery);
    ctx.fill();
    ctx.lineWidth = 1.6;
    ctx.strokeStyle = '#ffffff';
    ctx.stroke();
    const label = node.name || node.id || '';
    const fs = 12 / globalScale;
    ctx.font = `${fs}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = 'rgba(30,41,59,0.92)';
    ctx.fillText(label, node.x, node.y + r + 3);
  };

  const paintLink = (link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const src = link.source, dst = link.target;
    if (!src || !dst) return;
    const dx = dst.x - src.x, dy = dst.y - src.y;
    const len = Math.hypot(dx, dy) || 1;
    const ux = dx / len, uy = dy / len;
    const r = NODE_R;
    const sx = src.x + ux * r, sy = src.y + uy * r;
    const ex = dst.x - ux * r, ey = dst.y - uy * r;
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(ex, ey);
    ctx.strokeStyle = 'rgba(100,116,139,0.5)';
    ctx.lineWidth = 1.2;
    ctx.stroke();
    // arrowhead at target
    const ang = Math.atan2(dy, dx);
    const ah = 6;
    ctx.beginPath();
    ctx.moveTo(ex, ey);
    ctx.lineTo(ex - Math.cos(ang - 0.45) * ah, ey - Math.sin(ang - 0.45) * ah);
    ctx.lineTo(ex - Math.cos(ang + 0.45) * ah, ey - Math.sin(ang + 0.45) * ah);
    ctx.closePath();
    ctx.fillStyle = 'rgba(100,116,139,0.65)';
    ctx.fill();
    // edge annotation: 「先修」
    const mx = (sx + ex) / 2, my = (sy + ey) / 2;
    const fs = 10 / globalScale;
    ctx.font = `${fs}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    ctx.fillStyle = 'rgba(71,85,105,0.85)';
    ctx.fillText(link.label || '先修', mx, my - 2);
  };

  return (
    <Card title="课程知识图谱">
      {err && <div className="error">{err}</div>}
      <div className="row" style={{ gap: 12, alignItems: 'center' }}>
        <Button size="sm" variant="secondary" onClick={loadGraph}>🔄 刷新图谱</Button>
        <span className="meta">
          <span style={{ color: '#F87171' }}>● 薄弱</span>{' '}
          <span style={{ color: '#FB923C' }}>● 学习中</span>{' '}
          <span style={{ color: '#10B981' }}>● 已掌握</span>{' '}
          <span style={{ color: '#94A3B8' }}>● 未学习</span>
        </span>
        {frozenNodes.size > 0 && (
          <Button size="sm" variant="secondary" onClick={handleDoubleClick} className="!border-slate-500 !bg-slate-500 !text-white hover:!bg-slate-600">重置布局</Button>
        )}
      </div>
      {graph && graph.nodes.length > 0 ? (
        <div style={{ border: '1px solid #E2E8F0', borderRadius: 8, overflow: 'hidden', marginTop: 8 }}
          onDoubleClick={handleDoubleClick}>
          <ForceGraph2D
            ref={fgRef}
            graphData={graphData}
            nodeLabel={(node: any) => {
              const n = nodeById[node?.id];
              const label = n?.annotation || node?.name || node?.id || '';
              return label.length > 90 ? `${label.slice(0, 90)}…` : label;
            }}
            linkLabel={(link: any) => {
              const src = typeof link.source === 'object' ? link.source?.id : link.source;
              const dst = typeof link.target === 'object' ? link.target?.id : link.target;
              const a = link.annotation || `「${nodeById[src]?.name || src}」先于「${nodeById[dst]?.name || dst}」学习`;
              return a.length > 110 ? `${a.slice(0, 110)}…` : a;
            }}
            nodeColor={(node: any) => masteryColor(node.mastery)}
            nodeVal={1}
            nodeRelSize={NODE_R}
            nodeCanvasObject={paintNode}
            nodeCanvasObjectMode={() => 'replace'}
            linkColor={() => 'rgba(100,116,139,0.5)'}
            linkWidth={1.2}
            linkCanvasObject={paintLink}
            linkCanvasObjectMode={() => 'replace'}
            onNodeHover={(node: any) => setHoverNode(node ? graph.nodes.find((n) => n.id === node.id) || null : null)}
            onNodeDragEnd={handleDragEnd}
            onNodeClick={(node: any) => {
              if (node?.id) {
                setFrozenNodes((prev) => new Set(prev).add(node.id));
              }
            }}
            width={860}
            height={460}
            cooldownTicks={100}
          />
        </div>
      ) : (
        <div className="meta" style={{ marginTop: 8 }}>暂无课程图谱数据（请先摄入课程资料）。</div>
      )}
      {hoverNode && (
        <div className="card" style={{ marginTop: 8, animation: 'fadeIn 0.2s ease' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <b style={{ fontSize: 15 }}>{hoverNode.name}</b>
            {hoverNode.mastery != null && (
              <span style={{ color: masteryColor(hoverNode.mastery), fontWeight: 600 }}>
                {masteryLabel(hoverNode.mastery)} ({(hoverNode.mastery * 100).toFixed(0)}%)
              </span>
            )}
          </div>
          {hoverNode.concepts && hoverNode.concepts.length > 0 && (
            <div className="meta" style={{ marginTop: 4 }}>概念: {hoverNode.concepts.join(', ')}</div>
          )}
          {hoverNode.annotation && (
            <div style={{ marginTop: 6, padding: '6px 8px', background: '#F1F5F9', borderRadius: 6, fontSize: 12, color: '#334155', lineHeight: 1.5 }}>
              📌 {hoverNode.annotation}
            </div>
          )}
          {(hoverNode.unit_count != null || (hoverNode.source_titles && hoverNode.source_titles.length > 0)) && (
            <div style={{ marginTop: 4, fontSize: 12, color: '#6b7280' }}>
              {hoverNode.unit_count != null && <span>内容单元: {hoverNode.unit_count}</span>}
              {hoverNode.source_titles && hoverNode.source_titles.length > 0 && (
                <span> | 来源: {hoverNode.source_titles.join('、')}</span>
              )}
            </div>
          )}
          {prerequisites[hoverNode.id]?.length > 0 && (
            <div style={{ marginTop: 6, fontSize: 12 }}>
              <span style={{ color: '#6b7280' }}>前置知识：</span>
              {prerequisites[hoverNode.id].map((pid) => {
                const pn = nodeById[pid];
                return pn ? (
                  <span key={pid} style={{
                    display: 'inline-block',
                    padding: '1px 6px',
                    margin: '0 4px 2px 0',
                    background: pn.mastery != null && pn.mastery >= 0.7 ? '#dcfce7' : '#fee2e2',
                    borderRadius: 10,
                    fontSize: 11,
                  }}>
                    {pn.name} {pn.mastery != null ? `(${(pn.mastery * 100).toFixed(0)}%)` : ''}
                  </span>
                ) : null;
              })}
            </div>
          )}
          {dependents[hoverNode.id]?.length > 0 && (
            <div style={{ marginTop: 4, fontSize: 12 }}>
              <span style={{ color: '#6b7280' }}>后续依赖：</span>
              {dependents[hoverNode.id].slice(0, 5).map((did) => {
                const dn = nodeById[did];
                return dn ? (
                  <span key={did} style={{
                    display: 'inline-block',
                    padding: '1px 6px',
                    margin: '0 4px 2px 0',
                    background: '#F1F5F9',
                    borderRadius: 10,
                    fontSize: 11,
                  }}>
                    {dn.name}
                  </span>
                ) : null;
              })}
              {dependents[hoverNode.id].length > 5 && <span className="meta"> +{dependents[hoverNode.id].length - 5} 更多</span>}
            </div>
          )}
          {hoverNode.mastery != null && hoverNode.mastery < 0.7 && (
            <div style={{ marginTop: 6, padding: '4px 8px', background: '#FFF7ED', borderRadius: 4, fontSize: 12, color: '#9A3412' }}>
              💡 建议优先学习此主题（掌握度低于 70%）
              {prerequisites[hoverNode.id]?.some((pid) => nodeById[pid]?.mastery != null && nodeById[pid].mastery! < 0.4) && (
                <span style={{ display: 'block', marginTop: 2 }}>⚠️ 部分前置知识尚未掌握，建议先补基础</span>
              )}
            </div>
          )}
        </div>
      )}
      {graph && (
        <div className="card" style={{ marginTop: 8 }}>
          <h4 style={{ marginBottom: 6 }}>📚 课程内容标注</h4>
          {graph.meta?.course_titles && graph.meta.course_titles.length > 0 ? (
            <div className="meta" style={{ marginBottom: 6 }}>
              本图谱覆盖课程/教材：<b>{graph.meta.course_titles.join('、')}</b>
            </div>
          ) : null}
          {graph.meta?.legend && (
            <div style={{ fontSize: 12, color: '#6b7280', lineHeight: 1.7 }}>
              {Object.values(graph.meta.legend).map((l) => (
                <div key={l}>• {l}</div>
              ))}
            </div>
          )}
          {graph.edges.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>先修关系标注</div>
              <table style={{ width: '100%', fontSize: 12 }}>
                <tbody>
                  {graph.edges.map((e, idx) => {
                    const sn = nodeById[e.from];
                    const dn = nodeById[e.to];
                    return (
                      <tr key={`${e.from}->${e.to}-${idx}`}>
                        <td style={{ padding: '3px 6px', whiteSpace: 'nowrap', color: '#6b7280' }}>
                          {sn?.name || e.from} <span style={{ color: '#9aa3b2' }}>→</span> {dn?.name || e.to}
                        </td>
                        <td style={{ padding: '3px 6px', color: '#374151' }}>
                          {e.annotation || `「${sn?.name || e.from}」是「${dn?.name || e.to}」的前置知识`}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}