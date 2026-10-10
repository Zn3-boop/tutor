"""REST API for the Track D Tutor subsystem.

Exposes the multimodal ingestion, source-grounded chat, adaptive assessment and
learner-model (BKT) endpoints that the desktop dashboard calls.
"""

from __future__ import annotations

import asyncio
import os
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.tutor.store import get_tutor_store
from app.services.tutor.knowledge import get_kb_ingestor
from app.services.tutor.grounding import get_grounded_tutor
from app.services.tutor.assessment import get_assessment_generator
from app.services.tutor.evaluation import get_evaluation_runner
from app.services.tutor.planning import get_learning_planner

router = APIRouter(prefix="/tutor", tags=["tutor"])

_DEMO_MATERIALS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "demo_materials")
)


# ---------------- request models ----------------
class IngestTextRequest(BaseModel):
    title: str
    text: str
    kind: str = Field(default="text", description="text | textbook | video")
    chunk_size: int = 900


class IngestFileRequest(BaseModel):
    path: str
    title: str = ""


class ChatRequest(BaseModel):
    query: str
    llm: bool = True
    top_k: int = 5


class StudentCreateRequest(BaseModel):
    name: str = ""
    profile: dict = {}


class QuizRequest(BaseModel):
    student_id: str
    scope_topic_ids: list[str] | None = None
    num_questions: int = Field(default=6, ge=1, le=30)
    llm: bool = True


class SubmitRequest(BaseModel):
    student_id: str
    assessment_id: str
    question_id: str
    chosen: str


class SimulateRequest(BaseModel):
    n_sessions: int = 4
    questions_per_session: int = 5
    seed: int = 42


class FullEvalRequest(BaseModel):
    n_sessions: int = 4
    questions_per_session: int = 5
    seed: int = 42
    llm: bool = False


class DiagnosticRequest(BaseModel):
    student_id: str
    num_questions: int = Field(default=6, ge=1, le=30)
    llm: bool = False


class FlashcardsRequest(BaseModel):
    student_id: str
    limit: int = Field(default=10, ge=1, le=50)


class StudyPlanRequest(BaseModel):
    student_id: str
    exam_days: int = Field(default=14, ge=1, le=90)
    sessions_per_week: int = Field(default=7, ge=1, le=35)


def _require_student(store, student_id: str):
    student = store.get_student(student_id)
    if student is None:
        raise HTTPException(status_code=404, detail=f"student not found: {student_id}")
    return student


class MisconceptionRequest(BaseModel):
    student_id: str


class TTSRequest(BaseModel):
    text: str
    voice: str = "zh-CN-XiaoxiaoNeural"


# ---------------- ingestion ----------------
@router.post("/ingest/text")
async def ingest_text(req: IngestTextRequest):
    ing = get_kb_ingestor()
    topics = get_tutor_store().list_topics_by_id()
    result = await ing.ingest_text(
        title=req.title, text=req.text, kind=req.kind,
        topics=topics or None, chunk_size=req.chunk_size)
    return result


@router.post("/ingest/transcript")
async def ingest_transcript(req: IngestTextRequest):
    ing = get_kb_ingestor()
    topics = get_tutor_store().list_topics_by_id()
    return await ing.ingest_transcript(title=req.title, text=req.text,
                                       topics=topics or None)


@router.post("/ingest/docx")
async def ingest_docx(req: IngestFileRequest):
    ing = get_kb_ingestor()
    return await ing.ingest_docx(path=req.path, title=req.title)


@router.post("/ingest/pptx")
async def ingest_pptx(req: IngestFileRequest):
    ing = get_kb_ingestor()
    return await ing.ingest_pptx(path=req.path, title=req.title)


@router.post("/ingest/pdf")
async def ingest_pdf(req: IngestFileRequest):
    ing = get_kb_ingestor()
    return await ing.ingest_pdf(path=req.path, title=req.title)


class IngestVideoRequest(BaseModel):
    path: str
    title: str = ""
    interval_sec: float = Field(default=30.0, ge=1.0, le=600.0)
    max_frames: int = Field(default=60, ge=1, le=500)


