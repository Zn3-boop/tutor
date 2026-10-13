"""VLM 图片解析服务单元测试。"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def parser():
    from app.services.vlm.parser import VLMQuestionParser
    return VLMQuestionParser()


@pytest.mark.asyncio
async def test_parse_success(parser):
    with patch("app.services.vlm.parser.describe_image_fallback",
               new_callable=AsyncMock, return_value="Python 中 list.append() 的作用是追加元素"):
        result = await parser.parse_question_image("fake_image_data")
    assert result["ok"] is True
    assert "list.append()" in result["text"]
    assert result["elapsed_ms"] >= 0
    assert result["error"] is None


@pytest.mark.asyncio
async def test_parse_empty_result(parser):
    with patch("app.services.vlm.parser.describe_image_fallback",
               new_callable=AsyncMock, return_value=""):
        result = await parser.parse_question_image("fake_image_data")
    assert result["ok"] is False
    assert result["text"] == ""
    assert "empty" in result["error"].lower()


@pytest.mark.asyncio
async def test_parse_vlm_error(parser):
    with patch("app.services.vlm.parser.describe_image_fallback",
               new_callable=AsyncMock, side_effect=RuntimeError("model not loaded")):
        result = await parser.parse_question_image("fake_image_data")
    assert result["ok"] is False
    assert "model not loaded" in result["error"]


@pytest.mark.asyncio
async def test_parse_custom_prompt(parser):
    with patch("app.services.vlm.parser.describe_image_fallback",
               new_callable=AsyncMock, return_value="extracted text") as mock_fallback:
        result = await parser.parse_question_image(
            "fake_image_data", prompt="请提取公式",
        )
    assert result["ok"] is True
    assert result["prompt_used"] == "请提取公式"
    mock_fallback.assert_called_once()
    call_kwargs = mock_fallback.call_args
    assert call_kwargs[1]["prompt"] == "请提取公式"


@pytest.mark.asyncio
async def test_parse_skip_load(parser):
    result = await parser.parse_question_image("fake_image_data", skip_load=True)
    assert result["ok"] is True
    assert "MOCK DEBUG" in result["text"]
    assert result["mock"] is True
    assert result["elapsed_ms"] == 0.0
    assert result["error"] is None


@pytest.mark.asyncio
async def test_parse_skip_load_does_not_call_vlm(parser):
    with patch("app.services.vlm.parser.describe_image_fallback",
               new_callable=AsyncMock) as mock_fallback:
        result = await parser.parse_question_image("fake_image_data", skip_load=True)
    mock_fallback.assert_not_called()
    assert result["mock"] is True


def test_get_vlm_parser_singleton():
    from app.services.vlm.parser import get_vlm_parser
    p1 = get_vlm_parser()
    p2 = get_vlm_parser()
    assert p1 is p2