---
title: "Runbook — Bybit Testnet Setup"
type: runbook
tags: [runbook, bybit, testnet, ccxt, multi-exchange, setup]
status: ativo
created: 2026-05-19
updated: 2026-05-19
audience: [operador, dev]
related: [[ADR-002 - Multi-Exchange via CCXT]], [[ADR-003 - Bybit Testnet Readiness]]
---

# Runbook — Bybit Testnet Setup

> **Objetivo**: Subir o Mekka Trading apontado para **Bybit testnet** em **paper mode** em <10 minutos, do zero.
> **Pré-requisitos**: repo clonado, Python 3.13 disponível (Python 3.14 funciona em paper mas tem issues com `pandas-ta`/`numba`).

## Por que testar em Bybit testnet primeiro

- Endpoints reais de Bybit — exercita o caminho completo Superman → Vision → Batman → IronMan.
- USDT de faucet — sem risco financeiro.
- Validação cruzada com Hyperliquid testnet em paralelo (se desejar).
- Smoke test definitivo antes de qualquer consideração de mainnet.

## 1. Gerar chaves de API na Bybit testnet

1. Acesse https://testnet.bybit.com — **conta separada** da mainnet, precisa de email novo.
2. Confirme email e faça login.
3. Topo direito → ícone do perfil → **API**.
4. **Create New Key** → **System-generated**.
5. **Permissions**:
   - ✅ Read
   - ✅ Trade
   - ✅ **Unified Trading Account → Contract / Derivatives Trade** ← essencial. Sem isso, ordens em perp linear retornam código **10003** sem mensagem útil.
   - ❌ Withdraw (deixe desligado — testnet não tem por que)
6. **IP restriction**: deixe vazio para começar (libera todos os IPs). Restrinja depois quando souber seu IP de operação.
7. **Copie** API Key e API Secret. O secret só é exibido uma vez.

## 2. Pegar USDT do faucet de testnet

1. Logado em testnet.bybit.com, topo direito → **Testnet Faucet** (ou menu mobile).
2. Selecione **USDT** → quantia (10.000 USDT é suficiente para semanas de teste).
3. Confirme. Saldo cai no Funding Account.
4. Transfira para **Unified Trading Account** (UTA) via **Transfer** → Funding → Unified Trading. Sem isso, `fetch_balance()` retorna zero e a checagem pré-ordem de margem rejeita tudo.

## 3. Configurar `.env`

Copie de `.env.example` e use o **Profile 2** (já documentado lá):

```bash
cp .env.example .env
```

Edite `.env` adicionando ao topo (ou descomentando o Profile 2):

```bash
# --- Exchange ---
ACTIVE_EXCHANGE=bybit
BYBIT_TESTNET=true            # default — explícito por segurança
BYBIT_API_KEY=<sua key gerada no passo 1>
BYBIT_API_SECRET=<seu secret gerado no passo 1>

# --- Paper trading (mantenha true na primeira semana) ---
PAPER_TRADING=true

# --- Assets a operar (BTCUSDT, ETHUSDT, SOLUSDT em Bybit perp) ---
TRADING_ASSETS=BTC,ETH,SOL

# --- LLM (uma das duas, ou as duas) ---
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
```

> ⚠️ Você **não** precisa preencher `HYPERLIQUID_PRIVATE_KEY` / `HYPERLIQUID_WALLET_ADDRESS`. O `model_validator` em `settings.py` só exige as chaves da `ACTIVE_EXCHANGE`. Se preencher, fica ignorado.

## 4. Instalar dependências Python

```bash
python3.13 -m venv .venv     # use 3.13, NÃO 3.14 (pandas-ta/numba incompatíveis)
source .venv/bin/activate
pip install -r requirements.txt
```

Confirme que `ccxt` foi instalado:

```bash
python -c "import ccxt; print(ccxt.__version__)"
# Esperado: 4.x.x
```

## 5. Smoke test isolado: settings + connection

Antes de subir o sistema todo, rode um teste rápido para confirmar que as credenciais foram aceitas:

