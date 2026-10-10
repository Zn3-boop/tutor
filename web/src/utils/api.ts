// 最小 API 封装：所有请求走 vite 代理(/tutor -> http://127.0.0.1:8000)
const BASE = '';

export interface Citation {
  index: number;
  label: string;
  chunk_id: string;
  source_url: string;
}
export interface SourceOpen {
  ok: boolean;
  unit_id?: string;
  source_id?: string;
  source_title?: string;
  kind?: string;
  origin_label?: string;
  viewer?: 'pdf' | 'slides' | 'video' | 'transcript';
  page?: number;
  total_pages?: number;
  slide?: number;
  total_slides?: number;
  timestamp?: string;
  seconds?: number;
  open_url?: string;
  video_url?: string;
  youtube_url?: string;
  file?: string;
  file_exists?: boolean;
  error?: string;
}
export interface RetrievalMeta {
  retrieved: number;
  vector_count: number;
  bm25_count: number;
}
export interface ChatResponse {
  query: string;
  status: 'answered' | 'refused';
  refuse_reason?: string;
  answer?: string;
  used_offline_template?: boolean;
  citations?: Citation[];
  retrieval_meta?: RetrievalMeta;
}
export interface Topic {
  topic_id: string;
  name: string;
  concepts?: string[];
  prerequisites?: string[];
}
export interface Source {
  source_id: string;
  title: string;
  kind?: string;
  path?: string;
  total_pages?: number;
}
export interface IngestResult {
  ok: boolean;
  source_id?: string;
  unit_count?: number;
  error?: string;
  keyframes?: number;
  transcript_segments?: number;
  ocr_pages?: number[];
}
export interface Student {
  student_id: string;
  name?: string;
}
export interface QuizQuestion {
  question_id: string;
  text: string;
  type: string;
  options: string[];
  topic_ids: string[];
  difficulty?: string;
  origin?: { label?: string; timestamp?: string; index?: number };
}
export interface QuizResponse {
  ok: boolean;
  assessment_id: string;
  questions: QuizQuestion[];
  count: number;
}
export interface SubmitResponse {
  correct: boolean;
  feedback?: string;
  mastery_delta?: Record<string, { before: number; after: number }>;
}
export interface WeakTopic { topic_id: string; name: string; mastery: number; }
export interface Misconception { topic_id: string; name: string; error_count: number; misconception?: string; }
export interface MasteryEntry { name: string; mastery: number; n_correct?: number; n_wrong?: number; updates?: number; }
export interface MasteryTrajectory { student_id: string; trajectory: { step: number; mastery: number }[]; }
export interface ReportResponse {
  assessment_id: string;
  overall_mastery?: number;
  weak_topics?: WeakTopic[];
  misconceptions?: Misconception[];
  mastery_by_topic?: Record<string, MasteryEntry>;
}
export interface SimProfile {
  student: string;
  mastery_before: number;
  mastery_after: number;
  mastery_gain: number;
  question_repetition_rate: number;
  sessions: { session: number; questions: number; correct: number; accuracy: number; avg_mastery: number }[];
}
export interface SimulateResponse {
  ok: boolean;
  profiles: SimProfile[];
  config: Record<string, unknown>;
}
export interface AllMetrics {
  faithfulness: number;
  context_precision: number;
  context_recall: number;
  refusal_rate: number;
  mastery_gain: number;
  question_repetition_rate: number;
}
export interface StudentEvalProfile {
  profile: string;
  mastery_before: number;
  mastery_after: number;
  mastery_gain: number;
  question_repetition_rate: number;
  asked_questions: number;
  difficulty_distribution: Record<string, number>;
}
export interface TestDataset {
  total: number;
  on_material: number;
  off_material: number;
  topic_coverage: string[];
}
export interface FullEvalResponse {
  ok: boolean;
  ragas_used: boolean;
  test_dataset: TestDataset;
  rag_metrics: Record<string, number>;
  assessment_metrics: Record<string, number>;
  all_metrics: AllMetrics;
  student_profiles: StudentEvalProfile[];
  config: Record<string, unknown>;
}

export interface GraphNode { id: string; name: string; concepts?: string[]; mastery?: number | null; }
export interface GraphEdge { from: string; to: string; }
export interface CourseGraph { nodes: GraphNode[]; edges: GraphEdge[]; }
export interface Flashcard { unit_id: string; topic_id: string; topic_name: string; front: string; back: string; source_label: string; }
export interface FlashcardsResponse { ok: boolean; count: number; cards: Flashcard[]; }
export interface PlanActivity { day: number; topic_id: string; topic_name: string; action: string; reason: string; }
export interface PlanDay { day: number; activities: PlanActivity[]; minutes: number; }
export interface StudyPlanResponse {
  ok: boolean;
  exam_days: number;
  sessions_per_week: number;
  days: PlanDay[];
  stats: { total_activities: number; learn_sessions: number; review_sessions: number; covered_topics: number; };
}

