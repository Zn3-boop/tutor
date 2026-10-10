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
    """Naive suffix-stripping so 'loops' matches 'loop', 'working' matches 'work'."""
    for s in ("ing", "tion", "sion", "ment", "ness", "able", "ible"):
        if len(w) > len(s) + 2 and w.endswith(s):
            return w[: -len(s)]
    for s in ("ed", "ly", "er", "es"):
        if len(w) > len(s) + 2 and w.endswith(s):
            return w[: -len(s)]
    if w.endswith("s") and len(w) > 3 and w[-2] != "s":
        return w[:-1]
    return w


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


def _relevance_ok(query: str, retrieved: list[dict[str, Any]]) -> bool:
    """Cheap offline relevance gate: enough query tokens present in top evidence?"""
    q_tokens = _query_tokens(query)
    if not q_tokens:
        return True
    for item in retrieved[:3]:
        c_tokens = _query_tokens(item.get("content") or "")
        if not c_tokens:
            continue
        overlap = len(q_tokens & c_tokens)
        containment = overlap / max(len(q_tokens), 1)
        if containment >= _REFUSE_CONT_LO and overlap >= 1:
            return True
    return False


_REFUSE_REASON = (
    "检索到的资料与该问题相关度太低，可能是课程未覆盖的内容。"
    "为避免幻觉，我已拒绝作答。"
)
_NO_EVIDENCE_REASON = "没有检索到与问题相关的课程资料，为避免幻觉，我已拒绝作答。"


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
        }

        # R10: 超纲/无证据拒答 — refuse when no evidence or relevance is too low.
        if not retrieved or not answer_ready:
            return {
                **record,
                "status": "refused",
                "answer": "",
                "refuse_reason": _NO_EVIDENCE_REASON if not retrieved else _REFUSE_REASON,
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
                "citations": [],
                "evidence": retrieved,
                "retrieval_meta": {
                    "vector_count": retrieval_info.get("vector_count", 0),
                    "bm25_count": retrieval_info.get("bm25_count", 0),
                    "merged_count": retrieval_info.get("merged_count", 0),
                },
            }

        if llm:
            answer_text = await self._llm_generate(question, evidence_snippets)
        else:
            header = f"基于检索证据回答: {question}\n\n"
            answer_text = header + "\n".join(evidence_snippets)

        return {
            **record,
            "status": "answered",
            "answer": answer_text,
            "citations": citations,
            "evidence": retrieved,
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
    ) -> str:
        """Call the LLM to produce a polished grounded answer.

        Falls back to concatenation if the LLM is unavailable.
        """
        try:
            from app.services.llm import get_llm_service
            llm_svc = get_llm_service()
            context = "\n".join(evidence_snippets)
            prompt = (
                f"请基于以下证据回答问题，并在答案中用 [1] [2] 等标注引用来源。\n\n"
                f"证据:\n{context}\n\n问题: {question}\n\n"
                f"语言要求：学生用哪种语言提问，你就用哪种语言回答"
                f"（提问是中文就用中文，英文就用英文），不要擅自转换语言。"
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