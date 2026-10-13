import { useState } from 'react';
import { api, ReportResponse, SimulateResponse, FullEvalResponse } from '../utils/api';
import { Button, Card } from './ui';

interface Props { studentId: string; assessmentId: string; }

// Dependency-free inline SVG sparkline for the learner-mastery curve (20% weight).
function Sparkline({ points, width = 190, height = 40 }: { points: number[]; width?: number; height?: number }) {
  const vals = (points ?? []).filter((n) => typeof n === 'number');
  if (vals.length < 2) return <span style={{ color: '#888' }}>—</span>;
  const min = Math.min(...vals, 0);
  const max = Math.max(...vals, 1);
  const range = max - min || 1;
  const step = width / (vals.length - 1);
  const pts = vals.map((p, i) => `${(i * step).toFixed(1)},${(height - ((p - min) / range) * height).toFixed(1)}`).join(' ');
  return (
    <svg width={width} height={height} className="spark">
      <polyline fill="none" stroke="#10B981" strokeWidth={2} points={pts} />
      <circle
        cx={width}
        cy={height - ((vals[vals.length - 1] - min) / range) * height}
        r={2.6} fill="#34D399"
      />
    </svg>
  );
}

export default function ReportPanel({ studentId, assessmentId }: Props) {
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [traj, setTraj] = useState<number[]>([]);
  const [sim, setSim] = useState<SimulateResponse | null>(null);
  const [full, setFull] = useState<FullEvalResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [err, setErr] = useState('');

  const loadReport = async () => {
    if (!studentId || !assessmentId) { setErr('请先在 Quiz 面板生成测验(得到 assessment_id)'); return; }
    setBusy(true); setErr('');
    try {
      const [r, t] = await Promise.all([
        api.report(studentId, assessmentId),
        api.masteryTrajectory(studentId).then((x) => x.trajectory.map((p) => p.mastery)).catch(() => []),
      ]);
      setReport(r); setTraj(t);
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  const runSim = async () => {
    setBusy(true); setErr('');
    try { setSim(await api.simulate(4, 5, 42)); } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  const runFull = async () => {
    setBusy(true); setErr(''); setFull(null);
    try {
      const { task_id } = await api.fullEval(4, 5, 42, false);
      // 轮询任务状态直至完成
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const st = await api.evalStatus(task_id);
        if (st.status === 'done') { if (st.result) setFull(st.result); break; }
        if (st.status === 'error' || st.error) throw new Error(st.error || '评估失败');
      }
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  const diagnoseMisconceptions = async () => {
    if (!studentId || !report) { setErr('请先选择学生并加载报告'); return; }
    setBusy(true); setErr('');
    try {
      const mcon = await api.misconceptions(studentId);
      setReport((prev) => prev ? {
        ...prev,
        misconceptions: (prev.misconceptions ?? [])
          .map((m) => ({ ...m, misconception: mcon[m.topic_id]?.label ?? m.misconception })),
      } : prev);
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  const speakSummary = async () => {
    const miss = report?.misconceptions ?? [];
    const text =
      `本次评估总体掌握度为 ${((report?.overall_mastery ?? 0) * 100).toFixed(0)}%。` +
      (report?.weak_topics?.length ? `薄弱主题：${report.weak_topics.map((w) => w.name).join('、')}。` : '') +
      (miss.length ? `主要误解：${miss.map((m) => (m.misconception ?? '').trim() || `在${m.name}上重复出错`).join('；')}。` : '');
    setSpeaking(true); setErr('');
    try {
      const blob = await api.tts(text);
      const url = URL.createObjectURL(blob);
      const audioEl = document.getElementById('tts-audio') as HTMLAudioElement | null;
      if (audioEl) { audioEl.src = url; void audioEl.play(); }
    } catch (e) { setErr(String(e)); }
    finally { setSpeaking(false); }
  };

  return (
    <Card title="测评报告">
      <audio id="tts-audio" style={{ display: 'none' }} />
      <div className="row">
        <Button size="sm" variant="secondary" disabled={busy || !studentId || !assessmentId} onClick={loadReport}>加载报告 (assessment: {assessmentId || '—'})</Button>
        <Button size="sm" variant="secondary" disabled={busy || !report} onClick={diagnoseMisconceptions}>🧠 误解诊断 (LLM)</Button>
        <Button size="sm" variant="secondary" disabled={busy || !report || speaking} onClick={speakSummary}>{speaking ? '朗读中…' : '🔊 朗读总结'}</Button>
        <Button size="sm" variant="secondary" disabled={busy} onClick={runSim}>模拟学生评估</Button>
        <Button size="sm" variant="secondary" disabled={busy} onClick={runFull}>Day6 全流水线评估</Button>
      </div>
      {err && <div className="error">{err}</div>}

      {report && (
        <Card title="学习报告">
          <div className="meta">Assessment: {report.assessment_id}</div>
          <div>总体掌握度: <b>{report.overall_mastery?.toFixed(3)}</b></div>
          {traj.length >= 2 && (
            <div>
              <h4>掌握度随作答变化曲线</h4>
              <Sparkline points={traj} />
              <div className="meta">第 {traj.length} 次作答 → 平均掌握度 {traj[traj.length - 1].toFixed(3)}</div>
            </div>
          )}
          <h4>薄弱 Topic</h4>
          <ul>{report.weak_topics?.map((w) => <li key={w.topic_id}>{w.name}: {w.mastery.toFixed(3)}</li>)}</ul>
          <h4>Misconceptions</h4>
          <ul>{report.misconceptions?.map((m) => (
            <li key={m.topic_id}>
              <b>{m.name}</b>: {m.error_count} 次错误
              {m.misconception ? ` — ${m.misconception}` : '（点上面“误解诊断”用 LLM 分析）'}
            </li>
          ))}</ul>
          <h4>各 Topic 掌握度</h4>
          <table>
            <thead><tr><th>Topic</th><th>mastery</th><th>对/错/次</th></tr></thead>
            <tbody>
              {Object.entries(report.mastery_by_topic ?? {}).map(([tid, v]) => (
                <tr key={tid}><td>{v.name}</td><td>{v.mastery.toFixed(3)}</td><td>{v.n_correct ?? 0}/{v.n_wrong ?? 0}/{v.updates ?? 0}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {sim && (
        <Card title="模拟学生评估">
          <table>
            <thead><tr><th>学生</th><th>before</th><th>after</th><th>gain</th><th>重复率</th><th>掌握度曲线</th></tr></thead>
            <tbody>
              {sim.profiles.map((p) => (
                <tr key={p.student}>
                  <td>{p.student}</td><td>{p.mastery_before.toFixed(3)}</td><td>{p.mastery_after.toFixed(3)}</td>
                  <td>{p.mastery_gain.toFixed(3)}</td><td>{p.question_repetition_rate.toFixed(3)}</td>
                  <td><Sparkline points={(p.sessions ?? []).map((s) => s.avg_mastery)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {full && (
        <Card title={`Day6 全流水线评估 ${full.ragas_used ? '(RAGAS 真 LLM 评估)' : '(离线探针)'}`}>
          <div className="meta">
            测试集: {full.test_dataset.total} 例 = 课程内 {full.test_dataset.on_material}
            + 超纲 {full.test_dataset.off_material}
            ，覆盖 {full.test_dataset.topic_coverage.join(', ') || '—'} topics
          </div>
          <h4>核心指标</h4>
          <table>
            <thead><tr><th>faithfulness</th><th>上下文精确</th><th>上下文召回</th><th>掌握度增益</th><th>题目重复率</th><th>拒答率</th></tr></thead>
            <tbody><tr>
              <td>{(full.all_metrics.faithfulness).toFixed(3)}</td>
              <td>{(full.all_metrics.context_precision).toFixed(3)}</td>
              <td>{(full.all_metrics.context_recall).toFixed(3)}</td>
              <td>{(full.all_metrics.mastery_gain).toFixed(3)}</td>
              <td>{(full.all_metrics.question_repetition_rate).toFixed(3)}</td>
              <td>{(full.all_metrics.refusal_rate).toFixed(3)}</td>
            </tr></tbody>
          </table>
          <h4>学生画像</h4>
          <table>
            <thead><tr><th>画像</th><th>before</th><th>after</th><th>gain</th><th>重复率</th><th>难度分布</th></tr></thead>
            <tbody>
              {full.student_profiles.map((p) => (
                <tr key={p.profile}>
                  <td>{p.profile}</td><td>{p.mastery_before.toFixed(3)}</td><td>{p.mastery_after.toFixed(3)}</td>
                  <td>{p.mastery_gain.toFixed(3)}</td><td>{p.question_repetition_rate.toFixed(3)}</td>
                  <td>易{p.difficulty_distribution.easy ?? 0}/中{p.difficulty_distribution.medium ?? 0}/难{p.difficulty_distribution.hard ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </Card>
  );
}
