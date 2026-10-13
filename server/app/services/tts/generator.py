"""Edge-TTS based text-to-speech generator."""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_WIN_SAPI_SCRIPT = r"""
Add-Type -AssemblyName System.Speech
$t = [System.IO.File]::ReadAllText($env:ECV_TTS_TEXT, [System.Text.Encoding]::UTF8)
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SetOutputToWaveFile($env:ECV_TTS_OUT)
$s.Speak($t)
$s.Dispose()
"""


def _win_sapi_synthesize(text: str, out_wav: str) -> bool:
    """Synthesize ``text`` into a WAV using Windows' built-in SAPI5 voice.

    Fully offline; used as a fallback when Edge-TTS cannot reach
    speech.platform.bing.com. Returns True only for a non-empty WAV.
    """
    if os.name != "nt":
        return False
    tmp_text: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                         encoding="utf-8", delete=False) as tf:
            tf.write(text)
            tmp_text = tf.name
        env = dict(os.environ)
        env["ECV_TTS_TEXT"] = tmp_text
        env["ECV_TTS_OUT"] = out_wav
        cp = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _WIN_SAPI_SCRIPT],
            capture_output=True, timeout=120, env=env,
        )
        ok = cp.returncode == 0 and os.path.exists(out_wav) and os.path.getsize(out_wav) > 1024
        if not ok and cp.returncode != 0:
            logger.warning("SAPI5 TTS failed rc=%s err=%s",
                           cp.returncode, (cp.stderr or b"")[:160])
        return ok
    except Exception as exc:
        logger.warning("SAPI5 TTS fallback error: %s", exc)
        return False
    finally:
        if tmp_text:
            try:
                os.remove(tmp_text)
            except OSError:
                pass


class TTSService:
    """Generate audio from text using Edge-TTS (Microsoft)."""

    def __init__(self, output_dir: str = ""):
        self.output_dir = output_dir or os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "data", "tts"
        )
        os.makedirs(self.output_dir, exist_ok=True)
        self._voice_map = {
            "zh": "zh-CN-XiaoxiaoNeural",
            "en": "en-US-GuyNeural",
            "mixed": "zh-CN-XiaoxiaoNeural",
        }

    async def generate(
        self,
        text: str,
        lang: str = "zh",
        filename: str = "",
    ) -> dict[str, Any]:
        """Generate audio from text. Returns {ok, path, duration_s}.

        Primary: Microsoft Edge-TTS (online). Fallback: Windows built-in
        SAPI5 (System.Speech, fully offline) so the tutoring voice still works
        when the machine has no route to speech.platform.bing.com.
        """
        if not text or not text.strip():
            return {"ok": False, "error": "empty text"}

        voice = self._voice_map.get(lang, "zh-CN-XiaoxiaoNeural")
        if not filename:
            filename = f"tts_{lang}_{hash(text) & 0xFFFFFFFF:08x}"
        out_path = os.path.join(self.output_dir, filename + ".mp3")

        try:
            import edge_tts  # type: ignore
        except ImportError:
            edge_tts = None  # type: ignore[assignment]

        if edge_tts is not None:
            try:
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(out_path)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    # Estimate duration from text length (~4 chars/sec for Chinese, ~6 for English)
                    char_count = len(text)
                    rate = 4.0 if lang.startswith("zh") else 6.0
                    duration_s = round(char_count / rate, 1)
                    return {
                        "ok": True,
                        "path": out_path,
                        "filename": os.path.basename(out_path),
                        "duration_s": duration_s,
                        "voice": voice,
                    }
            except Exception as exc:  # network failure, service outage, ...
                logger.warning("Edge-TTS generation failed: %s", exc)

        # ---- offline fallback: Windows System.Speech (SAPI5) ----
        wav_path = os.path.join(self.output_dir, filename + ".wav")
        if _win_sapi_synthesize(text, wav_path):
            duration_s = round(len(text) / (4.0 if lang.startswith("zh") else 6.0), 1)
            return {
                "ok": True,
                "path": wav_path,
                "filename": os.path.basename(wav_path),
                "duration_s": duration_s,
                "voice": "SAPI5 (offline)",
            }

        return {"ok": False, "error": "tts service unavailable"}

    async def generate_url(self, text: str, lang: str = "zh") -> str:
        """Generate TTS and return a browser-accessible URL path."""
        result = await self.generate(text, lang=lang)
        if result["ok"]:
            # Return relative path for frontend to use
            return f"/tutor/tts/{result['filename']}"
        return ""


_tts: TTSService | None = None


def get_tts_service() -> TTSService:
    global _tts
    if _tts is None:
        _tts = TTSService()
    return _tts