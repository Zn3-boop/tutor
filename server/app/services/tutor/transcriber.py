"""Video transcription via Whisper (OpenAI whisper / faster-whisper).

Extracts a timestamped transcript from a video's audio track. The output
format matches what ``KnowledgeBaseIngestor.ingest_transcript`` expects:
    [HH:MM:SS] segment text

Two backends are supported:
  - **faster-whisper** (preferred): CTranslate2-based, ~4x faster, less RAM.
  - **openai-whisper**: The original OpenAI model, fallback if faster-whisper
    is not installed.

Both run fully offline after the model is downloaded once.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from typing import Any

logger = logging.getLogger(__name__)


def _ts_fmt(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _extract_audio(video_path: str, out_path: str) -> str:
    """Extract audio from video to WAV using ffmpeg (subprocess)."""
    import subprocess

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        "-y", out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (rc={result.returncode}): "
            f"{result.stderr.decode(errors='replace')[:500]}"
        )
    return out_path


def _transcribe_faster_whisper(
    audio_path: str,
    model_size: str,
    language: str | None,
) -> list[dict[str, Any]]:
    """Transcribe with faster-whisper, returning [{timestamp, text}] segments."""
    from faster_whisper import WhisperModel

    device = "cuda" if os.getenv("WHISPER_DEVICE", "cpu") == "cuda" else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments_iter, info = model.transcribe(
        audio_path,
        language=language,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    results = []
    for seg in segments_iter:
        text = seg.text.strip()
        if text:
            results.append({
                "start": seg.start,
                "end": seg.end,
                "timestamp": _ts_fmt(seg.start),
                "text": text,
            })
    return results


def _transcribe_openai_whisper(
    audio_path: str,
    model_size: str,
    language: str | None,
) -> list[dict[str, Any]]:
    """Transcribe with openai-whisper, returning [{timestamp, text}] segments."""
    import whisper

    device = "cuda" if os.getenv("WHISPER_DEVICE", "cpu") == "cuda" else "cpu"
    model = whisper.load_model(model_size, device=device)

    result = model.transcribe(
        audio_path,
        language=language,
        fp16=(device == "cuda"),
    )

    segments = []
    for seg in result.get("segments", []):
        text = seg.get("text", "").strip()
        if text:
            segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "timestamp": _ts_fmt(seg["start"]),
                "text": text,
            })
    return segments


def transcribe_video(
    video_path: str,
    *,
    model_size: str = "",
    language: str | None = None,
) -> dict[str, Any]:
    """Transcribe a video file's audio track to a timestamped transcript.

    Args:
        video_path: Path to the video file (.mp4, .avi, .mkv, .mov, …).
        model_size: Whisper model size (tiny/base/small/medium/large-v3).
                    Default: read WHISPER_MODEL from env, or "base".
        language: Language code (e.g. "zh", "en"). None = auto-detect.

    Returns:
        dict with:
            ok          : True on success
            transcript  : formatted string "[HH:MM:SS] text\\n…"
            segments    : list of {start, end, timestamp, text}
            model       : model size used
            backend     : "faster_whisper" | "openai_whisper"
            duration_s  : total audio duration (approx from last segment)
    """
    if not os.path.exists(video_path):
        return {"ok": False, "error": f"file not found: {video_path}"}

    model_size = model_size or os.getenv("WHISPER_MODEL", "base")
    language = language or os.getenv("WHISPER_LANG", "") or None

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        audio_path = f.name

    try:
        _extract_audio(video_path, audio_path)
    except Exception as exc:
        _cleanup(audio_path)
        return {"ok": False, "error": f"audio extraction failed: {exc}"}

    segments: list[dict[str, Any]] = []
    backend = ""

    try:
        segments = _transcribe_faster_whisper(audio_path, model_size, language)
        backend = "faster_whisper"
    except ImportError:
        try:
            segments = _transcribe_openai_whisper(audio_path, model_size, language)
            backend = "openai_whisper"
        except ImportError:
            _cleanup(audio_path)
            return {
                "ok": False,
                "error": (
                    "Neither faster-whisper nor openai-whisper is installed. "
                    "Run: pip install faster-whisper  (or  pip install openai-whisper)"
                ),
            }
    except Exception as exc:
        _cleanup(audio_path)
        return {"ok": False, "error": f"whisper transcription failed: {exc}"}

    _cleanup(audio_path)

    if not segments:
        return {"ok": True, "transcript": "", "segments": [],
                "model": model_size, "backend": backend, "duration_s": 0}

    lines = [f"[{seg['timestamp']}] {seg['text']}" for seg in segments]
    duration = segments[-1].get("end", 0)

    return {
        "ok": True,
        "transcript": "\n".join(lines),
        "segments": segments,
        "model": model_size,
        "backend": backend,
        "duration_s": round(duration, 1),
    }


def _cleanup(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


async def transcribe_video_async(
    video_path: str,
    *,
    model_size: str = "",
    language: str | None = None,
) -> dict[str, Any]:
    """Async wrapper — runs the CPU-bound transcription in a thread."""
    import asyncio
    return await asyncio.to_thread(
        transcribe_video, video_path,
        model_size=model_size, language=language,
    )