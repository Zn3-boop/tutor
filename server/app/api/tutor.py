
"""REST API for the Track D Tutor subsystem.

Exposes the multimodal ingestion, source-grounded chat, adaptive assessment and
learner-model (BKT) endpoints that the desktop dashboard calls.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.services.tutor.store import get_tutor_store
from app.services.tutor.knowledge import get_kb_ingestor
from app.services.tutor.grounding import get_grounded_tutor
from app.services.tutor.assessment import get_assessment_generator
from app.services.tutor.evaluation import get_evaluation_runner
from app.services.tutor.planning import get_learning_planner
from app.services.tutor.graph_enhancer import get_graph_enhancer
from app.services.tutor.error_analyzer import get_error_analyzer

from app.services.tutor.bilingual_questions import list_bilingual_questions

router = APIRouter(prefix="/tutor", tags=["tutor"])

logger = logging.getLogger(__name__)
_DEMO_MATERIALS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "demo_materials")
)

class BilingualQuizRequest(BaseModel):
    lang: str = Field(default="zh", description="zh | en")
    num_questions: int = Field(default=5, ge=1, le=10)
    scope_topic_ids: list[str] | None = None


@router.post("/quiz/bilingual")
async def quiz_bilingual(req: BilingualQuizRequest):
    """Generate quiz from bilingual question bank."""
    questions = list_bilingual_questions(
        lang=req.lang,
        topic_ids=req.scope_topic_ids,
        difficulty=None
    )[:req.num_questions]
    
    if not questions:
        return {
            "ok": False,
            "error": "No questions available",
            "questions": [],
            "count": 0,
            "assessment_id": str(uuid.uuid4()),
        }
    
    return {
        "ok": True,
        "assessment_id": str(uuid.uuid4()),
        "questions": [{
            "question_id": q["id"],
            "text": q["text"],
            "options": q["options"],
            "topic_ids": q["topic_ids"],
            "difficulty": q["difficulty"],
        } for q in questions],
        "count": len(questions),
        "mode": "bilingual",
        "language": req.lang,
    }


# ---------------- request models ----------------
class IngestTextRequest(BaseModel):
    title: str
    text: str
    kind: str = Field(default="text", description="text | textbook | transcript | video | slides | notes | lecture | paper")
    chunk_size: int = 900


class IngestFileRequest(BaseModel):
    path: str
    title: str = ""


class ChatRequest(BaseModel):
    query: str
    llm: bool = True
    top_k: int = 5
    tts: bool = Field(default=False, description="Return audio URL for answer")
    lang: str = Field(default="auto", description="聊天回答语言偏好: auto(随提问) | zh | en")


class StudentCreateRequest(BaseModel):
    name: str = ""
    profile: dict = {}
    lang: str = Field(default="auto", description="语言偏好(仅聊天回答): auto | zh | en")


class StudentPreferenceRequest(BaseModel):
    lang: str = Field(default="auto", description="auto | zh | en")


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


class TestSetRequest(BaseModel):
    regenerate: bool = False


class DiagnosticRequest(BaseModel):
    student_id: str
    num_questions: int = Field(default=6, ge=1, le=30)
    llm: bool = False
    scope_topic_ids: list[str] | None = None


class FlashcardsRequest(BaseModel):
    student_id: str
    limit: int = Field(default=10, ge=1, le=50)


class StudyPlanRequest(BaseModel):
    student_id: str
    exam_days: int = Field(default=14, ge=1, le=90)
    sessions_per_week: int = Field(default=7, ge=1, le=35)
    strategy: str = Field(default="static", description="static | rl")


class ImageChatRequest(BaseModel):
    image: str = Field(description="base64 encoded image or file path")
    prompt: str = Field(default="", description="custom VLM parse prompt")
    student_id: str = Field(default="")
    tts: bool = Field(default=False, description="Return audio URL for answer")
    llm: bool = True
    top_k: int = 5
    vlm_skip_load: bool = Field(default=False, description="debug: skip VLM inference, return mock text")


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
    kind = (req.kind or "text").strip().lower()
    # transcript/video kinds parse timestamps (SRT / [HH:MM:SS]) into units
    if kind in ("transcript", "video", "srt", "vtt"):
        return await ing.ingest_transcript(title=req.title, text=req.text,
                                           topics=topics or None)
    return await ing.ingest_text(
        title=req.title, text=req.text, kind=kind,
        topics=topics or None, chunk_size=req.chunk_size)


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
                 | slides | notes | lecture | paper | image
    Video files (.mp4/.avi/.mkv/.mov) are routed to ingest_video (keyframe extraction).
    Images are OCR'd (PaddleOCR/Tesseract) and ingested as text units.
    """
    ing = get_kb_ingestor()
    topics = get_tutor_store().list_topics_by_id()
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
    k = (kind or "auto").strip().lower()
    if k == "auto":
        k = {"pdf": "pdf", "pptx": "pptx", "docx": "docx", "odt": "docx",
             "txt": "transcript", "vtt": "transcript", "srt": "transcript",
             "md": "text", "csv": "text",
             "mp4": "video", "avi": "video", "mkv": "video", "mov": "video",
             "webm": "video", "flv": "video",
             "png": "image", "jpg": "image", "jpeg": "image",
             "gif": "image", "webp": "image", "bmp": "image"}.get(ext, "text")
    path = await _save_upload(file)
    title = file.filename or os.path.basename(path)
    try:
        if k == "pdf":
            return await ing.ingest_pdf(path=path, title=title)
        if k in ("pptx", "slides"):
            return await ing.ingest_pptx(path=path, title=title)
        if k in ("docx", "textbook", "paper", "odt"):
            return await ing.ingest_docx(path=path, title=title)
        if k == "video" and ext in ("mp4", "avi", "mkv", "mov", "webm", "flv"):
            return await ing.ingest_video(path=path, title=title)
        if k == "image" and ext in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
            # 图片素材：先 OCR 提取文字并摄入知识库，无法识别则交给「图片提问」
            from app.services.ocr.service import get_ocr_service
            ocr = get_ocr_service()
            ocr_result = await asyncio.to_thread(ocr.recognize_image, path)
            if ocr_result.success and ocr_result.text.strip():
                ocr_text = ocr_result.text.strip()
                return await ing.ingest_text(
                    title=title, text=f"[OCR 图片文字]\n{ocr_text}",
                    kind="text", topics=topics or None)
            return {"ok": True, "source_id": "", "unit_count": 0,
                    "message": "图片已保存，但 OCR 未能提取文字；请用「图片提问」做 VLM 理解",
                    "path": path}
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        if k in ("transcript", "video", "srt", "vtt"):
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


