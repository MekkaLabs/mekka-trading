# Mekka Trading — Claude Code Configuration

> Sistema de trading algorítmico para derivativos na Hyperliquid.
> Arquitetura multi-agente inspirada em personagens Marvel.
> Framework: Synkra AIOX v4.0 | Python 3.x + Pydantic v2 + aiohttp

---

## ⚠️ REGRAS DE SEGURANÇA CRÍTICAS

### Live Trading Double Gate (Story 036)

**NUNCA** habilite trading real sem ler `docs/MAINNET-AUTHORIZATION.md` primeiro.

Para operar em mainnet com dinheiro real, AMBAS as variáveis devem estar definidas:
```env
PAPER_TRADING=false
LIVE_TRADING_CONFIRMED=true
```

Qualquer combinação diferente mantém o sistema em paper trading.
O validador em `settings.py` rejeita na inicialização se apenas um dos flags estiver ativo.

### Regras Invioláveis

- **NUNCA** modifique `src/config/settings.py` para remover o validador `live_trading_double_gate`
- **NUNCA** altere os defaults de `paper_trading=True` e `live_trading_confirmed=False`
- **NUNCA** faça commit de `.env` com credenciais de mainnet
- **NUNCA** implemente lógica que bypasse Batman (risk manager) antes de IronMan (executor)
- **NUNCA** coloque ordens diretamente — toda execução passa por `IronMan._run()`
- Agentes de análise (Layer 1) são **read-only** — não colocam ordens

---

## Arquitetura de Agentes

### Layer 1 — Coleta e Análise de Dados

| Agente | Arquivo | Responsabilidade | Output |
|--------|---------|-----------------|--------|
| **Superman** | `superman.py` | Análise técnica: EMA, RSI, MACD, BB, ATR | `MarketData` |
| **Doctor Strange** | `doctor_strange.py` | Sentimento de mercado (Fear & Greed, redes sociais) | `SentimentData` |
| **Black Panther** | `black_panther.py` | Dados on-chain: funding rate, OI, sinais de whales | `OnchainData` |
| **Thor** | `thor.py` | Regime de volatilidade + multiplicador de posição | `VolatilityData` |
| **Aquaman** | `aquaman.py` | Liquidez: spread, profundidade do book, slippage | `LiquidityData` |
| **Spider-Man** | `spider_man.py` | Detector de anomalias (flash crash, volume spike, etc.) | `AnomalyReport` |
| **Flash** | `flash.py` | Momentum de curto prazo (scalping signals) | `MomentumData` |

### Layer 1.5 — Debate Multiagente (opcional)

| Agente | Arquivo | Responsabilidade |
|--------|---------|-----------------|
| **Professor X** | `professor_x.py` | DebateModerator — síntese de perspectivas divergentes |

Controlado por `DEBATE_MODE_ENABLED` nas settings.

### Layer 2 — Decisão (LLM)

| Agente | Arquivo | Responsabilidade | Modelo |
|--------|---------|-----------------|--------|
| **Vision** | `vision.py` | Decisão principal de trading (BUY/SELL/HOLD + size) | Claude Sonnet-4-6 (fallback: GPT-4o) |
| **VisionCritic** | `vision_critic.py` | Revisão crítica da decisão do Vision | GPT-4o |

Vision recebe `MarketAnalysis` consolidado com todos os dados de Layer 1.
`MarketAnalysis.is_safe_to_trade` é checado antes de chamar Vision.

### Layer 3 — Execução

| Agente | Arquivo | Responsabilidade |
|--------|---------|-----------------|
| **Batman** | `batman.py` | Risk Manager — gates de posição, drawdown, exposição |
| **IronMan** | `ironman.py` | Executor — envia ordens para Hyperliquid |
| **Cyclops** | `cyclops.py` | Monitor de posições abertas — stop loss, take profit |

Fluxo obrigatório: `Batman.approve()` → (Telegram approval se `OPERATION_MODE=manual`) → `IronMan.execute()`

### Orquestração

