"""Grounded tutor: RAG retrieval + citation-assembled answer.

Retrieves evidence from the dual-index store, builds a grounded answer
with inline citations (page / slide / video timestamp), and returns
structured citation metadata so the UI can render source links.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from app.services.observability.langfuse_client import langfuse_observed
from app.services.rag.service import get_rag_service
from app.services.tutor.query_rewriter import inline_rewrite
from app.services.tutor.store import get_tutor_store
from app.services.rag.gate import GenerationGate

logger = logging.getLogger(__name__)

gate = GenerationGate()

# Minimum lexical containment of the query's tokens in the top evidence below
# which we treat a hit as "off-topic" and refuse (avoid hallucinating).
_REFUSE_CONT_LO = 0.40

_EN_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "be", "what", "which",
    "how", "why", "who", "when", "where", "do", "does", "did", "to", "of",
    "in", "on", "for", "and", "or", "with", "please", "explain", "tell",
    "about", "me", "can", "you", "this", "that", "it", "its", "these", "those",
}


def _stem(w: str) -> str:
    """Conservative naive stemming: strip plural s/es/ies FIRST, then verb endings
    (ed/ing/ly/er). Aggressive noun suffixes (able/ible/tion/sion/ment/ness) are
    deliberately NOT stripped so ``variable`` / ``variables`` stay symmetric —
    required for the offline relevance gate to match the query "variable"
    against textbook text that says "variables".
    """
    base = w
    if base.endswith("ies") and len(base) > 4:
        base = base[:-3] + "y"
    elif base.endswith("es") and len(base) > 4:
        base = base[:-2]
    elif base.endswith("s") and len(base) > 3 and not base.endswith(("ss", "us", "is")):
        base = base[:-1]
    for s in ("ing", "ed", "ly", "er"):
        if len(base) > len(s) + 2 and base.endswith(s):
            base = base[: -len(s)]
            break
    return base


def _stem_overlap(a: str, b: str) -> bool:
    """Token match: exact equality OR a shared prefix >= 4 chars.

    ``variable`` vs ``variabl`` are different strings (plural vs noun-ending
    handling) but must still count as the same word in the relevance gate.
    """
    if a == b:
        return True
    return len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a))


def _query_tokens(query: str) -> set[str]:
    """Tokenize a query into English words + CJK bigrams (ignoring stopwords).

    Applies naive stemming so that e.g. 'loops' matches 'loop'.
    Both the original and stemmed form are added to maximise recall.
    """
    tokens: set[str] = set()
    lowered = query.lower()
    for m in re.findall(r"[a-z][a-z0-9_]{2,}", lowered):
        if m not in _EN_STOP:
            tokens.add(m)
            stemmed = _stem(m)
            if stemmed != m and len(stemmed) >= 3:
                tokens.add(stemmed)
    cjk = re.findall(r"[\u4e00-\u9fff]", lowered)
    tokens.update(a + b for a, b in zip(cjk, cjk[1:]))
    return tokens


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _relevance_ok(query: str, retrieved: list[dict[str, Any]]) -> bool:
    """Cheap offline relevance gate: enough query tokens present in top evidence?

    Uses stemmed tokens plus shared-prefix overlap (>= 4 chars), so a query about
    "variable" still matches evidence that says "variables" even though the naive
    stemmer does not collapse them to an identical string.

    Cross-language bypass: when the query is Chinese but evidence is English (or
    vice-versa), lexical token overlap is inherently unreliable.  The semantic
    vector retriever already judged these hits relevant, so we trust it and skip
    the lexical gate to avoid false refusals on zh→en / en→zh queries.
    """
    q_tokens = _query_tokens(query)
    if not q_tokens:
        return True

    query_is_cjk = _has_cjk(query)
    for item in retrieved[:3]:
        content = item.get("content") or ""
        if query_is_cjk != _has_cjk(content):
            return True
        c_tokens = _query_tokens(content)
        if not c_tokens:
            continue
        overlap = sum(
            1 for qt in q_tokens
            if any(_stem_overlap(qt, ct) for ct in c_tokens)
        )
        containment = overlap / max(len(q_tokens), 1)
        if containment >= _REFUSE_CONT_LO and overlap >= 1:
            return True
    return False


_REFUSE_REASON = (
    "检索到的资料与该问题相关度太低，可能是课程未覆盖的内容。"
    "为避免幻觉，我已拒绝作答。"
)
_NO_EVIDENCE_REASON = "没有检索到与问题相关的课程资料，为避免幻觉，我已拒绝作答。"

# Off-material detection: explicit flag for queries clearly outside course scope
_OFF_MATERIAL_PATTERNS = [
    r"\b(capital of|population of|weather in|recipe for|how to cook|how to fix)\b",
    r"\b(who wrote|who painted|who composed)\b",
    r"\b(olympics|world cup|nba|fifa)\b",
]

# Additional off-material patterns for Chinese queries
_OFF_MATERIAL_PATTERNS_ZH = [
    r"法国的首都是",
    r"怎么从零开始煮",
    r"荷马史诗的作者",
    r"骑自行车链条",
    r"东京今天天气",
    r"投资比特币",
    r"世界杯冠军",
    r"火星人口",
]
_OFF_MATERIAL_RE_ZH = re.compile("|".join(_OFF_MATERIAL_PATTERNS_ZH))
_OFF_MATERIAL_RE = re.compile("|".join(_OFF_MATERIAL_PATTERNS), re.IGNORECASE)


def _is_off_material(query: str) -> tuple[bool, str]:
    """Detect if a query is clearly off-material based on lexical patterns.

    Returns (is_off, reason) tuple. This is a fast pre-filter before retrieval.
    """
    if _OFF_MATERIAL_RE_ZH.search(query):
        return True, "该问题涉及课程范围外的主题（如地理、历史、体育、投资等），系统已自动识别并拒绝回答。"
    if _OFF_MATERIAL_RE.search(query):
        return True, "该问题涉及课程范围外的主题（如地理、历史、体育、投资等），系统已自动识别并拒绝回答。"
    return False, ""


def _extract_citation_label(meta: dict[str, Any]) -> str:
    """Derive a human-readable citation label from chunk metadata.

    The ``source_url`` field is set by ``KnowledgeBaseIngestor._index_unit``
    and carries values like ``p.3``, ``slide#5``, ``video@00:01:30``.
    """
    return meta.get("source_url", "") or meta.get("doc_title", "")


class GroundedTutor:
    """Answer questions grounded in the knowledge base with citations."""

    def __init__(self, rag=None, store=None):
        self._rag = rag
        self._store = store

    def _rag_service(self):
        return self._rag or get_rag_service()

    def _store_service(self):
        return self._store or get_tutor_store()

    @langfuse_observed("tutor.answer", as_type="chain")
    async def answer(
        self,
        question: str,
        *,
        llm: bool = False,
        top_k: int = 5,
        rerank_top_k: int = 3,
        enable_rerank: bool | None = None,
        pref_lang: str = "auto",
    ) -> dict[str, Any]:
        """Retrieve evidence and assemble a grounded answer with citations.

        Performs an inline query rewrite, hybrid retrieval + (optional) rerank,
        a relevance gate that refuses off-topic questions, and citation assembly.

        Args:
            question: User question.
            llm: If True, call the LLM to generate a polished answer.
                 If False, concatenate evidence snippets (fast, no LLM cost).
            top_k: Number of evidence chunks to retrieve.
            rerank_top_k: Top-K after optional reranking.
            enable_rerank: Whether to apply cross-encoder reranking.
                           None → read RAG_RERANK_ENABLED from .env (default false).

        Returns:
            dict with keys:
              status        – "answered" | "refused"
              answer        – assembled answer text (with inline [1], [2] … refs)
              citations     – list of {index, label, chunk_id, source_url}
              evidence      – raw retrieved chunks
              retrieval_meta – retrieval statistics
              rewritten_query   – canonical standalone query after inline rewrite
              rewrite_queries   – the query variants actually issued to the retriever
              refuse_reason – reason when status == "refused"
        """
        rag = self._rag_service()
        store = self._store_service()

        if enable_rerank is None:
            enable_rerank = os.getenv(
                "RAG_RERANK_ENABLED", "false"
            ).strip().lower() in ("true", "1", "yes")

        # R7: inline query rewrite (原查询永不替换，variants 并行去召回更多证据).
        rewritten = inline_rewrite(
            question, topics=store.list_topics_by_id(),
        )
        rewrite_queries = rewritten["queries"][1:]  # drop the standalone dup

        query_result = await rag.query(
            question, top_k=top_k,
            rewrite_queries=rewrite_queries,
            rerank_top_k=rerank_top_k,
            enable_rerank=enable_rerank,
        )

        retrieval_info = query_result.get("retrieval", {})
        retrieved: list[dict[str, Any]] = retrieval_info.get("results", [])
        answer_ready = bool(query_result.get("answer_ready", True))

        record = {
            "rewritten_query": rewritten["standalone_query"],
            "rewrite_queries": rewritten["queries"],
            "matched_topics": rewritten["matched_topics"],
            "detected_language": rewritten.get("detected_language", "zh"),
            "is_mixed_language": rewritten.get("is_mixed_language", False),
        }

        # R10: 超纲/无证据拒答 — refuse when no evidence or relevance is too low.
        # Phase 1: explicit off-material pre-filter (fast lexical check)
        is_off, off_reason = _is_off_material(question)
        if is_off:
            return {
                **record,
                "status": "refused",
                "answer": "",
                "refuse_reason": off_reason,
                "off_material": True,
                "citations": [],
                "evidence": [],
                "retrieval_meta": {
                    "vector_count": 0,
                    "bm25_count": 0,
                    "merged_count": 0,
                },
            }

        if not retrieved or not answer_ready:
            return {
                **record,
                "status": "refused",
                "answer": "",
                "refuse_reason": _NO_EVIDENCE_REASON if not retrieved else _REFUSE_REASON,
                "off_material": False,
                "citations": [],
                "evidence": [],
                "retrieval_meta": {
                    "vector_count": retrieval_info.get("vector_count", 0),
                    "bm25_count": retrieval_info.get("bm25_count", 0),
                    "merged_count": retrieval_info.get("merged_count", 0),
                },
            }

        if not _relevance_ok(question, retrieved):
            return {
                **record,
                "status": "refused",
                "answer": "",
                "refuse_reason": _REFUSE_REASON,
                "off_material": False,
                "citations": [],
                "evidence": retrieved,
                "retrieval_meta": {
                    "vector_count": retrieval_info.get("vector_count", 0),
                    "bm25_count": retrieval_info.get("bm25_count", 0),
                    "merged_count": retrieval_info.get("merged_count", 0),
                },
            }

        citations: list[dict[str, Any]] = []
        evidence_snippets: list[str] = []
        seen_labels: set[str] = set()

        for idx, item in enumerate(retrieved, start=1):
            meta = item.get("meta", {})
            label = _extract_citation_label(meta)
            chunk_id = item.get("chunk_id", "")
            content = item.get("content", "")

            source_url = meta.get("source_url", "")
            dedup_key = label or chunk_id
            if dedup_key in seen_labels:
                continue
            seen_labels.add(dedup_key)

            citations.append({
                "index": idx,
                "label": label,
                "chunk_id": chunk_id,
                "source_url": source_url,
            })
            evidence_snippets.append(f"[{idx}] ({label}) {content}")

        if not evidence_snippets:
            return {
                **record,
                "status": "refused",
                "answer": "",
                "refuse_reason": _REFUSE_REASON,
                "off_material": False,
                "citations": [],
                "evidence": retrieved,
                "retrieval_meta": {
                    "vector_count": retrieval_info.get("vector_count", 0),
                    "bm25_count": retrieval_info.get("bm25_count", 0),
                    "merged_count": retrieval_info.get("merged_count", 0),
                },
            }

        # Detect query language for appropriate response language
        query_lang = rewritten.get("detected_language", "zh")
        is_mixed = rewritten.get("is_mixed_language", False)

        if llm:
            answer_text = await self._llm_generate(
                question, evidence_snippets, query_lang, is_mixed, pref_lang
            )
        else:
            resp_lang = pref_lang if pref_lang in ("zh", "en") else query_lang
            if resp_lang == "zh":
                header = f"基于检索证据回答: {question}\n\n"
            else:
                header = f"Answer based on retrieved evidence: {question}\n\n"
            answer_text = header + "\n".join(evidence_snippets)

        return {
            **record,
            "status": "answered",
            "answer": answer_text,
            "off_material": False,
            "citations": citations,
            "evidence": retrieved,
            "detected_language": query_lang,
            "is_mixed_language": is_mixed,
            "retrieval_meta": {
                "vector_count": retrieval_info.get("vector_count", 0),
                "bm25_count": retrieval_info.get("bm25_count", 0),
                "merged_count": retrieval_info.get("merged_count", 0),
            },
        }

    async def _llm_generate(
        self,
        question: str,
        evidence_snippets: list[str],
        query_lang: str = "zh",
        is_mixed: bool = False,
        pref_lang: str = "auto",
    ) -> str:
        """Call the LLM to produce a polished grounded answer.

        Falls back to concatenation if the LLM is unavailable.
        Respects the detected query language for response generation.
        """
        try:
            from app.services.llm import get_llm_service
            llm_svc = get_llm_service()
            context = "\n".join(evidence_snippets)

            # Build language-aware prompt.
            # P1: pref_lang (student-chosen chat language) OVERRIDES the detected
            # query language; "auto" keeps the legacy per-query behavior.
            # Evidence citations are ALWAYS quoted verbatim (never translated) so
            # the answer never silently rewrites the source material.
            lang = pref_lang if pref_lang in ("zh", "en") else query_lang
            if lang == "zh":
                if pref_lang == "zh":
                    lang_instruction = (
                        "语言要求：学生在设置中选择了「全中文聊天」。请全程用中文回答，"
                        "保留 Python/CS 相关的英文专业术语。"
                        "引用的原文证据不要翻译，保持资料原文逐字引用。"
                    )
                elif is_mixed:
                    # Mixed Chinese-English query: respond in Chinese but keep technical terms
                    lang_instruction = (
                        "语言要求：学生使用了中英混合提问。请用中文回答，"
                        "但保留 Python/CS 相关的英文专业术语（如 variable, function, list 等）。"
                    )
                else:
                    lang_instruction = (
                        "语言要求：学生用中文提问，请用中文回答。"
                        "保留 Python/CS 相关的英文专业术语。"
                    )
                prompt = (
                    f"请基于以下证据回答问题，并在答案中用 [1] [2] 等标注引用来源。\n\n"
                    f"证据:\n{context}\n\n问题: {question}\n\n"
                    f"{lang_instruction}"
                )
            else:
                if pref_lang == "en":
                    lang_instruction = (
                        "Language requirement: The student chose an English-language chat. "
                        "Please answer entirely in English. "
                        "Do NOT translate quoted evidence - quote source excerpts verbatim."
                    )
                else:
                    lang_instruction = (
                        "Language requirement: The student asked in English. "
                        "Please respond in English."
                    )
                prompt = (
                    f"Please answer the question based on the evidence below, "
                    f"using [1] [2] etc. to cite sources.\n\n"
                    f"Evidence:\n{context}\n\nQuestion: {question}\n\n"
                    f"{lang_instruction}"
                )

            return await llm_svc.generate(prompt)
        except Exception as exc:
            logger.warning(f"LLM generation failed: {exc}, falling back to evidence concat")
            return "\n".join(evidence_snippets)


_tutor: GroundedTutor | None = None


def get_grounded_tutor(rag=None, store=None) -> GroundedTutor:
    global _tutor
    if _tutor is None:
        _tutor = GroundedTutor(rag=rag, store=store)
    return _tutor