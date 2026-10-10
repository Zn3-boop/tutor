#!/usr/bin/env bash
# One-click demo bootstrap (macOS / Linux / WSL).
set -euo pipefail
BASE="${ECV_TUTOR_BASE:-http://localhost:8000}"

echo "==> 1. 检查后端..."
if ! curl -sf "$BASE/kb-summary" >/dev/null 2>&1; then
  echo "   后端未运行，启动 server..."
  (cd "$(dirname "$0")/../server" && uvicorn app.main:app --port 8000 &) >/dev/null 2>&1
  sleep 7
fi

echo "==> 2. 幂等预置课程..."
summary=$(curl -sf "$BASE/kb-summary")
topics=$(printf '%s' "$summary" | python3 -c "import sys,json;print(json.load(sys.stdin)['topics'])")
units=$(printf '%s' "$summary" | python3 -c "import sys,json;print(json.load(sys.stdin)['units'])")
if [ "$topics" -gt 0 ] && [ "$units" -gt 0 ]; then
  echo "   课程已预置 (topics=$topics, units=$units)"
else
  curl -sf -X POST "$BASE/tutor/ingest/seed-demo" >/dev/null && echo "   已预置课程"
fi

echo "==> 3. 预热演示学生..."
w=$(curl -sf -X POST "$BASE/tutor/demo/warmup")
SID=$(printf '%s' "$w" | python3 -c "import sys,json;print(json.load(sys.stdin)['student_id'])")
echo "   学生 $SID"

echo "==> 4. 全流程冒烟..."
curl -sf "$BASE/tutor/graph?student_id=$SID"            >/dev/null && echo "   graph OK"
curl -sf -X POST "$BASE/tutor/flashcards" -d "{\"student_id\":\"$SID\"}" \
     -H "Content-Type: application/json"                >/dev/null && echo "   flashcards OK"
curl -sf -X POST "$BASE/tutor/study-plan" -d "{\"student_id\":\"$SID\"}" \
     -H "Content-Type: application/json"                >/dev/null && echo "   study-plan OK"
curl -sf -X POST "$BASE/tutor/misconceptions" -d "{\"student_id\":\"$SID\"}" \
     -H "Content-Type: application/json"                >/dev/null && echo "   misconceptions OK"
curl -sf "$BASE/tutor/mastery-trajectory/$SID"          >/dev/null && echo "   mastery-trajectory OK"

echo ""
echo "==> Demo 环境就绪。学生 ID: $SID"
