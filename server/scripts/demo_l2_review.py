#!/usr/bin/env python3
"""demo_l2_review.py — Level-2 judge evidence generator (HTTP client).

Calls the running ECV-Tutor backend over HTTP (no app imports, no third-party
deps) and emits a reproducible evidence bundle for the Hackathon grader:

  Section A — Source-grounded chat (知识库与来源标注 20%)
      3 in-course questions answered WITH citations (unit/source/page/caption)
      + 1 out-of-KB question REFUSED by the relevance gate.
  Section B — BKT learner model (个性化有效性 20%)
      POST /tutor/demo/warmup (scripted quiz rounds incl. deliberate mistakes)
      -> mastery trajectory + misconception labels; per-topic mastery readback
      via GET /tutor/students/{id}.
  Section C — System evaluation (系统评估 15%)
      POST /tutor/evaluate/full (small config, llm=False offline) + polling.

Output:
  - human-readable terminal report
  - eval_results/eval_results_l2_review.json  (evidence file)

Prerequisites (in order):
  1) Start backend   : cd server && python -m app.main   (port 8000 default)
  2) Seed demo course via web UI (上传 -> Seed Demo Course), or POST
     /tutor/demo/seed.  /demo/warmup auto-seeds if topics are absent.

Usage:
  python scripts/demo_l2_review.py            # from the server/ directory
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://localhost:8000"
REPO_ROOT = Path(__file__).resolve().parents[2]   # server/scripts -> repo root
OUT_FILE = REPO_ROOT / "eval_results" / "eval_results_l2_review.json"

CHAT_QUERIES = [
    ("What is a variable in Python?", "in_kb"),
    ("How does the def keyword define a function?", "in_kb"),
    ("Explain the return statement.", "in_kb"),
    ("What is the population of Mars?", "out_of_kb"),
]

EVAL_CONFIG = {"n_sessions": 1, "questions_per_session": 2, "seed": 42, "llm": False}

def _api(base: str, path: str, *, method: str = "GET", body: dict | None = None,
         timeout: int = 30) -> dict:
    """Thin urllib wrapper returning parsed JSON. Raises on HTTP/network errors."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{base}/tutor{path}", data=data, method=method,
        headers={"Content-Type": "application/json",
                 "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _api_health(base: str, timeout: int = 5) -> dict:
    req = urllib.request.Request(
        f"{base}/health", method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def print_section(title: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}")


def _truncate(text: str, limit: int = 160) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def run_rag_demo(base: str) -> list[dict]:
    """Section A: 3 in-KB grounded answers with citations + 1 out-of-KB refusal."""
    print_section("Section A — Source-Grounded Chat (知识库与来源标注)")
    entries: list[dict] = []
    for question, qtype in CHAT_QUERIES:
        print(f"\n  Q: {question}  [{qtype}]")
        try:
            resp = _api(base, "/chat", method="POST",
                        body={"query": question, "llm": False, "top_k": 5})
        except Exception as exc:  # noqa: BLE001 - keep going on per-question failure
            print(f"  ! chat call failed: {exc}")
            entries.append({
                "question": question,
                "type": qtype,
                "error": str(exc),
            })
            continue

        status = resp.get("status", "unknown")
        citations = resp.get("citations") or []
        entry: dict = {
            "question": question,
            "type": qtype,
            "status": status,
            "answer": resp.get("answer", ""),
            "citations": citations,
            "retrieval_meta": resp.get("retrieval_meta", {}),
            "evidence": resp.get("evidence", []),
            "detected_language": resp.get("detected_language", ""),
        }
        if status == "refused":
            entry["refuse_reason"] = resp.get("refuse_reason", "")
            entry["off_material"] = resp.get("off_material", False)
            print("  -> REFUSED (relevance gate). reason: "
                  f"{_truncate(resp.get('refuse_reason', ''))}")
        elif citations:
            print(f"  -> ANSWERED with {len(citations)} citations")
            for i, cite in enumerate(citations[:3], start=1):
                print(f"     [{i}] label={cite.get('label', '?')}  "
                      f"chunk={cite.get('chunk_id', '?')}  "
                      f"source={_truncate(cite.get('source_url', ''), 60)}")
            print(f"  answer: {_truncate(resp.get('answer', ''), 200)}")
        else:
            print("  -> ANSWERED but NO citations (unexpected)")
            print(f"  answer: {_truncate(resp.get('answer', ''), 200)}")

        entries.append(entry)
    return entries

def run_bkt_demo(base: str) -> dict:
    """Section B: scripted warmup quiz -> BKT mastery trajectory + misconceptions."""
    print_section("Section B — BKT Learner Model (个性化有效性)")
    bkt: dict = {}
    try:
        warmup = _api(base, "/demo/warmup", method="POST", body={}, timeout=60)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! warmup failed: {exc}")
        return {"error": str(exc)}

    ok = warmup.get("ok")
    student_id = warmup.get("student_id", "")
    print(f"  ok={ok}  student={student_id}")
    print(f"  quiz rounds answered={warmup.get('answers', 0)}  "
          f"wrong={warmup.get('wrong', 0)}  "
          f"topics covered={warmup.get('topics', 0)}")

    trajectory = warmup.get("trajectory") or []
    misconceptions = warmup.get("misconceptions") or {}
    bkt = {
        "ok": ok,
        "student_id": student_id,
        "n_answers": warmup.get("answers", 0),
        "n_wrong": warmup.get("wrong", 0),
        "n_topics": warmup.get("topics", 0),
        "trajectory": trajectory,
        "misconceptions": misconceptions,
    }

    if trajectory:
        print("\n  BKT mastery trajectory (avg across topics, per step):")
        for point in trajectory[:12]:
            print(f"     step {point.get('step', '?'):>3}  "
                  f"mastery {point.get('mastery', '?'):>6}")

    if misconceptions:
        print("\n  Misconception labels (LLM judge / count fallback):")
        for tid, info in list(misconceptions.items())[:5]:
            if isinstance(info, dict):
                print(f"     {tid}: {info.get('label', '?')} "
                      f"(errors={info.get('error_count', '?')})")
            else:
                print(f"     {tid}: {info}")

    # Read back per-topic mastery (evidence of individualized tracking).
    try:
        detail = _api(base, f"/students/{student_id}", method="GET")
        mastery_map = detail.get("mastery") or {}
        bkt["mastery_summary"] = {
            tid: {"name": m.get("name", tid),
                  "mastery": m.get("mastery", 0.0),
                  "n_correct": m.get("n_correct", 0),
                  "n_wrong": m.get("n_wrong", 0)}
            for tid, m in mastery_map.items()
        }
        print("\n  Per-topic BKT mastery:")
        for tid, m in bkt["mastery_summary"].items():
            print(f"     {tid:<12} {m['name']:<28} "
                  f"mastery={m['mastery']:.2f}  "
                  f"correct={m['n_correct']} wrong={m['n_wrong']}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ! per-topic mastery readback skipped: {exc}")

    return bkt

def run_eval_summary(base: str) -> dict:
    """Section C: offline full-pipeline evaluation (small, llm=False)."""
    print_section("Section C — System Evaluation (系统评估)")
    out: dict = {}
    try:
        launched = _api(base, "/evaluate/full", method="POST", body=EVAL_CONFIG,
                        timeout=60)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! evaluate/full launch failed: {exc}")
        return {"error": str(exc)}

    task_id = launched.get("task_id")
    status = launched.get("status")
    print(f"  launched eval task {task_id} (status={status})")

    deadline = time.time() + 900   # full eval (120-case BM25) can take ~10 min
    poll_interval = 3.0
    result: dict = {}
    last_progress = 0.0
    while time.time() < deadline:
        time.sleep(poll_interval)
        try:
            poll = _api(base, f"/evaluate/status/{task_id}", method="GET")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! status poll error: {exc}")
            continue
        status = poll.get("status")
        if status == "done" and poll.get("result"):
            result = poll["result"]
            break
        # print progress at most every ~30s so the terminal stays lively
        if time.time() - last_progress >= 30:
            print(f"     poll status={status}  (elapsed {int(time.time() - deadline + 900)}s / up to 900s)")
            last_progress = time.time()
        if status in ("failed", "error"):
            out["error"] = f"eval task failed: {poll.get('error', status)}"
            break
        poll_interval = min(poll_interval * 1.2, 5.0)

    if not result:
        out["error"] = out.get("error", "eval task did not complete in time")
        print(f"  ! {out['error']}")
        return out

    out.update(result)
    ragas_used = result.get("ragas_used", False)

    m = result.get("assessment_metrics", {}) or {}
    rm = result.get("rag_metrics", {}) or {}
    print("  + rag_metrics (offline probes):")
    for key in ("faithfulness", "context_precision", "context_recall",
                "refusal_rate"):
        val = rm.get(key)
        print(f"      {key}: {val if val is not None else 'n/a'}")
    print("  + assessment_metrics (personalization):")
    for key in ("mastery_gain_avg", "question_repetition_rate_avg"):
        val = m.get(key)
        print(f"      {key}: {val if val is not None else 'n/a'}")

    profiles = result.get("student_profiles") or []
    if profiles:
        print("  + simulated student profiles (before -> after mastery):")
        for p in profiles[:4]:
            print(f"      {p.get('profile', '?'):<12} "
                  f"before={p.get('mastery_before'):.3f}  "
                  f"after={p.get('mastery_after'):.3f}  "
                  f"gain=+{p.get('mastery_gain'):.3f}  "
                  f"repetition={p.get('question_repetition_rate'):.3f}")

    probes = {k: result[k] for k in ("rag_metrics", "quality_rag")
              if result.get(k)}
    if probes:
        print(f"  + quality-rag probes present: {list(probes.keys())}")
    print(f"  + ragas_used={ragas_used}  reports: "
          f"{list(result.get('ragas', {}).keys()) if result.get('ragas') else 'n/a (offline)'}")
    if result.get("test_set_path"):
        print(f"  + test set saved at: {result.get('test_set_path')}")
    prof_traj = result.get("profile_trajectories") or []
    if prof_traj:
        print(f"  + profile trajectories (per simulated student): {len(prof_traj)}")

    return out

def main() -> int:
    """Pre-flight health check, run all three evidence sections, write JSON."""
    print("ECV-Tutor — Level 2 Judge Demo Evidence Generator (HTTP client)")
    print(f"Backend: {BASE}   Output: {OUT_FILE}")

    # ---------- Pre-flight ----------
    print_section("Pre-flight: Backend Health Check")
    try:
        health = _api_health(BASE)
        print(f"  OK  status={health.get('status')}  service={health.get('service')}")
        print(f"      llm_enabled={health.get('llm_enabled')}  "
              f"model={health.get('llm_model')}")
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL backend unreachable at {BASE}: {exc}")
        print("  -> Start it first:  cd server && python -m app.main")
        print("     (seed demo course in the web UI: 上传 -> Seed Demo Course)")
        return 1

    result: dict = {
        "rag_demo": [],
        "bkt_demo": {},
        "eval_summary": {},
    }

    # ---------- Section A ----------
    result["rag_demo"] = run_rag_demo(BASE)

    # ---------- Section B ----------
    result["bkt_demo"] = run_bkt_demo(BASE)

    # ---------- Section C ----------
    result["eval_summary"] = run_eval_summary(BASE)

    # ---------- Output ----------
    print_section("Output")
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Written: {OUT_FILE}")

    # quick summary
    n_in = sum(1 for r in result["rag_demo"] if r.get("type") == "in_kb")
    n_out = sum(1 for r in result["rag_demo"] if r.get("type") == "out_of_kb")
    n_refused = sum(1 for r in result["rag_demo"]
                    if r.get("status") == "refused")
    print_section("Level 2 Evidence Complete")
    print(f"  rag_demo: {n_in} in-KB answered, {n_out} out-of-KB, "
          f"{n_refused} refused")
    print(f"  bkt_demo: student={result['bkt_demo'].get('student_id', '-')}  "
          f"trajectory points={len(result['bkt_demo'].get('trajectory', []))}")
    print(f"  eval_summary: {result['eval_summary'].get('status', 'see JSON')}")
    print(f"  Evidence file: {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())