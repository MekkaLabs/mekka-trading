# Handoff de sessão — 2026-05-08 — Recovery + Story 035b

> **Para a próxima IA (Claude Sonnet 4.6 ou outro)**: este documento é o
> contexto completo da sessão de continuidade do dia 2026-05-08. Lê-lo
> primeiro evita repetir trabalho. Tempo de leitura: 6 minutos.
>
> **Ordem absoluta de leitura no início da sessão:**
> 1. Este arquivo (até o fim).
> 2. `docs/HANDOFF.md` (handoff vivo do projeto, contexto histórico).
> 3. `docs/MEKKA-DEV.md` (regras absolutas).
> 4. `docs/AUTO-CONTINUE-PLAN.md` (roadmap automatizado).
> 5. `AGENTS.md` (roster — 15 super-heróis).

---

## 0. TL;DR — em uma frase

A sessão começou com objetivo de implementar **Story 035b (Telegram
inbound)**, mas encontrou a baseline `pytest` vermelha (7 falhas, 259
passes), aplicou 7 patches via § 99 do AUTO-CONTINUE-PLAN, e parou
aguardando o operador (Gusta) re-rodar o pytest pra confirmar verde
antes de prosseguir.

**Próxima ação concreta:** o operador roda o smoke test da seção 2
abaixo. Se verde → segue Story 035b conforme plano da seção 6. Se ainda
vermelho → diagnóstico extra (seção 5).

---

## 1. Estado do projeto (cabeçalho)

| Métrica                           | Valor                              |
| --------------------------------- | ---------------------------------- |
| Stories entregues                 | 34 (025–033 + 035) + ADR-001       |
| Pendentes                         | 032b · 034 · 035b · 036            |
| Pytest baseline esperado          | ~266 passes (após fixes desta sessão) |
| Pytest baseline observado pré-fix | **7 failed, 259 passed**           |
| Roster                            | 15 super-heróis (ver AGENTS.md)    |
| Modo                              | paper-trading-only                 |
| Python venv                       | macOS Python 3.14 em `.venv`       |

> ⚠️ **Memória do operador (regra absoluta)**: nunca usar nome "rat",
> "RatarIA" ou qualquer roedor. Todos os agentes do Mekka Trading têm
> nome de **super-herói**. Se ficar tentado a inventar codinome novo,
> ele tem que ser de Marvel/DC.

---

## 2. Ação imediata (operador)

> Há um diretório órfão `.venv-sandbox` no projeto (criado por engano
> pelo sandbox Linux desta sessão; o pip falhou no meio e não dá pra
> remover de dentro do sandbox). Limpe primeiro.

```bash
cd /Users/gustavovicente/Documents/Mekka-Trading

# 1. Remover .venv-sandbox órfão
chmod -R u+w .venv-sandbox 2>/dev/null
rm -rf .venv-sandbox
ls -la | grep -E '\.venv'   # deve listar só .venv (o venv real macOS)

# 2. Smoke test
source .venv/bin/activate
pytest -v 2>&1 | tail -50
python3 scripts/check_roster_consistency.py
```

**Resultado esperado após os 7 fixes da seção 4:**

- `pytest` → ~266 passed, 0 failed.
- `check_roster_consistency.py` → `[OK] 15 heroes`.

Se algum teste continuar vermelho, vá para **seção 5** (diagnóstico
contextual). Se tudo verde, vá para **seção 6** (Story 035b).

---

## 3. Sessão atual em 5 atos

### Ato 1 — Objetivo
Operador escolheu, via AskUserQuestion, a **Story 035b (Telegram
inbound — comandos `/status /pnl /pause /resume /positions`)** como
próxima frente automatizável. Pediu rodar baseline antes.

### Ato 2 — Bloqueio operacional
- O `.venv` do projeto é macOS Python 3.14; o sandbox da IA é Linux
  Python 3.10. Incompatível.
- Tentativa de criar `.venv-sandbox` local falhou (proxy 403 no PyPI).
- O diretório ficou órfão e a IA não consegue removê-lo de dentro do
  sandbox (`Operation not permitted`).
- Operador rodou `pytest` no host → **7 vermelhos** (drift do
  documentado, que era ~199 testes).

### Ato 3 — Diagnóstico (§ 99 do AUTO-CONTINUE-PLAN)
Tabela completa das 7 falhas:

