"""
src/prompt_engineering/catalog.py
==================================
Catálogo persistente de prompts auditados.

Storage: JSON em `data/prompts/catalog.json` (opt-in via env var
`PROMETHEUS_CATALOG_ENABLED`).

Garantias:
- Append-only do ponto de vista do usuário (atualizar = nova entrada
  com novo fingerprint).
- Atomic write (escreve em `.tmp` + os.replace).
- Sem locking — uso típico é single-process (CLI ou CI).
- Falha de I/O nunca é fatal — só loga e retorna None.

NOTA: o catálogo NUNCA é consultado pelo trading loop. É apenas
dev/ops artifact.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger
from pydantic import ValidationError

from src.prompt_engineering.models import PromptRecord

# Default location (relativo ao repo root). Pode ser sobrescrito no construtor.
DEFAULT_CATALOG_PATH = Path("data/prompts/catalog.json")


class PromptCatalog:
    """JSON-backed catalog of audited prompts."""

    def __init__(self, path: Optional[Path] = None):
        self.path: Path = path or DEFAULT_CATALOG_PATH
        self._records: list[PromptRecord] = []
        self._loaded: bool = False

    # ── persistence ──────────────────────────────────────────────────────

    def load(self) -> int:
        """Carrega catálogo do disco. Retorna número de registros."""
        if not self.path.exists():
            self._records = []
            self._loaded = True
            return 0
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"[Prometheus.catalog] falha ao ler {self.path}: {exc}")
            self._records = []
            self._loaded = True
            return 0

        records: list[PromptRecord] = []
        for item in raw.get("records", []):
            try:
                records.append(PromptRecord.model_validate(item))
            except ValidationError as exc:
                logger.warning(f"[Prometheus.catalog] registro inválido ignorado: {exc}")
        self._records = records
        self._loaded = True
        return len(records)

    def save(self) -> bool:
        """Persiste atomicamente. Retorna True em sucesso."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(f"[Prometheus.catalog] não consegui criar dir {self.path.parent}: {exc}")
            return False
        payload = {
            "catalog_version": "1.0",
            "updated_at": datetime.utcnow().isoformat(),
            "records": [r.model_dump(mode="json") for r in self._records],
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
            return True
        except OSError as exc:
            logger.warning(f"[Prometheus.catalog] falha ao escrever {self.path}: {exc}")
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            return False

    # ── queries ──────────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def all(self) -> list[PromptRecord]:
        self._ensure_loaded()
        return list(self._records)

    def find_by_fingerprint(self, fingerprint: str) -> Optional[PromptRecord]:
        self._ensure_loaded()
        for r in self._records:
            if r.fingerprint == fingerprint:
                return r
        return None

    def find_by_name(self, name: str) -> Optional[PromptRecord]:
        self._ensure_loaded()
        for r in self._records:
            if r.name == name:
                return r
        return None

    # ── mutations ────────────────────────────────────────────────────────

    def upsert(self, record: PromptRecord) -> str:
        """
        Insere ou atualiza pelo par (name, fingerprint).

        Returns
        -------
        "created" | "updated" | "unchanged"
        """
        self._ensure_loaded()
        for i, existing in enumerate(self._records):
            if existing.name == record.name:
                if existing.fingerprint == record.fingerprint:
                    # mesmo prompt — atualiza só scorecard se houver novo
                    if record.scorecard:
                        self._records[i].scorecard = record.scorecard
                        self._records[i].last_audited_at = datetime.utcnow()
                        return "updated"
                    return "unchanged"
                # novo conteúdo para mesmo nome — versão nova substitui
                self._records[i] = record
                return "updated"
        self._records.append(record)
        return "created"

    def remove(self, name: str) -> bool:
        self._ensure_loaded()
        before = len(self._records)
        self._records = [r for r in self._records if r.name != name]
        return len(self._records) < before


def is_catalog_enabled() -> bool:
    """
    Catálogo é opt-in via env var.

    Default = False. Trading loop nunca toca o catálogo.
    """
    return os.environ.get("PROMETHEUS_CATALOG_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )
