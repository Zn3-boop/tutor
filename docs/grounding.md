# Grounding, refusal, and citation provenance

## Purpose

The tutor must not turn a retrieval miss into a confident answer. Every answered chat response carries structured citations; an unsupported or off-topic query is refused with an empty citation list.

## Retrieval and refusal pipeline

```mermaid
flowchart TD
  Q[Student question] --> RW[Inline query rewrite]
  RW --> RET[Vector + BM25 retrieval]
  RET --> REL{Lexical relevance gate}
  REL -- below threshold --> REF[Refused; citations=[]]
  REL -- supported --> E[Evidence snippets]
  E --> GEN[Offline template or LLM]
  GEN --> OUT[Answer + citations + retrieval metadata]
```

The offline gate tokenizes English words and CJK bigrams, removes common English stopwords, and applies conservative stemming/prefix matching. The current minimum containment threshold is `0.40` over the top evidence. This is deliberately conservative: refusal is preferable to unsupported generation. LLM generation is only given retrieved evidence and is not the source of citation truth.

## Origin contract

A unit contains an origin such as:

```json
{
  "label": "p.14",
  "page": 14,
  "timestamp": "00:31:05",
  "index": 12
}
```

A retrieval citation contains only public-safe metadata:

```json
{
  "index": 1,
  "label": "p.14",
  "chunk_id": "unit_…",
  "source_url": "…"
}
```

`GET /tutor/source/open?unit_id=…` resolves that unit against the store and verifies the source file. PDF and slide origins include page/slide bounds; video/transcript origins include seconds and paragraph index. A manifest-bound transcript can return the associated video URL, preserving the timestamp without hardcoded filename mapping.

## Safety properties

- Refused answers return `citations: []`; the system never fabricates an origin.
- Public quiz questions are passed through `_public_question()` and do not expose answer keys.
- The file proxy allow-lists bundled/source-recorded paths and rejects missing or unapproved files.
- Citation integration tests use real demo materials to catch out-of-range pages, slides, and timestamps.

## Test boundary

Most grounding tests use in-memory units and BM25-only retrieval. `test_citation_resolve.py` is the intentional integration boundary that uses the real seeded course. This keeps CI fast while still validating that user-visible citations resolve to real material.
