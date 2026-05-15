# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.9.0] — 2026-05-15 — Stories 113-125: LLM Fallback Claude, Superman Python 3.14, Telegram pt-BR, Pixel Office 2x2, Fix Funding Rate

### Added
- **llm_client.py**: cliente unificado `LLMClient` com fallback automático OpenAI → Anthropic Claude. Quando a chave OpenAI é inválida ou ausente, o sistema usa Claude (`claude-sonnet-4-6`) transparentemente
- **Pixel Office layout 2x2**: office ocupa toda a largura no topo; abaixo dois painéis lado a lado (Agent Card + Trading Mode); Roster dos agentes em linha completa; grade de heróis em 4 colunas
- **Novos heróis no Pixel Office**: Flash, Wolverine, Cyclops e Deadpool adicionados com sprites e animações
- **Telegram pt-BR completo**: todas as mensagens do `TelegramAlerter` traduzidas para português do Brasil
- **Explicação leiga no alerta de trade**: campo `💡 Por que entrar agora?` com linguagem acessível explicando o motivo do trade (tendência, RSI, suporte, volume, etc.)
- **Estimativa de duração no alerta de trade**: campo `⏱ Duração estimada` calculado com base na distância SL/TP e alavancagem (Scalp / Curto prazo / Médio prazo / Swing)

### Fixed
- **Superman — Python 3.14 compatibility**: `pandas_ta` e `numba` não compilam no Python 3.14. Superman agora calcula RSI, EMA, Bollinger Bands, MACD e ATR manualmente com pandas puro, sem depender de `pandas_ta`
- **Funding rate bug** (`funding_provider.py`): `asyncio.timeout(5)` retornava um objeto `Timeout` (context manager) em vez de um número, causando `'>' not supported between instances of 'Timeout' and 'int'`. Corrigido para `aiohttp.ClientTimeout(total=5)`
- **Dashboard — flag obrigatória**: dashboard só sobe com `python3 run.py --dashboard`. Documentado para evitar confusão
- **.gitignore**: adicionados `data/dashboard_snapshots/`, `data/mekka_trading.db`, `.agent-os/` para não versionar dados de runtime

### Changed
- `vision.py` + `vision_critic.py`: migrados de cliente OpenAI direto para `LLMClient` — fallback automático sem alterar lógica de negócio
- `settings.py`: `openai_api_key` agora opcional (default `""`); novos campos `anthropic_api_key` e `anthropic_model`
- `telegram_alerter.py`: método `_format` com rótulos em pt-BR e emojis por severidade; `trade_opened()` com bloco de explicação leiga + duração estimada; helpers `_layman_explanation()` e `_estimate_duration()` adicionados

## [0.8.0] — 2026-05-15 — Stories 107-112: Calendar, Balance, Hourly PnL, Gate 3q, Cyclops Reset, Gates Timeline

### Added
- **Story 107 — Calendar heatmap mensal**: endpoint `GET /api/trades/calendar?year=YYYY&month=MM` retorna count e PnL por dia do mês; método `MekkaRepository.get_monthly_trade_calendar(year, month)`
- **Story 108 — Telegram /balance**: novo comando que consulta Hyperliquid REST API (`clearinghouseState`) e exibe accountValue, margin usado, margem livre e withdrawable
- **Story 109 — PnL por hora do dia**: endpoint `GET /api/pnl/hourly?days=30` retorna avg_pnl, total_pnl, count, win/loss por hora UTC (0-23); método `MekkaRepository.get_pnl_by_hour(days)`
- **Story 110 — Batman gate 3q**: rejeita sinal quando ATR% do símbolo é menor que `min_atr_pct` (mercado parado); `settings.min_atr_pct` default 0.0 (desabilitado)
- **Story 111 — Cyclops auto-reset gate 3o**: quando Cyclops fecha posição no TP com PnL positivo, escreve evento `GATE_3O_RESET` no audit log — reset observável da sequência de perdas consecutivas
- **Story 112 — Gates timeline**: endpoint `GET /api/gates/timeline?limit=50` retorna últimos N eventos `GATE_REJECTED` do Batman (3o, 3p, 3q); método `MekkaRepository.get_gate_rejections(limit)`