| Agente | Arquivo | Responsabilidade |
|--------|---------|-----------------|
| **Nick Fury** | `nick_fury.py` | Loop principal + opportunity scanner |
| **Beast** | `beast.py` | Self-improvement — análise de performance e ajuste de parâmetros |

---

## Stack Técnico

### Core
- **Python 3.x** com `asyncio` (tudo é `async/await`)
- **Pydantic v2** para modelos e configuração (`BaseModel`, `BaseSettings`)
- **aiohttp** para chamadas HTTP assíncronas
- **loguru** para logging (substituiu `logging` padrão)
- **pandas-ta** para indicadores técnicos

### Exchanges
- **Hyperliquid** (primária) — derivativos perpétuos via REST API + SDK
  - Mainnet: `https://api.hyperliquid.xyz`
  - Testnet: `https://api.hyperliquid-testnet.xyz`
- **Bybit** e **Binance** via **CCXT** (Story 047) — fallback e dados de referência

### Armazenamento
- **SQLite** em `data/mekka_trading.db` — histórico de trades, performance, logs

### LLMs
- **Anthropic Claude Sonnet-4-6** — modelo principal para Vision (preferencial)
- **OpenAI GPT-4o** — fallback quando Claude falha/ausente
- Ordem configurável via `LLM_PREFER_ANTHROPIC` (default `true`)

---

## Modelos de Dados (src/models/market_data.py)

### Enums Principais
```python
Trend: BULLISH | BEARISH | NEUTRAL | SIDEWAYS
VolatilityRegime: LOW | MEDIUM | HIGH | EXTREME
AnomalySeverity: NONE | LOW | MEDIUM | HIGH
WhaleSignal: ACCUMULATION | DISTRIBUTION | NEUTRAL
SentimentLabel: EXTREME_FEAR | FEAR | NEUTRAL | GREED | EXTREME_GREED
```

### Hierarquia de Modelos
```
Candle → MarketData (Superman output)
              ↓
         MarketAnalysis (consolidação para Vision)
         ├── chart: MarketData (required)
         ├── confirmation_chart: MarketData (opcional, timeframe diferente)
         ├── sentiment: SentimentData (Doctor Strange)
         ├── onchain: OnchainData (Black Panther)
         ├── volatility: VolatilityData (Thor)
         ├── liquidity: LiquidityData (Aquaman)
         ├── anomaly: AnomalyReport (Spider-Man)
         ├── momentum: MomentumData (Flash)
         └── debate_verdict: str (Professor X, opcional)
```

`MarketAnalysis.snapshot_id` — fingerprint SHA-256 (16 hex chars) para dedup/tracing (Story 141)
`MarketAnalysis.is_safe_to_trade` — False se `anomaly.should_pause` OU `volatility=EXTREME`
`MarketAnalysis.to_prompt()` — renderiza análise completa como prompt LLM para Vision

---

## Configuração (src/config/settings.py)

Baseado em `Pydantic BaseSettings` — lê de `.env` e variáveis de ambiente.

### Campos Obrigatórios (sem default)
```env
HYPERLIQUID_PRIVATE_KEY=0x...
HYPERLIQUID_WALLET_ADDRESS=0x...
```

### Campos de Segurança (defaults seguros)
```env
PAPER_TRADING=true          # default: true (seguro)
LIVE_TRADING_CONFIRMED=false # default: false (seguro)
HYPERLIQUID_NETWORK=testnet  # default: testnet
```

### Ativos e Exchange
```env
TRADING_ASSETS=BTC,ETH,SOL
ACTIVE_EXCHANGE=hyperliquid  # hyperliquid | bybit | binance
```

### Risk Management
```env
MAX_POSITION_SIZE_PCT=0.02   # 2% do portfolio por posição
MAX_LEVERAGE=5               # alavancagem máxima
MAX_DAILY_DRAWDOWN_PCT=0.10  # 10% drawdown diário = stop
```

### LLMs
```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_MODEL=gpt-4o
ANTHROPIC_MODEL=claude-sonnet-4-6
```

### Telegram (Story 074)
```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TELEGRAM_TRADE_APPROVAL_ENABLED=true  # SUPERSEDED por OPERATION_MODE (compat .env)
TELEGRAM_INBOUND_ENABLED=false        # comandos via Telegram (desabilitado por default)
```

