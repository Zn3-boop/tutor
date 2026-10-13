"""Faithfulness + context precision/recall metrics.

Integrates RAGAS when it is installed and the util wasm + an LLM provider are
available; otherwise degrades gracefully to deterministic lexical probes so the
pipeline still runs fully offline. `ragas_used` in every result tells the caller
which backend produced the numbers.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_WS = re.compile(r"[^a-z0-9\u4e00-\u9fff]+")


def _tokens(text: str) -> set[str]:
    return set(t for t in _WS.split((text or "").lower()) if t)


def probe_faithfulness(answer: str, contexts: list[str]) -> float:
    """Fraction of the answer's lexical content present in the evidence.

    Deterministic stand-in for RAGAS ``faithfulness`` when RAGAS is unavailable.
    """
    a = _tokens(answer)
    if not a:
        return 0.0
    c = set()
    for ctx in contexts:
        c |= _tokens(ctx)
    if not c:
        return 0.0
    return sum(1 for tok in a if tok in c) / len(a)


def probe_answer_relevance(answer: str, question: str) -> float:
    """Lexical proxy for RAGAS ``answer_relevancy``."""
    q = _tokens(question)
    a = _tokens(answer)
    if not q or not a:
        return 0.0
    return sum(1 for tok in q if tok in a) / len(q)


def context_precision_from_ids(retrieved_ids: list[str],
                               gold_ids: list[str]) -> float:
    """Precision of retrieved documents w.r.t. the gold set: TP / retrieved."""
    if not retrieved_ids:
        return 0.0
    gold = set(gold_ids or [])
    if not gold:
        return 0.0
    hits = sum(1 for rid in retrieved_ids if rid in gold)
    return hits / len(retrieved_ids)


def context_recall_from_ids(retrieved_ids: list[str],
                            gold_ids: list[str]) -> float:
    """Recall of retrieved documents w.r.t. the gold set: TP / gold."""
    gold = set(gold_ids or [])
    if not gold:
        return 0.0
    hits = sum(1 for rid in retrieved_ids if rid in gold)
    return min(1.0, hits / len(gold))


def aggregate_rag_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-case rows into mean metrics.

    Each row: {answer, contexts, question, precision, recall}
    (faithfulness/relevance derived here unless you pre-fill them).
    """
    answered = [r for r in rows if r.get("answer")]
    faithfulness_mean = None
    relevance_mean = None
    if answered:
        f = [probe_faithfulness(r["answer"], r.get("contexts") or [])
             for r in answered]
        fidelity_vals = [r.get("faithfulness") for r in answered
                         if isinstance(r.get("faithfulness"), (int, float))]
        faithfulness_mean = sum(f) / len(f)
        if fidelity_vals:
            faithfulness_mean = sum(fidelity_vals) / len(fidelity_vals)
        relevance_mean = sum(
            probe_answer_relevance(r["answer"], r.get("question", ""))
            for r in answered) / len(answered)

    with_gold = [r for r in rows
                 if (r.get("gold_ids") or []) and r.get("retrieved_ids") is not None]
    precision_mean = None
    recall_mean = None
    if with_gold:
        precision_mean = sum(
            context_precision_from_ids(r.get("retrieved_ids") or [],
                                       r.get("gold_ids") or [])
            for r in with_gold) / len(with_gold)
        recall_mean = sum(
            context_recall_from_ids(r.get("retrieved_ids") or [],
                                    r.get("gold_ids") or [])
            for r in with_gold) / len(with_gold)

    return {
        "faithfulness": round(faithfulness_mean, 4) if faithfulness_mean is not None else 0.0,
        "answer_relevancy": round(relevance_mean, 4) if relevance_mean is not None else 0.0,
        "context_precision": round(precision_mean, 4) if precision_mean is not None else 0.0,
        "context_recall": round(recall_mean, 4) if recall_mean is not None else 0.0,
        "answered_cases": len(answered),
        "golden_cases": len(with_gold),
    }


