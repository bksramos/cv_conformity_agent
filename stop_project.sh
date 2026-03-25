#!/bin/bash
# ============================================================
# FILE: stop_project.sh
# Encerra API, UI e containers Docker.
# Uso: bash stop_project.sh
# ============================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}==============================================${NC}"
echo -e "${CYAN}   CV Conformity Agent — Shutdown             ${NC}"
echo -e "${CYAN}==============================================${NC}"
echo ""

# Para API
if [ -f .api.pid ]; then
    PID=$(cat .api.pid)
    kill "$PID" 2>/dev/null && echo -e "${GREEN}✅ API encerrada (PID $PID)${NC}"
    rm -f .api.pid
else
    echo -e "${YELLOW}ℹ️  API não estava rodando via script${NC}"
fi

# Para UI
if [ -f .ui.pid ]; then
    PID=$(cat .ui.pid)
    kill "$PID" 2>/dev/null && echo -e "${GREEN}✅ UI encerrada (PID $PID)${NC}"
    rm -f .ui.pid
else
    echo -e "${YELLOW}ℹ️  UI não estava rodando via script${NC}"
fi

# Para containers
echo ""
docker compose down
echo -e "${GREEN}✅ Containers encerrados${NC}"

echo ""
echo -e "${CYAN}🏁 Sistema encerrado.${NC}"
echo -e "${CYAN}==============================================${NC}"
echo ""
