"""Idempotent real-course seeder (Phase 1: real-citations-first).

Ingests the verified REAL public course materials listed in
``server/demo_materials/materials-manifest.json`` directly through the service
layer, so it works even without a running server:

  - Think Python, 2nd edition (Green Tea Press, real page-numbered PDF)
  - MIT OCW 6.0001 Fall 2016 Lecture 1-6 slide decks
  - MIT 6.0001 Lecture 1 official SRT captions (real timestamps)

Re-running is safe: if the real sources are already present it skips instead of
duplicating units. To force a clean reseed, delete ``server/app/data/tutor/
tutor_db.json`` first (and rerun the RAG store / warmup as needed).
"""

from __future__ import annotations

import asyncio
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(SERVER_DIR, ".env"))

os.environ.setdefault("VLM_ENABLED", "false")
os.environ.setdefault("RAG_DEFER_FAISS_BUILD", "true")
os.environ.setdefault("RAG_AUTO_BUILD_FAISS", "false")


def already_seeded() -> bool:
    """Treat the topic graph as the idempotency marker."""
    from app.services.tutor.store import get_tutor_store
    return bool(get_tutor_store().list_topics())


async def _seed() -> None:
    from app.services.tutor.store import get_tutor_store
    from app.services.tutor.knowledge import get_kb_ingestor
    store = get_tutor_store()
    ing = get_kb_ingestor(store)

    print("[seed] ingesting REAL course materials (Think Python 2e + MIT OCW 6.0001)...")
    res = await ing.seed_real_course()
    if not res.get("ok"):
        print(f"[seed] FAILED: {res.get('error')}")
        for r in res.get("results", []):
            if not r.get("ok"):
                print(f"  - {r.get('filename')}: {r.get('error')}")
        raise SystemExit(1)
    for r in res.get("results", []):
        state = "ok" if r.get("ok") else "FAILED"
        print(f"[seed]   [{state}] {r.get('filename')} units={r.get('unit_count', '-')}")

    print(f"[seed] done: sources={len(store.list_sources())} "
          f"units={len(store.list_units())} questions={len(store.list_questions())}")


def main() -> None:
    if already_seeded():
        print("[seed] topic graph already present - skipping (idempotent). "
              "Reset tutorial: rm server/app/data/tutor/tutor_db.json and rerun.")
        return
    asyncio.run(_seed())


if __name__ == "__main__":
    main()