### Changed
- `settings.py`: novo campo `min_atr_pct` (gate 3q, default 0.0 = desabilitado)
- `batman.py`: gate 3q inserido após gate 3p; gates 3o, 3p e 3q emitem `GATE_REJECTED` no audit log
- `cyclops.py`: bloco Story 111 — audit `GATE_3O_RESET` após TP win
- `telegram_inbound.py`: novo handler `_cmd_balance`, `_HELP_TEXT` e `handlers` atualizados
- `repository.py`: 3 novos métodos estáticos — `get_monthly_trade_calendar`, `get_pnl_by_hour`, `get_gate_rejections`
- `server.py`: 3 novas rotas — `/api/trades/calendar`, `/api/pnl/hourly`, `/api/gates/timeline`

## [0.7.0] — 2026-05-14 — Stories 101-106: Operator UX + Gates 3o/3p

### Added
- **Story 101 — Telegram /weekly**: dispara relatório semanal Deadpool on-demand (janela 7 dias + analytics 30 dias)
- **Story 102 — Batman gate 3o**: rejeita novos trades após `max_consecutive_losses` (default 3) SLs consecutivos; reseta na próxima vitória; `repository.list_recent_closed_trades()`
- **Story 103 — Telegram /equity**: exibe breakdown completo — capital inicial + PnL realizado + PnL não realizado + equity total + variação %
- **Story 104 — R-múltiplo em posições**: `/api/positions` inclui `r_multiple` calculado como `(mark−entry)/|entry−sl|` para cada posição paper
- **Story 105 — Cyclops Partial SL**: fecha 50% da posição ao cruzar −0.75R; gated por `partial_sl_enabled=False`; sentinel `cyclops_partial_sl`; alerta Telegram WARNING
- **Story 106 — Batman gate 3p**: rejeita sinal na mesma direção se os últimos `max_same_direction_streak` (default 4) trades foram todos LONG ou todos SHORT

### Changed
- `settings.py`: novos campos `max_consecutive_losses`, `partial_sl_enabled`, `max_same_direction_streak`
- `telegram_inbound.py`: 2 novos handlers (`_cmd_weekly`, `_cmd_equity`) + help text atualizado
- `batman.py`: gates 3o e 3p inseridos antes do bloco de qualidade (seção 4)
- `cyclops.py`: bloco Partial SL após bloco −0.5R warning, antes do TP1 check
- `positions_provider.py`: campo `r_multiple` em cada item retornado

## [0.6.0] — 2026-05-14 — Stories 090-100: Weekly Report + Quality + Alerts

### Added
- **Story 090**: `DailyReporter.send_weekly_report()` + `run_weekly_loop()` + `/api/report/weekly`
- **Story 091**: comando `/dryrun on|off` e `settings.dry_run_mode`
- **Story 092**: endpoint `/api/session/stats` com resumo da sessão atual
- **Story 093**: endpoint `/api/signals/export?format=csv|json`
- **Story 094**: filtro `min_alert_notional_usd` em `TelegramAlerter.trade_opened()`
- **Story 095**: Wolverine move SL para +1R quando uPnL ≥ 2R
- **Story 096**: Batman gate 3m — rejeita micro-posições com notional < `min_trade_notional_usd`
- **Story 097**: mensagem de trade aberto inclui barra visual `signal_quality_score` + `breached_limits`
- **Story 098**: Cyclops alerta Telegram WARNING quando posição cruza −0.5R; sentinel `cyclops_half_r_warn`
- **Story 099**: `/api/positions` inclui `pnl_usd` real, `mark_price`, `duration_minutes` via `_hl_prices`
- **Story 100**: Batman gate 3n — rejeita símbolo com PnL semanal pior que `-(equity × max_symbol_drawdown_pct)`

## [0.5.0] — 2026-05-13 — Stories 078-089: Commands + Leaderboard + Export