@router.get("/topic-source/{topic_id}")
async def topic_source(topic_id: str):
    """Resolve study material for a weak topic into clickable citations.

    Returns per-topic units with source titles so the report can offer
    ``open`` links into the matching source viewer. Used by the diagnostic
    report weak-topic list (report cards).
    """
    from app.services.tutor.citations import resolve_citation
    from fastapi import HTTPException
    store = get_tutor_store()
    units = store.units_by_topics([topic_id])
    if not units:
        raise HTTPException(status_code=404, detail=f"no material for topic: {topic_id}")
    citations = []
    for u in units:
        rec = resolve_citation(store, unit_id=u["unit_id"])
        if rec.get("ok"):
            citations.append({
                "unit_id": u.get("unit_id", ""),
                "source_title": u.get("source_title", ""),
                "origin_label": u.get("origin", {}).get("label", ""),
                "resolved": rec,
            })
    return {"topic_id": topic_id, "citations": citations,
            "count": len(citations)}


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
    return store.create_student(name=req.name, profile=req.profile, lang=req.lang)


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


@router.put("/students/{student_id}/preference")
async def update_student_preference(student_id: str, req: StudentPreferenceRequest):
    """P1: student chat-language preference (auto | zh | en), persisted per learner.

    Only affects the *conversation* language; quiz questions, flashcards and
    graph annotations stay in the source-material language (no auto-translation).
    """
    if req.lang not in ("auto", "zh", "en"):
        raise HTTPException(status_code=400, detail="lang must be one of: auto | zh | en")
    store = get_tutor_store()
    _require_student(store, student_id)
    updated = store.update_student(student_id, {"lang": req.lang})
    logger.info("student %s language preference set to %s", student_id, req.lang)
    return {"student": updated}