### Modo de Operação (switch raiz de aprovação)
```env
OPERATION_MODE=manual   # manual | automatic — default: manual (seguro)
```

| Modo | Trades | Melhorias | Gates de risco |
|------|--------|-----------|----------------|
| **manual** (default) | operador aprova via Telegram | operador aprova | ✅ ativos |
| **automatic** | auto-executam | auto-aplicam (tighten-only) | ✅ ativos |

- **Fonte da verdade:** `src/config/operation_mode.py`. Default vem de `OPERATION_MODE` no `.env`; override em runtime persistido em `data/operation_mode.json`.
- **Troca em runtime sem reiniciar:** Telegram `/opmode`, `/manual`, `/auto` (entra em vigor no próximo ciclo).
- **Invariante de segurança:** `automatic` remove apenas o gate HUMANO. O double-gate, os gates do Batman, o kill-switch, o daily-loss e o clamp tighten-only do auto-apply continuam valendo — `automatic` **NUNCA** afrouxa risco automaticamente.
- **Consumidores:** gate de trade em `nick_fury.py` (`requires_trade_approval()`), `mentor_applier.is_enabled()`, `implementer/worker` (`worker_is_enabled`/`worker_should_apply`).
- **Preflight:** `automatic` + mainnet+live emite WARN bem visível (auto-trade com dinheiro real é decisão deliberada).

---

## BaseAgent Pattern

```python
class MeuAgente(BaseAgent[TipoDeOutput]):
    def __init__(self):
        super().__init__("NomeAgente", "Descrição do papel")

    async def _run(self, symbol: str, market_data: MarketData) -> TipoDeOutput:
        # implementação aqui
        ...
```

- `run()` é o método público — wraps `_run()` com timing e logging automático
- `_run()` é o método a ser implementado — lança `AgentError(agent, reason)` em falhas
- `AgentError` contém `agent: str` e `reason: str`
- Agentes de análise (Layer 1) **NUNCA** lançam exceptions — retornam resultado mesmo em falha parcial

---

## Comandos de Desenvolvimento

### Setup
```bash
cp .env.example .env          # copiar template de env
python -m venv .venv          # criar virtualenv
source .venv/bin/activate     # ativar (Linux/Mac)
pip install -r requirements.txt
```

### Execução
```bash
# Paper trading (seguro — default)
python -m src.main

# Verificar configuração atual
python -c "from src.config.settings import settings; print(settings.model_dump())"

# Rodar agente isolado para debug
python -c "
import asyncio
from src.agents.superman import Superman
asyncio.run(Superman().run(symbol='BTC', timeframe='4h'))
"
```

### Testes
```bash
pytest tests/                        # todos os testes
pytest tests/unit/                   # testes unitários
pytest tests/integration/            # testes de integração
pytest -k "test_batman" -v          # testes específicos
pytest --cov=src tests/             # com cobertura
```

### Checagem de Qualidade
```bash
ruff check src/                      # linter
mypy src/                            # type checking
ruff format src/                     # formatação
```

---

## Framework AIOX v4.0

### Modelo de Fronteiras L1-L4

| Layer | Papel | Modifica |
|-------|-------|---------|
| **L1** | Core framework | `.aiox-core/core/` — APENAS @devops |
| **L2** | Projeto base | `src/`, `tests/`, `docs/` — todos os agentes |
| **L3** | Configuração | `settings/`, `.env` — @dev, @devops |
| **L4** | Dados/Runtime | `data/`, `logs/` — runtime, não commitar |

### Agentes AIOX (para comunicação interna)

| Handle | Nome | Papel |
|--------|------|-------|
| `@dev` (Dex) | Developer | Implementação de features, código |
| `@qa` (Quinn) | QA Engineer | Testes, qualidade, cobertura |
| `@architect` (Aria) | Architect | Design de sistema, ADRs |
| `@pm` (Morgan) | Product Manager | Stories, backlog, prioridades |
| `@po` (Pax) | Product Owner | Aprovação de features |
| `@sm` (River) | Scrum Master | Processo, bloqueios, retrospectivas |
| `@analyst` (Alex) | Business Analyst | Requisitos, análise de negócio |
| `@data-engineer` (Dara) | Data Engineer | Pipelines, schemas, migrations |
| `@ux-design-expert` (Uma) | UX Designer | UI/UX, experiência do usuário |
| `@devops` (Gage) | DevOps | Infraestrutura, MCP, deploy, Docker |

