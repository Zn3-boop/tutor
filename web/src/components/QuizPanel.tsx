import { useState } from 'react';
import { api, QuizResponse, QuizQuestion } from '../utils/api';
import { Button, Card, Input, Select, Tag } from './ui';

interface Props { studentId: string; onAssessment: (id: string) => void; }

export default function QuizPanel({ studentId, onAssessment }: Props) {
  const [num, setNum] = useState(5);
  const [llm, setLlm] = useState(false);
  const [lang, setLang] = useState<'zh' | 'en'>('zh');
  const [quiz, setQuiz] = useState<QuizResponse | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, { correct: boolean; delta: string }>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const gen = async () => {
    if (!studentId) { setErr('请先创建 / 选择学生'); return; }
    setBusy(true); setErr(''); setQuiz(null); setAnswers({}); setResults({});
    try {
      const q = llm ? await api.quiz(studentId, num, llm) : await api.bilingualQuiz(lang, num);
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
    <div className="space-y-4">
      <Card
        title="自适应 Quiz"
        subtitle="根据当前掌握度推荐弱项题目，持续追踪 mastery 变化。（入学诊断用于首次建立 BKT 先验，此处用于日常练习。）"
        actions={quiz ? (
          <Button disabled={busy} onClick={submit}>提交全部</Button>
        ) : undefined}
      >
        <div className="row">
          <label className="flex items-center gap-2 text-sm text-slate-600">题数
            <Input type="number" min={1} max={30} value={num} onChange={(e) => setNum(Number(e.target.value))} className="w-24" />
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={llm} onChange={(e) => setLlm(e.target.checked)} /> LLM 出题
          </label>
          {!llm && (
            <label className="flex items-center gap-2 text-sm text-slate-600">语言
              <Select value={lang} onChange={(e) => setLang(e.target.value as 'zh' | 'en')} className="w-28">
                <option value="zh">中文</option>
                <option value="en">English</option>
              </Select>
            </label>
          )}
          <Button disabled={busy || !studentId} onClick={gen}>生成 Quiz</Button>
        </div>
        {err && <div className="error">{err}</div>}
      </Card>

      {quiz && (
        <Card
          title={quiz.count ? `题目（${quiz.count} 题）` : '题目（空）'}
          subtitle={`Assessment: ${quiz.assessment_id}`}
        >
          {quiz.questions.length === 0 ? (
            <p className="meta">📭 暂无可用题目，请先上传课程资料后再尝试 Quiz</p>
          ) : (
            <div className="space-y-3">
              {quiz.questions.map((q: QuizQuestion, i: number) => (
                <div key={q.question_id} className="rounded-card border border-slate-200 bg-white p-4 shadow-card">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-slate-800">{i + 1}. {q.text}</span>
                    {q.difficulty && <Tag tone={q.difficulty === 'hard' ? 'warn' : q.difficulty === 'medium' ? 'info' : 'success'}>{q.difficulty}</Tag>}
                  </div>
                  <div className="space-y-1.5">
                    {q.options.map((opt) => (
                      <label key={opt} className={answers[q.question_id] === opt ? 'opt on' : 'opt'}>
                        <input type="radio" name={q.question_id} value={opt}
                          checked={answers[q.question_id] === opt}
                          onChange={() => setAnswers((prev) => ({ ...prev, [q.question_id]: opt }))} />
                        {opt}
                      </label>
                    ))}
                  </div>
                  {results[q.question_id] && (
                    <div className={results[q.question_id].correct ? 'ok' : 'error'}>
                      {results[q.question_id].correct ? '✓ 正确' : '✗ 错误'} {results[q.question_id].delta}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}