# ---------------- grounded chat ----------------
async def _safe_answer(tutor, query: str, *, llm: bool, top_k: int = 4,
                       pref_lang: str = "auto") -> dict[str, Any]:
    """Run the grounded answer pipeline without letting a 500 escape to the UI.

    Any unexpected failure (retrieval hiccup, LLM outage, …) is logged with its
    traceback and degrades to the offline path first, then to a clear refusal —
    so the Tutor Chat panel always gets a usable JSON response.

    ``pref_lang`` (P1): student-chosen chat language (auto / zh / en). It is
    threaded into ``tutor.answer`` so the LLM prompt can enforce the student's
    language preference for the conversation.
    """
    try:
        return await tutor.answer(query, llm=llm, top_k=top_k, pref_lang=pref_lang)
    except Exception as exc:
        logger.warning("chat answer failed (llm=%s): %s", llm, exc, exc_info=True)
        try:
            return await tutor.answer(query, llm=False, top_k=top_k, pref_lang=pref_lang)
        except Exception as exc2:
            logger.warning("offline chat answer also failed: %s", exc2, exc_info=True)
            return {
                "query": query,
                "status": "refused",
                "refuse_reason": f"服务暂时不可用，请稍后重试（{type(exc).__name__}）",
                # off_material 仅用于「课程内容确实不覆盖该问题」的业务拒答；
                # 这里是服务异常，绝不是超纲，前端不应渲染「🚫 超纲查询」。
                "off_material": False,
                "answer": "",
                "citations": [],
                "evidence": [],
                "retrieval_meta": {"retrieved": 0, "vector_count": 0, "bm25_count": 0},
            }


@router.post("/chat")
async def chat(req: ChatRequest):
    tutor = get_grounded_tutor()
    result = await _safe_answer(tutor, req.query, llm=req.llm, top_k=req.top_k,
                                pref_lang=req.lang)
    # TTS audio generation for the answer
    if req.tts and result.get("answer"):
        from app.services.tts import get_tts_service
        tts_svc = get_tts_service()
        lang = result.get("detected_language", "zh")
        tts_result = await tts_svc.generate(
            text=result["answer"], lang=lang, filename=""
        )
        if tts_result["ok"]:
            result["tts_url"] = f"/tutor/tts/{tts_result['filename']}"
            result["tts_duration_s"] = tts_result.get("duration_s", 0)
    return result


@router.post("/chat/image")
async def chat_image(req: ImageChatRequest):
    """VLM image question: parse image -> extract text -> Tutor answer with citations."""
    from app.services.vlm.parser import get_vlm_parser
    parser = get_vlm_parser()
    parse_result = await parser.parse_question_image(
        req.image, prompt=req.prompt or None,
        skip_load=req.vlm_skip_load,
    )
    if not parse_result["ok"]:
        return {
            "status": "refused",
            "answer": "",
            "refuse_reason": f"图片解析失败: {parse_result['error']}",
            "vlm_parse": parse_result,
        }
    extracted_text = parse_result["text"]
    store = get_tutor_store() if req.student_id else None
    tutor = get_grounded_tutor(store)
    answer_result = await _safe_answer(tutor, extracted_text, llm=req.llm, top_k=req.top_k)
    answer_result["vlm_parse"] = parse_result
    # TTS audio generation for the answer
    if req.tts and answer_result.get("answer"):
        from app.services.tts import get_tts_service
        tts_svc = get_tts_service()
        lang = answer_result.get("detected_language", "zh")
        tts_result = await tts_svc.generate(
            text=answer_result["answer"], lang=lang, filename=""
        )
        if tts_result["ok"]:
            answer_result["tts_url"] = f"/tutor/tts/{tts_result['filename']}"
            answer_result["tts_duration_s"] = tts_result.get("duration_s", 0)
    return answer_result