| # | Teste                                                          | Tipo       | Causa raiz                                                                                                                                |
| - | -------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | `test_phase11_telegram::test_alert_disabled_returns_false`     | conftest   | `.env` tem `TELEGRAM_BOT_TOKEN=your-…` (truthy). Conftest não anula → `telegram_enabled=True` por default; AsyncMock vaza no result.       |
| 2 | `test_phase11_telegram::test_nick_fury_pushes_on_kill_switch_verdict` | **prod**   | `nick_fury.run_main_cycle` skip silencioso na kill switch antes de chamar `_telegram.alert`. Operador não recebe push do evento mais crítico. |
| 3 | `test_dashboard_replay::TestReplaySingle::test_unknown_returns_404` | test       | Filename não-canônico (`snapshot-nonexistent.json`) reprovado pelo regex → retorna 400, não 404 como teste esperava.                       |
| 4 | `test_dashboard_replay::TestOriginAllowlist::test_extra_origins_env_extends` | test       | Refactor moveu `EXTRA_WS_ORIGINS` pra `validators.py`. Teste patcha `server_module` → no-op. `is_origin_allowed` lê do módulo errado.       |
| 5 | `test_dashboard_replay::TestPersistSnapshotDedup::test_kill_clear_then_reactive_creates_new_bundle` | **prod**   | Bundle filename usa segundo (`HHMMSS`). Três chamadas no mesmo segundo do teste colidem → 1 arquivo no disco em vez de 2.                  |
| 6 | `test_dashboard_replay::TestPnlEndpoints::test_series_clamps_days_param` | **prod**   | `_safe_limit("-1", default=30, max=365)` retornava `1` (via `max(1, min(value, max))`). Teste espera negativos caírem no default.          |
| 7 | `test_dashboard_replay::TestReplayExport::test_utc_filter_excludes_out_of_range` | **prod**   | `+` no query `start_utc=2026-05-08T00:00:00+00:00` é URL-decodificado pra **espaço** → `_parse_iso_utc` falha → filtro vira no-op → count=2 em vez de 1. |

### Ato 4 — Patches aplicados
7 edits + 1 blindagem (ver seção 4).

### Ato 5 — Pausa pra confirmação humana
A IA NÃO pode rodar pytest no sandbox (problema do Ato 2). O operador
precisa rodar o smoke test e colar o resultado.

---

## 4. Patches aplicados nesta sessão

> Todas as alterações são **fix mínimo no lugar correto** conforme § 99
> do AUTO-CONTINUE-PLAN. Nada de refactor oportunista.

### 4.1 `conftest.py` (linhas 16-32)
Adicionados defaults vazios para variáveis de ambiente que o `.env`
populava com placeholders truthy:

```python
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")
os.environ.setdefault("TELEGRAM_CHAT_ID", "")
os.environ.setdefault("DASHBOARD_ALLOWED_ORIGINS", "")
```

**Por quê**: pydantic-settings prefere os.environ sobre `.env`; setando
vazio em conftest força o default seguro. Tests que precisam de telegram
ON usam `monkeypatch.setattr(real_settings, ...)` no escopo deles —
inalterado.

### 4.2 `src/agents/nick_fury.py::run_main_cycle` (linha ~158)
No early-return da kill switch, adicionado push do `RISK_KILL_SWITCH`:

```python
if is_kill_switch_active():
    self._log.warning(...)
    await MekkaRepository.log_event(... CYCLE_SKIPPED ...)
    # NOVO: push best-effort
    await self._telegram.alert(
        event="RISK_KILL_SWITCH",
        severity="ERROR",
        agent="NickFury",
        message="Kill switch active — main cycle skipped",
        payload={"source": "pre_cycle_check"},
    )
    return []
```

**Por quê**: o early-return economiza análise mas tornava silencioso o
guardrail mais crítico do sistema. Test design (nome
`test_nick_fury_pushes_on_kill_switch_verdict`) já documentava a
intenção: kill switch sempre dispara push.

### 4.3 `src/dashboard/server.py::_safe_limit` (linha ~1608)
Negativos caem no default em vez de clampar pra 1:

```python
if value < 1:
    return default
return min(value, max_value)
```

**Por quê**: `?days=-1` é input garbage (mesma classe que `?days=abc`).
Fallback pro default tá certo; clampar pra 1 mascara o erro do cliente.
Único uso de `_safe_limit` em testes (`test_series_clamps_days_param`)
valida a nova semântica.

### 4.4 `src/dashboard/server.py::_parse_iso_utc` (linha ~1965)
Tolera URL-decoded `+` → espaço no offset ISO 8601:

