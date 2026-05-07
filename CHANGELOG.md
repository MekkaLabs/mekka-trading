# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
