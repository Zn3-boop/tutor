"""轻量按需翻译客户端（Quiz / Flashcard / Diagnostic 跟随语言偏好）。

设计：
  - 复用项目现有 LLM provider 的 base_url / api_key / model（与聊天同一通道）。
  - 只翻译「生成出来的展示文本」（题干/闪卡正面），不翻译知识库 chunk，
    因此不动 DB、不动 ingestion。
  - 技术术语、代码标识符与下划线挖空占位符（______）原样保留，保证答案可校验。
  - 任何异常/超时/校验失败一律回退原文（translated=False），绝不阻断业务。
  - 模块级内存缓存：同一文本不重复调用 LLM。
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

# 加载 .env（client.py -> translation -> services -> app -> server）
_env_file = Path(__file__).parent.parent.parent.parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        pass

logger = logging.getLogger(__name__)

TRANSLATE_ENABLE = os.getenv("TRANSLATE_ENABLE", "false").lower() == "true"
TRANSLATE_SHORT_TIMEOUT = float(os.getenv("TRANSLATE_SHORT_TIMEOUT", "8"))

_SYSTEM_PROMPT = (
    "You are a translator for an educational tutoring system. Translate the "
    "given English text into natural Simplified Chinese.\n"
    "Rules:\n"
    "1. Preserve every underscore placeholder (e.g. ______, ____) exactly as-is.\n"
    "2. Preserve technical terms, keywords, code identifiers, variable names, "
    "numbers and abbreviations in their original English form; do NOT translate them.\n"
    "3. Output only the translated text with no commentary or quotes."
)

_CACHE_MAX = 2000


class TranslateResult:
    """翻译结果：text 始终可安全用于展示；translated 标记是否真正走了 LLM。"""

    __slots__ = ("text", "translated")

    def __init__(self, text: str, translated: bool):
        self.text = text
        self.translated = translated


_cache: dict[str, TranslateResult] = {}


def translation_enabled() -> bool:
    return TRANSLATE_ENABLE


def _provider_config() -> dict[str, str]:
    """读取与聊天同一条 LLM 通道的 base_url/api_key/model。

    优先复用 LLMProvider 单例（包含 ProviderManager 动态配置解析），
    解析失败时降级到 .env 直读 —— 与 provider.py 的降级逻辑一致。
    """
    try:
        from app.services.llm.provider import provider  # noqa: F401
        return {
            "base_url": str(provider.base_url).rstrip("/"),
            "api_key": str(provider.api_key or ""),
            "model": str(provider.model or "glm-5.3-flash"),
        }
    except Exception:
        return {
            "base_url": os.getenv("LLM_BASE_URL", "").rstrip("/"),
            "api_key": os.getenv("LLM_API_KEY", ""),
            "model": os.getenv("LLM_MODEL", "glm-5.3-flash"),
        }


def _looks_english(text: str) -> bool:
    """粗略判断是否为英文文本（避免对已是中文的题面重复翻译）。"""
    if not text:
        return False
    ascii_letters = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return ascii_letters > 0 and ascii_letters / len(text) > 0.35


def translate_text(raw_text: str, target_lang: str = "zh") -> TranslateResult:
    """按需翻译：英文 → 中文。任何失败都回退原文（translated=False）。"""
    if not TRANSLATE_ENABLE or not raw_text or not raw_text.strip():
        return TranslateResult(raw_text, False)
    if not _looks_english(raw_text):
        return TranslateResult(raw_text, False)
    if raw_text in _cache:
        return _cache[raw_text]

    cfg = _provider_config()
    if not cfg["api_key"] or not cfg["base_url"]:
        return TranslateResult(raw_text, False)

    started = time.monotonic()
    try:
        payload: dict[str, Any] = {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": raw_text},
            ],
            "temperature": 0.1,
            "max_tokens": 1500,
        }
        with httpx.Client(timeout=TRANSLATE_SHORT_TIMEOUT) as client:
            resp = client.post(
                f"{cfg['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {cfg['api_key']}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        out = (data["choices"][0]["message"]["content"] or "").strip()
        if not out:
            return TranslateResult(raw_text, False)
        # 长度合理性校验：拒绝明显超长/乱码输出，直接回退原文。
        if len(out) > max(200, len(raw_text) * 5):
            logger.warning(
                "translate output length suspicious (%d chars), fallback",
                len(out),
            )
            return TranslateResult(raw_text, False)
        res = TranslateResult(out, True)
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()
        _cache[raw_text] = res
        return res
    except Exception as exc:
        logger.warning(
            "translate_text failed in %.0fs, fallback to source: %s",
            time.monotonic() - started,
            exc,
        )
        return TranslateResult(raw_text, False)
