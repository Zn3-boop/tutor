import { useState, useRef, useCallback } from 'react';
import { ChatResponse } from '../utils/api';
import { Button, Card, Tag } from './ui';

export default function ImageQueryPanel({ studentId }: { studentId: string }) {
  const [preview, setPreview] = useState<string | null>(null);
  const [base64, setBase64] = useState('');
  const [res, setRes] = useState<ChatResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((file: File) => {
    if (!file.type.startsWith('image/')) {
      setErr('请选择图片文件');
      return;
    }
    setErr('');
    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target?.result as string;
      setPreview(dataUrl);
      setBase64(dataUrl.split(',')[1] || '');
    };
    reader.readAsDataURL(file);
  }, []);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const onPaste = useCallback((e: React.ClipboardEvent) => {
    const items = e.clipboardData.items;
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) handleFile(file);
        return;
      }
    }
  }, [handleFile]);

  const send = async () => {
    if (!base64) { setErr('请先选择或粘贴图片'); return; }
    setBusy(true); setErr(''); setRes(null);
    try {
      const resp = await fetch('/tutor/chat/image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image: base64,
          student_id: studentId || '',
          llm: true,
          top_k: 5,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setRes(await resp.json());
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  const clear = () => { setPreview(null); setBase64(''); setRes(null); setErr(''); };

  return (
    <div className="space-y-4" onPaste={onPaste}>
      <Card
        title="📷 图片提问"
        subtitle="上传题目图片，VLM 自动解析后回答。支持拖拽、粘贴、点击选择。"
      >
        {err && <div className="error">{err}</div>}

        <div
          className={`image-drop-zone${dragOver ? ' drag-over' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
          style={{
            border: `2px dashed ${dragOver ? '#34D399' : '#E2E8F0'}`,
            borderRadius: 12,
            padding: preview ? 8 : 32,
            textAlign: 'center',
            cursor: 'pointer',
            marginBottom: 8,
            background: dragOver ? '#ECFDF5' : '#F8FAFC',
            transition: 'all 0.2s ease',
          }}
        >
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
          />
          {preview ? (
            <img src={preview} alt="preview" style={{ maxWidth: '100%', maxHeight: 320, borderRadius: 8 }} />
          ) : (
            <div style={{ color: '#64748B' }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>📷</div>
              <div>拖拽图片到此处 / 点击选择 / Ctrl+V 粘贴</div>
            </div>
          )}
        </div>

        <div className="row">
          <Button disabled={busy || !base64} onClick={send}>
            {busy ? '⏳ 解析中...' : '🔍 解析并提问'}
          </Button>
          {preview && <Button variant="secondary" onClick={clear}>清除</Button>}
        </div>
      </Card>

      {res && (
        <Card title="识别与回答">
          {res.vlm_parse && (
            <details style={{ marginBottom: 8 }}>
              <summary className="meta">VLM 解析结果（{res.vlm_parse.elapsed_ms?.toFixed(0) ?? '?'}ms）</summary>
              <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap', background: '#F1F5F9', padding: 8, borderRadius: 8 }}>
                {res.vlm_parse.text}
              </pre>
            </details>
          )}
          <div className="status" style={{ marginBottom: 8 }}>
            {res.status === 'answered' ? (
              <Tag tone="success">✅ 已回答</Tag>
            ) : (
              <Tag tone="danger">❌ {res.refuse_reason || '已拒答'}</Tag>
            )}
          </div>
          {res.answer && (
            <div style={{ padding: '10px 14px', background: '#ECFDF5', borderRadius: 12, border: '1px solid #A7F3D0', lineHeight: 1.6, fontSize: 14 }}>
              {res.answer}
            </div>
          )}
          {res.citations && res.citations.length > 0 && (
            <details open style={{ marginTop: 8 }}>
              <summary>📚 引用来源 ({res.citations.length})</summary>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
                {res.citations.map((c: any) => (
                  <span key={c.chunk_id} className="meta" style={{ padding: '4px 8px', background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 8, fontSize: 12 }}>
                    [{c.index}] {c.label}
                  </span>
                ))}
              </div>
            </details>
          )}
        </Card>
      )}
    </div>
  );
}