### Added
- **/risk, /leaderboard, /stats, /unblacklist, /dryrun** — novos comandos Telegram
- **Symbol Leaderboard** no dashboard com rank, win rate, Sharpe, best/worst por símbolo
- **Pyramid entry** — gate 3k para scale-in em posições lucrativas
- **TP Ladder** — Cyclops 3 saídas graduais (1/3R, 2/3R, TP completo)
- **Export CSV/JSON** — `/api/trades/export` com BOM UTF-8
- **Signal Quality Score** — Batman calcula score 0-100 composto
- **PnL Heatmap** — grid 7×24 de PnL médio por hora e dia da semana
- Gates 3l (max trades/símbolo/dia), 3m (min notional), 3n (max drawdown semanal)

## [0.4.0] — 2026-05-11 — Stories 063-077: Memory + Advanced Risk + Live Trading

### Added
- Episodic Memory para VisionCritic e Batman
- Memory Panel no dashboard
- Partial TP/Scale-out, Trailing Stop, Daily PnL Auto-pause
- Gates: 3d (correlation), 3e (flash), 3f (cooldown), 3g (ATR), 3h (blacklist), 3i (funding), 3j (hours)
- Live Risk Panel, Trade Approval Flow via inline buttons Telegram
- Equity Curve Chart no dashboard

## [0.1.0] — 2026-05-07

### Added
- Estrutura inicial de governança Git: `.gitignore`, `.gitattributes`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`
- Templates GitHub: `PULL_REQUEST_TEMPLATE.md`, issue templates (bug, feature)
- Vault Obsidian (segundo cérebro) em `docs/obsidian/` com método PARA + MOC
- Templates Obsidian para ADR, Runbook, Aprendizado, Agente, Estratégia, Story, Daily Note
- MOCs iniciais: Arquitetura, Agentes IA, Trading & Estratégia, Risco & Compliance, Operações & Observability, Aprendizados
- ADR-001 documentando adoção de PARA + MOC
- Runbook inicial: "Iniciar runtime do Megazord"
- Glossário do projeto (Mekka, Trading, Hyperliquid, Observability, IA)
- Script `scripts/bootstrap-git.sh` para bootstrap do repositório local

## [0.1.0] — 2026-05-07

### Added
- Megazord v1.1: mission planner + squad router + runtime loop
- Stress scenario packs (volatility, liquidity, drawdown)
- Risk regime manager com kill switch crítico automático
- Controles risk-first com policy limits
- Execução paper-only via conector mock Hyperliquid
- Observabilidade estruturada: logs + eventos + audit trail
- 25 stories implementadas (story-001 a story-025)
- 14 squads especializadas (advisory-board, brand-squad, c-level-squad, claude-code-mastery, copy-squad, cybersecurity, data-squad, design-squad, hormozi-squad, movement, storytelling, traffic-masters)
- CLIs operacionais: runtime, replay, export-report, verify-integrity, health-check, replay-dlq, alerts-retention, ops-status, ops-alerts, ops-alert-audit
- Runtime Python (`run.py`) com flags `--once`, `--equity`, `--dashboard`, `--dashboard-only`
- Implementações Python dos agentes super-heroes em `src/agents/` (Aquaman, Batman, Black Panther, Doctor Strange, Iron Man, Nick Fury, Professor X, Spider-Man, Superman, Thor, Vision)
- **Dashboard web** em `src/dashboard/` (FastAPI/uvicorn) com pixel 3D temático Marvel/Wall Street
  - REST: `/api/overview`, `/api/signals`, `/api/trades`, `/api/audit`
  - WebSocket: `/ws` para atualização em tempo real
  - URL padrão: `http://localhost:8787`
- Persistência SQLite em `src/persistence/` (db, models, repository)
- Suite de testes (`tests/`) — pytest + asyncio

### Security
- Live trading bloqueado na camada de risco
- Kill switch sob controle de governança
- Hyperliquid integração mock-only
- Sem roteamento de ordens reais

[Unreleased]: https://github.com/USUARIO/REPO/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/USUARIO/REPO/releases/tag/v0.1.0