@router.post("/vlm/warmup")
async def vlm_warmup():
    """Preload VLM model weights into memory (async, non-blocking).

    Triggers background loading of the local VLM provider (Qwen2.5-VL-3B).
    The heavy CPU work runs in a separate thread so the event loop is not
    blocked.  Returns immediately; check progress with GET /vlm/status.
    """
    from app.services.vlm.provider import provider, cloud_provider
    import asyncio

    local_enabled = provider.enabled
    cloud_enabled = cloud_provider.enabled

    if local_enabled and not provider.loaded and not provider.is_loading:
        asyncio.create_task(provider.warmup())
        return {"status": "warming", "provider": "local", "cloud_ready": cloud_enabled}
    return {
        "status": provider.status,
        "provider": "local" if local_enabled else "none",
        "cloud_ready": cloud_enabled,
    }


@router.get("/vlm/status")
async def vlm_status():
    """Check VLM provider status: idle / warming / loaded / failed."""
    from app.services.vlm.provider import provider, cloud_provider
    return {
        "local": {
            "enabled": provider.enabled,
            "status": provider.status,
            "loaded": provider.loaded,
            "is_loading": provider.is_loading,
            "error": provider.load_error,
        },
        "cloud": {"enabled": cloud_provider.enabled},
    }


@router.post("/chat/{student_id}")
async def chat_for_student(student_id: str, req: ChatRequest):
    """Chat that also persists the session against a learner and offers a
    personalised preface based on the student's weakest topics.

    P1: the student's stored ``lang`` preference (auto/zh/en) is enforced for
    the answer language; a per-request ``req.lang`` override wins if present.
    """
    store = get_tutor_store()
    student = _require_student(store, student_id)
    pref_lang = (student.get("lang") or "auto") if isinstance(student, dict) else "auto"
    if req.lang in ("zh", "en"):
        pref_lang = req.lang
    tutor = get_grounded_tutor(store)
    result = await _safe_answer(tutor, req.query, llm=req.llm, top_k=req.top_k,
                                pref_lang=pref_lang)
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
    """Onboarding diagnostic for a learner (optionally scoped to selected topics).

    New students take this first to discover weak topics; BKT mastery is updated
    as they answer. Returns tagged assessment used by /submit and /diagnostic/finalize.
    """
    store = get_tutor_store()
    student = _require_student(store, req.student_id)
    gen = get_assessment_generator(store)
    if req.scope_topic_ids:
        return await gen.generate_diagnostic(
            student,
            num_questions=req.num_questions,
            llm=req.llm,
            scope_topic_ids=req.scope_topic_ids,
        )
    return await gen.generate_diagnostic(student, num_questions=req.num_questions,
                                         llm=req.llm)


# ---------------- learning planning (6a/6b/6c) ----------------
@router.get("/graph")
async def course_graph(student_id: str = ""):
    """Topic + prerequisite graph (with per-node annotations & edge labels)
    for the course-flow visualisation."""
    enhancer = get_graph_enhancer()
    return enhancer.build_enhanced_graph(student_id=student_id)


@router.post("/flashcards")
async def flashcards(req: FlashcardsRequest):
    """Weakness review flashcards mined from the weakest topics (offline)."""
    store = get_tutor_store()
    _require_student(store, req.student_id)
    return get_learning_planner(store).weakness_flashcards(req.student_id, limit=req.limit)