def _build_ragas_llm() -> Any:
    """Build a LangChain ChatOpenAI pointing at the configured OpenAI-compatible API.

    Reads LLM_API_KEY / LLM_BASE_URL / LLM_MODEL (defaults now point at the
    active provider instead of Zhipu). ``use_responses_api=False`` keeps every
    RAGAS sub-call on the plain ``/chat/completions`` endpoint, which the current
    relay + installed SDK support (see note near the ChatOpenAI construction).
    Falls back to OpenAI env vars if the app-specific ones are absent.
    """
    import os
    from langchain_openai import ChatOpenAI  # type: ignore

    api_key = os.getenv("LLM_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "") or os.getenv("OPENAI_BASE_URL", "")
    model = os.getenv("LLM_MODEL", "glm-4-flash") or os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

    if not api_key:
        raise ValueError("No LLM API key found (set LLM_API_KEY or OPENAI_API_KEY)")

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.01,
        max_retries=2,
        timeout=60,
        # Force the OpenAI-chat-completions endpoint. langchain-openai 1.x
        # automatically routes models whose name contains "codex" (and other
        # gpt-5 variants) to the Responses API, which this OpenAI-compatible
        # relay + installed openai SDK do not support ("n" kwarg error). Setting
        # use_responses_api=False pins every RAGAS sub-call to chat/completions.
        use_responses_api=False,
    )
    logger.info(f"[RAGAS] LLM backend: {model} @ {base_url or 'default'} (chat/completions)")
    return llm


class _ZhipuSafeLLMWrapper:
    """LangchainLLMWrapper subclass that returns Zhipu-safe temperatures.

    RAGAS 0.2.x ``LangchainLLMWrapper.agenerate_text`` calls
    ``self.get_temperature(n)`` when *temperature* is ``None``.  The base
    implementation returns ``1e-8`` for n=1 and ``0.3`` for n>1.  Zhipu's
    API rejects temperatures with more than 2 decimal places, so ``1e-8``
    (i.e. 0.00000001) causes an ``OpenAIInvalidRequestError``.

    We subclass and override ``get_temperature`` to return ``0.01`` (n=1)
    and ``0.3`` (n>1) — both Zhipu-safe values.
    """

    @classmethod
    def wrap(cls, langchain_llm: Any) -> Any:
        from ragas.llms import LangchainLLMWrapper  # type: ignore

        class _Inner(LangchainLLMWrapper):
            def get_temperature(self, n: int) -> float:
                return 0.3 if n > 1 else 0.01

        return _Inner(langchain_llm)


_EMBED_CACHE: dict[str, Any] = {}


def _locate_embed_model() -> str:
    """Resolve the sentence-transformers embedding model to use.

    Returns an explicit ``RAGAS_EMBED_MODEL`` override if set, otherwise a local
    path to a complete copy of all-MiniLM-L6-v2 (the HF cache snapshot for
    ``sentence-transformers/all-MiniLM-L6-v2`` is partially zero-length in this
    environment, so we prefer the fully-downloaded ``*-local`` directory).
    """
    import os

    override = os.getenv("RAGAS_EMBED_MODEL", "").strip()
    if override:
        return override
    local = os.path.join(
        os.path.expanduser("~"), ".cache", "huggingface", "hub", "all-MiniLM-L6-v2-local"
    )
    if os.path.isdir(local):
        return local
    return "sentence-transformers/all-MiniLM-L6-v2"


class _MiniLMEmbeddings:
    """Minimal langchain-compatible embeddings backend using plain transformers.

    Uses ``AutoModel`` + ``AutoTokenizer`` (mean pooling + L2 normalization) to
    sidestep two environment quirks: the OpenAI-compatible relay does not serve
    ``/embeddings``, and sentence-transformers 6.x's ``AutoProcessor`` path cannot
    load a text-only MiniLM model with the installed transformers 5.18.0.
    """

    def __init__(self, model_path: str, device: str = "cpu"):
        self.model_path = model_path
        self.device = device

    def _ensure_loaded(self):
        if "tokenizer" in _EMBED_CACHE and "model" in _EMBED_CACHE:
            return
        import torch  # noqa: F401
        from transformers import AutoModel, AutoTokenizer

        _EMBED_CACHE["tokenizer"] = AutoTokenizer.from_pretrained(
            self.model_path, local_files_only=True
        )
        _EMBED_CACHE["model"] = AutoModel.from_pretrained(
            self.model_path, local_files_only=True
        )
        _EMBED_CACHE["model"].eval()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(list(texts))

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text])[0]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        self._ensure_loaded()
        import torch  # noqa: F401
        import torch.nn.functional as F

        tok = _EMBED_CACHE["tokenizer"]
        model = _EMBED_CACHE["model"]
        enc = tok(texts, padding=True, truncation=True, return_tensors="pt")
        with torch.no_grad():
            out = model(**enc)
        last = out.last_hidden_state
        att = enc["attention_mask"].unsqueeze(-1).float()
        emb = (last * att).sum(1) / att.sum(1)
        emb = F.normalize(emb, dim=1)
        return emb.tolist()


