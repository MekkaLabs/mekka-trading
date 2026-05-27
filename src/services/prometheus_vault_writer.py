"""
src/services/prometheus_vault_writer.py
=========================================
Persistência opt-in dos aprendizados do Prometheus no vault Obsidian.

Cria/atualiza `60 - Daily/{YYYY-MM-DD}-prometheus-learnings.md` no vault
canônico. NUNCA bloqueia o agente: falha de I/O é fail-silent.

Princípios
----------
- **Opt-in**: requer `PROMETHEUS_VAULT_WRITER_ENABLED=true`.
- **Append-safe**: append em arquivo do dia; novo arquivo se for outro dia.
- **Throttle**: máximo `MAX_WRITES_PER_HOUR` escritas/hora (default 6).
- **Atomic write**: `os.replace` para não corromper em mid-write.
- **Sem segredos**: payload do learning não inclui credenciais/chaves.
- **Fail-silent**: exceção é logada DEBUG, agente continua observando.
- **Boundary respeitado**: escreve só em `60 - Daily/`, nunca em
  `10 - Projects/`, `30 - Resources/Decisoes Tecnicas/` etc.

Onde isso encaixa
-----------------
- `Prometheus.subscribe()` em `src/agents/prometheus.py` chama
  `record_learning()` daqui quando emite um learning.
- Não tem efeito se a flag estiver off → trading loop não toca arquivos.
"""

from __future__ import annotations

import json
import os
import time
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

_DEFAULT_VAULT_PATH = Path.home() / "Documents" / "mekka-trading-obsidian"
_DAILY_SUBDIR = "60 - Daily"
_FILE_SUFFIX = "-prometheus-learnings.md"

MAX_WRITES_PER_HOUR = int(os.environ.get("PROMETHEUS_VAULT_WRITES_PER_HOUR", "6"))


def is_writer_enabled() -> bool:
    """Flag explícita — default OFF."""
    return os.environ.get("PROMETHEUS_VAULT_WRITER_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )


def get_vault_path() -> Path:
    """
    Vault path canônico. Honra `MEKKA_VAULT_PATH` se definido.
    Não cria diretório — apenas reporta o caminho esperado.
    """
    raw = os.environ.get("MEKKA_VAULT_PATH")
    return Path(raw) if raw else _DEFAULT_VAULT_PATH


# ---------------------------------------------------------------------------
# Throttler local (não importa do prometheus.py para evitar ciclo)
# ---------------------------------------------------------------------------


class _HourlyThrottle:
    def __init__(self, max_events: int, window_s: float = 3600.0) -> None:
        self.max = max_events
        self.window = window_s
        self._events: deque[float] = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        while self._events and now - self._events[0] > self.window:
            self._events.popleft()
        if len(self._events) >= self.max:
            return False
        self._events.append(now)
        return True


_throttle = _HourlyThrottle(MAX_WRITES_PER_HOUR)


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------


def _today_str() -> str:
    return date.today().isoformat()


def _format_learning_block(learning: dict[str, Any]) -> str:
    """
    Bloco markdown sanitizado para o learning.

    Remove explicitamente quaisquer chaves que possam carregar secrets.
    Estrutura é tabela legível pelo operador.
    """
    SAFE_KEYS = {"ts", "cycle_id", "symbol", "observation_count", "topic_counts", "stats_snapshot"}
    safe = {k: v for k, v in learning.items() if k in SAFE_KEYS}

    ts = safe.get("ts")
    ts_str = datetime.fromtimestamp(ts).isoformat(timespec="seconds") if ts else "?"
    topic_lines = "\n".join(
        f"  - `{t}`: {c}" for t, c in sorted((safe.get("topic_counts") or {}).items())
    ) or "  - (vazio)"

    return f"""
### {ts_str} — cycle `{safe.get('cycle_id') or '?'}` ({safe.get('symbol') or '?'})

- **Observações na janela:** {safe.get('observation_count', 0)}
- **Distribuição por topic:**
{topic_lines}
- **Stats do agente:**

```json
{json.dumps(safe.get('stats_snapshot') or {}, indent=2)}
```
"""


def _ensure_header(file_path: Path) -> None:
    """Cria arquivo com header se não existir."""
    if file_path.exists():
        return
    header = f"""---
title: Prometheus Learnings — {_today_str()}
type: daily-prometheus
tags: [prometheus, learning, second-brain, mekka-trading]
created: {_today_str()}
---

# Prometheus Learnings — {_today_str()}

> Arquivo gerado automaticamente pelo agente **Prometheus** quando
> `PROMETHEUS_VAULT_WRITER_ENABLED=true`. Cada bloco abaixo é um
> aprendizado consolidado no event bus (sem segredos, sem dados
> pessoais — apenas metadados de execução).

"""
    file_path.write_text(header, encoding="utf-8")


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def record_learning(learning: dict[str, Any]) -> Optional[Path]:
    """
    Persiste um learning no vault. Retorna o Path do arquivo ou None.

    Fail-silent. Throttle. Opt-in. Caminho fixo em `60 - Daily/`.
    """
    if not is_writer_enabled():
        return None
    if not _throttle.allow():
        logger.debug("[Prometheus.vault_writer] throttled")
        return None

    vault = get_vault_path()
    if not vault.exists() or not vault.is_dir():
        logger.debug(f"[Prometheus.vault_writer] vault ausente: {vault}")
        return None

    daily_dir = vault / _DAILY_SUBDIR
    try:
        daily_dir.mkdir(exist_ok=True)
    except OSError as exc:
        logger.debug(f"[Prometheus.vault_writer] mkdir falhou: {exc}")
        return None

    fname = f"{_today_str()}{_FILE_SUFFIX}"
    target = daily_dir / fname

    try:
        _ensure_header(target)
    except OSError as exc:
        logger.debug(f"[Prometheus.vault_writer] header falhou: {exc}")
        return None

    block = _format_learning_block(learning)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        existing = target.read_text(encoding="utf-8")
        tmp.write_text(existing + block, encoding="utf-8")
        os.replace(tmp, target)
        return target
    except OSError as exc:
        logger.debug(f"[Prometheus.vault_writer] write falhou: {exc}")
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return None


def stats() -> dict[str, Any]:
    """Snapshot leve para o dashboard."""
    return {
        "enabled": is_writer_enabled(),
        "vault_path": str(get_vault_path()),
        "vault_available": get_vault_path().exists(),
        "writes_in_window": len(_throttle._events),
        "max_per_hour": MAX_WRITES_PER_HOUR,
    }
