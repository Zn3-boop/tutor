"""TTS (Text-to-Speech) service for audio tutoring."""
from .generator import get_tts_service, TTSService

__all__ = ["TTSService", "get_tts_service"]