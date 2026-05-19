"""
src/services/cycle_artifact_store.py
======================================
Story 200 — CycleArtifactStore: armazenamento de artefatos por ciclo,
inspirado no FileStore / InMemoryFileStore do OpenHands.

Inspirado no padrão OpenHands FileStore / InMemoryFileStore
(openhands-sdk/openhands/sdk/io):
  "FileStore abstracts artifact storage for agents — supporting
   put(path, content), get(path), list(prefix), delete(path).
   InMemoryFileStore keeps everything in a dict for testing and
   lightweight deployments. LocalFileStore writes to disk.
   Artifacts are keyed by path — typically cycle_id/type/name."

No OpenHands:
  FileStore é usada para armazenar artefatos produzidos pelos agentes:
  código gerado, outputs de comandos, resultados de análise, screenshots.
  InMemoryFileStore é o fallback quando não há filesystem disponível.
  O path segue convenção: "cycle_id/artifact_type/filename"

No Mekka, o equivalente é:
  CycleArtifactStore guarda artefatos produzidos por ciclo de análise:
  sinais gerados, reasoning do Vision, resultados do Batman risk gate,
  snapshots de mercado, outputs de sub-agentes. Útil para audit trail,
  replay de decisões e feed do dashboard.

  Artefatos são keyed por: "{symbol}/{cycle_id}/{artifact_type}"
  Tipos: SIGNAL, REASONING, RISK_REPORT, MARKET_SNAPSHOT, DELEGATE_OUTPUT

Arquitetura
-----------
  ArtifactType       — enum dos tipos de artefatos
  CycleArtifact      — payload de um artefato armazenado
  CycleArtifactStore (InMemory)
    ├── put(symbol, cycle_id, artifact_type, content, metadata)
    ├── get(symbol, cycle_id, artifact_type) → CycleArtifact|None
    ├── list(symbol, cycle_id) → List[CycleArtifact]
    ├── list_by_type(artifact_type, symbol, limit) → List[CycleArtifact]
    ├── delete(symbol, cycle_id, artifact_type)
    └── summary() → dict
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# ArtifactType
# ---------------------------------------------------------------------------

class ArtifactType(str, Enum):
    """
    Tipo de artefato armazenado por ciclo.

    Mapeamento com OpenHands FileStore:
      SIGNAL          ←→ output estruturado do agente (ActionOutput)
      REASONING       ←→ pre-reasoning / chain-of-thought (ThoughtAction)
      RISK_REPORT     ←→ validation report do sandbox (ObservationOutput)
      MARKET_SNAPSHOT ←→ estado do ambiente capturado (EnvironmentState)
      DELEGATE_OUTPUT ←→ output de sub-agente delegado (DelegateObservation)
      CUSTOM          ←→ artefato arbitrário definido pelo usuário
    """
    SIGNAL = "SIGNAL"
    REASONING = "REASONING"
    RISK_REPORT = "RISK_REPORT"
    MARKET_SNAPSHOT = "MARKET_SNAPSHOT"
    DELEGATE_OUTPUT = "DELEGATE_OUTPUT"
    CUSTOM = "CUSTOM"


# ---------------------------------------------------------------------------
# CycleArtifact
# ---------------------------------------------------------------------------

@dataclass
class CycleArtifact:
    """
    Artefato produzido por um ciclo de análise.

    Equivalente a um arquivo no FileStore do OpenHands:
    conteúdo (dict/str) + metadados + path de lookup.
    """
    symbol: str
    cycle_id: str
    artifact_type: ArtifactType
    content: Any  # dict, str, ou qualquer serializable
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)
    size_estimate: int = 0  # len(str(content))

    @property
    def path(self) -> str:
        """Path canônico: symbol/cycle_id/artifact_type"""
        return f"{self.symbol}/{self.cycle_id[:8]}/{self.artifact_type.value}"

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "symbol": self.symbol,
            "cycle_id": self.cycle_id,
            "artifact_type": self.artifact_type.value,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "size_estimate": self.size_estimate,
        }


# ---------------------------------------------------------------------------
# CycleArtifactStore
# ---------------------------------------------------------------------------

class CycleArtifactStore:
    """
    Armazena artefatos de ciclos em memória (InMemoryFileStore pattern).

    Padrão OpenHands FileStore:
    - put/get/list/delete com path canônico
    - InMemory: tudo em dict, sem I/O (adequado para pipeline síncrono)
    - Fail-silent: erros de armazenamento não travam o pipeline
    - max_artifacts: proteção contra memory leak

    Uso:
        store = get_cycle_artifact_store()
        store.put("BTC", cycle_id, ArtifactType.SIGNAL, signal_dict)
        artifact = store.get("BTC", cycle_id, ArtifactType.SIGNAL)
    """

    def __init__(
        self,
        max_artifacts: int = 500,
        max_per_symbol: int = 50,
    ) -> None:
        self.max_artifacts = max_artifacts
        self.max_per_symbol = max_per_symbol

        # Storage: path → CycleArtifact
        self._store: Dict[str, CycleArtifact] = {}
        # Índice por símbolo: symbol → list of paths (FIFO)
        self._by_symbol: Dict[str, List[str]] = {}
        self._total_stored: int = 0
        self._total_evicted: int = 0

    def _make_path(self, symbol: str, cycle_id: str, artifact_type: ArtifactType) -> str:
        return f"{symbol.upper()}/{cycle_id[:8]}/{artifact_type.value}"

    def put(
        self,
        symbol: str,
        cycle_id: str,
        artifact_type: ArtifactType,
        content: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CycleArtifact:
        """
        Armazena um artefato (PUT semântica: cria ou substitui).

        Args:
            symbol:        Símbolo do ativo
            cycle_id:      ID do ciclo
            artifact_type: Tipo do artefato
            content:       Conteúdo (dict, str, etc.)
            metadata:      Metadados opcionais

        Returns:
            CycleArtifact armazenado.
        """
        sym = symbol.upper() if symbol else "UNKNOWN"
        size = len(str(content))

        artifact = CycleArtifact(
            symbol=sym,
            cycle_id=cycle_id,
            artifact_type=artifact_type,
            content=content,
            metadata=metadata or {},
            size_estimate=size,
        )

        path = artifact.path
        self._store[path] = artifact

        # índice por símbolo
        if sym not in self._by_symbol:
            self._by_symbol[sym] = []
        if path not in self._by_symbol[sym]:
            self._by_symbol[sym].append(path)

        # evict se excedeu max_per_symbol
        while len(self._by_symbol[sym]) > self.max_per_symbol:
            oldest_path = self._by_symbol[sym].pop(0)
            self._store.pop(oldest_path, None)
            self._total_evicted += 1

        # evict global se excedeu max_artifacts
        if len(self._store) > self.max_artifacts:
            oldest_path = next(iter(self._store))
            self._store.pop(oldest_path, None)
            self._total_evicted += 1

        self._total_stored += 1
        logger.debug(f"[ArtifactStore] PUT {path} (~{size}B)")
        return artifact

    def get(
        self,
        symbol: str,
        cycle_id: str,
        artifact_type: ArtifactType,
    ) -> Optional[CycleArtifact]:
        """
        Recupera um artefato por path canônico.

        Returns:
            CycleArtifact se encontrado, None caso contrário.
        """
        path = self._make_path(symbol, cycle_id, artifact_type)
        return self._store.get(path)

    def list(
        self,
        symbol: str,
        cycle_id: Optional[str] = None,
    ) -> List[CycleArtifact]:
        """
        Lista artefatos de um símbolo, opcionalmente filtrado por cycle_id.

        Returns:
            Lista de CycleArtifact, do mais antigo ao mais recente.
        """
        sym = symbol.upper() if symbol else "UNKNOWN"
        paths = self._by_symbol.get(sym, [])
        artifacts = [self._store[p] for p in paths if p in self._store]
        if cycle_id:
            cid = cycle_id[:8]
            artifacts = [a for a in artifacts if a.cycle_id[:8] == cid]
        return artifacts

    def list_by_type(
        self,
        artifact_type: ArtifactType,
        symbol: Optional[str] = None,
        limit: int = 20,
    ) -> List[CycleArtifact]:
        """Lista artefatos por tipo, opcionalmente filtrado por símbolo."""
        artifacts = [
            a for a in self._store.values()
            if a.artifact_type == artifact_type
        ]
        if symbol:
            sym = symbol.upper()
            artifacts = [a for a in artifacts if a.symbol == sym]
        # mais recentes primeiro
        artifacts.sort(key=lambda a: a.timestamp, reverse=True)
        return artifacts[:limit]

    def delete(
        self,
        symbol: str,
        cycle_id: str,
        artifact_type: ArtifactType,
    ) -> bool:
        """Remove um artefato. Retorna True se encontrado e removido."""
        path = self._make_path(symbol, cycle_id, artifact_type)
        if path in self._store:
            del self._store[path]
            sym = symbol.upper()
            if sym in self._by_symbol and path in self._by_symbol[sym]:
                self._by_symbol[sym].remove(path)
            logger.debug(f"[ArtifactStore] DELETE {path}")
            return True
        return False

    def summary(self) -> dict:
        type_counts: Dict[str, int] = {}
        for a in self._store.values():
            type_counts[a.artifact_type.value] = type_counts.get(a.artifact_type.value, 0) + 1
        return {
            "total_stored": self._total_stored,
            "total_evicted": self._total_evicted,
            "current_count": len(self._store),
            "symbols_tracked": len(self._by_symbol),
            "by_type": type_counts,
            "max_artifacts": self.max_artifacts,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_store: Optional[CycleArtifactStore] = None


def get_cycle_artifact_store() -> CycleArtifactStore:
    """Retorna o singleton global do CycleArtifactStore."""
    global _store
    if _store is None:
        try:
            from src.config.settings import settings
            max_artifacts = int(getattr(settings, "artifact_store_max", 500))
            max_per_symbol = int(getattr(settings, "artifact_store_max_per_symbol", 50))
        except Exception:  # noqa: BLE001
            max_artifacts = 500
            max_per_symbol = 50
        _store = CycleArtifactStore(
            max_artifacts=max_artifacts,
            max_per_symbol=max_per_symbol,
        )
    return _store


def reset_cycle_artifact_store() -> None:
    """Reseta o singleton — para testes."""
    global _store
    _store = None
