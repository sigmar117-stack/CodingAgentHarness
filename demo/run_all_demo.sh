#!/bin/bash
# Run all CodingKit mechanism demos (T7.2).
# Each demo is independent and runs without a real LLM.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "=============================================="
echo "  CodingKit — All Demos"
echo "=============================================="
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  1/3: Guardrail Demo"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python guardrail_demo.py
echo ""
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  2/3: Feedback Loop Demo"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python feedback_demo.py
echo ""
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  3/3: Strategy Engine Deep Demo"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python strategy_engine_demo.py
echo ""
echo ""

echo "=============================================="
echo "  ✅ All demos completed successfully!"
echo "=============================================="