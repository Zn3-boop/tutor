import { useEffect, useMemo, useState } from 'react';
import { api, DiagnosticResponse, ReportResponse, SourceOpen, Topic, TopicSourceResponse } from '../utils/api';
import SourceDrawer from './SourceDrawer';
import { Button, Card, cn, Input, Select, Tag } from './ui';

type Step = 'select' | 'quiz' | 'report';

interface Props {
  studentId: string;
  topics: Topic[];
  onReport?: (report: ReportResponse) => void;
}

const STEP_LABEL: Record<Step, string> = { select: '1 选题', quiz: '2 答题', report: '3 报告' };

export default function DiagnosticWizard({ studentId, topics, onReport }: Props) {
  const [step, setStep] = useState<Step>('select');
  const [selected, setSelected] = useState<Set<string>>(() => new Set(topics.map((t) => t.topic_id)));
  const [numQuestions, setNumQuestions] = useState(6);
  const [llm, setLlm] = useState(false);
  const [lang, setLang] = useState<'zh' | 'en'>('zh');
  const [diag, setDiag] = useState<DiagnosticResponse | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [finalize, setFinalize] = useState<{ prior?: Record<string, number>; report?: ReportResponse } | null>(null);
  const [drawer, setDrawer] = useState<SourceOpen | null>(null);
  const [topicSources, setTopicSources] = useState<Record<string, TopicSourceResponse>>({});

  useEffect(() => {
    if (topics.length && selected.size === 0) setSelected(new Set(topics.map((t) => t.topic_id)));
  }, [topics]);

  const topicNames = useMemo(() => Object.fromEntries(topics.map((t) => [t.topic_id, t.name])), [topics]);

  const toggle = (tid: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(tid) ? next.delete(tid) : next.add(tid);
      return next;
    });
  };

  const start = async () => {
    if (!selected.size) { setErr('请至少选择一个主题'); return; }
    setBusy(true); setErr(''); setFinalize(null); setDiag(null); setAnswers({});
    try {
      const res = await api.diagnostic(studentId, numQuestions, llm, [...selected]);
      if (!res.ok) { setErr(res.error || '诊断生成失败'); return; }
      // For bilingual questions when not using LLM
      const qRes = llm ? res : await api.bilingualQuiz(lang, numQuestions, [...selected]);
      if (!qRes.ok) { setErr(qRes.error || '诊断生成失败'); return; }
      setDiag(res); setStep('quiz');
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  const choose = (qid: string, opt: string) => setAnswers((prev) => ({ ...prev, [qid]: opt }));

  const submitAll = async () => {
    if (!diag) return;
    setBusy(true); setErr('');
    try {
      for (const q of diag.questions) {
        const chosen = answers[q.question_id];
        if (!chosen) { setErr('还有题目未作答'); return; }
        await api.submit(studentId, diag.assessment_id, q.question_id, chosen);
      }
      const fin = await api.diagnosticFinalize(studentId, diag.assessment_id);
      if (!fin.ok) { setErr(fin.error || '报告生成失败'); return; }
      setFinalize({ prior: fin.prior, report: fin.report });
      if (fin.report && onReport) onReport(fin.report);
      setStep('report');
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  const openTopic = async (tid: string) => {
    setErr('');
    const cached = topicSources[tid];
    if (cached) { setDrawer(cached.citations[0]?.resolved ?? null); return; }
    try {
      const res = await api.topicSource(tid);
      setTopicSources((prev) => ({ ...prev, [tid]: res }));
      setDrawer(res.citations[0]?.resolved ?? null);
    } catch (e) {
      console.error('topic source failed', e);
      setErr('该主题暂无可直接打开的素材');
    }
  };

  const allAnswered = !!diag && diag.questions.length > 0 && diag.questions.every((q) => !!answers[q.question_id]);

  return (
    <div className="space-y-4">
      <Card title="入学诊断" subtitle="1 选题 → 2 答题 → 3 报告">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          {(['select', 'quiz', 'report'] as Step[]).map((s) => (
            <Tag key={s} tone={s === step ? 'success' : 'neutral'}>{STEP_LABEL[s]}</Tag>
          ))}
        </div>
{step === 'select' && (
          <div className="space-y-3">
            <p className="meta">诊断会为每个主题出题，完成后生成薄弱点报告与学习建议。</p>
            <div className="flex flex-wrap gap-2">
              {topics.map((t) => (
                <label key={t.topic_id} className={cn(
                  'cursor-pointer select-none rounded-pill border px-3 py-1.5 text-sm transition',
                  selected.has(t.topic_id)
                    ? 'border-brand-300 bg-brand-50 font-medium text-brand-700'
                    : 'border-slate-200 bg-white text-slate-600 hover:border-brand-300'
                )}>
                  <input type="checkbox" className="mr-1.5" checked={selected.has(t.topic_id)} onChange={() => toggle(t.topic_id)} />
                  {t.name}
                </label>
              ))}
            </div>
            <div className="row">
              <label className="flex items-center gap-2 text-sm text-slate-600">题目数
                <Input type="number" min={2} max={12} value={numQuestions} onChange={(e) => setNumQuestions(Number(e.target.value))} className="w-24" />
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input type="checkbox" checked={llm} onChange={(e) => setLlm(e.target.checked)} /> LLM 生成
              </label>
              {!llm && (
                <label className="flex items-center gap-2 text-sm text-slate-600">语言
                  <Select value={lang} onChange={(e) => setLang(e.target.value as 'zh' | 'en')} className="w-28">
                    <option value="zh">中文</option>
                    <option value="en">English</option>
                  </Select>
                </label>
              )}
              <Button disabled={busy || selected.size === 0} onClick={start}>开始诊断</Button>
            </div>
          </div>
        )}

{step === 'quiz' && diag && (
          <div className="space-y-3">
            <p className="meta">答题进度 {Object.keys(answers).length}/{diag.questions.length}</p>
            {diag.questions.map((q, qi) => (
              <div key={q.question_id} className="rounded-card border border-slate-200 bg-white p-4 shadow-card">
                <div className="meta mb-1">Q{qi + 1} · {q.topic_ids.map((tid) => topicNames[tid] || tid).join(', ') || '综合'}</div>
                <p className="answer text-sm text-slate-800">{q.text}</p>
                <div className="mt-2 space-y-1.5">
                  {q.options.map((opt) => (
                    <label key={opt} className={answers[q.question_id] === opt ? 'opt on' : 'opt'}>
                      <input type="radio" name={q.question_id} value={opt} checked={answers[q.question_id] === opt} onChange={() => choose(q.question_id, opt)} />
                      {opt}
                    </label>
                  ))}
                </div>
              </div>
            ))}
            <div className="row">
              <Button disabled={busy || !allAnswered} onClick={submitAll}>提交并生成报告</Button>
              {!allAnswered && <span className="meta">还有题目未作答</span>}
            </div>
          </div>
        )}

        {step === 'report' && finalize && (
          <div className="space-y-3">
            <h4 className="text-sm font-semibold text-slate-800">诊断报告</h4>
            {finalize.prior && Object.keys(finalize.prior).length > 0 && (
              <p className="meta">已播种先验: {Object.entries(finalize.prior).map(([t, p]) => `${topicNames[t] || t}=${(p as number).toFixed(2)}`).join(' · ')}</p>
            )}
            {finalize.report && (
              <div className="space-y-2">
                <div className="status">
                  <Tag tone="success">总体掌握度 {((finalize.report.overall_mastery ?? 0) * 100).toFixed(0)}%</Tag>
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-700">薄弱 Topic</p>
                  {finalize.report.weak_topics && finalize.report.weak_topics.length > 0 ? (
                    <ul className="weak-list">
                      {finalize.report.weak_topics.map((w) => (
                        <li key={w.topic_id}>
                          <button className="link" onClick={() => openTopic(w.topic_id)}>
                            {w.name} ({Math.round((w.mastery ?? 0) * 100)}%)
                          </button>
                          {topicSources[w.topic_id]?.count ? <span className="meta"> · 可复习</span> : null}
                        </li>
                      ))}
                    </ul>
                  ) : <div className="meta">没有明显薄弱点 🎉</div>}
                </div>
                {finalize.report.misconceptions && finalize.report.misconceptions.length > 0 && (
                  <div>
                    <p className="text-sm font-semibold text-slate-700">常见误区</p>
                    <ul className="list-disc pl-5 text-sm text-slate-600">
                      {finalize.report.misconceptions.map((m) => (
                        <li key={m.topic_id} className="meta"><b>{m.name}</b>: {m.misconception}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
            <div className="row">
              <Button variant="secondary" onClick={() => { setStep('select'); setDiag(null); setFinalize(null); setAnswers({}); }}>再做一次</Button>
            </div>
          </div>
        )}

        {err && <div className="error">{err}</div>}
      </Card>
      <SourceDrawer info={drawer} onClose={() => setDrawer(null)} />
    </div>
  );
}