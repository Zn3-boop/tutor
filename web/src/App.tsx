import { useEffect, useState } from 'react';
import { api, Student, Topic, Source } from './utils/api';
import { Button, Select, ToastStack, cn, type ToastItem } from './components/ui';
import { PlusIcon, RefreshIcon, UserPlusIcon } from './components/icons';
import CreateStudentModal from './components/CreateStudentModal';
import UploadPanel from './components/UploadPanel';
import ChatPanel from './components/ChatPanel';
import QuizPanel from './components/QuizPanel';
import ReportPanel from './components/ReportPanel';
import StudyPlanPanel from './components/StudyPlanPanel';
import DiagnosticWizard from './components/DiagnosticWizard';
import EvaluationPanel from './components/EvaluationPanel';
import CourseGraphPanel from './components/CourseGraphPanel';
import FlashcardsPanel from './components/FlashcardsPanel';
import WrongQuestionsPanel from './components/WrongQuestionsPanel';

type Tab = 'upload' | 'chat' | 'quiz' | 'report' | 'plan' | 'diagnostic' | 'evaluation' | 'graph' | 'flashcards' | 'wrong';

const TAB_URL_KEYS: Tab[] = ['upload','diagnostic','chat','quiz','report','graph','flashcards','wrong','plan','evaluation'];

