"""HTTP client that warms up the 'Demo 学生' via POST /tutor/demo/warmup.

The actual scripted answering runs server-side (the public quiz API hides answer
keys, so only the server can guarantee which choices are wrong). This script just
drives that endpoint and prints a human summary you can show during the demo.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

BASE = os.environ.get("ECV_TUTOR_BASE", "http://localhost:8000")


def _post(path: str) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    data = _post("/tutor/demo/warmup")
    if not data.get("ok"):
        print("[warmup] 失败:", data.get("error", data), file=sys.stderr)
        return 1
    print(f"[warmup] 学生 ID      : {data['student_id']}")
    print(f"[warmup] 已作答 / 答错 : {data['answers']} / {data['wrong']}")
    print(f"[warmup] 掌握度轨迹点  : {len(data['trajectory'])}  "
          f"(首个={data['trajectory'][0]['mastery'] if data['trajectory'] else '-'})")
    misconceptions = data.get("misconceptions", {})
    if misconceptions:
        print("[warmup] 检测到的误解 :")
        for tid, m in misconceptions.items():
            print(f"   - {tid}: {m.get('label')} (error_count={m.get('error_count')})")
    print("[warmup] 在前端选择该学生即可演示误解诊断 / 掌握度曲线 / 朗读总结。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
