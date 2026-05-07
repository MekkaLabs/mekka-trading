---
title: MOC — Agentes IA
type: moc
tags: [moc, agente]
created: 2026-05-07
---

# 🦸 MOC — Agentes IA

> Mapa vivo dos agentes que compõem a operação Mekka Trading. Inspiração temática: super-heróis.

## Identidade dos Agentes

| Codinome | Papel | Domínio |
|---|---|---|
| **Superman** | Chief Market Overseer | Visão geral de mercado |
| **Batman** | Risk Guardian | Políticas de risco / kill switch |
| **Iron Man** | Hyperliquid Execution Engineer | Execução em Hyperliquid (mock) |
| **Professor X** | Swarm Coordinator | Orquestração entre squads |
| **Doctor Strange** | Macro Probability Analyst | Probabilidades macro |
| **Flash** | Momentum Scalper | Estratégia de momentum/scalp |
| **Aquaman** | Liquidity Analyst | Análise de liquidez |
| **Spider-Man** | Anomaly Detector | Detecção de anomalias |
| **Wolverine** | Recovery Agent | Recuperação após falhas |
| **Black Panther** | Onchain Intelligence | Inteligência onchain |
| **Nick Fury** | Mission Commander | Comando de missão |
| **Vision** | Predictive Analyst | Análise preditiva |
| **Thor** | Volatility Engine | Motor de volatilidade |
| **Deadpool** | Chaos Simulator | Simulações de caos |

## Squads Baseline

- `alpha-risk-command` — política de risco, governança do kill-switch, gates de validação
- `hyperliquid-mock-ops` — adaptador da exchange (mock), feed de mercado, ensaio de execução
- `market-intel-lab` — experimentos de sinal, contexto de anomalia e volatilidade

## Squads Especializadas (em `/squads`)

- advisory-board, brand-squad, c-level-squad, claude-code-mastery
- copy-squad, cybersecurity, data-squad, design-squad
- hormozi-squad, movement, storytelling, traffic-masters

## Regras Duras (Hard Rules)

> ⚠️ Estas regras são **invioláveis** no projeto:
> - Nunca executar trades reais
> - Nunca contornar a validação de risco
> - Nunca introduzir compartilhamento de estado entre projetos
> - Sempre emitir logs, eventos e registros de auditoria

## Notas de agentes

```dataview
LIST
FROM #agente OR #squad
WHERE file.path != this.file.path
SORT file.name ASC
```

## Próximas adições (sugestões)

- [ ] Criar nota detalhada por agente em `20 - Areas/Agentes IA/`
- [ ] Documentar prompts de cada agente
- [ ] Mapear interações entre squads