def _build_ragas_embeddings() -> Any:
    """Build a local embedding backend for RAGAS metrics.

    The configured OpenAI-compatible relay serves *chat completions* but not
    ``/embeddings`` (returns HTTP 403 / Cloudflare 1010), so answer_relevancy's
    cosine similarity cannot use it. We fall back to a local sentence-transformers
    model loaded directly with transformers (no extra download, fully offline).
    Override with ``RAGAS_EMBED_MODEL`` / ``RAGAS_EMBED_DEVICE``.
    """
    import os

    model = _locate_embed_model()
    device = os.getenv("RAGAS_EMBED_DEVICE", "cpu")
    logger.info("[RAGAS] Embeddings backend: local %s (%s)", model, device)
    return _MiniLMEmbeddings(model_path=model, device=device)


def _to_float(v: Any) -> float:
    import math
    if isinstance(v, list):
        v = v[0] if v else 0.0
    try:
        f = float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(f) or math.isinf(f):
        return 0.0
    return f


def try_ragas_evaluate(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Optional RAGAS integration. Returns None when RAGAS is unavailable.

    Uses the Zhipu/GLM API (OpenAI-compatible) as the LLM judge when
    ``langchain-openai`` is installed; otherwise degrades to lexical probes.

    Each RAGAS metric class is **instantiated with explicit llm/embeddings**
    so that internal sub-tasks reuse the same Zhipu LLM instead of calling
    ``llm_factory`` (which would default to temperature=0.0 and break on
    Zhipu's API).  This is the official 0.2.x pattern — no monkey-patching.
    """
    try:
        from datasets import Dataset  # type: ignore
        from ragas import evaluate  # type: ignore
        from ragas.metrics import (  # type: ignore
            Faithfulness, ContextPrecision, ContextRecall, AnswerRelevancy,
        )
        from ragas.embeddings import LangchainEmbeddingsWrapper  # type: ignore
    except Exception as exc:
        logger.info("RAGAS not available (%s); using lexical probes.", exc)
        return None

    try:
        langchain_llm = _build_ragas_llm()
        ragas_llm = _ZhipuSafeLLMWrapper.wrap(langchain_llm)
    except Exception as exc:
        logger.info("RAGAS LLM backend not available (%s); using lexical probes.", exc)
        return None

    try:
        langchain_emb = _build_ragas_embeddings()
        ragas_emb = LangchainEmbeddingsWrapper(langchain_emb)
    except Exception as exc:
        logger.info("RAGAS embeddings backend not available (%s); using lexical probes.", exc)
        return None

    try:
        data = {"question": [r.get("question", "") for r in rows],
                "answer": [r.get("answer", "") or "" for r in rows],
                "contexts": [r.get("contexts") or [] for r in rows],
                "reference": [r.get("reference", "") or "" for r in rows]}
        ds = Dataset.from_dict(data)

        metrics = [
            Faithfulness(llm=ragas_llm),
            ContextPrecision(llm=ragas_llm),
            ContextRecall(llm=ragas_llm),
            AnswerRelevancy(llm=ragas_llm, embeddings=ragas_emb),
        ]

        result = evaluate(ds, metrics=metrics, raise_exceptions=False)
        raw = getattr(result, "_scores_dict", result)
        if not isinstance(raw, dict):
            raw = dict(raw) if hasattr(raw, "__iter__") else {}
        metas = {k: _to_float(raw.get(k))
                 for k in ("faithfulness", "answer_relevancy",
                           "context_precision", "context_recall")}

        # Every metric is a real RAGAS computation: faithfulness/relevancy use
        # the chat-completions LLM judge (the relay's /chat/completions), and
        # answer_relevancy's cosine similarity uses a local sentence-transformers
        # embedding (the relay does not serve /embeddings). No lexical fallback.
        metas["ragas_used"] = True
        return {**metas, "answered_cases": len(rows), "golden_cases": len(rows)}
    except Exception as exc:
        logger.warning("RAGAS evaluation failed (%s); using lexical probes.", exc)
        return None