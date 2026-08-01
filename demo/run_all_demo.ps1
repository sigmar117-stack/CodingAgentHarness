# Run all CodingKit mechanism demos (T7.2) — PowerShell version.
# Each demo is independent and runs without a real LLM.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host ""
Write-Host "=============================================="
Write-Host "  CodingKit — All Demos"
Write-Host "=============================================="
Write-Host ""

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "  1/3: Guardrail Demo"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python guardrail_demo.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "`n`n"

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "  2/3: Feedback Loop Demo"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python feedback_demo.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "`n`n"

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "  3/3: Strategy Engine Deep Demo"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python strategy_engine_demo.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "`n`n"

Write-Host "=============================================="
Write-Host "  ✅ All demos completed successfully!"
Write-Host "=============================================="