```python
normalized = re.sub(r" (\d{2}:\d{2})$", r"+\1", raw).replace("Z", "+00:00")
```

**Por quê**: aiohttp + parsing de query string decodifica `+` como
espaço (legacy form-encoding). Operadores que pastam URL ou clients que
não fazem `%2B` quebravam o filtro UTC sem erro visível. Regex só toca
" HH:MM$", não pega data sozinha nem timestamps sem tz.

### 4.5 `src/dashboard/server.py::_persist_snapshot` (linha ~1531) + `src/dashboard/validators.py::BUNDLE_NAME_RE` (linha 24)
Bundle filename ganha suffix de microssegundo + regex aceita as duas formas:

```python
# server.py
stamp = now.strftime("%Y%m%dT%H%M%S")
suffix = f"{now.microsecond:06d}"
bundle_name = f"incident-bundle-{stamp}-{suffix}.json"

# validators.py
BUNDLE_NAME_RE = re.compile(r"^incident-bundle-\d{8}T\d{6}(?:-\d{6})?\.json$")
```

**Por quê**: precisão de segundo colide quando duas transições rodam no
mesmo segundo (kill→clear→kill em testes; breaker churn rápido em
prod). Optional group preserva compatibilidade com filenames antigos
(`incident-bundle-20260507T120000.json`) que estão hardcoded em outros
testes (linhas 427, 612 de `test_dashboard_replay.py`).

### 4.6 `tests/test_dashboard_replay.py::test_unknown_returns_404` (linha ~221)
Filename trocado pra um que passa no regex mas não está em disco:

```python
resp = await client.get("/api/replay?snapshot=snapshot-20260101T0000.json")
```

### 4.7 `tests/test_dashboard_replay.py` — imports + `test_extra_origins_env_extends` (linhas 25-26 e ~660)
Adicionado import de `validators_module` e patch correto:

```python
from src.dashboard import validators as validators_module
# ...
monkeypatch.setattr(validators_module, "EXTRA_WS_ORIGINS", ("https://internal.corp",))
```

### 4.8 (bônus) `tests/test_phase11_telegram.py::test_nick_fury_no_push_on_clean_approval`
Blindado contra existência de `data/.kill_switch` no host. Sem isto, o
fix #2 deixaria o teste flaky em máquinas onde o operador esqueceu o
kill switch engajado:

```python
async def test_nick_fury_no_push_on_clean_approval(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.agents.batman._KILL_SWITCH_FILE",
        tmp_path / ".kill_switch_absent",
    )
    fury = NickFury()
    ...
```

---

## 5. Se a baseline ainda voltar vermelha

Cenário por cenário:

### 5.1 `test_alert_disabled_returns_false` ainda vermelho
Significa que `os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")` no
conftest não está sendo respeitado pela pydantic-settings em Python
3.14. Próximo passo: forçar com `os.environ["TELEGRAM_BOT_TOKEN"] = ""`
(não `setdefault`), ou mudar a ordem para que conftest rode **antes**
do `from src.config.settings import settings` em qualquer test module.

### 5.2 `test_nick_fury_pushes_on_kill_switch_verdict` ainda vermelho
Verificar se `is_kill_switch_active()` está realmente lendo o
`_KILL_SWITCH_FILE` patchado pelo monkeypatch. Adicionar print/log na
função e rodar com `pytest -s`. Se o path correto está sendo lido mas o
alert não dispara, ler de novo `nick_fury.run_main_cycle` linha 158-180.

### 5.3 Tests de dashboard ainda vermelhos
- Confirmar que `re` está importado no topo de `server.py` (linha 10).
- Confirmar que `BUNDLE_NAME_RE` foi atualizado no `validators.py` (não
  só re-exportado).
- Rodar `pytest tests/test_dashboard_replay.py::TestReplayExport -v
  --tb=long` e colar o traceback.

### 5.4 Teste totalmente novo virou vermelho
Provavelmente regressão introduzida por um dos 7 fixes. Rodar
`git diff` no projeto (não commitado ainda — operador é responsável
pelo commit) e comparar com a tabela da seção 4.

---

## 6. Plano da Story 035b (objetivo original da sessão)

> **Pré-requisito**: § 2 verde (todos pytest passam após fixes da § 4).

### 6.1 Decisão arquitetural recomendada
**Long-polling**, não webhook. Razões:

