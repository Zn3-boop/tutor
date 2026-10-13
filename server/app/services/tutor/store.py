"""JSON-backed persistence for the Tutor subsystem.

Kept dependency-free (stdlib only) and self-contained under a single data dir so
the hackathon prototype can run anywhere without DB migrations. Stores:
  - sources:  uploaded course materials (kind, path, title)
  - units:    extracted content units, each linked to an origin (page/slide/timestamp)
  - topics:   topic graph with prerequisites
  - students: learner models (BKT parameters + mastery per topic)
  - questions / assessments / sessions: adaptive assessment history
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "tutor")


def _now() -> float:
    return time.time()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class TutorStore:
    """Thread-safe JSON store with an in-memory index synced to a single file."""

    def __init__(self, data_dir: str = ""):
        self.data_dir = data_dir or os.getenv("TUTOR_DATA_DIR") or DEFAULT_DATA_DIR
        os.makedirs(self.data_dir, exist_ok=True)
        self._file = os.path.join(self.data_dir, "tutor_db.json")
        self._lock = threading.RLock()
        self.db: dict[str, Any] = {
            "sources": {},      # source_id -> source dict
            "units": {},        # unit_id -> unit dict
            "topics": {},       # topic_id -> topic dict
            "students": {},     # student_id -> student dict
            "questions": {},    # question_id -> question dict
            "assessments": {},  # assessment_id -> assessment dict
            "sessions": {},     # session_id -> session dict
            "wrong_questions": {},  # wq_id -> wrong question record
        }
        self._load()

    # ---------------- persistence helpers ----------------
    def _load(self) -> None:
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for key in self.db:
                        if isinstance(data.get(key), dict):
                            self.db[key] = data[key]
            except Exception:
                pass

    def _save(self) -> None:
        with self._lock:
            tmp = self._file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.db, f, ensure_ascii=False, indent=2)
            # os.replace on Windows can hit a transient PermissionError if the
            # target file handle is briefly held by another thread/process.
            for attempt in range(5):
                try:
                    os.replace(tmp, self._file)
                    return
                except PermissionError:
                    time.sleep(0.05 * (attempt + 1))
            # final fallback: plain overwrite
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self.db, f, ensure_ascii=False, indent=2)

    def _insert(self, collection: str, record: dict[str, Any], id_key: str) -> str:
        with self._lock:
            rid = record.get(id_key) or _new_id(collection[:-1])
            record[id_key] = rid
            record.setdefault("created_at", _now())
            self.db[collection][rid] = record
            self._save()
            return rid

    def _update(self, collection: str, rid: str, patch: dict[str, Any]) -> dict | None:
        with self._lock:
            rec = self.db[collection].get(rid)
            if rec is None:
                return None
            rec.update(patch)
            rec["updated_at"] = _now()
            self._save()
            return rec

    def _delete(self, collection: str, rid: str) -> bool:
        with self._lock:
            if rid in self.db[collection]:
                del self.db[collection][rid]
                self._save()
                return True
            return False

    def _get(self, collection: str, rid: str) -> dict | None:
        return self.db[collection].get(rid)

    def _all(self, collection: str) -> list[dict]:
        return list(self.db[collection].values())

    # ---------------- sources ----------------
    def add_source(self, *, title: str, kind: str, path: str = "",
                   total_pages: int = 0, meta: dict | None = None) -> dict:
        rec = {
            "title": title, "kind": kind, "path": path,
            "total_pages": total_pages, "meta": meta or {},
        }
        sid = self._insert("sources", rec, "source_id")
        return self._get("sources", sid) or rec

    def get_source(self, source_id: str) -> dict | None:
        return self._get("sources", source_id)

    def list_sources(self) -> list[dict]:
        return self._all("sources")

    def delete_source(self, source_id: str) -> bool:
        for uid, unit in list(self.db["units"].items()):
            if unit.get("source_id") == source_id:
                self._delete("units", uid)
        return self._delete("sources", source_id)

    # ---------------- units ----------------
    def add_unit(self, *, source_id: str, text: str, topic_ids: list[str],
                 concepts: list[str], origin: dict, chunk_id: str = "") -> dict:
        rec = {
            "source_id": source_id, "text": text, "topic_ids": topic_ids,
            "concepts": concepts, "origin": origin, "chunk_id": chunk_id,
        }
        uid = self._insert("units", rec, "unit_id")
        return self._get("units", uid) or rec

    def get_unit(self, unit_id: str) -> dict | None:
        return self._get("units", unit_id)

    def list_units(self, source_id: str = "") -> list[dict]:
        units = self._all("units")
        if source_id:
            units = [u for u in units if u.get("source_id") == source_id]
        return sorted(units, key=lambda u: u.get("created_at", 0))

    def units_by_topics(self, topic_ids: list[str]) -> list[dict]:
        """Return units (with source title) whose topic_ids intersect the given set."""
        want = set(topic_ids)
        out = []
        for u in self._all("units"):
            if want & set(u.get("topic_ids", [])):
                rec = dict(u)
                src = self.get_source(u.get("source_id", "")) or {}
                rec["source_title"] = src.get("title", src.get("name", ""))
                out.append(rec)
        return sorted(out, key=lambda u: u.get("created_at", 0))

    def get_unit_by_chunk(self, chunk_id: str) -> dict | None:
        for uid, unit in self.db["units"].items():
            if unit.get("chunk_id") == chunk_id or (chunk_id or "").startswith(uid):
                return unit
        return None

    # ---------------- topics ----------------
    def upsert_topic(self, *, topic_id: str, name: str, description: str = "",
                     prerequisites: list[str] | None = None,
                     concepts: list[str] | None = None) -> dict:
        with self._lock:
            rec = self.db["topics"].get(topic_id) or {"topic_id": topic_id,
                                                      "created_at": _now()}
            rec.update({
                "name": name, "description": description,
                "prerequisites": prerequisites or [],
                "concepts": concepts or [],
            })
            rec["updated_at"] = _now()
            self.db["topics"][topic_id] = rec
            self._save()
            return rec

    def get_topic(self, topic_id: str) -> dict | None:
        return self._get("topics", topic_id)

    def list_topics(self) -> list[dict]:
        return self._all("topics")

    def list_topics_by_id(self) -> dict[str, dict]:
        return {t["topic_id"]: t for t in self._all("topics")}

    # ---------------- students ----------------
    def create_student(self, *, name: str = "", profile: dict | None = None,
                       lang: str = "auto") -> dict:
        rec = {
            "name": name,
            "profile": profile or {},
            "lang": lang if lang in ("auto", "zh", "en") else "auto",  # P1 聊天语言偏好
            "mastery": {},          # topic_id -> BKT state
            "asked_questions": [],  # question_ids already shown (avoid repeats)
            "conversation_history": [],
            "misconceptions": {},   # topic_id -> count of repeated errors
            "created_at": _now(),
        }
        sid = self._insert("students", rec, "student_id")
        return self._get("students", sid) or rec

    def get_student(self, student_id: str) -> dict | None:
        return self._get("students", student_id)

    def list_students(self) -> list[dict]:
        return self._all("students")

    def update_student(self, student_id: str, patch: dict) -> dict | None:
        return self._update("students", student_id, patch)

    def save_student(self, student: dict) -> None:
        with self._lock:
            sid = student["student_id"]
            if sid in self.db["students"]:
                self.db["students"][sid] = student
                self._save()

    def delete_student(self, student_id: str) -> bool:
        return self._delete("students", student_id)

    # ---------------- questions / assessments / sessions ----------------
    def add_question(self, *, text: str, qtype: str, options: list[str],
                     answer: str, topic_ids: list[str], source_ids: list[str],
                     difficulty: str = "medium", answer_key: str = "",
                     explanation: str = "", origin: dict | None = None) -> str:
        rec = {
            "text": text, "type": qtype, "options": options, "answer": answer,
            "topic_ids": topic_ids, "source_ids": source_ids,
            "difficulty": difficulty, "answer_key": answer_key,
            "explanation": explanation, "origin": origin or {},
        }
        return self._insert("questions", rec, "question_id")

    def get_question(self, question_id: str) -> dict | None:
        return self._get("questions", question_id)

    def list_questions(self) -> list[dict]:
        return self._all("questions")

    def add_assessment(self, *, student_id: str, scope_topic_ids: list[str],
                       questions: list[dict], report: dict | None = None,
                       meta: dict | None = None) -> dict:
        rec = {
            "student_id": student_id, "scope_topic_ids": scope_topic_ids,
            "questions": questions, "report": report or {}, "meta": meta or {},
        }
        aid = self._insert("assessments", rec, "assessment_id")
        return self._get("assessments", aid) or rec

    def list_assessments(self, student_id: str = "") -> list[dict]:
        items = self._all("assessments")
        if student_id:
            items = [a for a in items if a.get("student_id") == student_id]
        return sorted(items, key=lambda a: a.get("created_at", 0), reverse=True)

    def add_session(self, *, student_id: str, mode: str, payload: dict) -> dict:
        rec = {"student_id": student_id, "mode": mode, "payload": payload}
        sid = self._insert("sessions", rec, "session_id")
        return self._get("sessions", sid) or rec

    # ---------------- wrong questions (错题本) ----------------
    def add_wrong_question(self, *, student_id: str, question_id: str,
                           question_text: str, chosen: str,
                           correct_answer: str, topic_ids: list[str],
                           assessment_id: str = "",
                           explanation: str = "") -> dict:
        rec = {
            "student_id": student_id,
            "question_id": question_id,
            "question_text": question_text,
            "chosen": chosen,
            "correct_answer": correct_answer,
            "topic_ids": topic_ids,
            "assessment_id": assessment_id,
            "explanation": explanation,
            "resolved": False,
        }
        wid = self._insert("wrong_questions", rec, "wq_id")
        return self._get("wrong_questions", wid) or rec

    def list_wrong_questions(self, student_id: str,
                             topic_id: str = "") -> list[dict]:
        items = self._all("wrong_questions")
        items = [w for w in items if w.get("student_id") == student_id]
        if topic_id:
            items = [w for w in items if topic_id in w.get("topic_ids", [])]
        return sorted(items, key=lambda w: w.get("created_at", 0), reverse=True)

    def mark_wrong_question_resolved(self, wq_id: str) -> dict | None:
        return self._update("wrong_questions", wq_id, {"resolved": True})

    def delete_wrong_question(self, wq_id: str) -> bool:
        return self._delete("wrong_questions", wq_id)


_instances: dict[str, TutorStore] = {}


def get_tutor_store(data_dir: str = "") -> TutorStore:
    key = data_dir or os.getenv("TUTOR_DATA_DIR") or DEFAULT_DATA_DIR
    if key not in _instances:
        _instances[key] = TutorStore(data_dir=key)
    return _instances[key]