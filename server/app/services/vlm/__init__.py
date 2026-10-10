from __future__ import annotations

from app.services.vlm.provider import (
    VLMProvider,
    VLMError,
    provider,
    CloudVLMProvider,
    cloud_provider,
    describe_image_fallback,
)

__all__ = [
    "VLMProvider",
    "VLMError",
    "get_vlm_provider",
    "provider",
    "CloudVLMProvider",
    "cloud_provider",
    "describe_image_fallback",
]


def get_vlm_provider() -> VLMProvider:
    return provider