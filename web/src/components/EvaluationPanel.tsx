import { useState, useEffect, useRef } from 'react';
import { api, FullEvalResponse, TestSetSummary } from '../utils/api';
import { Button, Card, Input } from './ui';

interface Props { studentId: string; }

export default function EvaluationPanel({ studentId }: Props) {
  const [fullEval, setFullEval] = useState<FullEvalResponse | null>(null);
  const [testSetSummary, setTestSetSummary] = useState<TestSetSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [pollStatus, setPollStatus] = useState('');
  const [nSessions, setNSessions] = useState(4);
  const [questionsPerSession, setQuestionsPerSession] = useState(5);
  const [seed, setSeed] = useState(42);
  const [llm, setLlm] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadTestSet = async () => {
    try {
      const summary = await api.testSetSummary();
      setTestSetSummary(summary);
    } catch (e) {
      setErr(String(e));
    }
  };

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  const runEval = async () => {
    if (!studentId) { setErr('请先创建 / 选择学生'); return; }
    setBusy(true); setErr(''); setFullEval(null); setPollStatus('提交中…');
    try {
      const { task_id } = await api.fullEval(nSessions, questionsPerSession, seed, llm);
      setPollStatus('评估运行中…');
      pollRef.current = setInterval(async () => {
        try {
          const status = await api.evalStatus(task_id);
          if (status.status === 'done' && status.result) {
            stopPolling();
            setFullEval(status.result);
            setBusy(false);
            setPollStatus('');
          } else if (status.status === 'failed') {
            stopPolling();
            setErr(status.error || '评估失败');
            setBusy(false);
            setPollStatus('');
          } else {
            setPollStatus(`评估运行中 (${status.status})…`);
          }
        } catch (e) {
          stopPolling();
          setErr(String(e));
          setBusy(false);
          setPollStatus('');
        }
      }, 2000);
    } catch (e) { setErr(String(e)); setBusy(false); setPollStatus(''); }
  };

  useEffect(() => { loadTestSet(); return () => stopPolling(); }, []);

  return (
    <Card title="系统评测">
      {err && <div className="error">{err}</div>}

      {/* Test Set Summary */}
      <Card title="测试集概览">
        {testSetSummary && (
          <div>
            <div className="meta">
              总题数: {testSetSummary.case_count} |
              课内问题: {testSetSummary.summary.on_material} |
              课外问题: {testSetSummary.summary.off_material}
            </div>
            {testSetSummary.summary.language_distribution && (
              <div className="meta">
                语言分布: {Object.entries(testSetSummary.summary.language_distribution)
                  .map(([k, v]) => `${k}: ${v}`).join(', ')}
              </div>
            )}
            {testSetSummary.summary.domain_distribution && (
              <div className="meta">
                领域分布: {Object.entries(testSetSummary.summary.domain_distribution)
                  .map(([k, v]) => `${k}: ${v}`).join(', ')}
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Evaluation Controls */}
      <Card title="运行评测">
        <p className="meta" style={{ margin: '0 0 8px 0', lineHeight: 1.5 }}>
          模拟多种学生画像，运行完整的问答+评估流水线，输出 RAG 质量（faithfulness / context recall）和学习效果（mastery gain）指标。
          勾选「LLM 评估」可启用 RAGAS LLM Judge（需 API Key），否则使用离线词法探针。
        </p>
        <div className="row">
          <label className="flex items-center gap-1.5 text-sm text-slate-600">会话数
            <Input type="number" min={1} max={20} value={nSessions} onChange={(e) => setNSessions(Number(e.target.value))} className="w-24" />
          </label>
          <label className="flex items-center gap-1.5 text-sm text-slate-600">每会话题数
            <Input type="number" min={1} max={30} value={questionsPerSession} onChange={(e) => setQuestionsPerSession(Number(e.target.value))} className="w-24" />
          </label>
          <label className="flex items-center gap-1.5 text-sm text-slate-600">种子
            <Input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} className="w-24" />
          </label>
          <label className="flex items-center gap-1.5 text-sm text-slate-600">
            <input type="checkbox" checked={llm} onChange={(e) => setLlm(e.target.checked)} /> LLM 评估
          </label>
          <Button disabled={busy || !studentId} loading={busy} onClick={runEval}>运行评测</Button>
          {busy && <span className="meta">{pollStatus}</span>}
        </div>
      </Card>

      {/* Evaluation Results */}
      {fullEval && (
        <Card
          title={<>评测结果 {fullEval.ragas_used ? <span style={{ color: '#10B981', fontSize: '0.8em' }}>● RAGAS LLM Judge</span> : <span style={{ color: '#FB923C', fontSize: '0.8em' }}>● 离线探针（词法代理）</span>}</>}
        >
          <div className="metrics-grid">
            <div className="metric">
              <div className="metric-label">Faithfulness</div>
              <div className="metric-value">{fullEval.rag_metrics.faithfulness?.toFixed(3) || 'N/A'}</div>
            </div>
            <div className="metric">
              <div className="metric-label">Context Precision</div>
              <div className="metric-value">{fullEval.rag_metrics.context_precision?.toFixed(3) || 'N/A'}</div>
            </div>
            <div className="metric">
              <div className="metric-label">Context Recall</div>
              <div className="metric-value">{fullEval.rag_metrics.context_recall?.toFixed(3) || 'N/A'}</div>
            </div>
            <div className="metric">
              <div className="metric-label">Refusal Rate</div>
              <div className="metric-value">{fullEval.rag_metrics.refusal_rate?.toFixed(3) || 'N/A'}</div>
            </div>
            <div className="metric">
              <div className="metric-label">Mastery Gain</div>
              <div className="metric-value">+{fullEval.assessment_metrics.mastery_gain_avg?.toFixed(3) || 'N/A'}</div>
            </div>
            <div className="metric">
              <div className="metric-label">Question Repetition</div>
              <div className="metric-value">{fullEval.assessment_metrics.question_repetition_rate_avg?.toFixed(3) || 'N/A'}</div>
            </div>
          </div>

          {/* Student Profiles */}
          <div className="profiles">
            <h4>模拟学生表现</h4>
            {fullEval.student_profiles?.map((profile, i) => (
              <div key={i} className="profile-card">
                <div className="profile-name">{profile.profile}</div>
                <div className="profile-stats">
                  <span>Before: {profile.mastery_before.toFixed(3)}</span>
                  <span>After: {profile.mastery_after.toFixed(3)}</span>
                  <span className="gain">Gain: +{profile.mastery_gain.toFixed(3)}</span>
                  <span>Repetition: {profile.question_repetition_rate.toFixed(3)}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Test Set Path */}
          {fullEval.test_set_path && (
            <div className="meta">
              测试集已保存至: {fullEval.test_set_path}
            </div>
          )}
        </Card>
      )}
    </Card>
  );
}