@router.post("/ingest/video")
async def ingest_video(req: IngestVideoRequest):
    ing = get_kb_ingestor()
    return await ing.ingest_video(
        path=req.path, title=req.title,
        interval_sec=req.interval_sec, max_frames=req.max_frames)


_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")


async def _save_upload(file: UploadFile) -> str:
    os.makedirs(_UPLOAD_DIR, exist_ok=True)
    name = f"{uuid.uuid4().hex[:12]}_{os.path.basename(file.filename or 'upload')}"
    dest = os.path.join(_UPLOAD_DIR, name)
    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
    return dest


@router.post("/ingest/upload")
async def ingest_upload(kind: str = Form("auto"), file: UploadFile = File(...)):
    """Multipart upload -> route by kind/extension, ingest, keep citations.

    kind can be: auto | pdf | pptx | docx | transcript | video | text
    Video files (.mp4/.avi/.mkv/.mov) are routed to ingest_video (keyframe extraction).
    """
    ing = get_kb_ingestor()
    topics = get_tutor_store().list_topics_by_id()
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
    k = (kind or "auto").strip().lower()
    if k == "auto":
        k = {"pdf": "pdf", "pptx": "pptx", "docx": "docx",
             "txt": "transcript", "vtt": "transcript", "srt": "transcript",
             "md": "text",
             "mp4": "video", "avi": "video", "mkv": "video", "mov": "video",
             "webm": "video", "flv": "video"}.get(ext, "text")
    path = await _save_upload(file)
    title = file.filename or os.path.basename(path)
    try:
        if k == "pdf":
            return await ing.ingest_pdf(path=path, title=title)
        if k in ("pptx", "slides"):
            return await ing.ingest_pptx(path=path, title=title)
        if k in ("docx", "textbook"):
            return await ing.ingest_docx(path=path, title=title)
        if k == "video" and ext in ("mp4", "avi", "mkv", "mov", "webm", "flv"):
            return await ing.ingest_video(path=path, title=title)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        if k in ("transcript", "video"):
            return await ing.ingest_transcript(title=title, text=text,
                                               topics=topics or None)
        return await ing.ingest_text(title=title, text=text,
                                     topics=topics or None)
    finally:
        pass


@router.post("/ingest/seed-demo")
async def seed_demo(variant: str = Form("real")):
    """Seed the demo knowledge base.

    Default ``variant=real`` ingests the bundled REAL public course materials
    (Think Python 2e PDF + MIT OCW 6.0001 slides + official timestamped SRT
    transcript) from server/demo_materials + materials-manifest.json.
    ``variant=fallback`` ingests the old synthetic demo course instead.
    """
    ing = get_kb_ingestor()
    if (variant or "").strip().lower() in ("fallback", "synthetic", "fake"):
        return await ing.seed_fallback_course()
    return await ing.seed_real_course()


# ---------------- knowledge base browse ----------------
@router.get("/sources")
async def list_sources():
    return {"sources": get_tutor_store().list_sources()}


@router.get("/topics")
async def list_topics():
    store = get_tutor_store()
    return {"topics": store.list_topics()}


@router.get("/units")
async def list_units(source_id: str = ""):
    return {"units": get_tutor_store().list_units(source_id)}


@router.get("/source/open")
async def open_source(source_id: str = "", unit_id: str = "", origin_label: str = ""):
    """Resolve a citation to an openable viewer reference.

    Accepts either the unit_id directly, or the (source_id, origin_label) pair
    that grounding returns on retrieved chunks. Returns the file path, page /
    slide number or video timestamp plus a ready-to-seek URL. Frontend wiring
    lands in Phase 3; the payload is stable API already.
    """
    from app.services.tutor.citations import resolve_citation
    from fastapi import HTTPException
    store = get_tutor_store()
    res = resolve_citation(store, source_id=source_id, unit_id=unit_id,
                           origin_label=origin_label)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error", "cannot resolve citation"))
    return res


