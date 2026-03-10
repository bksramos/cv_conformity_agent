#!/bin/bash
set -euo pipefail

# ============================================================
# update_deps.sh
# Compila requirements.in → requirements.txt com versões
# compatíveis entre si e sincroniza o venv.
#
# Uso:
#   bash update_deps.sh          → atualiza tudo
#   bash update_deps.sh --no-sync → só compila, não instala
# ============================================================

NO_SYNC=false
for arg in "$@"; do
    [[ "$arg" == "--no-sync" ]] && NO_SYNC=true
done

PYTHON_CMD="python"

# --- Separador visual ---
divider() { echo ""; echo "─────────────────────────────────────────────"; }

divider
echo "🔎 Verificando pré-requisitos..."
divider

# Verifica venv ativo
if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo "❌ Erro: Ambiente virtual não ativado." >&2
    echo "   Execute: source .venv/Scripts/activate  (Windows)" >&2
    echo "        ou: source .venv/bin/activate       (Linux/Mac)" >&2
    exit 1
fi
echo "✅ Ambiente virtual : $VIRTUAL_ENV"
echo "✅ Python           : $($PYTHON_CMD --version)"

# Verifica requirements.in
if [ ! -f "requirements.in" ]; then
    echo "❌ Erro: 'requirements.in' não encontrado na raiz do projeto." >&2
    exit 1
fi
echo "✅ requirements.in  : encontrado"

# --- Instalar / atualizar pip-tools ---
divider
echo "📦 Instalando/atualizando pip-tools..."
divider
$PYTHON_CMD -m pip install --upgrade pip pip-tools

# --- Compilar requirements.in → requirements.txt ---
divider
echo "⚙️  Compilando requirements.in → requirements.txt..."
echo "   (resolve versões compatíveis entre todos os pacotes)"
divider

$PYTHON_CMD -m piptools compile requirements.in \
    --upgrade \
    --resolver=backtracking \
    --output-file requirements.txt \
    --annotation-style line \
    --no-header \
    --verbose

echo ""
echo "✅ requirements.txt gerado com sucesso"

# Exibe quantos pacotes foram resolvidos
PKG_COUNT=$(grep -c "^[a-zA-Z]" requirements.txt || true)
echo "   📋 Total de pacotes pinados: $PKG_COUNT"

# --- Sincronizar o venv ---
if [ "$NO_SYNC" = true ]; then
    divider
    echo "⏭️  --no-sync ativo: sincronização do venv pulada."
else
    divider
    echo "🔄 Sincronizando venv com requirements.txt..."
    echo "   (instala novos, remove obsoletos, atualiza alterados)"
    divider
    $PYTHON_CMD -m piptools sync requirements.txt
    echo ""
    echo "✅ Venv sincronizado"
fi

# --- Resumo final ---
divider
echo "🎉 Dependências atualizadas com sucesso!"
echo ""
echo "   Próximos passos:"
echo "   → Para instalar:          pip install -r requirements.txt"
echo "   → Para atualizar de novo: bash update_deps.sh"
echo "   → Apenas compilar:        bash update_deps.sh --no-sync"
divider
echo ""