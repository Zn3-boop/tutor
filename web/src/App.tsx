import { useEffect, useState } from 'react';
import { api, Student, Topic, Source } from './utils/api';
import UploadPanel from './components/UploadPanel';
import ChatPanel from './components/ChatPanel';
import QuizPanel from './components/QuizPanel';
import ReportPanel from './components/ReportPanel';
import StudyPlanPanel from './components/StudyPlanPanel';

type Tab = 'upload' | 'chat' | 'quiz' | 'report' | 'plan';

export default function App() {
  const [tab, setTab] = useState<Tab>('upload');
  const [students, setStudents] = useState<Student[]>([]);
  const [studentId, setStudentId] = useState<string>('');
  const [topics, setTopics] = useState<Topic[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [assessmentId, setAssessmentId] = useState<string>('');

  const refreshStudents = async () => {
    try {
      const { students } = await api.students();
      setStudents(students);
      if (students.length) setStudentId((cur) => cur || students[0].student_id);
    } catch { /* ignore */ }
  };

  const refreshKnowledge = async () => {
    try {
      const [t, s] = await Promise.all([api.topics(), api.sources()]);
      setTopics(t.topics);
      setSources(s.sources);
    } catch { /* ignore */ }
  };

  useEffect(() => { refreshStudents(); refreshKnowledge(); }, []);

  const createStudent = async () => {
    try {
      const name = window.prompt('学生姓名 (留空则用默认)') || '';
      const st = await api.createStudent(name);
      setStudents((prev) => [...prev, st]);
      setStudentId(st.student_id);
    } catch (e) { window.alert(String(e)); }
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: 'upload', label: '知识库 / 上传' },
    { key: 'chat', label: 'Tutor 聊天' },
    { key: 'quiz', label: 'Quiz' },
    { key: 'report', label: '测评报告' },
    { key: 'plan', label: '学习计划' },
  ];

  return (
    <div className="app">
      <header>
        <h1>ECV-Tutor</h1>
        <div className="studentbar">
          <select value={studentId} onChange={(e) => setStudentId(e.target.value)}>
            <option value="">选择学生</option>
            {students.map((s) => (
              <option key={s.student_id} value={s.student_id}>{s.name || s.student_id}</option>
            ))}
          </select>
          <button onClick={createStudent}>+ 新建学生</button>
          <button onClick={refreshStudents}>刷新学生</button>
        </div>
      </header>
      <nav className="tabs">
        {tabs.map((t) => (
          <button key={t.key} className={tab === t.key ? 'active' : ''} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </nav>
      <main>
        {tab === 'upload' && <UploadPanel sources={sources} topics={topics} onRefresh={refreshKnowledge} />}
        {tab === 'chat' && <ChatPanel studentId={studentId} />}
        {tab === 'quiz' && <QuizPanel studentId={studentId} onAssessment={setAssessmentId} />}
        {tab === 'report' && <ReportPanel studentId={studentId} assessmentId={assessmentId} />}
        {tab === 'plan' && <StudyPlanPanel studentId={studentId} />}
      </main>
    </div>
  );
}
