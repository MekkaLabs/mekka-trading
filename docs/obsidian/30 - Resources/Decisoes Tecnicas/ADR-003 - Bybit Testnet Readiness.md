---
title: "ADR-003 — Bybit Testnet Readiness (sandbox routing + UX safety)"
type: adr
tags: [decisao, arquitetura, bybit, testnet, ccxt, multi-exchange]
status: aceita
date: 2026-05-19
supersedes: []
superseded-by: []
related: [[ADR-002 - Multi-Exchange via CCXT]]
---

# ADR-003 — Bybit Testnet Readiness

> **Status**: aceita (entregue em 7 commits na sessão 2026-05-19)
> **Data**: 2026-05-19
> **Autores**: Gusta (+ Claude pair-programming)
> **Branch**: `claude/quirky-ritchie-5352c4`
> **Runbook operacional**: [[Runbook - Bybit Testnet Setup]]

## Contexto

ADR-002 ([[ADR-002 - Multi-Exchange via CCXT]]) introduziu suporte multi-exchange via CCXT na Story 046. Entretanto, ao tentar operar o sistema contra **Bybit testnet** descobrimos cinco bloqueadores que tornavam impossível a validação:

1. **Boot impossível**: `settings.py` exigia `HYPERLIQUID_PRIVATE_KEY`/`ADDRESS` como `Field(...)` (obrigatórios), mesmo com `ACTIVE_EXCHANGE=bybit`. Operador sem chaves HL nunca conseguia ligar o sistema.
2. **Routing de sandbox ausente**: nem `superman.py` nem `iron_man.py` chamavam `exchange.set_sandbox_mode(True)` para Bybit. Resultado: chaves testnet faziam 401 contra mainnet — ou, pior, chaves live iam para produção.
3. **Painel de posições live hardcoded em HL**: `positions_provider.py` chamava `hyperliquid.info.Info` diretamente; `/api/positions` retornava stub em Bybit.
4. **WebSocket de preços hardcoded em HL**: `_hl_price_pump_loop` no `server.py` só conhecia `wss://api.hyperliquid{,-testnet}.xyz/ws`.
5. **Falta de blindagem operacional**: nenhum sinal visual diferenciava testnet de mainnet; nenhuma checagem de clock skew (Bybit rejeita ordens com skew >5s via código 10002, opaco no CCXT).

Adicionalmente, o operador reportou que o painel de Trading Mode "sumiu" — o componente só renderizava na aba Settings do dashboard v1, e havia dois sistemas paralelos não-coordenados (`/api/mode` no office_v2 vs `/api/settings` toggles no dashboard v1).

## Decisão

Entregar **prontidão completa para Bybit testnet** em 7 commits atômicos, divididos em duas fases técnicas + UX:

### Fase 1 — Desbloquear o boot (commits `b7cd04c`, `b039067`)

- Tornar credenciais Hyperliquid **opcionais no campo** (`Field(default="")`) e validar via `model_validator` condicional: cada exchange exige apenas as suas chaves.
- Adicionar `BYBIT_TESTNET: bool = True` (default seguro) e `BINANCE_TESTNET: bool = True`.
- Aplicar `exchange.set_sandbox_mode(True)` em `superman.py` e `iron_man.py`, **antes** de `load_markets()`, quando a flag de testnet estiver ligada.
- Documentar 3 perfis prontos em `.env.example`: HL paper, Bybit testnet paper, Bybit testnet live (com caps conservadores).

### Fase 2 — Adapter exchange-agnostic (commit `e58c7c1`)

- Criar `src/services/price_feed.py` com interface `PriceFeedProvider` + implementações `HyperliquidPriceFeed`, `BybitPriceFeed` e `_NullPriceFeed` (placeholder Binance).
- Factory `make_price_feed()` dispatch por `settings.active_exchange`.
- Em `server.py`: `_hl_price_pump_loop` deletado, substituído por `make_price_feed().run(self._mark_prices)`. Renomear `_hl_prices` → `_mark_prices` (9 ocorrências) e `_hl_pump_task` → `_price_pump_task`.
- Em `positions_provider.py`: nova função `_fetch_ccxt_positions()` + `map_ccxt_positions()` (pura, testável). Dispatch por `settings.active_exchange`.

### Blindagem operacional (commits `2d1c898`, `fc41821`, `9009b34`)

- **Env badge no header** com 4 estados (`unknown` grey, `paper` cyan, `testnet` orange, `mainnet` red+pulse) via novo endpoint `GET /api/env`. Estado inicial pessimista (`unknown`) para nunca implicar falsa segurança em queda de rede.
- **Pré-flight clock skew**: `_check_clock_skew` em `iron_man.py` compara `exchange.fetch_time()` com clock local antes de cada ordem CCXT. Skew >5s aborta com mensagem actionable (`sudo sntp -sS time.apple.com` / `timedatectl set-ntp true`). Skew 1-5s emite warning. Falha em fetch_time degrada open (não bloqueia trading por blip de rede).
- **Painel Trading Mode no Overview**: `data-page="overview settings"` para o painel aparecer já na landing page. Bloco "Modo Global" no topo lista os 3 presets do `/api/mode` (conservative/balanced/aggressive); toggles `super_aggressive` / `altcoins_enabled` continuam embaixo como overrides — texto explica a hierarquia.