async function http<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text.slice(0, 300)}`);
  }
  return res.json() as Promise<T>;
}

// multipart upload (no JSON content-type; let the browser set the boundary)
async function upload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(BASE + path, { method: 'POST', body: form });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text.slice(0, 300)}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  seedDemo: () => http<unknown>('/tutor/ingest/seed-demo', { method: 'POST' }),
  ingestText: (title: string, text: string, kind = 'text') =>
    http<unknown>('/tutor/ingest/text', { method: 'POST', body: JSON.stringify({ title, text, kind }) }),
  ingestFile: (path: string, title = '') =>
    http<IngestResult>('/tutor/ingest/pdf', { method: 'POST', body: JSON.stringify({ path, title }) }),
  ingestVideo: (path: string, title = '', intervalSec = 30, maxFrames = 60) =>
    http<IngestResult>('/tutor/ingest/video', { method: 'POST', body: JSON.stringify({ path, title, interval_sec: intervalSec, max_frames: maxFrames }) }),
  ingestUpload: (file: File, kind = 'auto') => {
    const form = new FormData();
    form.append('kind', kind);
    form.append('file', file);
    return upload<IngestResult>('/tutor/ingest/upload', form);
  },
  sources: () => http<{ sources: Source[] }>('/tutor/sources'),
  topics: () => http<{ topics: Topic[] }>('/tutor/topics'),
  students: () => http<{ students: Student[] }>('/tutor/students'),
  createStudent: (name: string) =>
    http<Student>('/tutor/students', { method: 'POST', body: JSON.stringify({ name }) }),
  chat: (query: string, llm: boolean, studentId?: string) => {
    const path = studentId ? `/tutor/chat/${studentId}` : '/tutor/chat';
    return http<ChatResponse>(path, { method: 'POST', body: JSON.stringify({ query, llm, top_k: 4 }) });
  },
  openSource: (unitId: string) =>
    http<SourceOpen>(`/tutor/source/open?unit_id=${encodeURIComponent(unitId)}`),
  fileUrl: (path: string) => {
    // 本地素材文件经 /tutor/files 代理，浏览器内嵌 viewer 可直接打开
    return `/tutor/files?path=${encodeURIComponent(path)}`;
  },
  quiz: (studentId: string, numQuestions: number, llm: boolean) =>
    http<QuizResponse>('/tutor/quiz', { method: 'POST', body: JSON.stringify({ student_id: studentId, num_questions: numQuestions, llm }) }),
  submit: (studentId: string, assessmentId: string, questionId: string, chosen: string) =>
    http<SubmitResponse>('/tutor/submit', { method: 'POST', body: JSON.stringify({ student_id: studentId, assessment_id: assessmentId, question_id: questionId, chosen }) }),
  report: (studentId: string, assessmentId: string) =>
    http<ReportResponse>('/tutor/report', { method: 'POST', body: JSON.stringify({ student_id: studentId, assessment_id: assessmentId, question_id: '', chosen: '' }) }),
  misconceptions: (studentId: string) =>
    http<Record<string, { label: string; error_count: number }>>('/tutor/misconceptions', { method: 'POST', body: JSON.stringify({ student_id: studentId }) }),
  masteryTrajectory: (studentId: string) =>
    http<MasteryTrajectory>(`/tutor/mastery-trajectory/${studentId}`),
  tts: async (text: string, voice = 'zh-CN-XiaoxiaoNeural') => {
    const res = await fetch('/tutor/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice }),
    });
    if (!res.ok) throw new Error(`${res.status}: ${(await res.text()).slice(0, 200)}`);
    return res.blob();
  },
  simulate: (nSessions = 4, questionsPerSession = 5, seed = 42) =>
    http<SimulateResponse>('/tutor/evaluate/simulate', { method: 'POST', body: JSON.stringify({ n_sessions: nSessions, questions_per_session: questionsPerSession, seed }) }),
  fullEval: (nSessions = 4, questionsPerSession = 5, seed = 42, llm = false) =>
    http<FullEvalResponse>('/tutor/evaluate/full', { method: 'POST', body: JSON.stringify({ n_sessions: nSessions, questions_per_session: questionsPerSession, seed, llm }) }),
  graph: (studentId = '') =>
    http<CourseGraph>(`/tutor/graph${studentId ? `?student_id=${studentId}` : ''}`),
  flashcards: (studentId: string, limit = 10) =>
    http<FlashcardsResponse>('/tutor/flashcards', { method: 'POST', body: JSON.stringify({ student_id: studentId, limit }) }),
  studyPlan: (studentId: string, examDays = 14, sessionsPerWeek = 7) =>
    http<StudyPlanResponse>('/tutor/study-plan', { method: 'POST', body: JSON.stringify({ student_id: studentId, exam_days: examDays, sessions_per_week: sessionsPerWeek }) }),
};