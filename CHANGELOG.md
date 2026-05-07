# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Estrutura inicial de governança Git: `.gitignore`, `.gitattributes`, `CHANGELOG.md`, `CONTRIBUTING.md`
- Vault Obsidian (segundo cérebro) em `docs/obsidian/` com método PARA + MOC
- Templates para ADR, Runbook, Aprendizado, Agente, Estratégia, Story, Daily Note
- MOCs iniciais: Arquitetura, Agentes IA, Trading & Estratégia, Risco & Compliance, Operações & Observability, Aprendizados
- ADR-001 documentando adoção de PARA + MOC
- Runbook inicial: "Iniciar runtime do Megazord"

## [0.1.0] — 2026-05-07

### Added
- Megazord v1.1: mission planner + squad router + runtime loop
- Stress scenario packs (volatility, liquidity, drawdown)
- Risk regime manager com kill switch crítico automático
- Controles risk-first com policy limits
- Execução paper-only via conector mock Hyperliquid
- Observabilidade estruturada: logs + eventos + audit trail
- 24 stories implementadas (story-001 a story-024)
- 14 squads especializadas (advisory-board, brand-squad, c-level-squad, claude-code-mastery, copy-squad, cybersecurity, data-squad, design-squad, hormozi-squad, movement, storytelling, traffic-masters)
- CLIs operacionais: runtime, replay, export-report, verify-integrity, health-check, replay-dlq, alerts-retention, ops-status, ops-alerts, ops-alert-audit

### Security
- Live trading bloqueado na camada de risco
- Kill switch sob controle de governança
- Hyperliquid integração mock-only
- Sem roteamento de ordens reais

[Unreleased]: https://github.com/USUARIO/REPO/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/USUARIO/REPO/releases/tag/v0.1.0
