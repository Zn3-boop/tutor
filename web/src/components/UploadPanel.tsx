import { useState } from 'react';
import { api, Source, Topic } from '../utils/api';

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
    <div className="panel">
      <h2>知识库 / 文件上传</h2>
      <div className="row">
        <button disabled={busy} onClick={() => run(() => api.seedDemo(), 'Seed 示例课程')}>Seed Demo 课程</button>
      </div>
      <h3>文本摄入</h3>
      <div className="row">
        <label>标题 <input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
        <label>类型
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="text">text</option>
            <option value="textbook">textbook</option>
            <option value="video">video</option>
          </select>
        </label>
      </div>
      <textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} placeholder="粘贴文本内容..." />
      <button disabled={busy || !text} onClick={() => run(() => api.ingestText(title, text, kind), '文本摄入')}>摄入文本</button>
      {msg && <div className="msg">{msg}</div>}

      <h3>Source 列表 ({sources.length})</h3>
      <ul>{sources.map((s) => <li key={s.source_id}>{s.title}</li>)}</ul>
      <h3>Topic 列表 ({topics.length})</h3>
      <ul>
        {topics.map((t) => (
          <li key={t.topic_id}>
            {t.name} {t.concepts?.length ? `(概念: ${t.concepts.join(', ')})` : ''}
          </li>
        ))}
      </ul>
    </div>
  );
}