@router.post("/study-plan")
async def study_plan(req: StudyPlanRequest):
    """Personalized study schedule: weak-first + prerequisites + forgetting curve.

    strategy: "static" (default) or "rl" (reinforcement learning enhanced).
    """
    store = get_tutor_store()
    _require_student(store, req.student_id)
    planner = get_learning_planner(store)
    return planner.study_plan(
        req.student_id, exam_days=req.exam_days,
        sessions_per_week=req.sessions_per_week,
        strategy=req.strategy)



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


@router.get("/mastery-stream/{student_id}")
async def mastery_stream(student_id: str):
    """SSE stream: pushes mastery updates after each answer submission.

    Frontend uses EventSource to listen. Falls back gracefully if SSE
    is not supported (client can poll /mastery-trajectory instead).
    """
    store = get_tutor_store()
    _require_student(store, student_id)

    async def event_generator():
        from app.services.tutor.learner import LearnerModel
        import json as _json
        learner = LearnerModel()
        topics = store.list_topics_by_id()
        last_snapshot: str = ""
        for _ in range(300):
            student = store.get_student(student_id)
            if student is None:
                break
            mastery = learner.mastery_summary(student, topics)
            snapshot = _json.dumps(mastery, sort_keys=True)
            if snapshot != last_snapshot:
                last_snapshot = snapshot
                yield f"data: {snapshot}\n\n"
            await asyncio.sleep(2)
        yield "data: {\"event\": \"done\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
    """TTS read-aloud (Edge-TTS online, falls back to Windows SAPI5 offline)."""
    from fastapi.responses import Response
    if not (req.text or "").strip():
        raise HTTPException(status_code=400, detail="empty text")
    from app.services.tts import get_tts_service
    result = await get_tts_service().generate(req.text.strip(), lang="zh", filename="")
    if not result["ok"]:
        raise HTTPException(status_code=502, detail=result.get("error", "tts unavailable"))
    ext = os.path.splitext(result["path"])[1].lower()
    media = "audio/wav" if ext == ".wav" else "audio/mpeg"
    with open(result["path"], "rb") as f:
        data = f.read()
    return Response(content=data, media_type=media,
                    headers={"Content-Disposition": f"inline; filename=tts{ext}",
                             "Cache-Control": "no-store"})


@router.get("/tts/{filename}")
async def tts_audio(filename: str):
    """Serve a previously generated TTS audio file (used by chat tts_url)."""
    from fastapi.responses import FileResponse
    from app.services.tts import get_tts_service
    svc = get_tts_service()
    # Reject path traversal: only allow names inside the TTS output dir.
    safe = os.path.basename(filename)
    path = os.path.abspath(os.path.join(svc.output_dir, safe))
    if not path.startswith(os.path.abspath(svc.output_dir)) or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="audio not found")
    return FileResponse(path, media_type="audio/wav" if safe.endswith(".wav") else "audio/mpeg")


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


_eval_tasks: dict[str, dict] = {}


async def _background_eval(task_id: str, req: FullEvalRequest):
    try:
        _eval_tasks[task_id]["status"] = "running"
        runner = get_evaluation_runner()
        result = await runner.run_full_evaluation(
            n_sessions=req.n_sessions,
            questions_per_session=req.questions_per_session,
            seed=req.seed, llm=req.llm)
        _eval_tasks[task_id]["status"] = "done"
        _eval_tasks[task_id]["result"] = result
    except Exception as e:
        _eval_tasks[task_id]["status"] = "failed"
        _eval_tasks[task_id]["error"] = str(e)


@router.post("/evaluate/full")
async def evaluate_full(req: FullEvalRequest):
    """Full-pipeline benchmark: runs as background task, returns task_id for polling."""
    task_id = str(uuid.uuid4())
    _eval_tasks[task_id] = {"status": "pending", "result": None, "error": None}
    asyncio.create_task(_background_eval(task_id, req))
    return {"task_id": task_id, "status": "pending"}


@router.get("/evaluate/status/{task_id}")
async def evaluate_status(task_id: str):
    task = _eval_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return {"task_id": task_id, **task}


