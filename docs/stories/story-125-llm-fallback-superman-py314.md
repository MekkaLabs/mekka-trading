# Story 125 — LLM Fallback Claude, Superman Python 3.14, Telegram pt-BR, Pixel Office 2×2

**Versão:** 0.9.0  
**Data:** 2026-05-15  
**Stories cobertas:** 113–125

---

## Context

Durante sessão de desenvolvimento em Python 3.14 (Homebrew), três
problemas críticos surgiram simultaneamente:

1. **Superman quebrou** com `'DataFrame' object has no attribute 'ta'`
   — `numba` não compila no Python ≥ 3.14 e `pandas_ta` depende de
   numba, portanto o accessor `.ta` nunca se registra.

2. **Funding rate bug** em `funding_provider.py`: `asyncio.timeout(5)`
   retorna um context manager (`Timeout`), não um número. O aiohttp
   recebia um objeto `Timeout` onde esperava `int`, causando
   `'>' not supported between instances of 'Timeout' and 'int'`.

3. **Resiliência do LLM**: quando a chave OpenAI é inválida ou ausente,
   o sistema falhava silenciosamente em vez de cair em fallback.

Além disso, o operador pediu: todas as mensagens Telegram em pt-BR com
explicação leiga do motivo do trade e estimativa de duração.

---

## Goal

- Sistema rodando em Python 3.14 sem dependências de numba/pandas_ta.
- LLM com fallback automático OpenAI → Anthropic Claude.
- Telegram 100% pt-BR com contexto operacional útil.
- Dashboard com layout Pixel Office 2×2 e novos heróis.

---

## Scope Delivered

### Story 113–114 — LLM Fallback (llm_client.py)

- `src/agents/llm_client.py`: classe `LLMClient` com método `chat()`.
- Tenta OpenAI primeiro; se `openai_api_key` vazio ou erro 401,
  usa Anthropic Claude (`claude-sonnet-4-6`) transparentemente.
- `make_llm_client()` é a factory que os agentes devem usar.
- `vision.py` e `vision_critic.py` migrados de `AsyncOpenAI` direto
  para `LLMClient`.
- `settings.py`: `openai_api_key` agora opcional (`default=""`);
  novos campos `anthropic_api_key` e `anthropic_model`.

### Story 115–120 — Superman Python 3.14

- `pandas_ta` importado dentro de `try/except`; em caso de falha,
  `ta = None` e a flag `_use_ta = False`.
- Implementações manuais com pandas puro para todos os indicadores
  que Batman e Vision consomem:
  - RSI(14), EMA(20), EMA(50)
  - Bollinger Bands (20, 2σ)
  - MACD(12, 26, 9) + sinal + histograma
  - ATR(14) via True Range + EWM
- Output `MarketData` inalterado — downstream não percebe a mudança.

### Story 121–122 — Pixel Office 2×2 + novos heróis

- Layout 2×2: office ocupa largura total no topo; abaixo dois painéis
  (Agent Card + Trading Mode); Roster em linha completa; grade 4 colunas.
- Flash, Wolverine, Cyclops e Deadpool adicionados com sprites e
  animações em `office_v2.bundle.js`.

### Story 123 — Fix funding rate

- `funding_provider.py`: substituído `asyncio.timeout(5)` (context manager)
  por `aiohttp.ClientTimeout(total=5)` nos métodos `_fetch_hyperliquid()`
  e `_fetch_binance()`.
- `import aiohttp` movido para topo do arquivo.

### Story 124–125 — Telegram pt-BR + explicação + duração

- `telegram_alerter.py` completamente reescrito em pt-BR.
- `_format()` com rótulos em português e emojis por severidade.
- `trade_opened()` inclui:
  - `💡 Por que entrar agora?` — `_layman_explanation()` extrai
    frases legíveis de `reasoning` (tendência, RSI, suporte, volume,
    momentum, funding, breakout).
  - `⏱ Duração estimada` — `_estimate_duration()` categoriza em
    Scalp / Curto prazo / Médio prazo / Swing com base em
    distância SL/TP e alavancagem.

---

## Hard Rules Mantidas

- `paper_trading=True` — Iron Man nunca tocou a SDK em modo live.
- Batman continua gate intransponível.
- Nenhuma API key real em código, testes ou docs.
- Nomenclatura super-heróis mantida.

---

## Pipeline End-to-End

```
NickFury → ProfessorX → Superman (indicadores manuais OK em Py3.14)
                     → [demais Layer-1]
         → Vision (LLMClient → OpenAI se key OK, Claude se não)
         → Batman → IronMan (paper)
         → TelegramAlerter (pt-BR, layman_explanation, duration)
```

---

## Acceptance

- [x] `python3 run.py --once` roda sem erros em Python 3.14.
- [x] Superman produz `MarketData` com RSI/EMA/BB/MACD/ATR válidos.
- [x] Funding rate sem `TypeError`.
- [x] Telegram recebe alerta em pt-BR com `💡 Por que` e `⏱ Duração`.
- [x] `python3 run.py --dashboard` sobe dashboard em `localhost:8787`.
- [x] Pixel Office carrega em `/office-v2/` com 4 novos heróis.

---

## What's Next

- Story 126+: melhorias de UX do operador, novos gates, backtesting
  mais rico com Deadpool, flash cycle sub-loop.

---

## Files Changed

| Arquivo | Tipo | Motivo |
| ------- | ---- | ------ |
| `src/agents/llm_client.py` | NEW | Abstração LLM com fallback |
| `src/agents/vision.py` | MODIFIED | Migrado para LLMClient |
| `src/agents/vision_critic.py` | MODIFIED | Migrado para LLMClient |
| `src/agents/superman.py` | MODIFIED | Indicadores manuais Py3.14 |
| `src/services/telegram_alerter.py` | MODIFIED | pt-BR + layman + duration |
| `src/dashboard/funding_provider.py` | MODIFIED | Fix asyncio.timeout bug |
| `src/config/settings.py` | MODIFIED | anthropic_api_key/model |
| `src/dashboard/static/office_v2.bundle.js` | MODIFIED | Layout 2×2 + heróis |
| `.gitignore` | MODIFIED | Excluir data/db + .agent-os |
| `CHANGELOG.md` | MODIFIED | Entrada 0.9.0 |
| `docs/ARCHITECTURE.md` | MODIFIED | LLMClient, Py3.14, Dashboard |
