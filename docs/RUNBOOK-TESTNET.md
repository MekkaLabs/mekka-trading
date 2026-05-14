# RUNBOOK — Cold Start Testnet

> **Para quem é este documento**: o operador (você ou quem for) que vai
> virar a chave de paper para testnet pela primeira vez. Cada passo
> tem um gate humano explícito. Não pular.

> **Pré-requisitos**: 30+ stories entregues, ≥150 testes pytest verdes,
> AUTO-CONTINUE-PLAN § 1–3 concluídos.

---

## 0. Antes de começar — alinhamento mental

Você está prestes a deixar `paper_trading=False` por 1 segundo na sua
vida. Isso significa que Iron Man pode mandar uma ordem real para
Hyperliquid testnet. Em testnet o dinheiro é fake, mas:

- A SDK Hyperliquid pode comportar-se diferente do que assumimos.
- A primeira ordem é o **smoke test** mais importante do projeto.
- Se algo dar errado, o kill switch (§ 6) é seu amigo.

**Bloqueie 1 hora** sem reuniões. Faça com café, não com pressa.

---

## 1. Ambiente Python correto (15 min)

`pandas-ta` runtime exige Python 3.13. Lazy imports salvam pytest, não
salvam Superman.run() em produção real.

```bash
brew install python@3.13
cd /Users/gustavovicente/Documents/Mekka-Trading
deactivate 2>/dev/null
rm -rf .venv
/opt/homebrew/bin/python3.13 -m venv .venv
source .venv/bin/activate
python -V                                  # confirma 3.13.x
pip install --upgrade pip
pip install -r requirements.txt
```

**Gate humano:** confirma `python -V` mostra 3.13.x antes de prosseguir.

```bash
pytest -v
```

**Esperado:** ~169 verdes. Se vermelho, **PARE** e investigue antes de
continuar — não tem como ir para testnet com baseline quebrado.

---

## 2. Criar wallet testnet dedicada (5 min)

**NUNCA** use sua wallet pessoal. Crie uma nova.

```python
# Em uma sessão Python isolada:
from eth_account import Account
acct = Account.create()
print("ADDRESS:", acct.address)
print("PRIVATE_KEY:", acct.key.hex())
```

**Gate humano:** copia ambos para um gerenciador de senhas SEGURO.
Confirma que entende: a private key dá acesso total à wallet. Não
commita, não compartilha.

---

## 3. Faucet — funded testnet wallet (10 min)

Acessa https://app.hyperliquid-testnet.xyz e:

1. Conecta a wallet do passo 2.
2. Solicita testnet USDC (1.000 USDC é suficiente).
3. Confirma saldo apareceu.

**Gate humano:** balance ≥ $500 USDC testnet visível na UI.

---

## 4. Preencher `.env` conservadoramente (5 min)

Edita `/Users/gustavovicente/Documents/Mekka-Trading/.env`:

```bash
# OpenAI (necessário para Vision)
OPENAI_API_KEY=sk-real-key-do-passo-anterior

# Hyperliquid testnet
HYPERLIQUID_PRIVATE_KEY=0x...  # do passo 2
HYPERLIQUID_WALLET_ADDRESS=0x... # do passo 2
HYPERLIQUID_NETWORK=testnet

# Comportamento conservador na primeira semana
PAPER_TRADING=false
TRADING_ASSETS=BTC

MAX_POSITION_SIZE_PCT=0.005   # 0.5% (default 2%)
MAX_LEVERAGE=2                # default 5
MAX_TRADES_PER_DAY=3          # default 10
MAX_TOTAL_CAPITAL_PCT=0.05    # 5% (default 10)
MAX_TOTAL_NOTIONAL_USD=100    # absoluto USD$100

# Vision Critic OFF na primeira semana (custo OpenAI dobra)
VISION_CRITIC_ENABLED=false

# Telegram (opcional, mas recomendado)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

**Gate humano:** confirma:
- `PAPER_TRADING=false` é a primeira vez na vida do projeto.
- `MAX_TOTAL_NOTIONAL_USD=100` significa Iron Man não pode pôr mais
  de $100 testnet em jogo simultâneo.
- `TRADING_ASSETS=BTC` reduz superficie de erro a um único símbolo.

```bash
python -c "from src.config.settings import settings; print(settings.summary())"
```

Confirma que `Mode = LIVE`, `Network = TESTNET`, `Max Position = 0.5%`.

---

## 5. Smoke test SDK manual (15 min) — CRÍTICO

**Antes de Vision decidir e Iron Man enviar**, valide a SDK na unha.

```python
# python -i (interactive)
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
import os