**Apenas @devops pode:** push para remote, gerenciar MCPs, configurar Docker.

### Desenvolvimento Orientado a Stories

- Todas as features são rastreadas como Stories numeradas (ex: Story 036, Story 074)
- Use `aiox story create` para criar novas stories
- Stories são implementadas sequencialmente, com tracking em `.aiox-core/development/tasks/`

---

## MCP Governance

Ver `~/.claude/rules/mcp-usage.md` para regras completas.

### MCPs Disponíveis
- **playwright** — automação de browser (uso direto)
- **desktop-commander (docker-gateway)** — operações Docker
  - **EXA** — pesquisa web e research
  - **Context7** — documentação de libraries
  - **Apify** — web scraping e extração de dados

### Prioridade de Ferramentas
Sempre preferir ferramentas nativas (`Read`, `Write`, `Bash`, `Grep`, `Glob`) sobre MCPs para operações locais.

---

## Estrutura do Projeto

```
Mekka-Trading/
├── src/
│   ├── agents/              # Todos os agentes Marvel
│   │   ├── base.py          # BaseAgent abstract class
│   │   ├── superman.py      # Layer 1: análise técnica
│   │   ├── doctor_strange.py # Layer 1: sentimento
│   │   ├── black_panther.py # Layer 1: on-chain
│   │   ├── thor.py          # Layer 1: volatilidade
│   │   ├── aquaman.py       # Layer 1: liquidez
│   │   ├── spider_man.py    # Layer 1: anomalias
│   │   ├── flash.py         # Layer 1: momentum
│   │   ├── professor_x.py   # Layer 1.5: debate
│   │   ├── vision.py        # Layer 2: decisão LLM
│   │   ├── vision_critic.py # Layer 2: revisão
│   │   ├── batman.py        # Layer 3: risk manager
│   │   ├── ironman.py       # Layer 3: executor
│   │   ├── cyclops.py       # Layer 3: monitor
│   │   ├── nick_fury.py     # Orquestração: loop principal
│   │   └── beast.py         # Orquestração: self-improvement
│   ├── config/
│   │   └── settings.py      # Pydantic BaseSettings — NUNCA remover double-gate
│   ├── models/
│   │   └── market_data.py   # Todos os modelos Pydantic
│   └── main.py              # Entry point
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
│   └── MAINNET-AUTHORIZATION.md  # LEIA ANTES de ir para mainnet
├── data/                    # SQLite DB (L4 — não commitar)
├── logs/                    # Logs de runtime (L4 — não commitar)
├── .aiox-core/              # Framework AIOX (L1 — somente @devops modifica core/)
├── .env.example             # Template — copiar para .env
├── .env                     # Credenciais reais — NUNCA commitar
└── requirements.txt
```

---

## Notas Importantes para Claude

1. **Responda sempre em português** — o usuário é brasileiro
2. **Este é um sistema de trading com dinheiro real** — segurança tem prioridade máxima
3. **Antes de qualquer mudança em `settings.py`** — verifique se não remove safety gates
4. **A arquitetura é async** — `asyncio.run()` ou `await` para chamadas a agentes
5. **Pydantic v2** — usar `model_dump()` não `.dict()`, `model_validate()` não `.parse_obj()`
6. **Type hints obrigatórios** — o projeto usa mypy strict
7. **Novos agentes** devem herdar de `BaseAgent[T]` e implementar `_run()`
8. **Layer 1 agents** nunca lançam exceptions — sempre retornam resultado (mesmo em falha parcial)
9. **SpiderMan severity HIGH** → `should_pause=True` é auto-aplicado pelo validator do modelo
10. **`MarketAnalysis.is_safe_to_trade`** deve ser checado antes de passar dados para Vision
