#!/bin/bash
# ─── Mekka Trading — executar paper trade via API ───────────────────────────
cd "$(dirname "$0")"

BASE="http://localhost:8787"

echo "============================================"
echo "  MEKKA TRADING — executando paper trade"
echo "============================================"
echo ""

# 1. Chamar /api/trade/analyze para gerar recomendação
echo "[1/3] Analisando sinal..."
ANALYZE=$(curl -s -X POST "$BASE/api/trade/analyze" \
  -H "Content-Type: application/json" \
  -d '{}')

echo "Resposta analyze: $ANALYZE" | head -c 500
echo ""

# Extrair rec_id
REC_ID=$(echo "$ANALYZE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('recommendation_id',''))" 2>/dev/null)

if [ -z "$REC_ID" ]; then
  echo "ERRO: rec_id não encontrado. Verifique se o servidor está rodando."
  read -p "Pressione Enter para fechar..."
  exit 1
fi

echo ""
echo "   Rec ID: $REC_ID"

# Checar source — só executa se não for mock
SOURCE=$(echo "$ANALYZE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('recommendation',{}).get('source',''))" 2>/dev/null)
echo "   Source: $SOURCE"

if [ "$SOURCE" = "mock" ]; then
  echo ""
  echo "⚠️  Sinal é MOCK — sem sinal real no banco."
  echo "   Rodando insert_test_signal.py para inserir novo sinal..."
  source .venv313/bin/activate
  python insert_test_signal.py
  echo ""
  echo "   Chamando analyze novamente..."
  ANALYZE=$(curl -s -X POST "$BASE/api/trade/analyze" \
    -H "Content-Type: application/json" \
    -d '{}')
  REC_ID=$(echo "$ANALYZE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('recommendation_id',''))" 2>/dev/null)
  SOURCE=$(echo "$ANALYZE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('recommendation',{}).get('source',''))" 2>/dev/null)
  echo "   Novo rec_id: $REC_ID  source: $SOURCE"
fi

echo ""

# 2. Executar trade
echo "[2/3] Executando paper trade..."
EXECUTE=$(curl -s -X POST "$BASE/api/trade/execute" \
  -H "Content-Type: application/json" \
  -d "{\"recommendation_id\": \"$REC_ID\", \"confirmed\": true}")

echo "Resposta execute: $EXECUTE"
echo ""

ORDER_ID=$(echo "$EXECUTE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('order_id','N/A'))" 2>/dev/null)
STATUS=$(echo "$EXECUTE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null)

echo "   Status : $STATUS"
echo "   Order  : $ORDER_ID"
echo ""

# 3. Verificar banco de dados
echo "[3/3] Verificando trades no banco..."
python3 -c "
import sqlite3
db = 'data/mekka_trading.db'
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute('SELECT id, symbol, status, is_paper, side, quantity, avg_price, order_id FROM trades ORDER BY id DESC LIMIT 5')
rows = cur.fetchall()
if rows:
    print('  Trades salvos no banco:')
    for r in rows:
        print(f'    #{r[0]} {r[1]} {r[2]} paper={r[3]} side={r[4]} qty={r[5]:.6f} avg=\${r[6]:,.2f}')
        print(f'       order_id: {r[7]}')
else:
    print('  Nenhum trade no banco ainda.')
conn.close()
"

echo ""
echo "============================================"
echo "  Pronto! Abra o dashboard em:"
echo "  http://localhost:8787"
echo ""
echo "  → Página 'Wallet' para ver posições"
echo "  → Página 'Agents' para ver trades"
echo "============================================"
read -p "Pressione Enter para fechar..."