- Webhook exige TLS público (Let's Encrypt + porta 443) — fricção
  desnecessária pra primeira versão.
- Long-polling com `getUpdates` é stateless do lado do servidor.
- Bot inicia o cliente que conecta no `api.telegram.org`; nada precisa
  ser exposto na LAN.
- Em produção testnet, o long-poll roda como serviço auxiliar do mesmo
  processo Mekka (asyncio task) ou separadamente via systemd.

Pode ser registrado como ADR-002 se valer a pena.

### 6.2 Settings a adicionar (`src/config/settings.py`)
```python
telegram_inbound_enabled: bool = Field(default=False, ...)
telegram_inbound_allowed_chat_ids_raw: str = Field(default="", ...)
telegram_inbound_poll_interval_seconds: float = Field(default=2.0, ge=0.5, le=30.0, ...)
telegram_inbound_long_poll_timeout_seconds: int = Field(default=25, ge=1, le=50, ...)

@cached_property
def telegram_inbound_allowed_chat_ids(self) -> set[str]:
    raw = self.telegram_inbound_allowed_chat_ids_raw
    return {tok.strip() for tok in raw.split(",") if tok.strip()}
```

### 6.3 Novo arquivo: `src/services/telegram_inbound.py`
Esqueleto:

```python
class TelegramInboundPoller:
    """
    Long-polling stateless contra api.telegram.org/getUpdates.
    Despacha comandos para handlers internos (status/pnl/pause/resume/
    positions). Toda resposta é via TelegramAlerter._post (reuso).
    """
    def __init__(
        self,
        *,
        nick_fury: "NickFury",      # acesso ao kill switch
        portfolio: "PortfolioManager",
        repo: type[MekkaRepository],
    ) -> None: ...

    async def run_forever(self) -> None: ...
    async def _poll_once(self, last_update_id: int) -> int: ...
    async def _dispatch(self, update: dict) -> None: ...

    # Handlers (cada um retorna a string a enviar de volta)
    async def _cmd_status(self) -> str: ...
    async def _cmd_pnl(self, args: list[str]) -> str: ...
    async def _cmd_pause(self) -> str: ...
    async def _cmd_resume(self) -> str: ...
    async def _cmd_positions(self) -> str: ...
    async def _cmd_help(self) -> str: ...
```

**Contratos importantes**:
- `_dispatch` rejeita silenciosamente (log warning, sem reply) qualquer
  update cujo `chat.id` não esteja em `settings.telegram_inbound_allowed_chat_ids`.
- `_cmd_pause` chama `engage_kill_switch("telegram_pause", reason=...)`
  do batman (existente).
- `_cmd_resume` chama `release_kill_switch()` do batman.
- Erros de rede são logados como WARNING e o loop continua (igual ao
  `TelegramAlerter`).
- Comando desconhecido devolve `_cmd_help`.

### 6.4 Wiring opcional em `nick_fury.py`
Não obrigatório na primeira versão — pode rodar como serviço separado
via `python -m src.services.telegram_inbound`. Em produção, depois,
adicionar `if settings.telegram_inbound_enabled: asyncio.create_task(poller.run_forever())`
em algum boot sequence. Documentar essa decisão no story doc.

### 6.5 Testes (`tests/test_phase12_telegram_inbound.py`)
Coverage mínima (mock de `requests.get/post` ou `aiohttp`):

1. `test_inbound_disabled_short_circuits` — `telegram_inbound_enabled=False` → loop não roda.
2. `test_unknown_chat_id_rejected` — chat_id fora da allowlist → log + sem reply.
3. `test_status_returns_roster_and_flags` — `/status` traz network/mode/kill_switch_active/positions_count.
4. `test_pause_engages_kill_switch` — `/pause` cria o `_KILL_SWITCH_FILE`.
5. `test_resume_clears_kill_switch` — `/resume` remove o arquivo.
6. `test_pnl_uses_repository` — `/pnl 7` chama `MekkaRepository.list_recent_daily_pnl(limit=7)`.
7. `test_positions_lists_open` — `/positions` chama `PortfolioManager.run` e formata abertas.
8. `test_unknown_command_returns_help` — `/foo` → texto de help.
9. `test_polling_timeout_is_swallowed` — exception no `_poll_once` não trava o loop.
10. `test_offset_advances` — `_poll_once` usa o `update_id` mais alto retornado +1 como próximo offset.

Target: ~10-12 testes, fase 12, total geral pula pra ~278.

### 6.6 Story doc + atualizações de índice
Criar `docs/stories/story-035b-telegram-inbound.md` com Goal/Scope/Tests
/Acceptance/Decisão arquitetural. Atualizar:

- `docs/stories/INDEX.md` — adicionar 035b ao milestone de Telegram.
- `docs/HANDOFF.md` § 0 — substituir tabela atual por uma janela nova
  da próxima sessão (ou empurrar a atual pra histórico).
- `docs/AUTO-CONTINUE-PLAN.md` § 6.1 — marcar `[x]`.
- `AGENTS.md` — entrada do TelegramInbound como sub-bullet do Layer
  "Services" (não é herói, é serviço).

---

## 7. Regras absolutas (lembretes)

1. **Naming**: super-heróis Marvel/DC apenas. Banido para sempre: rat,
   RatarIA, qualquer roedor.
2. **Paper-trading-only** até § 4 (hardening) verde + GO MAINNET
   manual. Nunca virar `PAPER_TRADING=false` por conta própria.
3. **Não tocar runtime sem baseline verde**. § 99 do AUTO-CONTINUE-PLAN
   é lei.
4. **Comentários `#` inline em comandos shell** quebram colagem (já
   listado em § 11.5 do HANDOFF.md). Comandos que vão pro chat usam
   `# comentário` em linha separada.
5. **Pydantic v2 BaseSettings**: nunca via `__dict__` em fields exceto
   `cached_property`.
6. **`pytest.approx`** com `round(x, N)` na produção precisa
   `abs=10**(-(N-1))`, não `rel`.

---

## 8. Tarefas trackedas (estado pós-sessão)

```
#1.  [completed] Rodar baseline pytest + roster check
#2.  [pending]   Estudar Story 035 (Telegram push) e 035b deferred items
#3.  [pending]   Decidir long-polling vs webhook para inbound
#4.  [pending]   Implementar TelegramInboundPoller + handlers de comando
#5.  [pending]   Settings + autenticação por chat_id allowlist
#6.  [pending]   Testes phase 12 — telegram_inbound
#7.  [pending]   Story doc 035b + atualizar HANDOFF/INDEX/AUTO-CONTINUE
#8.  [pending]   Verificação final — pytest + roster + diff review
#9.  [pending]   Pedir ao usuário rodar baseline no host + remover .venv-sandbox órfão
#10. [completed] §99 Recuperação — diagnosticar 7 falhas red baseline
#11. [in_progress] Aplicar fix das 7 falhas + re-rodar pytest verde
#12. [in_progress] Escrever handoff completo da sessão para próxima IA  ← este doc
```

A próxima sessão deve:
1. Confirmar #11 como completed (após smoke test verde).
2. Executar #2 → #8 em ordem.
3. Fechar #9 (limpeza do `.venv-sandbox`) explicitamente.

---

## 9. Arquivos modificados nesta sessão (git diff esperado)

```
modified:   conftest.py
modified:   src/agents/nick_fury.py
modified:   src/dashboard/server.py
modified:   src/dashboard/validators.py
modified:   tests/test_dashboard_replay.py
modified:   tests/test_phase11_telegram.py
new file:   docs/HANDOFF-2026-05-08-recovery-035b.md   (este arquivo)
```

Nenhum commit foi feito — operador é responsável pelo commit/push após
verificar verde. Mensagem sugerida:

```
fix(baseline): § 99 recovery — 7 falhas resolvidas pré-035b

- nick_fury: push RISK_KILL_SWITCH no skip pre-cycle
- _safe_limit: negativos caem no default
- _parse_iso_utc: tolera URL-decoded + → espaço
- _persist_snapshot: suffix de microssegundo no bundle filename
- BUNDLE_NAME_RE: aceita os dois formatos (compat)
- conftest: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID / DASHBOARD_ALLOWED_ORIGINS = ""
- test_unknown_returns_404: filename agora canônico
- test_extra_origins_env_extends: patcha validators_module (era server_module no-op)
- test_nick_fury_no_push_on_clean_approval: blindagem contra .kill_switch existente

Pytest baseline: 259 → ~266 verdes. Roster inalterado (15 heróis).
```

---

## 10. Como reabrir esta sessão em Sonnet 4.6

Prompt sugerido pra colar no início da nova task:

> Continue o projeto Mekka Trading em
> `/Users/gustavovicente/Documents/Mekka-Trading`. Comece lendo
> `docs/HANDOFF-2026-05-08-recovery-035b.md` (este arquivo) e siga as
> instruções da seção 2 ("Ação imediata"). Não toque em código novo até
> baseline verde. Próxima frente após verde: Story 035b (Telegram
> inbound) conforme plano da seção 6.

---

*Fim do handoff. Bons trabalhos pra próxima sessão.*