@router.post("/test-set")
async def get_test_set(req: TestSetRequest = TestSetRequest()):
    """Get the current evaluation test set with metadata."""
    from app.services.eval.dataset import build_comprehensive_test_set
    from app.services.tutor.store import get_tutor_store
    
    store = get_tutor_store()
    result = build_comprehensive_test_set(store)
    return {
        "ok": True,
        "summary": result["summary"],
        "test_set_path": result["path"],
        "case_count": len(result["cases"]),
    }


@router.get("/test-set/summary")
async def get_test_set_summary():
    """Get a lightweight summary of the current test set."""
    from app.services.tutor.store import get_tutor_store
    from app.services.eval.dataset import build_comprehensive_test_set
    
    store = get_tutor_store()
    result = build_comprehensive_test_set(store)
    return {
        "ok": True,
        "summary": result["summary"],
        "case_count": len(result["cases"]),
    }


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


# ---------------- wrong questions (错题本) ----------------
@router.get("/wrong-questions/{student_id}")
async def list_wrong_questions(student_id: str, topic_id: str = ""):
    store = get_tutor_store()
    _require_student(store, student_id)
    return {"wrong_questions": store.list_wrong_questions(student_id, topic_id=topic_id)}


class WrongQuestionResolveRequest(BaseModel):
    wq_id: str


@router.post("/wrong-questions/resolve")
async def resolve_wrong_question(req: WrongQuestionResolveRequest):
    store = get_tutor_store()
    result = store.mark_wrong_question_resolved(req.wq_id)
    if result is None:
        raise HTTPException(status_code=404, detail="wrong question record not found")
    return {"ok": True, "wq_id": req.wq_id, "resolved": True}


@router.delete("/wrong-questions/{wq_id}")
async def delete_wrong_question(wq_id: str):
    store = get_tutor_store()
    ok = store.delete_wrong_question(wq_id)
    if not ok:
        raise HTTPException(status_code=404, detail="wrong question record not found")
    return {"ok": True, "wq_id": wq_id}


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str):
    """Delete a source and all its associated units."""
    store = get_tutor_store()
    ok = store.delete_source(source_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"source {source_id} not found")
    return {"ok": True, "source_id": source_id}


@router.post("/wrong-questions/{student_id}/retest")
async def retest_wrong_questions(student_id: str, num_questions: int = 6):
    """Generate a quiz scoped to the topics of the student's unresolved wrong questions."""
    store = get_tutor_store()
    student = _require_student(store, student_id)
    wrong = store.list_wrong_questions(student_id)
    unresolved = [w for w in wrong if not w.get("resolved")]
    if not unresolved:
        return {"ok": False, "error": "没有未解决的错题", "questions": []}
    topic_ids = list({tid for w in unresolved for tid in w.get("topic_ids", [])})
    gen = get_assessment_generator(store)
    return await gen.generate_quiz(student, topic_ids, num_questions=num_questions, llm=False)


# ---------------- enhanced graph ----------------
@router.get("/enhanced-graph/{student_id}")
async def get_enhanced_graph(student_id: str):
    """获取增强版知识图谱（含统计指标、簇分析、推荐路径）。"""
    enhancer = get_graph_enhancer()
    result = enhancer.build_enhanced_graph(student_id)
    return result


@router.get("/enhanced-graph")
async def get_global_graph():
    """获取全局知识图谱（无学生数据）。"""
    enhancer = get_graph_enhancer()
    return enhancer.build_enhanced_graph("")


# ---------------- error analysis ----------------
class ErrorAnalysisRequest(BaseModel):
    student_id: str
    assessment_id: str | None = None