export default function App() {
  const [tab, setTab] = useState<Tab>('upload');

  // P0-1: 初始化读取 URL tab 参数；监听浏览器前进/后退
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const t = params.get('tab');
    if (t && TAB_URL_KEYS.includes(t as Tab)) setTab(t as Tab);
    const handlePop = () => {
      const t2 = new URLSearchParams(window.location.search).get('tab');
      if (t2 && TAB_URL_KEYS.includes(t2 as Tab)) setTab(t2 as Tab);
    };
    window.addEventListener('popstate', handlePop);
    return () => window.removeEventListener('popstate', handlePop);
  }, []);

  const [students, setStudents] = useState<Student[]>([]);
  const [studentId, setStudentId] = useState<string>('');
  const [topics, setTopics] = useState<Topic[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [assessmentId, setAssessmentId] = useState<string>('');
  const [createOpen, setCreateOpen] = useState(false);
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const pushToast = (tone: ToastItem['tone'], message: string) => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, tone, message }]);
    window.setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 2600);
  };

  const refreshStudents = async () => {
    try {
      const { students } = await api.students();
      setStudents(students);
      if (students.length) setStudentId((cur) => cur || students[0].student_id);
    } catch (e) {
      pushToast('warn', `刷新学生失败：${String(e)}`);
    }
  };

  const refreshKnowledge = async () => {
    try {
      const [t, s] = await Promise.all([api.topics(), api.sources()]);
      setTopics(t.topics);
      setSources(s.sources);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    refreshStudents();
    refreshKnowledge();
  }, []);

  // 与原 window.prompt 逻辑一致：空名走后端默认名称；成功后追加并选中
  const handleCreateStudent = async (name: string) => {
    const st = await api.createStudent(name);
    setStudents((prev) => [...prev, st]);
    setStudentId(st.student_id);
    pushToast('success', `学生「${st.name || st.student_id}」创建成功`);
  };

  // P1: 聊天语言偏好（auto | zh | en）— 仅影响聊天回答语言，不翻译题目/闪卡/资料
  const LANG_OPTIONS = [
    { value: 'auto', label: '🌐 自动（随提问语言）' },
    { value: 'zh', label: '中文回答' },
    { value: 'en', label: 'English' },
  ];
  const currentLang: 'auto' | 'zh' | 'en' =
    students.find((s) => s.student_id === studentId)?.lang ?? 'auto';

  const handleLangChange = async (lang: string) => {
    if (!studentId) {
      pushToast('warn', '请先创建或选择学生');
      return;
    }
    try {
      const res = await api.updateStudentPreference(studentId, lang as 'auto' | 'zh' | 'en');
      setStudents((prev) => prev.map((s) => (s.student_id === studentId ? res.student : s)));
      const label = LANG_OPTIONS.find((o) => o.value === lang)?.label ?? lang;
      pushToast('success', `聊天语言已设为：${label}（题目/闪卡仍按资料原文）`);
    } catch (e) {
      pushToast('warn', `语言偏好保存失败：${String(e)}`);
    }
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: 'upload', label: '知识库 / 上传' },
    { key: 'diagnostic', label: '入学诊断' },
    { key: 'chat', label: 'Tutor 聊天' },
    { key: 'quiz', label: 'Quiz' },
    { key: 'report', label: '测评报告' },
    { key: 'graph', label: '课程图谱' },
    { key: 'flashcards', label: '闪卡复习' },
    { key: 'wrong', label: '错题本' },
    { key: 'plan', label: '学习计划' },
    { key: 'evaluation', label: '系统评测' },
  ];

  return (
    <div className="min-h-screen bg-canvas text-slate-800">
      <div className="mx-auto w-full max-w-[1120px] px-5 py-6">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-card bg-brand-600 text-white shadow-sm">
              <UserPlusIcon className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-brand-800">ECV-Tutor</h1>
              <p className="text-xs text-slate-500">自适应学习 · 课程图谱 · AI 辅导</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <Select value={studentId} onChange={(e) => setStudentId(e.target.value)} className="w-44" aria-label="选择学生">
              <option value="">选择学生</option>
              {students.map((s) => (
                <option key={s.student_id} value={s.student_id}>
                  {s.name || s.student_id}
                </option>
              ))}
            </Select>
            <Select
              value={currentLang}
              onChange={(e) => handleLangChange(e.target.value)}
              className="w-44"
              
              title="仅控制聊天回答语言；题目、闪卡、课程图谱文字按上传资料原文，不做自动翻译"
              aria-label="聊天语言偏好"
            >
              {LANG_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </Select>
            <Button variant="secondary" size="md" icon={<RefreshIcon className="h-4 w-4" />} onClick={refreshStudents}>
              刷新学生
            </Button>
            <Button variant="primary" size="md" icon={<PlusIcon className="h-4 w-4" />} onClick={() => setCreateOpen(true)}>
              新建学生
            </Button>
          </div>
        </header>

        <nav className="mt-5 flex flex-wrap gap-2">
          {tabs.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => {
                setTab(t.key);
                const url = new URL(window.location.href);
                url.searchParams.set('tab', t.key);
                window.history.pushState({}, '', url);
              }}
              className={cn(
                'rounded-field px-3.5 py-2 text-sm font-medium transition hover:-translate-y-0.5 active:translate-y-0',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-300 focus-visible:ring-offset-1',
                tab === t.key
                  ? 'bg-brand-600 text-white shadow-sm hover:bg-brand-700 hover:shadow-md'
                  : 'border border-slate-200 bg-white text-slate-600 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700'
              )}
            >
              {t.label}
            </button>
          ))}
        </nav>

        {studentId && currentLang !== 'auto' && (
          <p className="mt-2 text-xs text-slate-500">
            💡 语言偏好「{LANG_OPTIONS.find((o) => o.value === currentLang)?.label}」仅影响聊天回答；
            题目、闪卡、课程图谱文字来自上传资料原文，不会自动翻译。
          </p>
        )}

        <main className="mt-5 animate-fade-in-up">
          {tab === 'upload' && <UploadPanel sources={sources} topics={topics} onRefresh={refreshKnowledge} />}
          {tab === 'diagnostic' && (
            <DiagnosticWizard studentId={studentId} topics={topics} onReport={(report) => setAssessmentId(report.assessment_id)} />
          )}
          {tab === 'chat' && <ChatPanel studentId={studentId} />}
          {tab === 'quiz' && <QuizPanel studentId={studentId} onAssessment={setAssessmentId} />}
          {tab === 'report' && <ReportPanel studentId={studentId} assessmentId={assessmentId} />}
          {tab === 'graph' && <CourseGraphPanel studentId={studentId} topics={topics} />}
          {tab === 'flashcards' && <FlashcardsPanel studentId={studentId} />}
          {tab === 'wrong' && <WrongQuestionsPanel studentId={studentId} topics={topics} onAssessment={setAssessmentId} />}
          {tab === 'plan' && <StudyPlanPanel studentId={studentId} onOpenGraph={() => setTab('graph')} />}
          {tab === 'evaluation' && <EvaluationPanel studentId={studentId} />}
        </main>
      </div>

      <CreateStudentModal open={createOpen} onClose={() => setCreateOpen(false)} onSubmit={handleCreateStudent} />
      <ToastStack items={toasts} onDismiss={(id) => setToasts((prev) => prev.filter((t) => t.id !== id))} />
    </div>
  );
}