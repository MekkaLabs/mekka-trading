# MEKKA-DEV — Manual operacional para a próxima IA

Este documento é o **primeiro arquivo** que qualquer IA (Claude, Codex,
Cursor, Antigravity, Gemini) deve ler antes de tocar em qualquer coisa
no Mekka Trading. Não é README. Não é roster. É o **contrato de como
desenvolver aqui sem quebrar o que já funciona**.

Tempo de leitura: 5 minutos. Lê tudo antes de escrever a primeira linha
de código.

---

## 1. Identidade do projeto em uma frase

Mekka Trading é uma empresa digital autônoma de trading multi-agente,
baseada em AIOX Core, focada em Hyperliquid, paper-trading-first, com
arquitetura CLI-first / risk-first / observability-first. Está sendo
construída de forma **pedagógica e progressiva** — uma feature, uma
story, uma aula gravada por vez.

## 2. Regras absolutas (não negociáveis)

1. **Nunca** colocar ordens reais. `paper_trading=True` é o default e
   Iron Man não toca a SDK quando essa flag está ligada.
2. **Nunca** burlar Batman. Toda execução passa pelo gate de risco.
3. **Nunca** usar nome de "rato/Rat/RatarIA/squad dos ratos" — o
   tema é **exclusivamente super-heróis**. Mapeamento canônico em
   `AGENTS.md`.
4. **Nunca** acelerar arquitetura. Uma feature → uma story em
   `docs/stories/` → um teste → parar. Quem está apressado é problema.
5. **Nunca** misturar pipeline TypeScript e Python sem ler a seção de
   ponte em `docs/ARCHITECTURE.md`. Os dois coexistem; cada um é dono
   da sua superfície.
6. **Nunca** modificar `risk-engine/`, `src/agents/batman.py`,
   `kill_switch`, ou geometria SL/TP do `TradingSignal` sem aprovação
   explícita do operador humano.
7. **Nunca** usar API keys reais em código, exemplos, testes ou docs.
   O `conftest.py` injeta stubs; siga esse padrão.

## 3. Ordem de leitura obrigatória

Antes de escrever código, leia nesta ordem:

1. Este arquivo (você está aqui).
2. `AGENTS.md` — roster de heróis e responsabilidades.
3. `docs/ARCHITECTURE.md` — pipeline, I/O por agente, ponte TS↔Python.
4. **A última story em `docs/stories/`** (ordem numérica). Hoje a mais
   recente é `story-025-strategic-pipeline.md`. Próxima entrega vira
   story-026.
5. `src/config/settings.py` — todas as flags de comportamento moram
   aqui, nunca em constantes mágicas.

Se você for tocar em um agente específico, leia o arquivo Python dele e
o respectivo Pydantic model em `src/models/` antes de qualquer edição.

## 4. Pacing — uma feature, uma parada

Este projeto é gravado em aulas. A IA **precisa** parar entre etapas
para que o operador possa explicar a entrega para terceiros. Como
consequência:

- **Não** implementar 5 agentes de uma vez.
- **Não** adicionar abstrações "pra futuro".
- **Não** fazer refactor agressivo "de passagem".
- **Sempre** entregar dentro do escopo declarado da story atual.
- **Sempre** parar e perguntar quando o escopo cresce.

Regra prática: se a entrega não cabe em uma única explicação de 10
minutos, ela é grande demais. Quebre em duas stories.

## 5. Como criar uma nova story

1. Ler `docs/stories/story-{N-1}-*.md` (a mais recente).
2. Criar `docs/stories/story-{N}-{slug-curto}.md` seguindo a estrutura:
   `Context → Goal → Scope Delivered → Hard Rules Mantidas →
   Pipeline End-to-End (se aplicável) → Acceptance → What's Next`.
3. Implementar **somente** o que está no Scope. Tudo que aparecer
   "no caminho" vira What's Next.
4. Adicionar testes em `tests/` para a entrega.
5. Não fechar a story sem rodar `pytest` e `npm test` localmente.

## 6. Naming e convenções

- **Codename de agente**: super-herói (Superman, Batman, Iron Man, …).
  Ver `AGENTS.md`.
- **Arquivo Python de agente**: snake_case da identidade
  (`iron_man.py`, `doctor_strange.py`, `nick_fury.py`).
- **Classe de agente**: PascalCase sem espaço (`IronMan`,
  `DoctorStrange`, `NickFury`).
- **Story file**: `docs/stories/story-NNN-slug-curto.md`, NNN com 3
  dígitos zero-padded. Index agrupado por milestone em
  `docs/stories/INDEX.md`.
- **Pydantic model**: PascalCase, vive em `src/models/` (signal.py,
  market_data.py, risk.py, execution.py, portfolio.py).
- **Squad folder**: `squads/<dominio>-squad/` ou `squads/<dominio>/`.
- **Dashboard**: read-only por princípio. Detalhes em
  `docs/DASHBOARD.md`. Não escrever no SQLite a partir do dashboard.

## 7. TS vs Python — quem é dono de quê

