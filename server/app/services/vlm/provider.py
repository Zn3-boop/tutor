from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_env_file = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)


class VLMError(RuntimeError):
    """Raised when the local VLM fails."""


class VLMProvider:
    """
    [DISABLED by default] Local multimodal vision-language model.

    Set VLM_ENABLED=true to re-enable. Kept for future extension — the
    transformers-based Qwen2.5-VL loader can be restored when GPU / model
    resources are available.

    Original doc:
      Local multimodal vision-language model (loaded via transformers; CPU/GPU
      auto-detected). Replaces the vLLM approach so machines without a GPU can
      load small models in the Qwen2.5-VL-3B-Instruct class. The model loads
      lazily on first use, and inference is offloaded to a thread pool to avoid
      blocking the event loop.

    Environment variables:
        VLM_ENABLED           enable/disable, default "false"
        VLM_MODEL             HF model name, default "Qwen/Qwen2.5-VL-3B-Instruct"
        VLM_DEVICE            "cpu" / "cuda" / "auto", default "cpu"
        VLM_MAX_NEW_TOKENS    max generated tokens, default 256
        VLM_MAX_IMAGE_SIDE    resize image longest edge (faster on CPU), default 640; 0 disables
        VLM_TORCH_DTYPE       "auto" / "float32" / "bfloat16" / "float16"
    """

    def __init__(self) -> None:
        self.model_path = os.getenv("VLM_MODEL_PATH", "").strip()
        self.model_name = self.model_path or os.getenv("VLM_MODEL", "Qwen/Qwen2.5-VL-3B-Instruct")
        self.device = os.getenv("VLM_DEVICE", "cpu")
        self.max_new_tokens = int(os.getenv("VLM_MAX_NEW_TOKENS", "256"))
        self.max_image_side = int(os.getenv("VLM_MAX_IMAGE_SIDE", "640"))
        self.torch_dtype = os.getenv("VLM_TORCH_DTYPE", "auto")
        self._model = None
        self._processor = None
        self._load_lock = asyncio.Lock()
        self._is_loading = False
        self._load_error: str | None = None

    @property
    def enabled(self) -> bool:
        return os.getenv("VLM_ENABLED", "false").strip().lower() == "true"

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def is_loading(self) -> bool:
        return self._is_loading

    @property
    def load_error(self) -> str | None:
        return self._load_error

    @property
    def status(self) -> str:
        if self.loaded:
            return "loaded"
        if self._is_loading:
            return "warming"
        if self._load_error:
            return "failed"
        return "idle"

    async def warmup(self) -> None:
        """Trigger model loading in a background thread (non-blocking).

        Uses asyncio.to_thread so the CPU-heavy _load() does not block
        the async event loop.  Safe to call multiple times — concurrent
        calls are deduplicated by _load_lock.
        """
        if self.loaded or self._is_loading:
            return
        await self._ensure_loaded()

    async def describe_image(
        self,
        *,
        prompt: str,
        image: Any,
        max_new_tokens: int | None = None,
    ) -> str:
        """Run a visual question-answer over a single image.

        ``image`` may be:
            - a local file path (str / Path)
            - an http(s) URL
            - a base64 string (optionally with the data:image prefix)
            - a PIL.Image object
        """
        if not self.enabled:
            raise VLMError("VLM is disabled. Set VLM_ENABLED=true.")
        if self._is_loading:
            raise VLMError("VLM model is warming up, please retry in a moment.")
        if self._load_error and not self.loaded:
            raise VLMError(f"VLM model failed to load: {self._load_error}")
        await self._ensure_loaded()
        return await asyncio.to_thread(
            self._generate, prompt, image, max_new_tokens or self.max_new_tokens
        )

    async def _ensure_loaded(self) -> None:
        async with self._load_lock:
            if self._model is not None:
                return
            self._is_loading = True
            self._load_error = None
            try:
                await asyncio.to_thread(self._load)
            except Exception as exc:
                self._load_error = str(exc)
                logger.error(f"[VLM] model load failed: {exc}")
                raise
            finally:
                self._is_loading = False

    def _load(self) -> None:
        import torch
        from transformers import Qwen2_5_VLForConditionalGeneration

        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        load_from = self.model_name
        logger.info(f"[VLM] loading {load_from} on {self.device} (offline) ...")
        dtype = "auto" if self.torch_dtype == "auto" else getattr(torch, self.torch_dtype)

        self._processor = self._load_processor(load_from)
        self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            load_from,
            dtype=dtype,
            device_map=self.device,
            low_cpu_mem_usage=True,
            local_files_only=True,
        )
        self._model.eval()
        logger.info("[VLM] model loaded.")

    @staticmethod
    def _load_processor(model_dir: str):
        from transformers import Qwen2_5_VLProcessor

        try:
            return Qwen2_5_VLProcessor.from_pretrained(
                model_dir, local_files_only=True,
            )
        except ValueError as e:
            if "Unrecognized image processor" not in str(e):
                raise
            logger.warning("[VLM] Qwen2_5_VLProcessor failed (old preprocessor_config), building manually...")
            from transformers import Qwen2VLImageProcessor, Qwen2VLProcessor, AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
            image_processor = Qwen2VLImageProcessor.from_pretrained(model_dir, local_files_only=True)
            return Qwen2VLProcessor(image_processor=image_processor, tokenizer=tokenizer)

    def _to_pil(self, image: Any):
        from PIL import Image

        if isinstance(image, Image.Image):
            pil = image.convert("RGB")
        elif isinstance(image, (bytes, bytearray)):
            pil = Image.open(io.BytesIO(image)).convert("RGB")
        elif isinstance(image, Path):
            pil = Image.open(image).convert("RGB")
        elif isinstance(image, str):
            s = image
            if s.startswith("data:image"):
                s = s.split(",", 1)[1]
                pil = Image.open(io.BytesIO(base64.b64decode(s))).convert("RGB")
            elif os.path.exists(s):
                pil = Image.open(s).convert("RGB")
            elif s.startswith(("http://", "https://")):
                import httpx
                resp = httpx.get(s, timeout=30)
                resp.raise_for_status()
                pil = Image.open(io.BytesIO(resp.content)).convert("RGB")
            else:
                pil = Image.open(io.BytesIO(base64.b64decode(s))).convert("RGB")
        else:
            raise VLMError(f"Unsupported image type: {type(image)}")

        if self.max_image_side > 0 and max(pil.size) > self.max_image_side:
            pil.thumbnail((self.max_image_side, self.max_image_side))
        return pil

    def _to_image_ref(self, image: Any) -> Any:
        if isinstance(image, str):
            return image
        if isinstance(image, Path):
            return str(image)
        pil = self._to_pil(image)
        buf = io.BytesIO()
        pil.save(buf, format="JPEG")
        return base64.b64encode(buf.getvalue()).decode()

    def _generate(self, prompt: str, image: Any, max_new_tokens: int) -> str:
        import torch
        from qwen_vl_utils import process_vision_info

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": self._to_image_ref(image)},
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        text = self._processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self._processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            return_tensors="pt",
        ).to(self._model.device)

        with torch.no_grad():
            generated = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )
        new_tokens = generated[:, inputs["input_ids"].shape[1]:]
        result = self._processor.batch_decode(new_tokens, skip_special_tokens=True)[0]
        return result.strip()


