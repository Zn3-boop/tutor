import { useState } from 'react';
import { api, ChatResponse, SourceOpen } from '../utils/api';

type OpenState = Record<string, SourceOpen | 'loading' | 'error'>;

export default function ChatPanel({ studentId }: { studentId: string }) {
  const [query, setQuery] = useState('');
  const [llm, setLlm] = useState(true);
  const [res, setRes] = useState<ChatResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [open, setOpen] = useState<OpenState>({});

  const send = async () => {
    if (!query.trim()) return;
    setBusy(true); setErr(''); setOpen({});
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
    } catch (e) {
      setOpen((prev) => ({ ...prev, [chunkId]: 'error' }));
      console.error('open source failed', e);
    }
  };

  const targetUrl = (info: SourceOpen): string => {
    if (info.open_url) return info.open_url;
    if (info.video_url) return info.video_url;
    if (info.youtube_url) return info.youtube_url;
    return '';
  };

  return (
    <div className="panel">
      <h2>Tutor 聊天</h2>
      <div className="row">
        <input className="grow" value={query} placeholder="问课程内容相关问题..." onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') send(); }} />
        <label><input type="checkbox" checked={llm} onChange={(e) => setLlm(e.target.checked)} /> LLM</label>
        <button disabled={busy || !query.trim()} onClick={send}>发送</button>
      </div>
      {err && <div className="error">{err}</div>}
      {res && (
        <div className="card">
          <div className="status">状态: <b>{res.status}</b>{res.used_offline_template ? ' (离线模板)' : ''}</div>
          {res.refuse_reason && <div className="error">{res.refuse_reason}</div>}
          {res.answer && <p className="answer">{res.answer}</p>}
          {res.citations && res.citations.length > 0 && (
            <details open>
              <summary>引用 ({res.citations.length})</summary>
              {res.citations.map((c) => {
                const st = open[c.chunk_id];
                const info = st && st !== 'loading' && st !== 'error' ? st : null;
                const url = info ? targetUrl(info) : '';
                return (
                  <div key={c.chunk_id} className="cite">
                    <div className="cite-row">
                      <b>[{c.index}] {c.label}</b>
                      <button
                        className="mini"
                        disabled={st === 'loading'}
                        onClick={() => handleOpen(c.chunk_id)}
                      >
                        {st === 'loading' ? '解析中…' : '打开'}
                      </button>
                      {info && url && (
                        <a className="mini-link" href={url} target="_blank" rel="noreferrer">新窗口</a>
                      )}
                    </div>
                    {info && info.viewer && (
                      <div className="meta">
                        {info.viewer === 'pdf' && info.page != null && `PDF · 第 ${info.page} 页 / 共 ${info.total_pages ?? '?'} 页`}
                        {info.viewer === 'slides' && info.slide != null && `幻灯片 · 第 ${info.slide} 张 / 共 ${info.total_slides ?? '?'} 张`}
                        {info.viewer === 'video' && `视频 · ${info.timestamp || info.seconds ? `@${info.timestamp || info.seconds + 's'}` : ''}`}
                        {info.viewer === 'transcript' && '文字稿'}
                      </div>
                    )}
                    {st === 'error' && <div className="meta">无法解析该引用</div>}
                  </div>
                );
              })}
            </details>
          )}
          {res.retrieval_meta && (
            <div className="meta">vector={res.retrieval_meta.vector_count} · bm25={res.retrieval_meta.bm25_count}</div>
          )}
        </div>
      )}
    </div>
  );
}
