# Runbook — Virada para Binance Mainnet (Go-Live)

> **ATENÇÃO**: Este procedimento move o sistema para **dinheiro real**. Só execute
> após `docs/MAINNET-AUTHORIZATION.md` estar assinado (gates H1–H6) e o
> preflight passar. A decisão de virar é **humana e exclusiva** — a IA não autoriza.

---

## Pré-condições (não pule)

1. **Preflight verde**
   ```bash
   .venv313/bin/python scripts/preflight_mainnet.py --strict
   ```
   Deve retornar `🟢 ALL AUTOMATED CHECKS PASSED`.
2. **Autorização assinada** — `docs/MAINNET-AUTHORIZATION.md` contém `GO MAINNET`,
   sem placeholders `____`/`YOUR_NAME`, gates H1–H6 marcados.
3. **Wallet/API mainnet dedicada** — chaves de mainnet da Binance Futures (NÃO
   testnet, NÃO conta pessoal), com saldo real conservador.
4. **≥ 1 mês de testnet** sem incidente crítico (H1).

## Parâmetros conservadores da 1ª semana (recomendado)

| Parâmetro | Cap 1ª semana |
|-----------|---------------|
| `MAX_POSITION_SIZE_PCT` | 0.001 (0.1%) |
| `MAX_LEVERAGE` | 2 |
| `MAX_TRADES_PER_DAY` | 3 |
| `MAX_OPEN_POSITIONS` | 2 |
| `MAX_DAILY_DRAWDOWN_PCT` | 0.05 (5%) |

> O NickFury emite **WARNING + alerta Telegram** (`MAINNET_FIRSTWEEK_LIMITS`) no
> boot se algum limite exceder esses caps em mainnet. Ele não altera os valores —
> ajuste-os você no `.env` antes de virar.

## Procedimento de virada

1. **Parar o sistema** (graceful):
   ```bash
   pkill -f "run.py --dashboard"
   ```
2. **Editar `.env`** (chaves mainnet já configuradas):
   ```env
   ACTIVE_EXCHANGE=binance
   BINANCE_TESTNET=false        # ← a virada
   BINANCE_API_KEY=<mainnet>
   BINANCE_API_SECRET=<mainnet>
   PAPER_TRADING=false
   LIVE_TRADING_CONFIRMED=true
   # caps da 1ª semana (ver tabela acima)
   MAX_POSITION_SIZE_PCT=0.001
   MAX_LEVERAGE=2
   ```
3. **Reconfirmar preflight** (agora deve passar o gate de network):
   ```bash
   .venv313/bin/python scripts/preflight_mainnet.py --strict
   ```
4. **Subir** e observar o boot:
   ```bash
   nohup .venv313/bin/python run.py --dashboard >logs/dashboard_runtime.log 2>&1 &
   ```
   No log, confirmar: `BOOT` com `network=mainnet`/`BINANCE_TESTNET=false`,
   `BOOT_RECONCILE` (sem erros), e o provider do Vision ativo.

## Validações pós-virada (primeiros minutos)

- [ ] `/api/system/status` → `running:true`, `paper_trading:false`, `mode` correto.
- [ ] `/api/overview` → `portfolio_source: BINANCE`, equity real plausível.
- [ ] Painel de posições ao vivo: mark/PnL atualizando (BinancePriceFeed conectado).
- [ ] Kill switch acessível e funcional (`/api/killswitch/status`).
- [ ] Primeiro trade (se houver): confirmar **SL reduce-only criado** na corretora
      (o SL fail-safe fecha a posição se o SL não puder ser colocado).

## Monitoramento da 1ª semana

- Acompanhar ativamente (H6). Telegram com alertas habilitado.
- Verificar `BOOT_RECONCILE` a cada restart (posições sempre protegidas).
- Sage acompanha regressões (win rate / pico de erros) — revisar `/Melhorias`.

## Rollback (a qualquer sinal de disfunção)

1. **Kill switch imediato**:
   ```bash
   curl -X POST http://localhost:8787/api/killswitch/engage -d '{"reason":"rollback"}'
   ```
   (ou pelo dashboard / Telegram). Isso **halta o trading**; o guardião de SL
   mantém as posições protegidas.
2. **Fechar posições manualmente** se necessário (botão Fechar no painel, ou na
   própria Binance).
3. **Reverter para testnet**: `BINANCE_TESTNET=true` no `.env` e reiniciar.

---

*Ver também: `docs/MAINNET-AUTHORIZATION.md`, `docs/INCIDENT-PLAYBOOK.md`,
`scripts/preflight_mainnet.py`. Vault: [[Departamento de Melhoria Contínua]].*
