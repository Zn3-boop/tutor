#!/bin/bash
# 冒烟测试脚本 - 一键验证所有新增 API
# 用法：./scripts/smoke_test.sh

BASE_URL="http://localhost:8000"
PASS_COUNT=0
FAIL_COUNT=0

echo "=================================="
echo "ECV-Tutor 冒烟测试启动"
echo "=================================="
echo ""

# 检查服务器是否运行
echo "[1/6] 检查服务器状态..."
if curl -s "$BASE_URL/docs" > /dev/null 2>&1; then
    echo "✅ 服务器正常运行"
    ((PASS_COUNT++))
else
    echo "❌ 服务器未运行，请先启动：cd server && uvicorn app.main:app --reload"
    exit 1
fi
echo ""

# 测试错误分析 API
echo "[2/6] 测试错误分析 API (analyze-errors)..."
RESPONSE=$(curl -s -X POST "$BASE_URL/tutor/analyze-errors" \
  -H "Content-Type: application/json" \
  -d '{"student_id": "demo_student"}' 2>&1)

if echo "$RESPONSE" | grep -q '"ok"'; then
    echo "✅ 错误分析 API 正常"
    ((PASS_COUNT++))
else
    echo "❌ 错误分析 API 异常：$RESPONSE"
    ((FAIL_COUNT++))
fi
echo ""

# 测试知识图谱 API
echo "[3/6] 测试知识图谱 API (enhanced-graph)..."
RESPONSE=$(curl -s "$BASE_URL/tutor/enhanced-graph/demo_student" 2>&1)

if echo "$RESPONSE" | grep -q '"nodes"'; then
    echo "✅ 知识图谱 API 正常"
    ((PASS_COUNT++))
else
    echo "❌ 知识图谱 API 异常：$RESPONSE"
    ((FAIL_COUNT++))
fi
echo ""

# 测试全局知识图谱
echo "[4/6] 测试全局知识图谱 API..."
RESPONSE=$(curl -s "$BASE_URL/tutor/enhanced-graph" 2>&1)

if echo "$RESPONSE" | grep -q '"nodes"' && echo "$RESPONSE" | grep -q '"statistics"'; then
    echo "✅ 全局知识图谱 API 正常"
    ((PASS_COUNT++))
else
    echo "❌ 全局知识图谱 API 异常：$RESPONSE"
    ((FAIL_COUNT++))
fi
echo ""

# 测试对抗性测试 API
echo "[5/6] 测试对抗性测试 API (adversarial-test)..."
echo "(这将运行一个简化版测试套件)"
RESPONSE=$(curl -s -X POST "$BASE_URL/tutor/adversarial-test" \
  -H "Content-Type: application/json" \
  -d '{"full_suite": false, "test_types": ["out_of_material"], "max_retries": 1, "timeout_seconds": 5}' 2>&1)

if echo "$RESPONSE" | grep -q '"summary"'; then
    echo "✅ 对抗性测试 API 正常"
    ((PASS_COUNT++))
else
    echo "❌ 对抗性测试 API 异常：$RESPONSE"
    ((FAIL_COUNT++))
fi
echo ""

# 运行单元测试
echo "[6/6] 运行单元测试..."
cd "$(dirname "$0")/../server" || exit 1
if python -m pytest tests/test_error_analyzer.py -q --tb=no 2>&1 | grep -q "passed"; then
    echo "✅ 单元测试通过"
    ((PASS_COUNT++))
else
    echo "❌ 单元测试失败"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================="
echo "测试完成!"
echo "通过：$PASS_COUNT / $((PASS_COUNT + FAIL_COUNT))"
echo "=================================="

if [ $FAIL_COUNT -gt 0 ]; then
    echo "⚠️  存在失败项，请检查日志"
    exit 1
else
    echo "✅ 所有测试通过!"
    exit 0
fi