#!/bin/bash
# ─── Mekka Trading — startup completo ───────────────────────────────────────
cd "$(dirname "$0")"

echo "============================================"
echo "  MEKKA TRADING — iniciando..."
echo "============================================"

# 1. Mata qualquer instância antiga
echo "[1/4] Parando servidor antigo..."
pkill -f "python.*run\.py" 2>/dev/null
pkill -f "run\.py" 2>/dev/null
sleep 2

# 2. Ativa o venv
echo "[2/4] Ativando venv313..."
source .venv313/bin/activate

# 3. Insere sinal de teste no banco
echo "[3/4] Inserindo sinal de teste BTC LONG..."
python insert_test_signal.py
echo ""

# 4. Inicia o servidor com dashboard habilitado
echo "[4/4] Iniciando servidor em http://localhost:8787 ..."
echo "      (Ctrl+C para parar)"
echo "============================================"
python run.py --dashboard
