# Smoke test script - one-click verification of all new APIs.
# Usage: .\scripts\smoke_test.ps1
# ASCII/English keeps PowerShell 5.1 parsing consistent (no BOM sensitivity).

$BASE_URL = "http://localhost:8000"
$PASS_COUNT = 0
$FAIL_COUNT = 0

Write-Host "=================================="
Write-Host "ECV-Tutor smoke test"
Write-Host "=================================="
Write-Host ""

# [1/6] Server status
Write-Host "[1/6] Checking server status..."
try {
    $r = Invoke-WebRequest -Uri "$BASE_URL/docs" -UseBasicParsing -TimeoutSec 5
    Write-Host "  [OK] Server is running"
    $PASS_COUNT++
} catch {
    Write-Host "  [FAIL] Server not running. Start it first: cd server && uvicorn app.main:app --reload"
    exit 1
}
Write-Host ""

# [2/6] Error analysis API
Write-Host "[2/6] Testing error analysis API (analyze-errors)..."
try {
    $RESPONSE = (Invoke-WebRequest -Uri "$BASE_URL/tutor/analyze-errors" -Method POST -ContentType "application/json" -Body '{"student_id": "demo_student"}' -UseBasicParsing -TimeoutSec 30).Content
    if ($RESPONSE -match '"ok"') {
        Write-Host "  [OK] Error analysis API works"
        $PASS_COUNT++
    } else {
        Write-Host "  [FAIL] Error analysis API returned unexpected response: $RESPONSE"
        $FAIL_COUNT++
    }
} catch {
    Write-Host "  [FAIL] Error analysis API error: $($_.Exception.Message)"
    $FAIL_COUNT++
}
Write-Host ""

# [3/6] Knowledge graph API (per-student)
Write-Host "[3/6] Testing knowledge graph API (enhanced-graph)..."
try {
    $RESPONSE = (Invoke-WebRequest -Uri "$BASE_URL/tutor/enhanced-graph/demo_student" -UseBasicParsing -TimeoutSec 30).Content
    if ($RESPONSE -match '"nodes"') {
        Write-Host "  [OK] Knowledge graph API works"
        $PASS_COUNT++
    } else {
        Write-Host "  [FAIL] Knowledge graph API returned unexpected response: $RESPONSE"
        $FAIL_COUNT++
    }
} catch {
    Write-Host "  [FAIL] Knowledge graph API error: $($_.Exception.Message)"
    $FAIL_COUNT++
}
Write-Host ""

# [4/6] Global knowledge graph API
Write-Host "[4/6] Testing global knowledge graph API..."
try {
    $RESPONSE = (Invoke-WebRequest -Uri "$BASE_URL/tutor/enhanced-graph" -UseBasicParsing -TimeoutSec 30).Content
    if ($RESPONSE -match '"nodes"' -and $RESPONSE -match '"statistics"') {
        Write-Host "  [OK] Global knowledge graph API works"
        $PASS_COUNT++
    } else {
        Write-Host "  [FAIL] Global knowledge graph API returned unexpected response: $RESPONSE"
        $FAIL_COUNT++
    }
} catch {
    Write-Host "  [FAIL] Global knowledge graph API error: $($_.Exception.Message)"
    $FAIL_COUNT++
}
Write-Host ""

# [5/6] Adversarial test API
Write-Host "[5/6] Testing adversarial test API (adversarial-test)..."
Write-Host "  (running a simplified suite)"
try {
    $RESPONSE = (Invoke-WebRequest -Uri "$BASE_URL/tutor/adversarial-test" -Method POST -ContentType "application/json" -Body '{"full_suite": false, "test_types": ["out_of_material"], "max_retries": 1, "timeout_seconds": 5}' -UseBasicParsing -TimeoutSec 60).Content
    if ($RESPONSE -match '"summary"') {
        Write-Host "  [OK] Adversarial test API works"
        $PASS_COUNT++
    } else {
        Write-Host "  [FAIL] Adversarial test API returned unexpected response: $RESPONSE"
        $FAIL_COUNT++
    }
} catch {
    Write-Host "  [FAIL] Adversarial test API error: $($_.Exception.Message)"
    $FAIL_COUNT++
}
Write-Host ""

# [6/6] Unit tests
Write-Host "[6/6] Running unit tests (test_error_analyzer)..."
Push-Location "d:\ecv-tutor\server"
try {
    $out = (& python -m pytest tests/test_error_analyzer.py -q --tb=no 2>&1 | Out-String)
    if ($out -match "passed") {
        Write-Host "  [OK] Unit tests passed"
        $PASS_COUNT++
    } else {
        Write-Host "  [FAIL] Unit tests failed"
        $FAIL_COUNT++
    }
} finally {
    Pop-Location
}
Write-Host ""

Write-Host "=================================="
Write-Host "Done."
Write-Host "Passed: $PASS_COUNT / $($PASS_COUNT + $FAIL_COUNT)"
Write-Host "=================================="

if ($FAIL_COUNT -gt 0) {
    Write-Host "Some checks failed, please check the log above."
    exit 1
} else {
    Write-Host "All smoke tests passed!"
    exit 0
}