@router.get("/files")
async def serve_source_file(path: str = ""):
    """Serve a bundled course-material file (PDF / PPTX / SRT) so the browser
    viewer can open it directly with a #page / #slide fragment.

    Only files under the demo materials dir (or any path recorded on a source)
    are served — arbitrary filesystem access is not allowed.
    """
    from fastapi import HTTPException
    store = get_tutor_store()
    allowed = {os.path.abspath(p) for p in {
        os.path.join(_DEMO_MATERIALS_DIR, f) for f in os.listdir(_DEMO_MATERIALS_DIR)
        if f.lower().endswith((".pdf", ".pptx", ".srt", ".vtt", ".docx"))
    } if os.path.isfile(p)}
    allowed |= {os.path.abspath(s.get("path", "")) for s in store.list_sources() if s.get("path")}
    abs_path = os.path.abspath(path)
    if abs_path not in allowed or not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail=f"file not allowed: {path}")
    media_type = {
        ".pdf": "application/pdf",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".srt": "text/plain; charset=utf-8",
        ".vtt": "text/plain; charset=utf-8",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(os.path.splitext(abs_path)[1].lower(), "application/octet-stream")
    return FileResponse(abs_path, media_type=media_type, filename=os.path.basename(abs_path))


@router.get("/kb-summary")
async def kb_summary():
    store = get_tutor_store()
    return {
        "sources": len(store.list_sources()),
        "units": len(store.list_units()),
        "topics": len(store.list_topics()),
        "questions": len(store.list_questions()),
    }


# ---------------- students ----------------
@router.post("/students")
async def create_student(req: StudentCreateRequest):
    store = get_tutor_store()
    return store.create_student(name=req.name, profile=req.profile)


@router.get("/students")
async def list_students():
    return {"students": get_tutor_store().list_students()}


@router.get("/students/{student_id}")
async def get_student(student_id: str):
    store = get_tutor_store()
    student = _require_student(store, student_id)
    from app.services.tutor.learner import LearnerModel
    return {"student": student,
            "mastery": LearnerModel().mastery_summary(
                student, store.list_topics_by_id())}


# ---------------- grounded chat ----------------
@router.post("/chat")
async def chat(req: ChatRequest):
    tutor = get_grounded_tutor()
    return await tutor.answer(req.query, llm=req.llm, top_k=req.top_k)


@router.post("/chat/{student_id}")
async def chat_for_student(student_id: str, req: ChatRequest):
    """Chat that also persists the session against a learner and offers a
    personalised preface based on the student's weakest topics."""
    store = get_tutor_store()
    _require_student(store, student_id)
    tutor = get_grounded_tutor(store)
    result = await tutor.answer(req.query, llm=req.llm, top_k=req.top_k)
    return result


# ---------------- adaptive assessment ----------------
@router.post("/quiz")
async def generate_quiz(req: QuizRequest):
    store = get_tutor_store()
    student = _require_student(store, req.student_id)
    gen = get_assessment_generator(store)
    scope = req.scope_topic_ids or list(store.list_topics_by_id().keys())
    return await gen.generate_quiz(student, scope,
                                   num_questions=req.num_questions, llm=req.llm)


@router.post("/diagnostic")
async def diagnostic(req: DiagnosticRequest):
    """Onboarding diagnostic for a learner across all topics.

    New students take this first to discover weak topics; BKT mastery is updated
    as they answer. Returns tagged assessment used by /submit and /diagnostic/finalize.
    """
    store = get_tutor_store()
    student = _require_student(store, req.student_id)
    gen = get_assessment_generator(store)
    return await gen.generate_diagnostic(student, num_questions=req.num_questions,
                                         llm=req.llm)


# ---------------- learning planning (6a/6b/6c) ----------------
@router.get("/graph")
async def course_graph(student_id: str = ""):
    """Topic + prerequisite graph for the course-flow visualisation."""
    return get_learning_planner().course_graph(student_id=student_id)


@router.post("/flashcards")
async def flashcards(req: FlashcardsRequest):
    """Weakness review flashcards mined from the weakest topics (offline)."""
    store = get_tutor_store()
    _require_student(store, req.student_id)
    return get_learning_planner(store).weakness_flashcards(req.student_id, limit=req.limit)


@router.post("/study-plan")
async def study_plan(req: StudyPlanRequest):
    """Personalized study schedule: weak-first + prerequisites + forgetting curve."""
    store = get_tutor_store()
    _require_student(store, req.student_id)
    planner = get_learning_planner(store)
    return planner.study_plan(
        req.student_id, exam_days=req.exam_days,
        sessions_per_week=req.sessions_per_week)



@router.post("/diagnostic/finalize")
async def diagnostic_finalize(req: SubmitRequest):
    """Apply IRT-ish BKT priors from a completed diagnostic and return the report."""
    store = get_tutor_store()
    student = _require_student(store, req.student_id)
    gen = get_assessment_generator(store)
    return gen.finalize_diagnostic(student, req.assessment_id)


@router.post("/submit")
async def submit(req: SubmitRequest):
    store = get_tutor_store()
    student = _require_student(store, req.student_id)
    gen = get_assessment_generator(store)
    return await gen.submit_answer(student, req.assessment_id,
                                   req.question_id, req.chosen)


@router.post("/report")
async def report(req: SubmitRequest):
    store = get_tutor_store()
    student = _require_student(store, req.student_id)
    gen = get_assessment_generator(store)
    return gen.generate_report(student, req.assessment_id)


@router.get("/report/{student_id}")
async def get_last_report(student_id: str):
    store = get_tutor_store()
    student = _require_student(store, student_id)
    return {"report": student.get("last_report", {})}


@router.post("/misconceptions")
async def analyze_misconceptions(req: MisconceptionRequest):
    """LLM judge over the student's wrong-answer samples -> per-topic labels."""
    store = get_tutor_store()
    student = _require_student(store, req.student_id)
    gen = get_assessment_generator(store)
    return await gen.analyze_misconceptions(student)


@router.get("/mastery-trajectory/{student_id}")
async def mastery_trajectory(student_id: str):
    """Per-answer mastery curve for the learner-model visualisation."""
    store = get_tutor_store()
    student = _require_student(store, student_id)
    return {"student_id": student_id, "trajectory": student.get("mastery_traj", [])}


# ---------------- demo scaffold ---------------- 
# Demo tooling: seeds the built-in course (idempotent) and warms up a base
# "Demo 学生" with scripted answers so the misconception judge + mastery sparkline
# already have data when the reviewer opens the dashboard. Server-side on purpose:
# the public quiz payload hides answer keys, so warmup reads them from the store
# inside the same process (no second DB writer).
DEMO_STUDENT_NAME = "Demo 学生"
_DEMO_CORRECT_PATTERN = [True, True, False, True, True, False, True, True, False, True]


@router.post("/demo/warmup")
async def demo_warmup():
    """Reuse/create 'Demo 学生', run scripted quiz rounds (some deliberately wrong),
    then run the LLM misconception judge. Returns the student + trajectory + labels."""
    from itertools import cycle
    store = get_tutor_store()
    gen = get_assessment_generator(store)

    student = next((s for s in store.list_students()
                    if s.get("name") == DEMO_STUDENT_NAME), None)
    if student is None:
        student = store.create_student(name=DEMO_STUDENT_NAME,
                                       profile={"level": "beginner", "mode": "demo"})

    topics = store.list_topics_by_id()
    units = store.list_units()
    topic_with_units: set[str] = set()
    for u in units:
        topic_with_units |= set(u.get("topic_ids", []) or [])
    scope = [tid for tid in topics if tid in topic_with_units]
    if not scope:
        await get_kb_ingestor(store).seed_real_course()
        topics = store.list_topics_by_id()
        scope = list(topics.keys())

    asked = set(student.get("asked_questions", []))
    correctness = cycle(_DEMO_CORRECT_PATTERN)
    answered = 0
    wrong = 0
    for _ in range(3):
        quiz = await gen.generate_quiz(student, scope, num_questions=5, llm=False)
        if not quiz.get("ok"):
            continue
        for pq in quiz.get("questions", []):
            qid = pq.get("question_id")
            if not qid or qid in asked:
                continue
            q = store.get_question(qid)
            if not q:
                continue
            opts = q.get("options") or []
            answer = q.get("answer", "")
            should_be_correct = next(correctness)
            if should_be_correct and answer in opts:
                chosen = answer
            elif opts:
                chosen = next((o for o in opts if o != answer), answer)
            else:
                chosen = answer if should_be_correct else (answer or "故意答错")
            res = await gen.submit_answer(student, quiz["assessment_id"], qid, chosen)
            asked.add(qid)
            answered += 1
            wrong += 0 if res.get("correct") else 1

    analysis = await gen.analyze_misconceptions(student)
    return {
        "ok": True,
        "student_id": student["student_id"],
        "answers": answered,
        "wrong": wrong,
        "trajectory": student.get("mastery_traj", []),
        "misconceptions": analysis,
        "topics": len(scope),
    }


@router.post("/tts")
async def tts(req: TTSRequest):
    """Edge-TTS read-aloud of any text (quiz feedback / report summary)."""
    from fastapi.responses import Response
    if not (req.text or "").strip():
        raise HTTPException(status_code=400, detail="empty text")
    import edge_tts
    communicate = edge_tts.Communicate(req.text.strip(), req.voice)
    audio = bytearray()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            audio.extend(chunk.get("data") or b"")
    if not audio:
        raise HTTPException(status_code=502, detail="edge-tts produced no audio")
    return Response(content=bytes(audio), media_type="audio/mpeg",
                    headers={"Content-Disposition": "inline; filename=tts.mp3",
                             "Cache-Control": "no-store"})


@router.get("/verify-question/{question_id}")
async def verify_question(question_id: str):
    gen = get_assessment_generator()
    return gen.verify_question(question_id)


# ---------------- evaluation ----------------
@router.post("/evaluate/simulate")
async def simulate(req: SimulateRequest):
    runner = get_evaluation_runner()
    return await runner.run_simulated_students(
        n_sessions=req.n_sessions,
        questions_per_session=req.questions_per_session,
        seed=req.seed)


@router.post("/evaluate/full")
async def evaluate_full(req: FullEvalRequest):
    """Day6 full benchmark: RAG faithfulness/context metrics + mastery/repetition."""
    runner = get_evaluation_runner()
    return await runner.run_full_evaluation(
        n_sessions=req.n_sessions,
        questions_per_session=req.questions_per_session,
        seed=req.seed, llm=req.llm)


@router.post("/evaluate/rag")
async def evaluate_rag():
    runner = get_evaluation_runner()
    return await runner.evaluate_rag_metrics()


# ---------------- transcription ----------------
class TranscribeRequest(BaseModel):
    path: str
    model_size: str = ""
    language: str | None = None


@router.post("/transcribe")
async def transcribe(req: TranscribeRequest):
    """Transcribe a video file using Whisper. Returns timestamped transcript."""
    from app.services.tutor.transcriber import transcribe_video_async
    return await transcribe_video_async(
        req.path, model_size=req.model_size, language=req.language,
    )


# ---------------- VLM caption test ----------------
class VLMCaptionRequest(BaseModel):
    prompt: str = "请描述这张图片的内容。"
    image_path: str = ""


@router.post("/vlm/caption")
async def vlm_caption(req: VLMCaptionRequest):
    """Test VLM caption on a local image file."""
    from app.services.vlm.provider import describe_image_fallback
    if not req.image_path or not os.path.exists(req.image_path):
        raise HTTPException(status_code=400, detail="image_path does not exist")
    with open(req.image_path, "rb") as f:
        data = f.read()
    caption = await describe_image_fallback(prompt=req.prompt, image=data)
    return {"ok": bool(caption), "caption": caption}