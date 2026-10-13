# LLM service exports
from .provider import provider, LLMProvider
from .generator import generate_structured, GENERATOR_SYSTEM_PROMPT
from .orchestrator import run_simple_generation, run_agent_workflow

__all__ = [
    "provider", "LLMProvider", "generate_structured",
    "GENERATOR_SYSTEM_PROMPT", "run_simple_generation", "run_agent_workflow",
]

# Source-grounded tutor persona for the simple chat path. A non-empty system
# message is required: several OpenAI-compatible providers reject a request
# whose system message has empty content with HTTP 400 ("message content must
# not be empty"), which previously made every LLM chat silently fall back to
# raw evidence concatenation.
_TUTOR_SYSTEM_PROMPT = (
    "你是 ECV-Tutor，一个以课程资料为证据源的自适应编程辅导老师（2026 多模态 "
    "AI 黑客松 Track D）。回答时必须只依据用户提供的证据片段作答，不得编造事实；"
    "当证据支持某个结论时，用 [1]、[2] 等编号标注来源。回答要清晰、简洁、有教学价值，"
    "中文问题用中文回答，英文问题用英文回答。若证据不足，请明确说明无法回答。"
)


def get_llm_service():
    """Return a simple LLM service wrapper for legacy code."""
    class SimpleLLMService:
        def __init__(self):
            self._provider = provider

        async def generate(self, prompt: str, **kwargs) -> str:
            return await self._provider.chat(
                system_prompt=_TUTOR_SYSTEM_PROMPT,
                user_prompt=prompt,
                **kwargs,
            )

    return SimpleLLMService()

