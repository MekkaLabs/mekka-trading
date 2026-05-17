"""
src/services/cycle_batched_exporter.py
=======================================
Story 197 — CycleBatchedExporter: export em lotes de eventos para webhook externo.

Inspirado no padrão OpenHands BatchedWebHook (openhands/storage/batched_web_hook.py):
  "Stores events and flushes them to an external webhook in batches.
   Configuration:
     file_store_web_hook_url:     URL do webhook receptor
     file_store_web_hook_headers: Headers HTTP (ex: Authorization)
     file_store_web_hook_batch:   Habilita batching (default False)
   Flush strategy: por batch_size OU por flush_interval_s (timer)."

No OpenHands:
  - BatchedWebHook acumula eventos e flush quando batch_size é atingido
    OU quando o timer periódico dispara
  - Payload: lista de eventos serializados em JSON
  - Headers configuráveis (auth, content-type)
  - Fail-silent: se o webhook falhar, o agente continua rodando

No Mekka, o equivalente é:
  CycleBatchedExporter acumula eventos do CycleEventLog (e SourcedEvents)
  e exporta em lotes para uma URL configurável (webhook, Grafana, analytics).
  Útil para integração com dashboards externos sem poluir o pipeline principal.

  Flush é trigger-based (não usa asyncio — pipeline é síncrono):
    - Ao atingir batch_size: flush automático no próximo emit()
    - Ao chamar flush() manualmente: útil no final de cada ciclo
    - Exporter é fail-silent: qualquer erro HTTP vira log de debug

Arquitetura
-----------
  ExportBatch      — payload de um lote de eventos
  CycleBatchedExporter
    ├── add(event_dict)              — adiciona evento ao buffer
    ├── flush() → int               — exporta buffer (retorna count)
    ├── maybe_flush() → int         — flush se batch_size atingido
    └── summary() → dict
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# ExportBatch — payload de um lote de eventos
# ---------------------------------------------------------------------------

@dataclass
class ExportBatch:
    """
    Payload de um lote de eventos para export.

    Equivalente ao payload do BatchedWebHook do OpenHands:
    lista de eventos serializados com metadados do lote.
    """
    events: List[Dict[str, Any]]
    batch_id: str
    batch_size: int
    timestamp: float = field(default_factory=time.time)
    source: str = "mekka-trading"

    def to_json(self) -> str:
        """Serializa para JSON."""
        return json.dumps({
            "batch_id": self.batch_id,
            "batch_size": self.batch_size,
            "timestamp": self.timestamp,
            "source": self.source,
            "events": self.events,
        }, default=str)


# ---------------------------------------------------------------------------
# CycleBatchedExporter
# ---------------------------------------------------------------------------

class CycleBatchedExporter:
    """
    Exporta eventos do ciclo em lotes para webhook externo.

    Padrão OpenHands BatchedWebHook:
    - Acumula eventos no buffer
    - Flush quando batch_size é atingido ou manualmente
    - POST JSON para webhook_url configurável
    - Fail-silent: falha de HTTP não crasha o pipeline
    - Headers configuráveis (Authorization, X-API-Key, etc.)

    Uso:
        exporter = get_cycle_batched_exporter()
        exporter.add({"event_type": "CYCLE_END", "symbol": "BTC", ...})
        exporter.maybe_flush()   # flush automático se batch cheio
        exporter.flush()         # flush manual no final do ciclo
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        batch_size: int = 20,
        headers: Optional[Dict[str, str]] = None,
        enabled: bool = True,
        max_buffer_size: int = 200,
        timeout_s: float = 5.0,
    ) -> None:
        self.webhook_url = webhook_url
        self.batch_size = batch_size
        self.headers = headers or {"Content-Type": "application/json"}
        self.enabled = enabled and bool(webhook_url)
        self.max_buffer_size = max_buffer_size
        self.timeout_s = timeout_s

        self._buffer: List[Dict[str, Any]] = []
        self._batch_counter: int = 0
        self._total_exported: int = 0
        self._total_batches: int = 0
        self._total_errors: int = 0
        self._last_flush_ts: float = 0.0

    def add(self, event: Dict[str, Any]) -> None:
        """
        Adiciona um evento ao buffer de export.

        Args:
            event: Dict representando o evento (de CycleEvent.to_dict() ou SourcedEvent.to_dict())
        """
        if not self.enabled:
            return

        self._buffer.append(event)

        # Protege contra buffer overflow (drop oldest)
        if len(self._buffer) > self.max_buffer_size:
            dropped = len(self._buffer) - self.max_buffer_size
            self._buffer = self._buffer[-self.max_buffer_size:]
            logger.debug(f"[BatchedExporter] buffer overflow — dropped {dropped} events")

    def maybe_flush(self) -> int:
        """
        Flush automático se batch_size foi atingido.

        Returns:
            Número de eventos exportados (0 se flush não foi necessário).
        """
        if not self.enabled:
            return 0
        if len(self._buffer) >= self.batch_size:
            return self.flush()
        return 0

    def flush(self) -> int:
        """
        Exporta todos os eventos do buffer para o webhook.

        Returns:
            Número de eventos exportados (0 em caso de erro ou buffer vazio).
        """
        if not self.enabled or not self._buffer:
            return 0

        batch_events = list(self._buffer)
        self._buffer.clear()

        self._batch_counter += 1
        batch = ExportBatch(
            events=batch_events,
            batch_id=f"batch-{self._batch_counter:05d}",
            batch_size=len(batch_events),
        )

        exported = self._post_batch(batch)
        if exported > 0:
            self._total_exported += exported
            self._total_batches += 1
            self._last_flush_ts = time.time()
        return exported

    def _post_batch(self, batch: ExportBatch) -> int:
        """
        Envia o lote para o webhook via HTTP POST.

        Fail-silent: qualquer erro HTTP/conexão vira log de debug.

        Returns:
            Número de eventos enviados (0 se falhou).
        """
        if not self.webhook_url:
            return 0

        try:
            payload = batch.to_json().encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=payload,
                method="POST",
            )
            for key, value in self.headers.items():
                req.add_header(key, value)

            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                status = resp.status
                if status < 300:
                    logger.debug(
                        f"[BatchedExporter] flushed {batch.batch_size} events "
                        f"to webhook (HTTP {status})"
                    )
                    return batch.batch_size
                else:
                    logger.debug(
                        f"[BatchedExporter] webhook returned HTTP {status}"
                    )
                    self._total_errors += 1
                    return 0

        except urllib.error.URLError as exc:
            logger.debug(f"[BatchedExporter] webhook URLError: {exc}")
            self._total_errors += 1
            return 0
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[BatchedExporter] webhook failed: {exc}")
            self._total_errors += 1
            return 0

    def buffer_size(self) -> int:
        """Retorna o tamanho atual do buffer."""
        return len(self._buffer)

    def is_configured(self) -> bool:
        """Retorna True se o exporter está configurado com URL."""
        return bool(self.webhook_url)

    def summary(self) -> dict:
        return {
            "enabled": self.enabled,
            "webhook_url": self.webhook_url or "(not configured)",
            "batch_size": self.batch_size,
            "buffer_size": len(self._buffer),
            "total_exported": self._total_exported,
            "total_batches": self._total_batches,
            "total_errors": self._total_errors,
            "last_flush_ts": self._last_flush_ts,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_exporter: Optional[CycleBatchedExporter] = None


def get_cycle_batched_exporter() -> CycleBatchedExporter:
    """Retorna o singleton global do CycleBatchedExporter."""
    global _exporter
    if _exporter is None:
        try:
            from src.config.settings import settings
            webhook_url = getattr(settings, "cycle_webhook_url", None) or None
            batch_size = int(getattr(settings, "cycle_webhook_batch_size", 20))
            enabled = bool(getattr(settings, "cycle_webhook_enabled", True))
            headers_raw = getattr(settings, "cycle_webhook_headers", {}) or {}
            headers: Dict[str, str] = {"Content-Type": "application/json"}
            if isinstance(headers_raw, dict):
                headers.update(headers_raw)
        except Exception:  # noqa: BLE001
            webhook_url = None
            batch_size = 20
            enabled = False
            headers = {"Content-Type": "application/json"}

        _exporter = CycleBatchedExporter(
            webhook_url=webhook_url,
            batch_size=batch_size,
            headers=headers,
            enabled=enabled,
        )
    return _exporter


def reset_cycle_batched_exporter() -> None:
    """Reseta o singleton — para testes."""
    global _exporter
    _exporter = None
