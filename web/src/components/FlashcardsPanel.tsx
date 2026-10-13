import { useState } from 'react';
import { api, Flashcard } from '../utils/api';
import { Button, Card, Input } from './ui';

interface Props { studentId: string; }

export default function FlashcardsPanel({ studentId }: Props) {
  const [cards, setCards] = useState<Flashcard[]>([]);
  const [flipped, setFlipped] = useState<Set<number>>(new Set());
  const [memorized, setMemorized] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [limit, setLimit] = useState(10);
  const [currentBatch, setCurrentBatch] = useState(0);

  const genCards = async () => {
    if (!studentId) { setErr('请先选择学生'); return; }
    setBusy(true); setErr(''); setFlipped(new Set()); setMemorized(new Set()); setCurrentBatch(0);
    try {
      const res = await api.flashcards(studentId, limit);
      if (res.ok) setCards(res.cards);
      else setErr(res.count === 0 ? '暂无可用卡片' : '生成失败');
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  const toggleCard = (i: number) => {
    setFlipped((prev) => { const s = new Set(prev); s.has(i) ? s.delete(i) : s.add(i); return s; });
  };

  const markMemorized = (i: number) => {
    setMemorized((prev) => { const s = new Set(prev); s.add(i); return s; });
  };

  const nextBatch = () => {
    setCurrentBatch((prev) => prev + 1);
    setFlipped(new Set());
  };

  const prevBatch = () => {
    setCurrentBatch((prev) => Math.max(0, prev - 1));
    setFlipped(new Set());
  };

  const BATCH_SIZE = 5;
  const startIdx = currentBatch * BATCH_SIZE;
  const visibleCards = cards.slice(startIdx, startIdx + BATCH_SIZE);
  const totalBatches = Math.ceil(cards.length / BATCH_SIZE);

  return (
    <div className="space-y-4">
      <Card
        title="闪卡复习"
        subtitle="从薄弱主题中自动挖取关键术语填空题（离线生成，不依赖 LLM）"
        actions={
          <Button disabled={busy || !studentId} onClick={genCards}>生成闪卡</Button>
        }
      >
        <div className="row">
          <label className="flex items-center gap-2 text-sm text-slate-600">数量
            <Input type="number" min={1} max={50} value={limit} onChange={(e) => setLimit(Number(e.target.value))} className="w-24" />
          </label>
        </div>
        {err && <div className="error">{err}</div>}
      </Card>

      {cards.length > 0 && (
        <Card
          title="复习卡片"
          subtitle={`已记忆 ${memorized.size}/${cards.length} · 批次 ${currentBatch + 1}/${totalBatches}`}
        >
          <div className="flashgrid">
            {visibleCards.map((c, i) => {
              const globalIdx = startIdx + i;
              const isFlipped = flipped.has(globalIdx);
              const isMemorized = memorized.has(globalIdx);
              return (
                <div key={c.unit_id + globalIdx}
                  className={'flashcard' + (isFlipped ? ' flipped' : '') + (isMemorized ? ' memorized' : '')}
                  onClick={() => toggleCard(globalIdx)}
                  style={isMemorized ? { opacity: 0.6, borderColor: '#34D399' } : {}}>
                  {isFlipped
                    ? <div className="back">
                        <b>{c.back}</b>
                        <span className="meta">{c.topic_name} · {c.source_label}</span>
                        {!isMemorized && (
                          <button className="mini" onClick={(e) => { e.stopPropagation(); markMemorized(globalIdx); }}>已记住</button>
                        )}
                      </div>
                    : <div className="front">{c.front}</div>}
                </div>
              );
            })}
          </div>
          <div className="row" style={{ marginTop: 8, justifyContent: 'center' }}>
            <Button size="sm" variant="secondary" disabled={currentBatch === 0} onClick={prevBatch}>上一批</Button>
            <Button size="sm" variant="secondary" disabled={currentBatch >= totalBatches - 1} onClick={nextBatch}>下一批</Button>
          </div>
        </Card>
      )}

      {cards.length === 0 && !busy && (
        <Card title="提示">
          <p className="meta">暂无可用卡片（请先摄入资料 / 上传课程）。</p>
        </Card>
      )}
    </div>
  );
}