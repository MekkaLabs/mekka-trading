---
title: Agente — Mentor
type: agente
tags: [agente, learning, parameter-tuning, read-only, mentor, charles-xavier, continuous-improvement]
codename: Mentor
real_name: Charles Xavier (Professor X)
role: Pattern distiller — converte outcomes em deltas de parâmetro
status: ativo
layer: L4 (Learning tier)
introduced: 2026-05-25
created: 2026-05-25
updated: 2026-05-25
---

# Agente — Mentor

> **Codinome**: Mentor (Charles Xavier — Professor X)
> **Papel**: Distila padrões de outcomes resolvidos em deltas de parâmetros concretos
> **Layer**: L4 (Learning — fecha o loop que [[Beast]] deixava aberto)
> **Arquivo**: `src/agents/mentor.py`
> **Endpoint**: `GET /api/mentor/suggestions`
> **Cabeado**: `NickFury.run_monitor_cycle` a cada 5 min (~260ms quando há dados)

## Missão

Fechar o **loop de aprendizagem** do sistema. Antes, [[Beast]] produzia
`ImprovementProposal` em inglês livre e enviava pro Telegram — operador
humano lia e decidia manualmente. Vision/Batman injetavam memory blocks
mas nunca ajustavam thresholds.

Mentor lê os **resolved outcomes** (WIN/LOSS/NEUTRAL) do `agent_memories`,
recentes rejeições do Batman, e proximidade do drawdown, e produz
`ParameterSuggestion` **tipados**: nome do parâmetro + valor atual +
valor sugerido + razão + evidência + flag `can_auto_apply`.

> _Por que Charles Xavier?_ É o **mentor** dos X-Men, o que sintetiza
> padrões e ensina os outros agentes a evoluírem. Read-only do mundo,
> escreve nas mentes (parâmetros).

## Pré-requisito histórico

Mentor só funciona porque os **4 gaps de memory writer órfão** foram
fechados em `57bdc96` (2026-05-25). Antes desse commit, `agent_memories`
tinha 0 outcomes resolved. Agora cada close (auto-Cyclops, manual via
dashboard) chama [[Trade Outcome Resolver]] que popula WIN/LOSS/NEUTRAL.

## Heurísticas iniciais (v1)

| Trigger | Ação | Auto-apply? |
|---|---|---|
| `win_rate < 35%` em ≥8 trades | tighten `min_confidence` (+0.05) | ✅ sim |
| `win_rate > 65%` em ≥20 trades | loosen `min_confidence` (−0.05) | ❌ exige operator |
| Batman `rejection_rate > 80%` | sugere loosen gates | ❌ exige operator |
| Drawdown ≥ 70% do limite diário | tighten `max_daily_drawdown_pct` (/2) | ✅ sim |

**Conservative bias**: loosening **sempre** exige `can_auto_apply=False`.
Apertar gates de risco é sempre seguro; soltar exige revisão humana.

## Output (ParameterSuggestion)

```python
@dataclass
class ParameterSuggestion:
    parameter_name: str        # "min_confidence", "max_daily_drawdown_pct"
    current_value: Any         # 0.65
    suggested_value: Any       # 0.70
    direction: str             # "tighten" | "loosen"
    reason: str                # "win rate 25% em 20 trades"
    evidence: dict             # {n, win_rate, wins, losses, ...}
    confidence: float          # 0.0–1.0
    can_auto_apply: bool       # False por default; True em tightening
```

`to_env_line()` produz `MEKKA_MIN_CONFIDENCE=0.7` pronto para `.env`.
Operator continua dono do apply.

## Princípios

1. **READ-ONLY**: Mentor NUNCA muta `settings.py`. Só sugere.
2. **Conservative bias**: loosening = manual review obrigatório.
3. **Evidence-based**: cada suggestion vem com dict de números.
4. **Fail-silent isolated**: cada coletor (winrate, rejection, drawdown)
   é try/except independente. Falha em um não bloqueia os outros.
5. **Zero spam**: audit `MENTOR_SUGGESTED` **só** quando há suggestion.
6. **Conhecimento, não regras hardcoded**: a sugestão é alimentada por
   dados reais — não há "if regime=BULL then…" estático.

## Cross-references

- Leitor primário (futuro): [[Vision]] vai consumir suggestions auto-applicable como input pro Batman
- Fonte de outcomes: [[Trade Outcome Resolver]] → `agent_memories`
- Fonte de rejections: [[Batman]] → audit_log `RISK_REJECTED`
- Fonte de drawdown: `MekkaRepository.get_today_drawdown_pct()`
- Auditor que **propunha** em inglês livre (paralelo): [[Beast]]
- Cabeamento: [[Nick Fury]] no `run_monitor_cycle`

## Status atual

- ✅ Implementado em `src/agents/mentor.py` (commit `fde8c01`)
- ✅ Endpoint `GET /api/mentor/suggestions`
- ✅ Cabeado no `NickFury.run_monitor_cycle` (commit `29f3f80`)
- ✅ 8 testes em `tests/test_mentor.py` (8/8 PASS)
- ✅ Audit `MENTOR_SUGGESTED` ao gravar suggestion
- ⏳ **Aguardando dados**: 0 suggestions agora porque resolved_outcomes=0
  no DB. Vai começar a produzir suggestions quando 2-3 trades fecharem
  via Cyclops auto-close (paper) ou manual close (live) e popularem
  `agent_memories` com WIN/LOSS.
- ⏳ Próximo: dashboard tab para suggestions + 1-click apply para
  `can_auto_apply=True`
- ⏳ Próximo: Mentor daily report no Telegram (similar Beast)

## Próximas heurísticas (backlog)

- Correlação action × regime (LONG em BEARISH historicamente falha)
- Tempo médio até resolution (trades que demoram > N horas → revisar TP)
- Pattern de PnL por símbolo (BTC vs ETH vs SOL)
- Detecção de regime de mercado e sugestão de pausar trades
- Tunagem de `vision_critic_min_disagreement` baseado em endorse rate
