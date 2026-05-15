#!/usr/bin/env bash
# =============================================================================
# Mekka Trading — Kill Switch Operator Helper (Story 029a — Safety Net)
#
# Manipula o kill switch persistente em data/.kill_switch, lido por
# src/agents/batman.py:is_kill_switch_active(). Quando o arquivo existe,
# Batman emite RiskVerdict.KILL_SWITCH e Nick Fury aborta o ciclo.
#
# Subcomandos:
#   on [reason]   Engaja o kill switch (cria data/.kill_switch com o motivo)
#   off           Solta o kill switch (remove data/.kill_switch)
#   status        Mostra o estado atual (engaged/clear) e o motivo se houver
#
# Exemplos:
#   ./scripts/kill.sh on "manual halt during deploy"
#   ./scripts/kill.sh status
#   ./scripts/kill.sh off
#
# Notas:
#   - O env var MEKKA_KILL_SWITCH=1 também ativa o halt mas é transiente
#     ao processo. Este script só lida com o flag persistente em arquivo.
#   - Mantido em sync com src/agents/batman.py:_KILL_SWITCH_FILE.
# =============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Resolve repo root: este script vive em scripts/, then go up one level.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "${SCRIPT_DIR}/.." && pwd )"
KILL_FILE="${REPO_ROOT}/data/.kill_switch"

cmd="${1:-status}"
shift || true

case "${cmd}" in
    on|engage)
        reason="${*:-manual kill switch via scripts/kill.sh}"
        mkdir -p "$(dirname "${KILL_FILE}")"
        printf '%s\n' "${reason}" > "${KILL_FILE}"
        echo -e "${RED}🛑 Kill switch ENGAGED${NC}"
        echo -e "   File:   ${BLUE}${KILL_FILE}${NC}"
        echo -e "   Reason: ${YELLOW}${reason}${NC}"
        ;;
    off|release|clear)
        if [ -f "${KILL_FILE}" ]; then
            rm -f "${KILL_FILE}"
            echo -e "${GREEN}✅ Kill switch RELEASED${NC}"
            echo -e "   Removed: ${BLUE}${KILL_FILE}${NC}"
        else
            echo -e "${YELLOW}ℹ️  Kill switch already clear${NC} (no file at ${KILL_FILE})"
        fi
        ;;
    status|"")
        if [ -f "${KILL_FILE}" ]; then
            echo -e "${RED}🛑 Kill switch ENGAGED${NC}"
            echo -e "   File:   ${BLUE}${KILL_FILE}${NC}"
            if [ -s "${KILL_FILE}" ]; then
                echo -e "   Reason: ${YELLOW}$(head -n 1 "${KILL_FILE}")${NC}"
            fi
        else
            echo -e "${GREEN}✅ Kill switch CLEAR${NC} (no file at ${KILL_FILE})"
        fi
        if [ "${MEKKA_KILL_SWITCH:-}" = "1" ]; then
            echo -e "${YELLOW}⚠️  Env var MEKKA_KILL_SWITCH=1 is set in this shell — that also halts trading.${NC}"
        fi
        ;;
    -h|--help|help)
        sed -n '2,/^# ====/p' "$0" | sed 's/^# \{0,1\}//;/^====/d'
        ;;
    *)
        echo -e "${RED}Unknown subcommand: ${cmd}${NC}"
        echo "Usage: $0 {on [reason]|off|status}"
        exit 2
        ;;
esac
