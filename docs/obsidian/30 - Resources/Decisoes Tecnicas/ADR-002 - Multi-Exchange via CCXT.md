---
title: "ADR-002 — Suporte Multi-Exchange via CCXT (Hyperliquid + Bybit + Binance)"
type: adr
tags: [decisao, arquitetura, exchange, ccxt]
status: aceita
date: 2026-05-12
supersedes: []
superseded-by: []
related: [[ADR-003 - Bybit Testnet Readiness]]
---

# ADR-002 — Suporte Multi-Exchange via CCXT

> **Status**: aceita (entregue na Story 046)
> **Data**: 2026-05-12
> **Autores**: Gusta
> **Implementação**: `src/agents/superman.py`, `src/agents/iron_man.py`, `src/config/settings.py`

## Contexto

O sistema nasceu acoplado à Hyperliquid via o SDK oficial `hyperliquid-python-sdk`. Isso funcionou para a fase de fundação (Stories 001–045) mas trouxe três problemas observados em produção:

1. **Risco de fornecedor único** — qualquer indisponibilidade do feed HL parava a operação inteira. Sem fallback de market data, o sistema fica cego.
2. **Cobertura limitada de ativos** — alguns símbolos que aparecem em Bybit/Binance não existem em HL (ou têm liquidez muito menor), restringindo a estratégia.
3. **Validação cruzada impossível** — sem segunda fonte de preço, qualquer anomalia em HL parecia "verdade absoluta" para Spider-Man.

Hyperliquid também impõe um modelo de signing único (EVM keys) que dificulta onboarding — chaves Bybit/Binance são API key + secret padrão.

## Decisão

Adotar **CCXT como camada unificada de market data e execução** para Bybit e Binance, mantendo o SDK nativo da Hyperliquid para a operação histórica:

| Exchange | SDK | Padrão de credenciais |
|---|---|---|
| `hyperliquid` | `hyperliquid-python-sdk` (oficial) | EVM private key + wallet address |
| `bybit` | `ccxt.async_support` | API key + secret |
| `binance` | `ccxt.async_support` | API key + secret |

Seleção via env var **`ACTIVE_EXCHANGE`** (default: `hyperliquid`). O `settings.py` aplica validação condicional: só exige as chaves da exchange ativa. Cadeia de fallback automática:

```
hyperliquid → bybit → binance
bybit       → hyperliquid → binance
binance     → hyperliquid → bybit
```

## Alternativas Consideradas

### Alternativa 1 — Continuar apenas com Hyperliquid
- ✅ Prós: zero código novo, ecossistema já conhecido.
- ❌ Contras: risco de fornecedor único; impossível validar dados via segunda fonte; impossível escalar para ativos fora do catálogo HL.

### Alternativa 2 — Implementar adapters manuais para cada exchange
- ✅ Prós: controle total sobre cada integração; nenhuma dependência transitiva pesada.
- ❌ Contras: ~2-3 semanas por exchange; manutenção contínua de auth flows, rate limits, schema changes; reinventar o que CCXT já testou em produção há anos.

### Alternativa 3 — CCXT como camada única (escolhida)
- ✅ Prós: 100+ exchanges suportadas de fábrica; auth + symbol mapping + rate limit gerenciados; API unificada (`fetch_ohlcv`, `fetch_balance`, `create_order`); usado em produção por inúmeros sistemas similares.
- ❌ Contras: dependência transitiva pesada (~80MB com todos os exchanges); algumas features avançadas (HL position close-on-trigger nativo) não mapeiam 1:1 na interface unificada — por isso HL continua usando SDK nativo.

## Consequências

### Positivas
- **Resiliência**: queda de uma exchange não derruba o sistema, fallback automático.
- **Onboarding fácil**: API key + secret é padrão da indústria; sem complexidade EVM.
- **Validação cruzada**: Spider-Man pode comparar preço HL vs Bybit vs Binance.
- **Extensibilidade**: adicionar OKX, Bitget, dYdX = ~10 linhas de config.
- **Testnet uniforme**: `set_sandbox_mode(True)` funciona em Bybit e Binance, simplificando dev/test.

### Negativas / Trade-offs
- **Dependência transitiva**: `ccxt>=4.0.0` adiciona ~80MB ao venv. Aceito porque o ganho operacional supera.
- **SDK híbrido**: HL continua com SDK próprio. Dois caminhos de código em `iron_man.py` (`_place_hl_order` vs `_place_ccxt_order`) — complexidade controlada via dispatch por `settings.active_exchange`.
- **Symbol format inconsistente**: HL usa `BTC`, CCXT perp usa `BTC/USDT:USDT`, Bybit wire usa `BTCUSDT`. Normalização espalhada no código — `Bug #4 — Symbol normalization (MarketRegistry)` está no backlog para centralizar.

## Implementação

- **`src/config/settings.py`**: enum `Literal["hyperliquid", "bybit", "binance"]`; campos `bybit_api_key`, `binance_api_key`; `model_validator` condicional (ADR-003 adicionou `bybit_testnet` e validação por exchange ativa).
- **`src/agents/superman.py`** — fallback chain + `_build_ccxt_config` por exchange. Hyperliquid usa `options.sandboxMode`; Bybit/Binance usam `exchange.set_sandbox_mode(True)` aplicado pós-construção e pré-`load_markets()` (introduzido em ADR-003).
- **`src/agents/iron_man.py`** — dois caminhos:
  - `_place_hl_order` — usa `Exchange.order()` do SDK HL com signing EVM.
  - `_place_ccxt_order` — usa `exchange.create_order()` unificado + SL/TP separados como reduce-only.

## Hard Rules Mantidas

- `live_trading_confirmed=True` obrigatório para ordens live em qualquer exchange.
- Paper mode ignora a exchange — trades são simulados localmente.
- Cyclops e Wolverine continuam paper-only (nunca chamam `_place_ccxt_order`).

## Notas

- ADR-003 ([[ADR-003 - Bybit Testnet Readiness]]) estendeu esta decisão para garantir routing correto de sandbox.
- Story 046 ([[Stories do Projeto|046 — Equity Dinâmica + Wolverine Exec + Cyclops + Bybit]]) é a entrega original.
