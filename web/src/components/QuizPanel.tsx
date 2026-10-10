import { useState } from 'react';
import { api, QuizResponse, QuizQuestion } from '../utils/api';

interface Props { studentId: string; onAssessment: (id: string) => void; }

export default function QuizPanel({ studentId, onAssessment }: Props) {
  const [num, setNum] = useState(5);
  const [llm, setLlm] = useState(false);
  const [quiz, setQuiz] = useState<QuizResponse | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, { correct: boolean; delta: string }>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const gen = async () => {
    if (!studentId) { setErr('请先创建 / 选择学生'); return; }
    setBusy(true); setErr(''); setQuiz(null); setAnswers({}); setResults({});
    try {
      const q = await api.quiz(studentId, num, llm);
      setQuiz(q); onAssessment(q.assessment_id);
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  const submit = async () => {
    if (!quiz) return;
    setBusy(true); setErr('');
    const out: Record<string, { correct: boolean; delta: string }> = {};
    for (const q of quiz.questions) {
      const chosen = answers[q.question_id];
      if (!chosen) continue;
      try {
        const r = await api.submit(studentId, quiz.assessment_id, q.question_id, chosen);
        const delta = r.mastery_delta
          ? Object.entries(r.mastery_delta).map(([tid, d]) => `${tid}: ${d.before}→${d.after}`).join(', ')
          : '';
        out[q.question_id] = { correct: r.correct, delta };
      } catch (e) { setErr(String(e)); }
    }
    setResults(out);
    setBusy(false);
  };

  return (
    <div className="panel">
      <h2>自适应 Quiz</h2>
      <div className="row">
        <label>题数 <input type="number" min={1} max={30} value={num} onChange={(e) => setNum(Number(e.target.value))} /></label>
        <label><input type="checkbox" checked={llm} onChange={(e) => setLlm(e.target.checked)} /> LLM 出题</label>
        <button disabled={busy} onClick={gen}>生成 Quiz</button>
        {quiz && <button disabled={busy} onClick={submit}>提交全部</button>}
      </div>
      {err && <div className="error">{err}</div>}
      {quiz && (
        <div>
          <div className="meta">Assessment: {quiz.assessment_id} · 题数 {quiz.count}</div>
          {quiz.questions.map((q: QuizQuestion, i: number) => (
            <div key={q.question_id} className="q">
              <div className="qtext">{i + 1}. {q.text} {q.difficulty ? `[${q.difficulty}]` : ''}</div>
              {q.options.map((opt) => (
                <label key={opt} className="opt">
                  <input type="radio" name={q.question_id} value={opt}
                    checked={answers[q.question_id] === opt}
                    onChange={() => setAnswers((prev) => ({ ...prev, [q.question_id]: opt }))} />
                  {opt}
                </label>
              ))}
              {results[q.question_id] && (
                <div className={results[q.question_id].correct ? 'ok' : 'error'}>
                  {results[q.question_id].correct ? '✓ 正确' : '✗ 错误'} {results[q.question_id].delta}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
