# ============================================================
# FILE: start_ollama.ps1
# PASSO 1 DE 2 — Rodar no PowerShell Admin (Windows)
# Inicializa o Ollama com GPU, Flash Attention e Keep Alive.
#
# Uso: .\start_ollama.ps1
# Depois: no WSL, rode bash start_project.sh
# ============================================================

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  CV Conformity Agent - Ollama Startup        " -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Mata processos existentes do Ollama ---
Write-Host "Encerrando processos Ollama existentes..." -ForegroundColor Yellow
$procs = Get-Process | Where-Object { $_.Name -like "*ollama*" }
if ($procs) {
    $procs | Stop-Process -Force
    Start-Sleep -Seconds 2
    Write-Host "  OK - Processos encerrados" -ForegroundColor Green
} else {
    Write-Host "  INFO - Nenhum processo Ollama rodando" -ForegroundColor Gray
}

# --- 2. Configura variaveis de ambiente ---
Write-Host ""
Write-Host "Configurando variaveis de ambiente..." -ForegroundColor Yellow

$env:OLLAMA_HOST              = "0.0.0.0:11434"
$env:OLLAMA_KEEP_ALIVE        = "-1"
$env:OLLAMA_FLASH_ATTENTION   = "1"
$env:OLLAMA_NUM_PARALLEL      = "1"
$env:OLLAMA_MAX_LOADED_MODELS = "1"

Write-Host "  OLLAMA_HOST              = $env:OLLAMA_HOST" -ForegroundColor Gray
Write-Host "  OLLAMA_KEEP_ALIVE        = $env:OLLAMA_KEEP_ALIVE" -ForegroundColor Gray
Write-Host "  OLLAMA_FLASH_ATTENTION   = $env:OLLAMA_FLASH_ATTENTION" -ForegroundColor Gray
Write-Host "  OLLAMA_NUM_PARALLEL      = $env:OLLAMA_NUM_PARALLEL" -ForegroundColor Gray
Write-Host "  OK - Variaveis configuradas" -ForegroundColor Green

# --- 3. Inicia o Ollama ---
Write-Host ""
Write-Host "Iniciando Ollama..." -ForegroundColor Yellow
Write-Host "  (Mantenha este terminal aberto)" -ForegroundColor Gray
Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  Ollama rodando em http://0.0.0.0:11434      " -ForegroundColor Green
Write-Host "  Para encerrar: Ctrl+C                       " -ForegroundColor Gray
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

ollama serve