```bash
python -c "
import asyncio
from src.config.settings import settings
print(settings.summary())

async def probe():
    import ccxt.async_support as ccxt
    ex = ccxt.bybit({'apiKey': settings.bybit_api_key, 'secret': settings.bybit_api_secret, 'options': {'defaultType': 'swap'}})
    ex.set_sandbox_mode(True)
    await ex.load_markets()
    bal = await ex.fetch_balance()
    print(f'USDT free: {bal[\"USDT\"][\"free\"]}')
    await ex.close()

asyncio.run(probe())
"
```

Saída esperada:

```
============================================================
  Mekka Trading — Configuration Summary
============================================================
  Mode          : PAPER
  Live confirmed: no
  Exchange      : BYBIT
  Network       : TESTNET
  ...
USDT free: 10000.0
```

Se você ver `USDT free: 0.0`, volte ao **passo 2** e confirme que transferiu USDT para o Unified Trading Account.

## 6. Subir o dashboard

```bash
python3.13 run.py --dashboard
```

Abra http://localhost:8787

**O que você deve ver**:
- Header com badge laranja **BYBIT · TESTNET** ao lado de "Mekka Trading Command Center"
- (Como `PAPER_TRADING=true`, o badge mostra cyan **BYBIT · PAPER** — operação simulada)
- TopBar financeiro lendo saldo do unified account via CCXT
- Painel "⚡ Modos de Trading" já visível na aba **Overview** com os 3 presets (conservative/balanced/aggressive) e os toggles
- Live Trading panel pegando preços de Bybit testnet via WebSocket V5 (`stream-testnet.bybit.com/v5/public/linear`)

## 7. Forçar um sinal de paper trade

Na aba **Live** do dashboard:

1. Clique em **Trade Now**.
2. Vision vai analisar BTC; Batman vai validar risco; o card mostra o `RecommendationCard`.
3. **Confirmar** → o paper trade é registrado em `data/mekka_trading.db`.
4. Cyclops começa a monitorar SL/TP no próximo monitor cycle (5 min default).

## 8. Próximos passos para ir live testnet (cuidado)

> **Só faça isso depois de pelo menos 24h em paper mode funcionando 100%.**

Para passar de paper testnet → live testnet (sem dinheiro real, mas ordens reais na corretora):

```bash
# Edite .env:
PAPER_TRADING=false
LIVE_TRADING_CONFIRMED=true     # double-gate obrigatório
MAX_POSITION_SIZE_PCT=0.005     # 0.5% — comece pequeno
MAX_LEVERAGE=2                  # 2x — comece baixo
MAX_TOTAL_NOTIONAL_USD=100.0    # hard cap absoluto
```

Reinicie o dashboard. Badge no header agora vai mostrar **BYBIT · TESTNET** (laranja sem o "PAPER"). Toda ordem passa pelo `_place_ccxt_order` em `iron_man.py` com:
- Clock skew check (aborta se >5s)
- Pre-flight margin check via `fetch_balance()`
- Entry como limit IOC
- SL/TP separados como reduce-only stops
- Retry 3x com backoff exponencial

## Troubleshooting

### "BYBIT_API_KEY not set"

Sua `.env` não tem a chave ou está em outro diretório. Confira:
```bash
grep BYBIT .env
```

### "set_sandbox_mode failed" no log

Versão antiga de CCXT (<4.0). Force atualizar:
```bash
pip install --upgrade 'ccxt>=4.0.0'
```

### Ordem rejeitada com código `10002`

Clock skew >5s. O sistema já detecta e aborta com mensagem clara. Sincronize NTP:
```bash
# macOS
sudo sntp -sS time.apple.com
# Linux
sudo timedatectl set-ntp true
```

### Ordem rejeitada com código `10003`

Permissão de Contract/Derivatives Trade não habilitada na chave. Volte ao **passo 1** e marque essa permissão.

### `fetch_balance()` retorna `USDT: 0`

Você tem USDT no Funding Account mas não no Unified Trading Account. Transfira via UI da Bybit testnet (passo 2).

### Badge no header fica em **"??? · ???"** (cinza)

`/api/env` está respondendo erro. Confira logs do servidor — provavelmente a app caiu durante startup. Normalmente o terminal mostra a stack trace.

## Notas

- Veja [[ADR-003 - Bybit Testnet Readiness]] para o histórico técnico das mudanças.
- Veja [[ADR-002 - Multi-Exchange via CCXT]] para a decisão original de adotar CCXT.
- Veja [[2026-05-19]] para o log da sessão que entregou este caminho.