pk = os.environ["HYPERLIQUID_PRIVATE_KEY"]
if pk.startswith("0x"):
    pk = pk[2:]
wallet = Account.from_key(bytes.fromhex(pk))
addr = os.environ["HYPERLIQUID_WALLET_ADDRESS"]

info = Info(constants.TESTNET_API_URL, skip_ws=True)
ex = Exchange(wallet=wallet, base_url=constants.TESTNET_API_URL, account_address=addr)

# 5.1. Read clearinghouseState — confirma wallet conhecida pela testnet
state = info.user_state(addr)
print("equity:", state.get("marginSummary", {}).get("accountValue"))

# 5.2. Set leverage 2x cross em BTC
print("update_leverage:", ex.update_leverage(2, "BTC", True))

# 5.3. Coloca uma ordem TINY ($10 USDC) IOC limit ABAIXO do market
#      (não vai filar — é só smoke test do shape de resposta)
mid_price = 65000  # ajusta para o mid atual real
order_resp = ex.order(
    "BTC", True, 0.0002, mid_price * 0.95,  # 5% abaixo, não fila
    {"limit": {"tif": "Ioc"}}, False,
)
print("order_resp shape:")
import json; print(json.dumps(order_resp, indent=2))
```

**Gates humanos:**
- 5.1: equity > 0 (faucet funcionou).
- 5.2: leverage update retornou `{"status": "ok"}` ou similar.
- 5.3: response tem `data.statuses[0]` — anota a estrutura **exata** e
  compara com o que `IronMan._extract_oid` / `_extract_avg_px` /
  `_extract_filled_size` esperam (ler `src/agents/iron_man.py`
  linhas 175–205).

**Se a SDK retornar shape diferente do que Iron Man parseia: PARE.**
Abre uma micro-story para ajustar os parsers ANTES de virar a chave.

---

## 6. Kill switch reflexo (2 min)

Antes de qualquer coisa correr, treine o gesto:

```bash
# Janela 1 (ops): tem o kill switch sempre pronto
cd /Users/gustavovicente/Documents/Mekka-Trading
./scripts/kill.sh "operator panic"

