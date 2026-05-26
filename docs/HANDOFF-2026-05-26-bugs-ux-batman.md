# Handoff — 2026-05-26 — Bug Fixes + UX Pro Max + Batman Refactor [4/N]

> Sessão longa cobrindo 7 bug fixes críticos, 4 melhorias de UX, neural graph
> opcional e refactor incremental do `batman._run()`. **20 commits**, zero
> regressão. Servidor estável em Binance testnet LIVE.

---

## Inventário de commits

| Commit | Tipo | Resumo |
|--------|------|--------|
| `8744a42` | fix | `load_dotenv` defensivo no `run.py` (Vision sem LLM por nohup perder cwd) |
| `cfb005e` | fix | `/api/settings` global_mode silencioso + Vision fallback streak kill switch |
| `1c9cf05` | fix | Banner `KILL_SWITCH_EVENT` respeita RELEASE posterior |
| `b4a3404` | fix | `anthropic` package + diagnóstico explícito no LLMClient |
| `f29acae` | chore | IMP-4f32cc28e7bf resolved (KS tinha causa raiz config) |
| `085d63a` | feat | 3 heróis novos no roster: Mentor + IceMan + Sage |
| `791e9ac` | feat | Vault enrichment opt-in — agentes consultam 2º cérebro |
| `a40b5d9` | fix | Modo Deus em testnet usa market (IOC fill 0 bug) |
| `d8abd44` | fix(ux) | Modo Deus + HOLD: botão claro, banner explicativo |
| `02eb7f1` | feat(ux) | 4 melhorias do UI/UX Pro Max (#6 Financial Dashboard) |
| `ed7bde8` | refactor | batman: extrair gate 3m — #73 [1/N] |
| `4cd09fc` | refactor | batman: extrair gates 3l, 3n, 3o — #73 [2/N] |
| `659e934` | refactor | batman: extrair gates 3h, 3i, 3j — #73 [3/N] |
| `ad48405` | refactor | batman: extrair gates 3p, 3q — #73 [4/N] |

---

## Bugs corrigidos (7)

### 1. Vision sem LLM após restart (`load_dotenv` no `run.py`)
**Sintoma**: após `nohup python run.py --dashboard`, Vision retornava HOLD-fallback em todo ciclo. Em ~1min o kill switch engatava automaticamente por "5 consecutive Vision HOLD-fallbacks".

**Causa raiz**: pydantic-settings depende de cwd, mas nohup/systemd/cron podem perder cwd. `OPENAI_API_KEY=""` vazio do shell tinha precedência sobre `.env`.

**Fix** (`run.py`):
```python
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=False)
except ImportError:
    pass
```

### 2. `anthropic` package faltando + diagnóstico ruim
**Sintoma**: mesmo com `ANTHROPIC_API_KEY` válida no `.env`, LLMClient dizia "No LLM provider configured".

**Causa raiz**: `requirements.txt` só listava `openai>=1.0.0`. Sem `anthropic` no venv, `_ANTHROPIC_AVAILABLE = False`.

**Fix**:
- `requirements.txt`: adicionado `anthropic>=0.40.0`
- `llm_client.py`: diagnóstico estruturado quando não há provider — diz EXATAMENTE qual lib/key falta

### 3. `/api/settings` ignorava `global_mode` silenciosamente
**Sintoma**: POST `/api/settings` com `{"global_mode": "conservative"}` retornava `status: ok` mas o modo não mudava.

**Fix** (`server.py::_handle_settings_set`):
- Whitelist explícita: `super_aggressive`, `altcoins_enabled`, `mode`, `global_mode`
- Campos não reconhecidos → 400 com lista de aceitos
- `mode`/`global_mode` delega para `runtime_mode.set_mode`, emite `MODE_CHANGED` audit, retorna `mode_changed` na resposta

### 4. Vision fallback streak engatava KS automaticamente (1min)
**Sintoma**: config error (key vazia) ou anomalia persistente faziam o `_vision_fallback_breaker` (threshold=5) engatar o kill switch em ~1min, assustando o operador.

**Fix**:
- `vision.py`: `_fallback_hold` ganha parâmetro `category` com 4 valores:
  - `llm_degraded`, `parse_error` → contam no breaker (degradação real)
  - `safety_skip`, `config_error` → NÃO contam (pause legítimo, fix do op)
- `nick_fury.py::_check_breakers`: filtra por `fallback_category in (llm_degraded, parse_error)`
- Defensivo: signal sem category não conta (legacy paths)

### 5. Banner `KILL_SWITCH_EVENT` não respeitava RELEASE posterior
**Sintoma**: banner aparecia "KILL_SWITCH ATIVO" por 10min mesmo após operador liberar o KS.

**Causa raiz**: `_build_global_alerts` filtrava só eventos com `RELEASED` no nome, não considerava **ordem**. ENGAGED → RELEASE deixava ENGAGED aparecendo.

**Fix** (`server.py`): coleta TODOS os eventos KS na janela (engage + release), ordena desc, pega o mais recente. Se for RELEASED → sem banner.

### 6. Modo Deus em testnet com IOC fill 0
**Sintoma**: operador clicava Modo Deus, Batman era overrideado, IronMan rodava, mas resultado era REJECTED com `error: "limit_ioc order filled 0 units"`.

**Causa raiz**: `settings.mainnet_dry_run=True` faz IronMan simular comportamento mainnet em testnet (`limit_ioc`). Testnet tem book ralo, IOC zera com frequência.

**Fix** (`iron_man.py`):
- `_place_ccxt_order` ganha param `force_market_in_testnet`
- `_run` propaga `approval.metadata.force_execute` para o helper
- Quando `force_execute=True && _is_testnet` → usar market (fill garantido)
- Mainnet INTOCADO (force_execute em mainnet ainda é hard-rejected pelo server)

### 7. Modo Deus + HOLD não habilitava botão + sem feedback
**Sintoma**: operador marcava Modo Deus com direção=HOLD, esperava executar, mas botão "Confirmar" continuava disabled sem explicação visível.

**Fix** (app.js + index.html + style.css):
- Lógica 3-way no botão: HOLD sempre disabled; LONG/SHORT + Modo Deus → enabled
- Banner amarelo aparece quando `isHold && forceOn`: "Modo Deus + HOLD não executa..."
- Listener `change` no checkbox recalcula sem refetch

---

## Melhorias de UX (UI/UX Pro Max #6 Financial Dashboard)

Auditoria contra `nextlevelbuilder/ui-ux-pro-max-skill` rendeu 4 quick-wins:

### A. `prefers-reduced-motion`
0 → suporte completo via media query. Sprites/parallax param automaticamente quando OS pede.

### B. `aria-live` em status críticos
- `#killswitch-status`: `role=status` + `aria-live=assertive`
- `#trade-result-content`: `role=status` + `aria-live=polite`
- Banner drawdown >=9%: `role=alert` + `aria-live=assertive`
- Banner 7-9%: `aria-live=polite`

### C. Bullet charts nos KPIs (Win Rate + Drawdown)
Cards ganharam barra 8px com 3 zonas (bad/ok/good) + tick branco no target. Mais info no mesmo espaço.

### D. Inline error claro em falhas de execução
Helper `_tradeDiagnose()` classifica 8+ padrões de erro em PT-BR com sugestão:
- IOC fill 0 → "Marque Modo Deus e tente de novo"
- HOLD → "Aguarde direção LONG/SHORT"
- Kill switch → "Vá em Kill Switch e libere"
- Notional cap, balance insuficiente, mainnet+force, network, low consensus, rejected
- Fallback: JSON expandível para padrões desconhecidos

---

## Feature nova: Neural Graph / 2º cérebro ensinando agentes

`src/services/vault_context.py` + flag `VAULT_ENRICHMENT_ENABLED`.

Quando ligada, Vision consulta `JeanGrey.recall()` antes do LLM e adiciona um bloco curto de contexto do vault Obsidian ao prompt. **Read-only**, **opt-in**, **fail-silent**:
- Timeout 1.5s
- Cache 5min por (symbol, topic)
- Max 2000 chars
- 9/9 testes garantem off-by-default, fail-silent, timeout, bounded output, cache

Ativar: `VAULT_ENRICHMENT_ENABLED=true` no `.env` + restart.

---

## Refactor batman._run() — #73 [4/N parcial, 47% completo]

### Métricas
| Stage | `_run` linhas | Gates extraídos | Δ |
|-------|--------------|----------------|---|
| Original | 1303 | 0 | — |
| [1/N] gate 3m | 1296 | 1 | -7 |
| [2/N] + 3l/3n/3o | 1249 | 4 | -47 |
| [3/N] + 3h/3i/3j | 1043 | 7 | -206 |
| [4/N] + 3p/3q | **969** | **9 / 19** | **-334 (-26%)** |

### Padrão usado (Extract Method conservador)
- Cada gate vira `_gate_<id>_<nome>` privado
- Helpers que mutam signal retornam `tuple[Optional[RiskApproval], TradingSignal]`
- Helpers sem mutação retornam `Optional[RiskApproval]`
- state (`reasons`, `breached`) passado por referência (mesma lista)
- Lógica BYTE-A-BYTE preservada — só mudança de escopo
- Regressão verde em cada batch (29 pass / 14 fail pré-existente)

### Gates extraídos
| ID | Nome | Tipo |
|----|------|------|
| 3m | Min trade notional | sync |
| 3l | Max trades/symbol/day | async |
| 3n | Symbol weekly drawdown | async |
| 3o | Consecutive losses | async + audit |
| 3h | MTF Confluence | async + muta signal |
| 3i | Funding Rate | async + muta signal |
| 3j | Trading Hours | sync |
| 3p | Directional bias | async + audit |
| 3q | Min ATR filter | async + audit |

### Gates ainda no _run (TODO próxima sessão)
| ID | Nome | Dificuldade |
|----|------|-------------|
| 3b | Total capital cap | média |
| 3c | Correlation | média (lê current_positions) |
| 3d | Episodic memory | baixa |
| 3e | Portfolio exposure | média |
| 3f | Re-entry cooldown | baixa |
| 3g | Symbol strike + blacklist | média |
| 3k | Pyramid bypass | **alta** (lógica complexa, muta signal) |
| 3r | Flash divergence | **alta** (define `_flash_size_reduction_pct` consumido depois) |
| 5b | Market regime | alta |
| 5c | Asset classifier | média |

### Próximos passos sugeridos
1. Extrair 3b, 3c, 3e, 3f, 3g (gates de inventory, padrão similar) — 1 batch
2. Extrair 3d (episodic memory) — sozinho
3. Extrair 3k (Pyramid — cuidado com mutação de signal + skip de outro gate)
4. Extrair 3r (Flash — propagar variável `_flash_size_reduction_pct`)
5. Extrair 5b/5c (regime + classifier — última rodada)
6. Final: validação ampla + medir tamanho final do _run (esperado ~200 linhas, orquestrador puro)

### Baseline de testes para próxima sessão
```
29 pass, 14 fail, 3 skipped, 1901 deselected
```
Os 14 fails são pré-existentes (`test_phase2_pipeline`, `regime_classifier`, `gate_3r flash`).
Salvar em `/tmp/_batman_baseline.txt` antes de mexer, validar com `diff` após cada batch.

---

## Estado do sistema (final da sessão)

- **Servidor**: rodando, PID em `/tmp/_mekka_dashboard.log`, healthy
- **Kill switch**: `active: false`
- **Exchange**: Binance testnet LIVE
- **Modo**: aggressive (max_pos 5%, max_lev 10x)
- **Toggles**: super_aggressive ON, altcoins OFF
- **Vision LLM**: Anthropic funcionando
- **Vault enrichment**: OFF (default)
- **Posições abertas**: 0

## Operador deve saber
- Banner "KILL_SWITCH ATIVO" não volta sozinho após release (bug #5 corrigido)
- Modo Deus em testnet agora usa market (fill garantido)
- Modo Deus + HOLD mostra banner explicativo claro
- Falhas de trade têm mensagem em PT-BR com sugestão
- Bullet charts visíveis em Win Rate + Drawdown na Overview

## Smoke tests sugeridos para nova sessão
```bash
# Sanity
curl -s http://127.0.0.1:8787/api/health
curl -s http://127.0.0.1:8787/api/killswitch/status

# Batman regression antes de mexer
.venv/bin/python -m pytest tests/ -k batman -q --tb=no
# Esperado: 29 pass, 14 fail, 3 skipped (baseline)

# Vision smoke
.venv/bin/python -c "
import asyncio
from src.agents.vision import Vision
print('Vision import OK:', Vision().codename)
"

# Vault smoke (com flag)
VAULT_ENRICHMENT_ENABLED=true .venv/bin/python -c "
import asyncio
from src.services.vault_context import vault_context_for
print(asyncio.run(vault_context_for('BTC', topic='bullish'))[:200])
"
```
