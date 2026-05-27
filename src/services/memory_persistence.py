"""
src/services/memory_persistence.py
====================================
Camada leve de persistência para os 3 caches in-memory:
  - RoleWorkingMemory
  - SignalOutcomeMemory
  - CycleConversationMemory

Antes deste módulo, todas as 3 perdiam histórico em todo restart do
runtime (CIO Engineer audit, 2026-05-27). Vision recebia blocos vazios
até que novos trades acontecessem.

Estratégia (intencionalmente simples):
  - 1 arquivo JSON por singleton em `data/memory/<name>.json`
  - Atomic write via `os.replace` (igual prompt_engineering catalog)
  - Cap de tamanho por arquivo (10 MB) para não inflar
  - Fail-silent: I/O error → log debug + return (no-op)
  - Cada singleton chama `save_state(name, payload)` em cada write e
    `load_state(name)` no `__init__`

Sem DB schema novo. Não toca em `audit_log` (que é mais pesado).
JSON é suficiente porque os 3 caches já têm max_size limitado por
config (deques com maxlen).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from loguru import logger

_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _ROOT / "data" / "memory"
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB safety cap


def _path_for(name: str) -> Path:
    # Sanity: name deve ser slug simples
    safe = "".join(c for c in name if c.isalnum() or c in "_-")
    return _DATA_DIR / f"{safe}.json"


def load_state(name: str) -> Optional[dict[str, Any]]:
    """Carrega payload salvo. None se vazio/inexistente/corrupto."""
    p = _path_for(name)
    if not p.exists():
        return None
    try:
        size = p.stat().st_size
        if size == 0 or size > _MAX_BYTES:
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug(f"[memory_persistence] load {name}: {exc}")
        return None


def save_state(name: str, payload: dict[str, Any]) -> bool:
    """
    Persiste payload. Fail-silent (retorna False em erro).
    Sempre atomic via os.replace.
    """
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        p = _path_for(name)
        tmp = p.with_suffix(p.suffix + ".tmp")
        serialized = json.dumps(payload, default=str, ensure_ascii=False)
        if len(serialized) > _MAX_BYTES:
            logger.warning(f"[memory_persistence] {name}: payload >10MB, skip save")
            return False
        tmp.write_text(serialized, encoding="utf-8")
        os.replace(tmp, p)
        return True
    except OSError as exc:
        logger.debug(f"[memory_persistence] save {name}: {exc}")
        return False
