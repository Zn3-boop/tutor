import { useEffect, useState } from 'react';
import { api, WrongQuestion, Topic, QuizResponse, QuizQuestion } from '../utils/api';
import { Button, Card, Select } from './ui';

interface Props { studentId: string; topics: Topic[]; onAssessment?: (id: string) => void; }

export default function WrongQuestionsPanel({ studentId, topics, onAssessment }: Props) {
  const [wrongQuestions, setWrongQuestions] = useState<WrongQuestion[]>([]);
  const [filterTopic, setFilterTopic] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [retestQuiz, setRetestQuiz] = useState<QuizResponse | null>(null);
  const [retestAnswers, setRetestAnswers] = useState<Record<string, string>>({});
  const [retestResults, setRetestResults] = useState<Record<string, boolean>>({});

  const loadWrongQuestions = async () => {
    if (!studentId) return;
    setBusy(true); setErr('');
    try {
      const res = await api.wrongQuestions(studentId, filterTopic);
      setWrongQuestions(res.wrong_questions);
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  useEffect(() => { loadWrongQuestions(); }, [studentId, filterTopic]);

  const resolveWQ = async (wqId: string) => {
    try {
      await api.resolveWrongQuestion(wqId);
      setWrongQuestions((prev) => prev.map((w) => w.wq_id === wqId ? { ...w, resolved: true } : w));
    } catch (e) { setErr(String(e)); }
  };

  const deleteWQ = async (wqId: string) => {
    try {
      await api.deleteWrongQuestion(wqId);
      setWrongQuestions((prev) => prev.filter((w) => w.wq_id !== wqId));
    } catch (e) { setErr(String(e)); }
  };

  const startRetest = async () => {
    if (!studentId) return;
    setBusy(true); setErr(''); setRetestQuiz(null); setRetestAnswers({}); setRetestResults({});
    try {
      const res = await api.retestWrongQuestions(studentId, 6);
      setRetestQuiz(res);
      if (onAssessment && res.assessment_id) onAssessment(res.assessment_id);
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  const submitRetestAnswer = async (questionId: string) => {
    if (!retestQuiz || !studentId) return;
    const chosen = retestAnswers[questionId];
    if (!chosen) return;
    try {
      const res = await api.submit(studentId, retestQuiz.assessment_id, questionId, chosen);
      setRetestResults((prev) => ({ ...prev, [questionId]: res.correct }));
    } catch (e) { setErr(String(e)); }
  };

  const topicName = (tid: string) => topics.find((t) => t.topic_id === tid)?.name || tid;
  const unresolved = wrongQuestions.filter((w) => !w.resolved);
  const resolved = wrongQuestions.filter((w) => w.resolved);
  const topicOptions = Array.from(new Set(wrongQuestions.flatMap((w) => w.topic_ids)));

  return (
    <Card title="错题本">
      {err && <div className="error">{err}</div>}
      <div className="row">
        <Select value={filterTopic} onChange={(e) => setFilterTopic(e.target.value)} className="max-w-[220px]">
          <option value="">全部知识点</option>
          {topicOptions.map((tid) => (
            <option key={tid} value={tid}>{topicName(tid)}</option>
          ))}
        </Select>
        <Button size="sm" variant="secondary" disabled={busy} onClick={loadWrongQuestions}>🔄 刷新</Button>
        <Button size="sm" disabled={busy || !studentId || unresolved.length === 0} onClick={startRetest}>
          一键重测错题 ({unresolved.length})
        </Button>
      </div>

      {retestQuiz && retestQuiz.ok && (
        <Card title="错题重测" className="mt-2 border-brand-200" bodyClassName="space-y-3">
          {retestQuiz.questions.map((q: QuizQuestion, i: number) => (
            <div key={q.question_id} className="rounded-card border border-slate-200 bg-white p-4 shadow-card">
              <div className="mb-2 text-sm font-semibold text-slate-800">{i + 1}. {q.text}</div>
              <div className="space-y-1.5">
                {q.options.map((opt: string) => (
                  <label key={opt} className={'opt' + (retestAnswers[q.question_id] === opt ? ' on' : '')}>
                    <input type="radio" name={`retest-${q.question_id}`} checked={retestAnswers[q.question_id] === opt} onChange={() => setRetestAnswers((prev) => ({ ...prev, [q.question_id]: opt }))} />
                    {opt}
                  </label>
                ))}
              </div>
              <div className="row">
                <Button size="sm" variant="secondary" disabled={!retestAnswers[q.question_id] || retestResults[q.question_id] !== undefined} onClick={() => submitRetestAnswer(q.question_id)}>提交</Button>
                {retestResults[q.question_id] !== undefined && (
                  <span className={retestResults[q.question_id] ? 'ok' : 'error'}>
                    {retestResults[q.question_id] ? '✓ 正确' : '✗ 仍需练习'}
                  </span>
                )}
              </div>
            </div>
          ))}
          <div className="flex gap-2 pt-1">
            <Button size="sm" variant="secondary" onClick={() => { setRetestQuiz(null); loadWrongQuestions(); }}>完成重测</Button>
          </div>
        </Card>
      )}

      {unresolved.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <h3>未解决 ({unresolved.length})</h3>
          {unresolved.map((w) => (
            <div key={w.wq_id} className="card border-l-4" style={{ borderLeftColor: '#F87171' }}>
              <div style={{ fontSize: 13 }}>{w.question_text}</div>
              <div className="meta" style={{ marginTop: 4 }}>
                <span style={{ color: '#F87171' }}>你的答案: {w.chosen}</span> · <span style={{ color: '#10B981' }}>正确答案: {w.correct_answer}</span>
              </div>
              <div className="meta">知识点: {w.topic_ids.map(topicName).join(', ')}</div>
              {w.explanation && <div className="meta">解析: {w.explanation}</div>}
              <div className="row" style={{ marginTop: 4 }}>
                <Button size="sm" variant="secondary" onClick={() => resolveWQ(w.wq_id)}>标记已解决</Button>
                <Button size="sm" variant="danger" onClick={() => deleteWQ(w.wq_id)}>删除</Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {resolved.length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary>已解决 ({resolved.length})</summary>
          {resolved.map((w) => (
            <div key={w.wq_id} className="card border-l-4" style={{ borderLeftColor: '#10B981', opacity: 0.7 }}>
              <div style={{ fontSize: 13 }}>{w.question_text}</div>
              <div className="meta" style={{ marginTop: 4 }}>
                <span style={{ color: '#10B981' }}>正确答案: {w.correct_answer}</span>
              </div>
              <div className="meta">知识点: {w.topic_ids.map(topicName).join(', ')}</div>
            </div>
          ))}
        </details>
      )}

      {wrongQuestions.length === 0 && !busy && (
        <div className="meta" style={{ marginTop: 12 }}>
          {studentId ? '暂无错题记录，继续保持！' : '请先选择学生'}
        </div>
      )}
    </Card>
  );
}