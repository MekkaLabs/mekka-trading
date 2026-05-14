#!/bin/bash
# Restart Mekka Trading Server
echo "🔴 Parando servidor atual..."
pkill -f "run.py" 2>/dev/null || true
sleep 2
echo "🟢 Iniciando servidor..."
cd ~/Documents/Mekka-Trading

# Encontra o python correto
if [ -f ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
elif command -v python3 &>/dev/null; then
  PYTHON="python3"
else
  PYTHON="python"
fi

echo "Usando: $PYTHON"
$PYTHON run.py --dashboard
