import { useEffect, useRef, useState } from 'react';
import * as pdfjs from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { api, SourceOpen } from '../utils/api';

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

interface Props { info: SourceOpen | null; onClose: () => void; }

export default function SourceDrawer({ info, onClose }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    let cancelled = false;
    setError('');
    setLoading(false);
    if (!info) return;
    if (!info.ok || info.file_exists === false) {
      setError(info.error || '来源无法定位');
      return;
    }
    if (info.viewer !== 'pdf' || !info.file || !canvasRef.current) return;
    setLoading(true);
    (async () => {
      try {
        const doc = await pdfjs.getDocument(api.fileUrl(info.file!)).promise;
        const page = await doc.getPage(Math.max(1, info.page ?? 1));
        const viewport = page.getViewport({ scale: 1.15 });
        const canvas = canvasRef.current;
        if (!canvas || cancelled) return;
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        await page.render({ canvasContext: canvas.getContext('2d')!, viewport }).promise;
      } catch (e) {
        if (!cancelled) { console.error('source viewer failed', e); setError('引用加载失败，请稍后重试'); }
      } finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [info]);

  useEffect(() => {
    if (info?.viewer !== 'video' || !videoRef.current) return;
    const video = videoRef.current;
    const seek = () => { if (info.seconds != null) video.currentTime = info.seconds; };
    video.addEventListener('loadedmetadata', seek);
    return () => video.removeEventListener('loadedmetadata', seek);
  }, [info]);

  if (!info) return null;
  const videoSrc = info.video_url?.split('#')[0] || '';
  return <aside className="source-drawer" role="dialog" aria-label="引用来源">
    <div className="drawer-head"><b>{info.source_title || '引用来源'}</b><button className="mini" onClick={onClose}>关闭</button></div>
    <div className="meta">{info.origin_label || ''}{info.timestamp ? ` · ${info.timestamp}` : ''}</div>
    {error && <div className="error">{error}</div>}
    {loading && <div className="viewer-loading">正在加载来源…</div>}
    {!error && info.viewer === 'pdf' && <div className="pdf-page"><canvas ref={canvasRef} /></div>}
    {!error && info.viewer === 'slides' && <div className="card">幻灯片第 {info.slide ?? '?'} 页。<br />当前素材为 PPTX，浏览器不直接渲染；可用同源 PDF 版本查看。</div>}
    {!error && info.viewer === 'video' && videoSrc && <video ref={videoRef} className="source-video" controls preload="metadata" src={videoSrc} />}
    {!error && info.viewer === 'video' && info.youtube_url && (
      <a href={info.youtube_url} target="_blank" rel="noopener noreferrer"
         style={{display:'inline-block',marginTop:6,padding:'4px 10px',background:'#c4302b',color:'#fff',borderRadius:4,textDecoration:'none',fontSize:'0.85em'}}>
        ▶ 在 YouTube 打开{info.timestamp ? ` @${info.timestamp}` : ''}
      </a>
    )}
    {!error && info.viewer === 'transcript' && (
      <div className="card">
        文字稿定位：第 {(info.paragraph_index ?? 0) + 1} 段{info.timestamp ? ` · ${info.timestamp}` : ''}
        {info.youtube_url && info.timestamp && (
          <a className="source-youtube-link" href={info.youtube_url} target="_blank" rel="noreferrer noopener">
            ▶ 在 YouTube 打开 @ {info.timestamp}
          </a>
        )}
      </div>
    )}
  </aside>;
}