@router.post("/analyze-errors")
async def analyze_errors(req: ErrorAnalysisRequest):
    """分析学生的错误模式（基于最近评估或指定评估）。"""
    store = get_tutor_store()
    student = _require_student(store, req.student_id)
    
    analyzer = get_error_analyzer()
    
    # 获取评估结果
    assessments = student.get("assessments") or {}
    if req.assessment_id:
        assessment = assessments.get(req.assessment_id)
        if not assessment:
            raise HTTPException(
                status_code=404, 
                detail=f"assessment {req.assessment_id} not found"
            )
    else:
        # 使用最近的评估
        if not assessments:
            return {
                "ok": False,
                "error": "该学生尚无评估记录",
                "error_distribution": {},
                "recommendations": []
            }
        latest_id = max(assessments.keys(), key=lambda k: assessments[k].get("timestamp", ""))
        assessment = assessments[latest_id]
    
    # 构建问题结果列表
    quiz_results = []
    for q_record in assessment.get("questions", []):
        if not q_record.get("is_correct"):
            quiz_results.append({
                "question": q_record.get("question", ""),
                "student_answer": q_record.get("chosen", ""),
                "correct_answer": q_record.get("answer", ""),
                "explanation": q_record.get("explanation"),
                "topic_ids": q_record.get("topic_ids", []),
                "is_correct": False
            })
    
    if not quiz_results:
        return {
            "ok": True,
            "error_distribution": {},
            "strongest_misconceptions": [],
            "recommendations": [],
            "message": "该评估无错误记录"
        }
    
    # 执行错误分析
    analysis = analyzer.analyze_quiz_errors(quiz_results)
    
    # 生成个性化建议
    recommendations = []
    for misconception in analysis.get("strongest_misconceptions", []):
        error_type = misconception["error_type"]
        error_label = misconception["label"]
        
        # 从分类法获取建议
        from app.services.tutor.error_analyzer import MISCONCEPTION_TAXONOMY
        hint = MISCONCEPTION_TAXONOMY.get(error_type, {}).get(
            "description", "需要加强该方面练习"
        )
        
        recommendations.append({
            "priority": misconception["count"],
            "error_type": error_type,
            "label": error_label,
            "issue": hint,
            "focus_hint": f"该主题出错 {misconception['count']} 次 (占比 {misconception['percentage']}%)"
        })
    
    return {
        "ok": True,
        "student_id": req.student_id,
        "assessment_id": req.assessment_id or assessment.get("assessment_id"),
        "total_errors": analysis.get("total_errors", 0),
        "error_distribution": analysis.get("error_distribution", {}),
        "topic_error_patterns": analysis.get("topic_error_patterns", {}),
        "strongest_misconceptions": analysis.get("strongest_misconceptions", []),
        "recommendations": recommendations,
        "analysis_timestamp": analysis.get("analysis_timestamp")
    }


# ---------------- adversarial testing ----------------
class AdversarialTestRequest(BaseModel):
    full_suite: bool = True
    test_types: list[str] | None = None
    max_retries: int = 3
    timeout_seconds: float = 10.0


@router.post("/adversarial-test")
async def run_adversarial_tests(req: AdversarialTestRequest):
    """运行对抗性测试套件。"""
    from app.services.eval.adversarial_test import get_adversarial_test_runner
    
    runner = get_adversatorial_test_runner()
    runner.max_retries = req.max_retries
    runner.timeout_seconds = req.timeout_seconds
    
    if req.full_suite:
        runner.build_test_suite()
    elif req.test_types:
        # 过滤特定类型的测试
        all_cases = runner.build_test_suite()
        from app.services.eval.adversarial_test import TestCaseType
        runner.test_cases = [
            tc for tc in all_cases 
            if tc.type.value in req.test_types
        ]
    
    suite_result = await runner.run_full_suite()
    report = runner.generate_report(suite_result)
    
    return {
        "ok": True,
        **report
    }


@router.get("/adversarial-test/report")
async def get_last_adversarial_report():
    """获取上次对抗性测试的报告缓存。"""
    # 这里可以集成到现有的评估报告中
    # 暂时返回空结构供前端轮询
    return {
        "ok": True,
        "message": "尚未运行对抗性测试，请 POST 到 /adversarial-test",
        "last_run": None
    }
    gen = get_assessment_generator(store)
    return await gen.generate_quiz(student, topic_ids, num_questions=num_questions, llm=False)