class CloudVLMProvider:
    """Cloud-based VLM fallback using OpenAI-compatible vision API (e.g. Zhipu GLM-4V).

    When the local Qwen2.5-VL model is unavailable (no GPU / model not downloaded),
    this provider calls a cloud vision API instead. It reuses LLM_API_KEY /
    LLM_BASE_URL from .env, or dedicated VLM_CLOUD_* vars if set.

    Environment variables:
        VLM_CLOUD_API_KEY   API key (falls back to LLM_API_KEY)
        VLM_CLOUD_BASE_URL  API base URL (falls back to LLM_BASE_URL)
        VLM_CLOUD_MODEL     Model name (default: glm-4v-flash)
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("VLM_CLOUD_API_KEY", "") or os.getenv("LLM_API_KEY", "")
        self.base_url = (
            os.getenv("VLM_CLOUD_BASE_URL", "")
            or os.getenv("LLM_BASE_URL", "")
        )
        self.model = os.getenv("VLM_CLOUD_MODEL", "glm-4v-flash")
        self.max_image_side = int(os.getenv("VLM_MAX_IMAGE_SIDE", "1280"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.base_url)

    async def describe_image(
        self,
        *,
        prompt: str,
        image: Any,
        max_new_tokens: int | None = None,
    ) -> str:
        if not self.enabled:
            raise VLMError("Cloud VLM not configured (need VLM_CLOUD_API_KEY or LLM_API_KEY).")
        pil = self._to_pil(image)
        b64 = self._pil_to_b64(pil)
        return await self._call_api(prompt, b64, max_new_tokens or 256)

    def _to_pil(self, image: Any):
        from PIL import Image

        if isinstance(image, Image.Image):
            pil = image.convert("RGB")
        elif isinstance(image, (bytes, bytearray)):
            pil = Image.open(io.BytesIO(image)).convert("RGB")
        elif isinstance(image, Path):
            pil = Image.open(image).convert("RGB")
        elif isinstance(image, str):
            s = image
            if s.startswith("data:image"):
                s = s.split(",", 1)[1]
                pil = Image.open(io.BytesIO(base64.b64decode(s))).convert("RGB")
            elif os.path.exists(s):
                pil = Image.open(s).convert("RGB")
            elif s.startswith(("http://", "https://")):
                import httpx
                resp = httpx.get(s, timeout=30)
                resp.raise_for_status()
                pil = Image.open(io.BytesIO(resp.content)).convert("RGB")
            else:
                pil = Image.open(io.BytesIO(base64.b64decode(s))).convert("RGB")
        else:
            raise VLMError(f"Unsupported image type: {type(image)}")

        if self.max_image_side > 0 and max(pil.size) > self.max_image_side:
            pil.thumbnail((self.max_image_side, self.max_image_side))
        return pil

    def _pil_to_b64(self, pil) -> str:
        buf = io.BytesIO()
        pil.save(buf, format="JPEG")
        return base64.b64encode(buf.getvalue()).decode()

    async def _call_api(self, prompt: str, image_b64: str, max_tokens: int) -> str:
        import httpx

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


cloud_provider = CloudVLMProvider()


async def describe_image_fallback(*, prompt: str, image: Any, max_new_tokens: int | None = None) -> str:
    """Try cloud VLM first, fall back to local, return '' on all failures.

    Order is cloud → local: on CPU boxes the 3B local model is frequently
    memory-starved (OOM mid-load), so waiting for it to crash on every call
    makes ingestion stall. When a cloud vision API is configured it is the
    fast path; the local model remains the offline fallback.
    """
    for prov in (cloud_provider, provider):
        if not prov.enabled:
            continue
        try:
            return await prov.describe_image(prompt=prompt, image=image, max_new_tokens=max_new_tokens)
        except Exception as exc:
            logger.debug(f"[VLM] {type(prov).__name__} failed: {exc}; trying next")
    return ""


provider = VLMProvider()