| Domínio                                     | Lado     | Caminho                                         |
| ------------------------------------------- | -------- | ----------------------------------------------- |
| Mission planner, squad router, runtime loop | TS       | `workflows/`, `cli/`, `dist/`                   |
| Risk Engine (TS — original)                 | TS       | `risk-engine/`                                  |
| Observability (events, audit, alerts, ops)  | TS       | `observability/`, `memory/*.ndjson`             |
| Hyperliquid mock connector                  | TS       | `exchanges/hyperliquid/`                        |
| Strategy engine (signal mocks)              | TS       | `strategy-engine/`                              |
| Agentes Marvel (Layer 1–4)                  | Python   | `src/agents/`                                   |
| Pydantic data contracts                     | Python   | `src/models/`                                   |
| LLM decision (Vision)                       | Python   | `src/agents/vision.py`                          |
| Risk gate (Batman, deterministic)           | Python   | `src/agents/batman.py`                          |
| Hyperliquid execution (Iron Man)            | Python   | `src/agents/iron_man.py`                        |
| Portfolio Manager (read-only account state) | Python   | `src/agents/portfolio_manager.py`               |
| SQLite persistence                          | Python   | `src/persistence/`, `data/mekka_trading.db`     |
| Dashboard web (aiohttp + WebSocket)         | Python   | `src/dashboard/server.py`, `src/dashboard/static/` |
| CLI Python                                  | Python   | `run.py` (`--once`, `--dashboard`, `--dashboard-only`) |
| CLI TypeScript                              | TS       | `cli/main.ts`, `dist/cli/*.js`                  |

**Regra de não-duplicação:** se um conceito existe dos dois lados (ex:
audit log), um lado é fonte de verdade e o outro é mirror. Hoje os dois
lados coexistem sem decisão formal — não introduza um terceiro caminho.

**Catálogo de heróis:** `AGENTS.md` é a fonte humana; `agents/registry.ts`
é a fonte de código TS. Use `python3 scripts/check_roster_consistency.py`
antes de commitar quando tocar em qualquer um dos dois.

**Convenções de contrato (Story 028):**
- Codename canônico: importe `HeroName` de `src/models/heroes.py`
  em vez de string literal quando criar agente novo.
- Event code para audit log: importe `AgentEvent` de
  `src/models/events.py`. Strings ainda funcionam mas estão em
  modo de adoção progressiva.
- Erros estruturados: emita `AgentErrorReport` (de
  `src/models/errors.py`) em paths defensivos, em vez de dict
  livre.
- Timestamp UTC: use `utc_now()` de `src/utils/time.py`.
- Todo model novo herda `BaseModel` e ganha `schema_version: int = 1`.
- Todo model que vai para LLM implementa `to_prompt_section() -> str`
  (Protocol `Promptable`).
- Todo model que vai para `audit_log.payload` implementa
  `to_audit_payload() -> dict` (Protocol `AuditPayloadable`).

## 8. Settings — comportamento mora aqui

Todas as flags de runtime estão em `src/config/settings.py`
(Pydantic v2 BaseSettings). Antes de adicionar `if foo:` em código,
veja se já existe um campo em Settings. Se não existir, **adicione lá
primeiro**, com default conservador.

Settings críticas para entender o sistema:

- `paper_trading: bool = True`
- `hyperliquid_network: "testnet" | "mainnet" = "testnet"`
- `max_position_size_pct: float = 0.02`
- `max_leverage: int = 5`
- `max_daily_drawdown_pct: float = 0.10`
- `min_confidence_threshold: float = 0.65`
- `min_risk_reward_ratio: float = 1.5`
- `main_loop_interval_seconds: int = 14_400` (4h)
- `monitor_interval_seconds: int = 300` (5min)
- `sqlite_db_path: str = "data/mekka_trading.db"`
- `MEKKA_KILL_SWITCH=1` (env) ou arquivo `data/.kill_switch` → halt absoluto

## 9. Testes — quando exigir

Adicione testes quando:

- Criar um novo agente em `src/agents/`.
- Adicionar uma nova validação em `src/models/`.
- Mudar comportamento determinístico (Batman, Thor regimes, etc).

**Não exija** teste para:

- Reescrita de docstrings, comentários, READMEs.
- Renomeações sem mudança de comportamento.
- Mudanças que apenas reorganizam imports.

Mocks padrão:

- OpenAI: `unittest.mock.patch("openai.AsyncOpenAI")` em Vision.
- Hyperliquid SDK: o `paper_trading=True` cobre 99% dos casos sem
  precisar mockar a SDK.
- HTTP externo (CryptoPanic, Hyperliquid /info, CoinGecko): use
  `aiohttp.ClientSession` mocks ou `pytest-httpx`/`aioresponses`.

## 10. Qualidade dos prompts (Vision, futuros LLMs)

- Sempre `response_format={"type": "json_object"}` em chamadas OpenAI.
- Sempre fallback HOLD/no-op em qualquer falha (timeout, rate limit,
  parse, schema). Vision é a referência.
- Sempre coerce defensivo: clip de ranges, cap em hard limits,
  TradeAction inválido → HOLD.
- Sempre logue `metadata.fallback=True` quando entrar no caminho seguro.

## 11. O que NÃO fazer mesmo que pareça boa ideia

- Migrar SQLite para Postgres.
- Adicionar Redis, Kafka, RabbitMQ.
- Construir frontend React.
- Adicionar microsserviço.
- Substituir loguru.
- Substituir Pydantic v2.
- Mexer em `aiox-core/` interno.
- Adicionar typer/click/fire — `argparse` resolve.
- Ligar trade real "só pra testar".

## 12. Quando travar e perguntar

Sempre que:

- O escopo da story crescer durante a implementação.
- Um conceito que parecia óbvio se mostrar ambíguo.
- Houver duplicação iminente entre TS e Python.
- A mudança tocar em risk-engine ou Batman.
- O usuário pedir algo que viola uma regra absoluta da seção 2.

Trave e pergunte. É mais barato perguntar agora que reverter depois.

---

**Fim do MEKKA-DEV.** Próxima leitura: `AGENTS.md`.
