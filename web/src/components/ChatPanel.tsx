import { useState, useEffect, useRef } from 'react';
import { api, ChatResponse, SourceOpen, ReportResponse } from '../utils/api';
import SourceDrawer from './SourceDrawer';
import { Button, Card, cn, Input, Tag } from './ui';

type OpenState = Record<string, SourceOpen | 'loading' | 'error'>;

function MasteryBar({ mastery, label }: { mastery: number; label: string }) {
  const pct = Math.max(0, Math.min(1, mastery)) * 100;
  const color = mastery >= 0.7 ? 'var(--color-master)' : mastery >= 0.4 ? 'var(--color-learning)' : 'var(--color-weak)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, marginBottom: 2 }}>
      <span style={{ width: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#64748B' }}>{label}</span>
      <div style={{ flex: 1, height: 8, background: '#E2E8F0', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 4, transition: 'width 0.6s ease' }} />
      </div>
      <span style={{ width: 36, textAlign: 'right', color, fontWeight: 600 }}>{(mastery * 100).toFixed(0)}%</span>
    </div>
  );
}

function TypewriterText({ text, speed = 18 }: { text: string; speed?: number }) {
  const [displayed, setDisplayed] = useState('');
  const [done, setDone] = useState(false);
  const indexRef = useRef(0);

  useEffect(() => {
    setDisplayed('');
    setDone(false);
    indexRef.current = 0;
    if (!text) { setDone(true); return; }
    const timer = setInterval(() => {
      indexRef.current += 1;
      if (indexRef.current >= text.length) {
        setDisplayed(text);
        setDone(true);
        clearInterval(timer);
      } else {
        setDisplayed(text.slice(0, indexRef.current));
      }
    }, speed);
    return () => clearInterval(timer);
  }, [text, speed]);

  return (
    <span>
      {displayed.split('\n').map((line, i) => (
        <span key={i}>
          {line}
          {i < displayed.split('\n').length - 1 && <br />}
        </span>
      ))}
      {!done && <span className="typewriter-cursor">▌</span>}
    </span>
  );
}

export default function ChatPanel({ studentId }: { studentId: string }) {
  const [query, setQuery] = useState('');
  const [llm, setLlm] = useState(true);
  const [res, setRes] = useState<ChatResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [open, setOpen] = useState<OpenState>({});
  const [current, setCurrent] = useState<SourceOpen | null>(null);
  const [masteryMap, setMasteryMap] = useState<Record<string, { name: string; mastery: number }> | null>(null);
  const [showMastery, setShowMastery] = useState(false);

  // ---- TTS 朗读（服务端已返回 tts_url，点击播放/暂停）----
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [ttsPlaying, setTtsPlaying] = useState(false);

  const stopTts = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
      audioRef.current = null;
    }
    setTtsPlaying(false);
  };

  const toggleTts = () => {
    const url = res?.tts_url;
    if (!url) return;
    const existing = audioRef.current;
    if (existing) {
      if (ttsPlaying) {
        existing.pause();
        setTtsPlaying(false);
        return;
      }
      existing.currentTime = 0;
      void existing.play().catch(() => setTtsPlaying(false));
      setTtsPlaying(true);
      return;
    }
    const a = new Audio(url);
    a.onended = () => setTtsPlaying(false);
    audioRef.current = a;
    setTtsPlaying(true);
    void a.play().catch(() => {
      if (audioRef.current === a) audioRef.current = null;
      setTtsPlaying(false);
    });
  };
  // 组件卸载时静音，避免切换面板后仍在播放
  useEffect(() => () => { audioRef.current?.pause(); }, []);

  useEffect(() => {
    if (!studentId) { setMasteryMap(null); return; }
    const fetchMastery = async () => {
      try {
        const traj = await api.masteryTrajectory(studentId);
        void traj;
      } catch { /* ignore */ }
    };
    void fetchMastery();
  }, [studentId]);

  const loadMastery = async () => {
    if (!studentId) return;
    try {
      const reportRes = await fetch(`/tutor/report/${studentId}`);
      if (!reportRes.ok) return;
      const data: ReportResponse = await reportRes.json();
      if (data.mastery_by_topic) {
        setMasteryMap(data.mastery_by_topic);
        setShowMastery(true);
      }
    } catch { /* ignore */ }
  };

  const send = async () => {
    if (!query.trim()) return;
    stopTts();
    setBusy(true); setErr(''); setOpen({}); setCurrent(null);
    try {
      setRes(await api.chat(query.trim(), llm, studentId || undefined));
    } catch (e) { setErr(String(e)); setRes(null); }
    finally { setBusy(false); }
  };

  const handleOpen = async (chunkId: string) => {
    setOpen((prev) => ({ ...prev, [chunkId]: 'loading' }));
    try {
      const info = await api.openSource(chunkId);
      setOpen((prev) => ({ ...prev, [chunkId]: info }));
      setCurrent(info);
    } catch (e) {
      setOpen((prev) => ({ ...prev, [chunkId]: 'error' }));
      console.error('open source failed', e);
    }
  };

  const reset = () => { setOpen({}); setCurrent(null); };

  const overallMastery = masteryMap
    ? Object.values(masteryMap).reduce((s, v) => s + v.mastery, 0) / Math.max(Object.keys(masteryMap).length, 1)
    : null;

  return (
    <Card
      title="Tutor 聊天"
      actions={
        studentId && (
          <Button size="sm" variant="secondary" onClick={loadMastery}>📊 掌握度</Button>
        )
      }
    >
      {showMastery && masteryMap && (
        <div className="mb-2 rounded-card border border-brand-200 bg-brand-50 p-3">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-xs font-semibold text-brand-700">📈 能力提升进度</span>
            {overallMastery !== null && (
              <span
                className="text-[11px] font-semibold"
                style={{ color: overallMastery >= 0.7 ? 'var(--color-master)' : overallMastery >= 0.4 ? 'var(--color-learning)' : 'var(--color-weak)' }}
              >
                总体 {(overallMastery * 100).toFixed(0)}%
              </span>
            )}
            <Button size="sm" variant="ghost" onClick={() => setShowMastery(false)}>✕</Button>
          </div>
          {Object.entries(masteryMap)
            .sort(([, a], [, b]) => a.mastery - b.mastery)
            .map(([tid, v]) => (
              <MasteryBar key={tid} mastery={v.mastery} label={v.name} />
            ))}
        </div>
      )}
      <div className="row">
        <Input
          className="grow"
          value={query}
          placeholder="问课程内容相关问题..."
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
        />
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input type="checkbox" checked={llm} onChange={(e) => setLlm(e.target.checked)} /> LLM
        </label>
        <Button disabled={busy || !query.trim()} loading={busy} onClick={send}>发送</Button>
      </div>
      {err && <div className="error">{err}</div>}

{res && (
        <div className="mt-1 space-y-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {res.status === 'answered' ? (
              <Tag tone="success">✅ 已回答</Tag>
            ) : (
              <Tag tone="danger">❌ 已拒答</Tag>
            )}
            {res.used_offline_template && <Tag tone="neutral">离线模板</Tag>}
            {res.off_material && <Tag tone="warn">🚫 超纲查询</Tag>}
            {res.detected_language === 'zh' && res.is_mixed_language && (
              <Tag tone="info">🌐 中英混合</Tag>
            )}
          </div>
          {res.refuse_reason && (
            <div
              className={res.off_material ? 'rounded-field border border-warn-300 bg-warn-50 px-3 py-2 text-sm text-warn-800' : 'error'}
            >
              {res.off_material ? '⚠️ ' : ''}{res.refuse_reason}
            </div>
          )}
          {/* P0-3: 区分四种拒答/空结果情况 */}
          {res.status === 'refused' && !res.refuse_reason && (() => {
            const rt = res.refuse_type;
            if (rt === 'service_error')
              return <div className="rounded-field bg-danger-50 px-3 py-2 text-[13px] font-medium text-danger-800">⚠️ 服务暂时不可用，请稍后重试</div>;
            if (rt === 'out_of_scope')
              return <div className="rounded-field bg-warn-50 px-3 py-2 text-[13px] font-medium text-warn-800">📚 该问题不在当前课程知识范围内</div>;
            if (rt === 'gate_blocked')
              return <div className="rounded-field bg-danger-50 px-3 py-2 text-[13px] font-medium text-danger-800">🚫 问题不符合安全规范，无法回答</div>;
            if (rt === 'rag_empty')
              return <div className="rounded-field bg-info-100 px-3 py-2 text-[13px] font-medium text-info-700">💡 当前知识库未检索到相关学习资料，将直接使用 LLM 回答</div>;
            return null;
          })()}
          {/* 后端返回 rag_empty 但 answer 不为空时，提示走了 LLM */}
          {res.status === 'refused' && res.refuse_type === 'rag_empty' && res.answer && (
            <div className="mb-2 rounded-field bg-info-100 px-3 py-2 text-[13px] font-medium text-info-700">
              💡 当前知识库未检索到相关学习资料，以下为 LLM 直接回答（未引用课程资料）
            </div>
          )}
          {res.answer && (
            <div className="rounded-field border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm leading-relaxed">
              <TypewriterText text={res.answer} />
            </div>
          )}
          {/* P1-T9: 拒答/超纲标签移到气泡内部 */}
          {res.status === 'refused' && (
            <div
              className={cn(
                'rounded-field px-3 py-2 text-[13px]',
                res.off_material
                  ? 'border border-warn-300 bg-warn-50 text-warn-800'
                  : 'border border-danger-200 bg-danger-50 text-danger-800'
              )}
            >
              {res.off_material ? '🚫 超纲查询' : '❌ 已拒答'}
              {res.refuse_reason && <span className="ml-2">{res.refuse_reason}</span>}
            </div>
          )}
          {res.status === 'answered' && res.answer && res.tts_url && (
            <Button size="sm" variant="secondary" onClick={toggleTts} className="mt-1.5">
              {ttsPlaying ? '⏸ 暂停' : '🔊 朗读回答'}
            </Button>
          )}
{res.citations && res.citations.length > 0 && (
            <details open>
              <summary>📚 引用来源 ({res.citations.length})</summary>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
                {res.citations.map((c) => {
                  const st = open[c.chunk_id];
                  const info = st && st !== 'loading' && st !== 'error' ? st : null;
                  const viewerIcon = info?.viewer === 'pdf' ? '📄' : info?.viewer === 'slides' ? '📊' : info?.viewer === 'video' ? '🎬' : info?.viewer === 'transcript' ? '📝' : '📎';
                  return (
                    <div key={c.chunk_id} className="rounded-field border border-slate-200 bg-canvas px-2.5 py-1.5 text-xs" style={{ minWidth: 140 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 2 }}>
                        <span>{viewerIcon}</span>
                        <b className="text-slate-700">[{c.index}]</b>
                        <span className="text-slate-500">{c.label}</span>
                      </div>
                      {info && info.viewer && (
                        <div className="text-[10px] text-slate-400">
                          {info.viewer === 'pdf' && info.page != null && `PDF 第${info.page}页/${info.total_pages ?? '?'}页`}
                          {info.viewer === 'slides' && info.slide != null && `幻灯片 第${info.slide}张/${info.total_slides ?? '?'}张`}
                          {info.viewer === 'video' && `视频 @${info.timestamp || (info.seconds ? info.seconds + 's' : '')}`}
                          {info.viewer === 'transcript' && '文字稿'}
                        </div>
                      )}
                      <div className="mt-1 flex gap-1">
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={st === 'loading'}
                          onClick={() => handleOpen(c.chunk_id)}
                          className="!px-1.5 !py-0.5 text-[10px]"
                        >
                          {st === 'loading' ? '⏳' : '🔍 打开'}
                        </Button>
                        {info && (
                          <a className="mini-link" href="#" onClick={(e) => { e.preventDefault(); setCurrent(info); }}>👁 查看</a>
                        )}
                      </div>
                      {st === 'error' && <div className="text-[10px] text-danger-500">⚠ 无法解析</div>}
                    </div>
                  );
                })}
              </div>
            </details>
          )}
          {res.retrieval_meta && (
            <div className="meta">vector={res.retrieval_meta.vector_count} · bm25={res.retrieval_meta.bm25_count}</div>
          )}
        </div>
      )}
      {current && <SourceDrawer info={current} onClose={reset} />}
    </Card>
  );
}
