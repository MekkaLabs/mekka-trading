#!/usr/bin/env bash
#
# scripts/kill.sh — engage the Mekka Trading kill switch (Story 029).
#
# Creates `data/.kill_switch` with a reason payload. Batman reads this
# file at the start of every `_run` and returns `RiskVerdict.KILL_SWITCH`
# while it exists. Nick Fury also short-circuits the main cycle.
#
# Usage
# -----
#     ./scripts/kill.sh                 # default reason
#     ./scripts/kill.sh "drawdown spike on BTC at 14:32 UTC"
#
# Release
# -------
#     rm data/.kill_switch              # operator deliberate release
#
# Or in Python:
#     from src.agents.batman import release_kill_switch
#     release_kill_switch()
#
# Notes
# -----
# - The env var MEKKA_KILL_SWITCH=1 is an alternative transient kill
#   switch (clears on restart). The file is the persistent variant.
# - This script does not touch SQLite. The next cycle will emit a
#   `RISK_KILL_SWITCH` audit row when Batman sees the flag.

set -euo pipefail

# Resolve repo root (script lives in <repo>/scripts/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "${SCRIPT_DIR}/.." && pwd )"
KILL_FILE="${REPO_ROOT}/data/.kill_switch"

REASON="${1:-manual kill via scripts/kill.sh}"
TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

mkdir -p "${REPO_ROOT}/data"
printf "[%s] %s\n" "${TS}" "${REASON}" > "${KILL_FILE}"

echo "================================================================"
echo "  KILL SWITCH ENGAGED"
echo "================================================================"
echo "  File   : ${KILL_FILE}"
echo "  Time   : ${TS}"
echo "  Reason : ${REASON}"
echo ""
echo "  Next cycle: Batman will return RiskVerdict.KILL_SWITCH for"
echo "              every signal. Nick Fury will skip main cycle."
echo ""
echo "  To release:"
echo "    rm ${KILL_FILE}"
echo "================================================================"