## Alternativas Consideradas

### Alternativa 1 — Aceitar credenciais HL stub
- ✅ Prós: zero código novo, operador Bybit põe chaves HL fake e segue a vida.
- ❌ Contras: vergonhoso UX; primeira impressão ruim; abre brecha para chave HL inválida vazar para módulos que tentariam usá-la em paths não-paper.

### Alternativa 2 — Manter `set_sandbox_mode` opcional via env hardcoded fora do código
- ✅ Prós: nenhuma mudança no `settings.py`.
- ❌ Contras: estado escondido; impossível de inspecionar via `/api/env`; operador troca testnet→mainnet editando env sem rastro.

### Alternativa 3 — Refactor pesado em LivePricesProvider abstrato com factory + DI
- ✅ Prós: arquitetura "limpa" futura para qualquer exchange.
- ❌ Contras: 4-6h só pra reorganização sem entregar valor novo; arquitetura ideal é construída a partir de 3+ implementações reais, não 2 (HL + Bybit).

### Alternativa 4 — Provider strategy mínimo + dispatch por settings (escolhida)
- ✅ Prós: 2h, funciona, comportamento HL é byte-identical, comportamento Bybit é exercitável end-to-end.
- ❌ Contras: `_NullPriceFeed` para Binance é tech-debt explícito até alguém implementar.

## Consequências

### Positivas
- **Sistema bootavel em Bybit testnet sem nenhum stub de HL.** `python3 run.py --dashboard` sobe limpo com 5 env vars (`ACTIVE_EXCHANGE`, `BYBIT_API_KEY`, `BYBIT_API_SECRET`, `BYBIT_TESTNET=true`, `PAPER_TRADING=true`).
- **Routing sandbox impossível de errar**: default `BYBIT_TESTNET=true` significa que esquecer essa variável **nunca** vai para mainnet.
- **Validação cruzada**: badge no header garante que o operador nunca confunde paper, testnet e mainnet — pulse vermelho em mainnet é fisicamente impossível de ignorar.
- **Clock skew nunca mais surpreende**: erro 10002 da Bybit agora aborta a ordem **antes** de tentar com mensagem actionable.
- **Painel Trading Mode descobrível**: aparece na Overview, não só Settings. Modo global + overrides coexistem visualmente.

### Negativas / Trade-offs
- **Binance ficou como placeholder** (`_NullPriceFeed`). Operador que ative `ACTIVE_EXCHANGE=binance` tem dashboard funcional mas live-tick vazio. Marcado como TODO no código e no backlog.
- **Dois sistemas de "modo" continuam** no backend (`/api/mode` enum + `/api/settings` booleanos). A consolidação foi visual, não estrutural — uma futura story pode unificá-los no servidor também.
- **Renome `_hl_prices` → `_mark_prices`** quebra qualquer fork interno que dependa do nome antigo. Aceito porque o nome novo é precisamente o que a variável é hoje.

## Implementação

| Commit | Arquivo(s) | LOC |
|---|---|---|
| `b7cd04c` | `settings.py`, `iron_man.py`, `superman.py` | +125 / -3 |
| `b039067` | `.env.example` | +69 |
| `e58c7c1` | `src/services/price_feed.py` (novo), `server.py`, `positions_provider.py` | +452 / -62 |
| `2d1c898` | `server.py`, `index.html`, `style.css`, `app.js` | +152 / -1 |
| `fc41821` | `iron_man.py` | +75 |
| `9009b34` | `index.html`, `app.js`, `style.css` | +188 / -3 |

**Total**: 1.061 linhas adicionadas / 69 removidas em 8 arquivos.

## Hard Rules Mantidas

- `live_trading_confirmed=True` continua obrigatório para `PAPER_TRADING=false`.
- Cyclops e Wolverine continuam paper-only.
- Nenhuma chave de API ou prefixo aparece em log, audit ou response (incluindo `/api/env`).
- Default `BYBIT_TESTNET=true` é uma **camada extra** sobre o double-gate, não substituto.

## Próximos Passos

- [ ] **Bug #4 — Symbol normalization** (`MarketRegistry`) — centraliza `BTC ↔ BTCUSDT ↔ BTC-USD`.
- [ ] **Bug #5 — Teste de integração Bybit testnet** (skip-by-default, roda só se `BYBIT_TESTNET_API_KEY` existe).
- [ ] Implementar `BinancePriceFeed` substituindo `_NullPriceFeed`.
- [ ] Considerar consolidação backend dos dois sistemas de modo (`/api/mode` + `/api/settings`) numa story dedicada.

## Notas

- Veja [[2026-05-19]] para o log da sessão (todas as decisões pontuais e validações).
- O runbook operacional para subir um ambiente Bybit testnet do zero está em [[Runbook - Bybit Testnet Setup]].
