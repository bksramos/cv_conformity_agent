#!/bin/bash
# ============================================================
# FILE: start_project.sh
# PASSO 2 DE 2 — Rodar no WSL
# Inicializa todos os serviços do CV Conformity Agent.
#
# Pré-requisito: start_ollama.ps1 já deve estar rodando
# no PowerShell Admin do Windows.
#
# Uso: bash start_project.sh [--no-api] [--no-ui]
# ============================================================

set -euo pipefail

START_API=true
START_UI=true

for arg in "$@"; do
    [[ "$arg" == "--no-api" ]] && START_API=false
    [[ "$arg" == "--no-ui"  ]] && START_UI=false
done

# Cores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
GRAY='\033[0;90m'
NC='\033[0m'

divider() { echo -e "${CYAN}==============================================${NC}"; }

divider
echo -e "${CYAN}   CV Conformity Agent — Project Startup      ${NC}"
divider
echo ""

# --- Verifica venv ativo ---
if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo -e "${RED}❌ Venv não ativado.${NC}"
    echo -e "   Execute: ${GRAY}source venv/Scripts/activate${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Venv ativo:${NC} $VIRTUAL_ENV"

# --- 1. Atualiza IP do Ollama no .env ---
echo ""
divider
echo -e "${YELLOW}🌐 Atualizando IP do Ollama...${NC}"
divider

WINDOWS_IP=$(ip route show | grep -i default | awk '{ print $3}')
if [ -z "$WINDOWS_IP" ]; then
    echo -e "${RED}❌ Não foi possível detectar o IP do Windows.${NC}"
    exit 1
fi

sed -i "s|OLLAMA_BASE_URL=.*|OLLAMA_BASE_URL=http://$WINDOWS_IP:11434|" .env
echo -e "${GREEN}✅ OLLAMA_BASE_URL=http://$WINDOWS_IP:11434${NC}"

# --- 2. Sobe containers Docker ---
echo ""
divider
echo -e "${YELLOW}🐳 Subindo containers Docker...${NC}"
divider

docker compose up -d
echo ""

# Aguarda PostgreSQL ficar healthy
echo -e "${GRAY}   Aguardando PostgreSQL ficar pronto...${NC}"
for i in $(seq 1 15); do
    if docker exec cva_postgres pg_isready -U cva_user -q 2>/dev/null; then
        echo -e "${GREEN}✅ PostgreSQL pronto${NC}"
        break
    fi
    if [ "$i" -eq 15 ]; then
        echo -e "${RED}❌ PostgreSQL não ficou pronto a tempo.${NC}"
        exit 1
    fi
    sleep 1
done

# --- 3. Verifica se Ollama está acessível ---
echo ""
divider
echo -e "${YELLOW}🦙 Verificando Ollama...${NC}"
divider

MAX_TRIES=10
for i in $(seq 1 $MAX_TRIES); do
    if curl -s "http://$WINDOWS_IP:11434/api/tags" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Ollama acessível em http://$WINDOWS_IP:11434${NC}"
        break
    fi
    if [ "$i" -eq $MAX_TRIES ]; then
        echo -e "${RED}❌ Ollama não está acessível.${NC}"
        echo -e "   ${GRAY}Certifique-se que start_ollama.ps1 está rodando no PowerShell Admin.${NC}"
        exit 1
    fi
    echo -e "${GRAY}   Tentativa $i/$MAX_TRIES...${NC}"
    sleep 2
done

# --- 4. Bootstrap (health check completo) ---
echo ""
divider
echo -e "${YELLOW}🔎 Validando ambiente...${NC}"
divider

python bootstrap.py
echo ""

# --- 5. Sobe API (background) ---
if [ "$START_API" = true ]; then
    divider
    echo -e "${YELLOW}🚀 Iniciando API FastAPI...${NC}"
    divider
    nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 \
        > logs/api.log 2>&1 &
    API_PID=$!
    echo $API_PID > .api.pid
    sleep 2
    if curl -s http://localhost:8000/api/v1/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ API rodando — http://localhost:8000/docs (PID: $API_PID)${NC}"
    else
        echo -e "${YELLOW}⚠️  API iniciada mas ainda não respondeu (verifique logs/api.log)${NC}"
    fi
fi

# --- 6. Sobe UI Streamlit (background) ---
if [ "$START_UI" = true ]; then
    echo ""
    divider
    echo -e "${YELLOW}🎨 Iniciando UI Streamlit...${NC}"
    divider
    nohup streamlit run ui/app.py \
        --server.port 8501 \
        --server.headless true \
        > logs/ui.log 2>&1 &
    UI_PID=$!
    echo $UI_PID > .ui.pid
    sleep 2
    echo -e "${GREEN}✅ UI rodando  — http://localhost:8501 (PID: $UI_PID)${NC}"
fi

# --- Resumo final ---
echo ""
divider
echo -e "${GREEN}🎉 Sistema pronto!${NC}"
divider
echo -e "   🌐 UI       → ${CYAN}http://localhost:8501${NC}"
echo -e "   📡 API      → ${CYAN}http://localhost:8000/docs${NC}"
echo -e "   🦙 Ollama   → ${CYAN}http://$WINDOWS_IP:11434${NC}"
echo ""
echo -e "${GRAY}   Logs:"
echo -e "   API → tail -f logs/api.log"
echo -e "   UI  → tail -f logs/ui.log${NC}"
echo ""
echo -e "${GRAY}   Para encerrar: bash stop_project.sh${NC}"
divider


# ============================================================
# FILE: stop_project.sh
# Encerra API, UI e containers.
# Uso: bash stop_project.sh
# ============================================================

# (cole abaixo em stop_project.sh separado)
#
# #!/bin/bash
# echo "🛑 Encerrando serviços..."
#
# [ -f .api.pid ] && kill $(cat .api.pid) 2>/dev/null && rm .api.pid && echo "✅ API encerrada"
# [ -f .ui.pid  ] && kill $(cat .ui.pid)  2>/dev/null && rm .ui.pid  && echo "✅ UI encerrada"
#
# docker compose down
# echo "✅ Containers encerrados"
# echo "🏁 Sistema encerrado."
