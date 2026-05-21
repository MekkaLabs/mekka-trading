# Mekka Trading — Mainnet Authorization

> **ATENÇÃO**: Este arquivo é verificado automaticamente por
> `scripts/preflight_mainnet.py`. Para que o pré-voo passe, ele deve
> conter a string "GO MAINNET" e não deve conter "____" nem "YOUR_NAME".
> Não edite este arquivo até que TODOS os gates humanos abaixo sejam
> satisfeitos.

---

## Declaração de Autorização

<!-- Quando pronto, substitua a linha abaixo: -->
<!-- GO MAINNET -->

**Status**: ⚠️ PENDENTE — gates humanos H1–H6 ainda não satisfeitos.

---

## Identificação do Operador

**Nome**: ____  
**Email**: ____  
**Data da autorização**: ____  
**Wallet mainnet (endereço)**: ____  
**Valor inicial de capital**: USD ____

---

## Checklist de Gates Humanos

Marque com [x] apenas após verificação real. Não marque antecipadamente.

### H1 — Histórico testnet mínimo
- [ ] ≥ 1 mês de operação testnet sem incidente crítico registrado.
- Período verificado: ____ a ____
- Incidentes registrados: ____
- Referência: `docs/INCIDENT-PLAYBOOK.md`

### H2 — Wolverine SL ENDORSE rate
- [ ] Taxa de aprovação (ENDORSE) das recomendações de stop-loss do
  Wolverine ≥ 70% nos últimos 30 dias.
- Taxa medida: ____%
- Período: ____ a ____

### H3 — Vision Critic estabilidade
- [ ] Vision Critic operando com `VISION_CRITIC_ENABLED=true` por ≥ 1
  semana sem regressão de sinal (não aumentou taxa de HOLD anômalo).
- Período: ____ a ____
- Taxa de HOLD antes: ____%  |  após: ____%

### H4 — Audit harmonization (Story 032b)
- [ ] Story 032b (TS audit shim) entregue, OU waiver documentado abaixo:
- Waiver: ____

### H5 — Conta/wallet mainnet dedicada
- [ ] **Hyperliquid:** wallet mainnet criada, separada de wallet pessoal; chave privada em local seguro (não em `.env` versionado).
- [ ] **Binance:** subconta dedicada de Futures (USDⓈ-M); API key com permissão **apenas** de Futures (sem saque), **IP allowlist** habilitada; chaves fora de `.env` versionado.
- Endereço/conta: ____

### H6 — Conta funded via transferência real
- [ ] Funded por transferência real (não faucet de testnet).
- [ ] Valor inicial conservador: ≤ USD ____
- [ ] `MAX_POSITION_SIZE_PCT=0.001` (0.1%) confirmado para primeira semana.
- [ ] (Binance) `ACTIVE_EXCHANGE=binance` e `BINANCE_TESTNET=false` confirmados; preflight passa com os gates de Binance (chaves `BINANCE_*`, network mainnet).

---

## Parâmetros de Capital Inicial (primeira semana mainnet)

| Parâmetro | Valor máximo recomendado | Valor adotado |
|-----------|--------------------------|---------------|
| `MAX_POSITION_SIZE_PCT` | 0.001 (0.1%) | ____ |
| `MAX_LEVERAGE` | 2x | ____ |
| `MAX_TRADES_PER_DAY` | 3 | ____ |
| `MAX_OPEN_POSITIONS` | 2 | ____ |
| `MAX_DAILY_DRAWDOWN_PCT` | 0.05 (5%) | ____ |

---

## Verificação Automatizada Pré-Voo

Antes de ativar `LIVE_TRADING_CONFIRMED=true`, rode:

```bash
cd /Users/gustavovicente/Documents/Mekka-Trading
source .venv/bin/activate

# Verificação completa
python3 scripts/preflight_mainnet.py

# Modo estrito (exit 1 em warnings)
python3 scripts/preflight_mainnet.py --strict

# Output para CI/auditoria
python3 scripts/preflight_mainnet.py --json > docs/preflight-$(date +%Y%m%d).json
```

O script deve retornar `🟢 ALL AUTOMATED CHECKS PASSED` antes de
continuar.

---

## Assinatura

Ao assinar abaixo, declaro que:

1. Li e compreendi `docs/MEKKA-DEV.md`, `docs/RUNBOOK-TESTNET.md` e
   `docs/INCIDENT-PLAYBOOK.md`.
2. Todos os 6 gates humanos (H1–H6) foram verificados pessoalmente.
3. O capital inicial está dentro dos limites conservadores desta tabela.
4. Entendo que a IA (Claude/Codex) **não autoriza** esta operação —
   é uma decisão humana exclusiva.
5. Monitораrei a primeira semana ativamente e agirei ao menor sinal de
   disfunção.

**Assinatura**: ____  
**Data**: ____  
**Commit SHA da versão autorizada**: ____

---

*Template criado por Story 036 — Mainnet Readiness (2026-05-08).*  
*Verificado por: `scripts/preflight_mainnet.py check_authorization_file`.*
