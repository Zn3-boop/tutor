# One-click demo bootstrap (Windows / PowerShell).
# Run:  powershell -ExecutionPolicy Bypass -File scripts\demo.ps1
# Does: ensure backend -> idempotently seed course -> warm up "Demo Student"
#       -> smoke-test every learner-model endpoint.
# NOTE: messages are ASCII-only so Windows PowerShell 5.1 (ANSI codepage) parses
#       this file cleanly regardless of the console encoding.

$ErrorActionPreference = "Stop"
$BASE = if ($env:ECV_TUTOR_BASE) { $env:ECV_TUTOR_BASE } else { "http://localhost:8000" }

Write-Host "==> 1. check backend..." -ForegroundColor Cyan
$backendUp = $true
try { Invoke-RestMethod "$BASE/kb-summary" -Method Get | Out-Null }
catch { $backendUp = $false }

if (-not $backendUp) {
    Write-Host "   backend down, starting server (uvicorn app.main:app --port 8000)..."
    $serverDir = Join-Path $PSScriptRoot "..\server"
    Start-Process powershell -ArgumentList "-NoExit", "-Command",
        "cd '$serverDir'; uvicorn app.main:app --port 8000"
    Start-Sleep -Seconds 7
}

Write-Host "==> 2. seed course (idempotent)..." -ForegroundColor Cyan
$summary = Invoke-RestMethod "$BASE/kb-summary" -Method Get
if ($summary.topics -gt 0 -and $summary.units -gt 0) {
    Write-Host "   already seeded (topics=$($summary.topics), units=$($summary.units))"
} else {
    $seedRes = Invoke-RestMethod "$BASE/tutor/ingest/seed-demo" -Method Post
    Write-Host "   seeded: $($seedRes | ConvertTo-Json -Compress)"
}

Write-Host "==> 3. warm up demo student..." -ForegroundColor Cyan
$w = Invoke-RestMethod "$BASE/tutor/demo/warmup" -Method Post
$SID = $w.student_id
Write-Host "   student $SID : answers=$($w.answers), wrong=$($w.wrong), traj=$($w.trajectory.Count)"

Write-Host "==> 4. smoke test..." -ForegroundColor Cyan
function Smoke {
    param([string]$name, [scriptblock]$action)
    try { & $action | Out-Null; Write-Host "   $name  OK" -ForegroundColor Green }
    catch { Write-Host "   $name  FAIL: $($_.Exception.Message)" -ForegroundColor Red }
}
Smoke "graph"              { Invoke-RestMethod "$BASE/tutor/graph?student_id=$SID" -Method Get }
Smoke "flashcards"         { Invoke-RestMethod "$BASE/tutor/flashcards" -Method Post -Body (@{student_id=$SID} | ConvertTo-Json) -ContentType "application/json" }
Smoke "study-plan"         { Invoke-RestMethod "$BASE/tutor/study-plan" -Method Post -Body (@{student_id=$SID} | ConvertTo-Json) -ContentType "application/json" }
Smoke "misconceptions"     { Invoke-RestMethod "$BASE/tutor/misconceptions" -Method Post -Body (@{student_id=$SID} | ConvertTo-Json) -ContentType "application/json" }
Smoke "mastery-trajectory" { Invoke-RestMethod "$BASE/tutor/mastery-trajectory/$SID" -Method Get }

Write-Host ""
Write-Host "==> Demo ready. Student ID: $SID" -ForegroundColor Green
Write-Host "   Open the dashboard, select this student, then demo grounded Q&A,"
Write-Host "   Misconception Diagnose, mastery sparkline, and Read-aloud summary."
Write-Host "   For RAGAS real judge: POST /tutor/evaluate/full (one call ~10-35s)."

