"""VLM 图片题目解析服务。

将图片中的题目内容提取为结构化文本，接入 Tutor 问答链路。
仅使用 LangFuse 做观测，不引入 OTel。
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.services.observability.langfuse_client import langfuse_observed
from app.services.vlm.provider import describe_image_fallback

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "请解析图片中的题目内容，提取所有文字和公式。"
    "如果图片包含代码，请完整提取代码。"
    "如果图片包含图表，请描述图表内容。"
    "输出格式：直接输出提取的文本内容，不要添加额外解释。"
)


class VLMQuestionParser:
    """图片题目解析器，调用 VLM 提取文本后送入 Tutor 问答。"""

    def __init__(self, default_prompt: str = _DEFAULT_PROMPT):
        self.default_prompt = default_prompt

    _MOCK_TEXT = "【MOCK DEBUG】图片内题目：Python变量的定义规则"

    @langfuse_observed("vlm.parser.parse_question_image", as_type="chain")
    async def parse_question_image(
        self,
        image: Any,
        *,
        prompt: str | None = None,
        max_new_tokens: int | None = None,
        skip_load: bool = False,
    ) -> dict[str, Any]:
        """解析图片中的题目内容。

        Args:
            image: 图片输入（路径/URL/base64/PIL.Image/bytes）
            prompt: 自定义解析提示词，None 使用默认
            max_new_tokens: 最大生成 token 数
            skip_load: 调试开关，True 时跳过VLM推理，直接返回mock文本

        Returns:
            dict with keys:
              ok: 是否成功
              text: 提取的文本内容
              prompt_used: 实际使用的提示词
              elapsed_ms: 耗时（毫秒）
              error: 错误信息（失败时）
              mock: 是否为mock返回（仅 skip_load=True 时存在）
        """
        used_prompt = prompt or self.default_prompt
        if skip_load:
            logger.info("VLM parse skipped (skip_load=True), returning mock text")
            return {
                "ok": True,
                "text": self._MOCK_TEXT,
                "prompt_used": used_prompt,
                "elapsed_ms": 0.0,
                "error": None,
                "mock": True,
            }
        t0 = time.perf_counter()
        try:
            text = await describe_image_fallback(
                prompt=used_prompt,
                image=image,
                max_new_tokens=max_new_tokens or 512,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            if not text or not text.strip():
                return {
                    "ok": False,
                    "text": "",
                    "prompt_used": used_prompt,
                    "elapsed_ms": round(elapsed, 1),
                    "error": "VLM returned empty result",
                }
            return {
                "ok": True,
                "text": text.strip(),
                "prompt_used": used_prompt,
                "elapsed_ms": round(elapsed, 1),
                "error": None,
            }
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.error(f"VLM parse failed: {exc}")
            return {
                "ok": False,
                "text": "",
                "prompt_used": used_prompt,
                "elapsed_ms": round(elapsed, 1),
                "error": str(exc),
            }


_parser: VLMQuestionParser | None = None


def get_vlm_parser() -> VLMQuestionParser:
    global _parser
    if _parser is None:
        _parser = VLMQuestionParser()
    return _parser