# Janela 2 (release):
rm data/.kill_switch
```

**Gate humano:** você consegue executar `./scripts/kill.sh` em < 5 segundos?

---

## 7. First run — `--once` mode (15 min — vigiado)

```bash
# Janela 1 (runtime)
source .venv/bin/activate
python run.py --once
```

**O que esperar:**
1. Settings.summary() printa `Mode = LIVE`, `Network = TESTNET`.
2. NickFury BOOT event no audit_log.
3. PortfolioManager.run() → SNAPSHOT_HYPERLIQUID (não PAPER_FALLBACK!).
4. ProfessorX rodando (logs de Superman, Doctor Strange, etc).
5. Vision retorna TradingSignal.
6. Batman avaliando.
7. Iron Man:
   - Se Vision retornou HOLD ou Batman REJECTED → status `SKIPPED`.
   - Se Batman APPROVED → tentativa de ordem real.

**Possíveis cenários:**

| Cenário | Ação |
| ------- | ---- |
| Tudo verde, ordem placed | Vai para passo 8 |
| `EXEC_ERROR: SDK returned ...` | PARA, abre micro-story para ajustar parser |
| Vision sempre HOLD | Mercado neutro? OK. Repete em algumas horas. |
| Batman sempre REJECTED | Capital cap muito apertado? Revisa `.env` |
| Algum traceback Python | PARA. Não é OK em live. Volta para paper. |

**Gate humano após 15 min:**
- audit_log tem ≥ 5 events.
- Nenhum CYCLE_ERROR severity ERROR.
- Wallet testnet ainda intacta (saldo razoável vs. esperado).

---

## 8. Loop infinito — primeira meia hora vigiada (30 min)

```bash
python run.py --dashboard
```

Abre browser em http://localhost:8787 e fica olhando:

- `/api/overview` mostra contadores subindo.
- `/api/audit` mostra eventos chegando.
- `/api/trades` aparece quando uma ordem fila.

**Métricas para vigiar nas primeiras 30 min:**

| Métrica | OK | Suspeito | Pare |
| ------- | -- | -------- | ---- |
| EXEC_ERROR count | 0 | 1 | ≥ 2 |
| RISK_KILL_SWITCH | 0 | — | ≥ 1 |
| Vision fallback streak | 0 | 2 | ≥ 3 |
| `audit.payload.breaker` aparece | nunca | — | qualquer |
| Saldo wallet movimentou | ±0.5% | ±2% | ≥ 5% |

Se entrou em **Pare** em qualquer métrica:
1. `./scripts/kill.sh "first session metric breach"`
2. `Ctrl+C` no `run.py`
3. Investigar o audit_log antes de retomar.

---

## 9. Daily review — primeiro dia inteiro

Ao fim do dia:

```bash
# Verificar daily_pnl
python -c "
import asyncio, sqlite3
conn = sqlite3.connect('data/mekka_trading.db')
c = conn.cursor()
print(list(c.execute('select * from daily_pnl order by date_utc desc limit 5')))
print(list(c.execute('select agent, event, count(*) from audit_log group by agent, event')))
"
```

Confirme:
- `daily_pnl` tem 1 row para hoje.
- `pnl_pct` faz sentido vs. movimento do mercado.
- `drawdown_pct < max_daily_drawdown_pct` (default 10%).
- audit_log distribution não está dominado por ERROR.

---

## 10. Promoção — depois de 1 semana verde

Critérios para relaxar os limites do `.env`:
- 7 dias consecutivos sem `RISK_KILL_SWITCH` automático.
- Win rate (wins/(wins+losses)) ≥ 0.40 (paper trading válido).
- Nenhum `EXEC_ERROR` não-explicado.
- Operador acompanhou pelo menos 1× por dia o dashboard.

**Se passou:** edita `.env` para defaults canônicos:
```bash
MAX_POSITION_SIZE_PCT=0.02
MAX_LEVERAGE=5
MAX_TRADES_PER_DAY=10
MAX_TOTAL_CAPITAL_PCT=0.10
TRADING_ASSETS=BTC,ETH,SOL  # adiciona symbols
```

**Se não passou:** revisa o INCIDENT-PLAYBOOK e identifica padrão.

---

## 11. Mainnet — gate humano formal

**Não fazer ainda.** AUTO-CONTINUE-PLAN § 7 lista os pré-requisitos:
cobertura ≥ 80% em Vision/Batman/Iron Man, 1 mês de testnet limpo,
Wolverine ENDORSE rate ≥ 70%, Vision Critic ON 1 semana sem regressão,
Story 032b (audit single source) entregue.

---

## Apêndice — checklist consolidado

```
[ ] 1. Python 3.13 venv criado, pytest ~169 verdes
[ ] 2. Wallet testnet criada, address+key em gerenciador de senhas
[ ] 3. Faucet processado, balance ≥ $500 testnet USDC
[ ] 4. .env conservador preenchido (paper=false, limits apertados)
[ ] 5. Smoke test SDK manual: clearinghouseState ok, leverage ok,
       order shape compatível com IronMan parsers
[ ] 6. kill.sh testado em < 5 segundos
[ ] 7. python run.py --once vigiado por 15 min — sem ERROR
[ ] 8. python run.py --dashboard vigiado por 30 min
[ ] 9. Daily review do primeiro dia: daily_pnl ok, audit limpo
[ ] 10. 7 dias verdes → relaxa limites no .env
[ ] 11. Mainnet readiness — gate humano AUTO-CONTINUE § 7
```
