import { useRef, useState } from 'react';
import { api, Source, Topic } from '../utils/api';
import { Button, Card, Input, Select, Textarea } from './ui';

interface Props { sources: Source[]; topics: Topic[]; onRefresh: () => Promise<void> }

const UPLOAD_KINDS: Array<{ value: string; label: string }> = [
  { value: 'auto', label: '自动识别（按文件扩展名）' },
  { value: 'pdf', label: 'pdf 教材/讲义' },
  { value: 'pptx', label: 'ppt 幻灯片' },
  { value: 'docx', label: 'docx 文档' },
  { value: 'video', label: 'video 视频' },
  { value: 'transcript', label: 'transcript 字幕/文字稿' },
  { value: 'image', label: 'image 图片（OCR）' },
  { value: 'text', label: 'text 纯文本' },
];

export default function UploadPanel({ sources, topics, onRefresh }: Props) {
  const [title, setTitle] = useState('示例材料');
  const [text, setText] = useState('');
  const [kind, setKind] = useState('text');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [fileName, setFileName] = useState('');
  const [uploadKind, setUploadKind] = useState('auto');
  const fileRef = useRef<HTMLInputElement>(null);

  const run = async (fn: () => Promise<unknown>, label: string) => {
    setBusy(true); setMsg(`处理中: ${label} ...`);
    try { await fn(); setMsg(`${label} 完成`); await onRefresh(); }
    catch (e) { setMsg(`失败: ${String(e)}`); }
    finally { setBusy(false); }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    await run(() => api.uploadFile(file, uploadKind, title.trim() || file.name), `上传 ${file.name}`);
    e.target.value = '';
  };

  return (
    <div className="space-y-4">
      <Card
        title="知识库 / 文件上传"
        subtitle="上传 pdf/ppt/docx/video/图片/文本，按主题自动分类并保留来源（页码/幻灯片/时间戳），供 Quiz、课程图谱、闪卡与引用回答使用"
        actions={
          <Button disabled={busy} onClick={() => run(() => api.seedDemo(), 'Seed 示例课程')}>
            Seed Demo 课程
          </Button>
        }
      >
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Input value={title} onChange={(e) => setTitle(e.target.value)} className="grow" placeholder="材料标题" aria-label="标题" />
            <Select value={uploadKind} onChange={(e) => setUploadKind(e.target.value)} aria-label="上传类型">
              {UPLOAD_KINDS.map((k) => (
                <option key={k.value} value={k.value}>{k.label}</option>
              ))}
            </Select>
          </div>

          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="flex w-full flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-sm text-slate-500 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 disabled:opacity-50"
            aria-label="选择文件上传"
          >
            <span className="text-lg font-semibold">+ 点击选择文件上传</span>
            <span className="mt-1">支持 pdf / ppt / docx / mp4 / 图片 / 字幕，自动识别并摄入知识库</span>
            <input ref={fileRef} type="file" className="hidden" onChange={handleFileChange} />
          </button>
          {fileName && <p className="meta">已选择: {fileName}</p>}
          {msg && <p className={msg.startsWith('失败') ? 'error' : 'msg'}>{msg}</p>}
        </div>
      </Card>

      <Card
        title="文本摄入"
        subtitle="粘贴文本或字幕（SRT/[HH:MM:SS] 会按时间戳分段），可用于手动录入材料"
      >
        <div className="row">
          <Select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="文本类型">
            <option value="text">text</option>
            <option value="textbook">textbook</option>
            <option value="transcript">transcript 字幕</option>
            <option value="video">video 时间戳文本</option>
          </Select>
        </div>
        <Textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} placeholder="粘贴文本内容..." />
        <div className="row">
          <Button disabled={busy || !text} onClick={() => run(() => api.ingestText(title, text, kind), '文本摄入')}>
            摄入文本
          </Button>
        </div>
      </Card>

      <Card title={`Source 列表 (${sources.length})`}>
        {sources.length > 0 ? (
          <ul className="space-y-1">
            {sources.map((s) => <li key={s.source_id} className="meta">{s.title}{s.kind ? `（${s.kind}）` : ''}</li>)}
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
                {t.prerequisites?.length ? <span className="meta">（先修: {t.prerequisites.join(', ')}）</span> : null}
              </li>
            ))}
          </ul>
        ) : <p className="meta">暂无 Topic。</p>}
      </Card>
    </div>
  );
}
