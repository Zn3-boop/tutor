import { useState } from 'react';
import { api, Source, Topic } from '../utils/api';
import { Button, Card, Input, Select, Textarea } from './ui';

interface Props { sources: Source[]; topics: Topic[]; onRefresh: () => Promise<void>; }

export default function UploadPanel({ sources, topics, onRefresh }: Props) {
  const [title, setTitle] = useState('示例材料');
  const [text, setText] = useState('');
  const [kind, setKind] = useState('text');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const run = async (fn: () => Promise<unknown>, label: string) => {
    setBusy(true); setMsg(`处理中: ${label} ...`);
    try { await fn(); setMsg(`${label} 完成`); await onRefresh(); }
    catch (e) { setMsg(`失败: ${String(e)}`); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <Card
        title="知识库 / 文件上传"
        subtitle="Seed 示例课程或摄入文本材料，供 Quiz、课程图谱、闪卡使用"
        actions={
          <Button disabled={busy} onClick={() => run(() => api.seedDemo(), 'Seed 示例课程')}>
            Seed Demo 课程
          </Button>
        }
      >
        <div className="row">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} className="grow" placeholder="材料标题" aria-label="标题" />
          <Select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="类型">
            <option value="text">text</option>
            <option value="textbook">textbook</option>
            <option value="video">video</option>
          </Select>
        </div>
        <Textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} placeholder="粘贴文本内容..." />
        <div className="row">
          <Button disabled={busy || !text} onClick={() => run(() => api.ingestText(title, text, kind), '文本摄入')}>
            摄入文本
          </Button>
          {msg && <span className={msg.startsWith('失败') ? 'error' : 'msg'}>{msg}</span>}
        </div>
      </Card>

      <Card title={`Source 列表 (${sources.length})`}>
        {sources.length > 0 ? (
          <ul className="space-y-1">
            {sources.map((s) => <li key={s.source_id} className="meta">{s.title}</li>)}
          </ul>
        ) : <p className="meta">暂无 Source，请先 Seed 或上传。</p>}
      </Card>

      <Card title={`Topic 列表 (${topics.length})`}>
        {topics.length > 0 ? (
          <ul className="space-y-1.5">
            {topics.map((t) => (
              <li key={t.topic_id} className="text-sm text-slate-700">
                {t.name}
                {t.concepts?.length ? <span className="meta">（概念: {t.concepts.join(', ')}）</span> : null}
              </li>
            ))}
          </ul>
        ) : <p className="meta">暂无 Topic。</p>}
      </Card>
    </div>
  );
}
