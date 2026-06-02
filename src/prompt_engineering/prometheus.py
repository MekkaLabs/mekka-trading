"""
src/prompt_engineering/prometheus.py
=====================================
Prometheus — orquestrador de alto nível para engenharia de prompts.

API stable + minimalista. Usado por:
- scripts/prometheus_cli.py (CLI)
- tests/test_prompt_engineering.py (testes)
- CI workflow futuro
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from src.prompt_engineering.auditor import audit_prompt, audit_text
from src.prompt_engineering.catalog import PromptCatalog, is_catalog_enabled
from src.prompt_engineering.extractor import extract_from_file, scan_directory
from src.prompt_engineering.models import (
    ExtractedPrompt,
    PromptRecord,
    Scorecard,
)

# Modelos compatíveis padrão (alinhado com llm_client.py).
DEFAULT_COMPATIBLE_MODELS = ["gpt-4o", "claude-sonnet-4-6"]


class Prometheus:
    """
    Orquestrador. Sempre-disponível mesmo se catálogo desabilitado.

    Examples
    --------
    >>> p = Prometheus()
    >>> prompts = p.scan_agents(Path("src/agents"))
    >>> sc = p.audit(prompts[0])
    >>> p.register(prompts[0], scorecard=sc, name="vision_system_prompt")
    """

    def __init__(self, catalog_path: Optional[Path] = None, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path.cwd()
        self.catalog = PromptCatalog(path=catalog_path) if catalog_path else PromptCatalog()
        self._catalog_enabled = is_catalog_enabled() or catalog_path is not None

    # ── extração ────────────────────────────────────────────────────────

    def extract(self, file_path: Path) -> list[ExtractedPrompt]:
        """Extrai prompts de um arquivo."""
        return extract_from_file(file_path, repo_root=self.repo_root)

    def scan_agents(self, agents_dir: Optional[Path] = None) -> list[ExtractedPrompt]:
        """Varre o diretório de agentes (default: src/agents)."""
        agents_dir = agents_dir or (self.repo_root / "src" / "agents")
        return scan_directory(agents_dir, repo_root=self.repo_root)

    # ── auditoria ───────────────────────────────────────────────────────

    def audit(self, prompt: ExtractedPrompt) -> Scorecard:
        """Audita um ExtractedPrompt. 100% determinístico, sem LLM."""
        return audit_prompt(prompt)

    def audit_text(self, text: str) -> Scorecard:
        """Conveniência para auditar texto bruto (sem extração)."""
        return audit_text(text)

    # ── catálogo (opt-in) ───────────────────────────────────────────────

    def register(
        self,
        prompt: ExtractedPrompt,
        scorecard: Optional[Scorecard] = None,
        name: Optional[str] = None,
        compatible_models: Optional[list[str]] = None,
        notes: str = "",
    ) -> tuple[Optional[str], Optional[PromptRecord]]:
        """
        Registra (ou atualiza) prompt no catálogo persistente.

        Returns
        -------
        (status, record) onde status ∈ {"created", "updated", "unchanged", None}.
        None se catálogo desabilitado.
        """
        if not self._catalog_enabled:
            logger.debug("[Prometheus] catálogo desabilitado — register() no-op")
            return None, None

        record = PromptRecord(
            name=name or self._derive_name(prompt),
            fingerprint=prompt.fingerprint,
            extracted=prompt,
            scorecard=scorecard,
            compatible_models=compatible_models or DEFAULT_COMPATIBLE_MODELS,
            notes=notes,
            last_audited_at=datetime.utcnow() if scorecard else None,
        )
        status = self.catalog.upsert(record)
        if not self.catalog.save():
            logger.warning("[Prometheus] catálogo modificado em memória mas não salvo em disco")
        return status, record

    def list_catalog(self) -> list[PromptRecord]:
        """Lista catálogo persistente (vazia se desabilitado)."""
        if not self._catalog_enabled:
            return []
        return self.catalog.all()

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _derive_name(prompt: ExtractedPrompt) -> str:
        """
        Deriva nome canônico a partir do arquivo + variável.

        Ex: src/agents/vision.py + _SYSTEM_PROMPT → "vision_system_prompt"
        """
        stem = Path(prompt.source_file).stem
        var = prompt.variable_name.lstrip("_").lower()
        return f"{stem}_{var}"

    # ── relatórios ──────────────────────────────────────────────────────

    def report_text(self, prompt: ExtractedPrompt, scorecard: Scorecard) -> str:
        """Relatório human-readable (mesmo formato do agente Prometheus original)."""
        name = self._derive_name(prompt)
        lines = [
            f"SCORECARD DE AUDITORIA — {name}",
            "=" * 50,
            f"  source: {prompt.source_file}:{prompt.line_number}",
            f"  variable: {prompt.variable_name}",
            f"  fingerprint: {prompt.fingerprint}",
            f"  detected_role: {prompt.detected_role or 'N/A'}",
            "",
        ]
        for d in scorecard.dimensions:
            lines.append(f"{d.dimension.value.upper():22s}: {d.score}/10")
            for f in d.findings:
                lines.append(f"  → {f}")
            lines.append("")
        lines.extend([
            f"SCORE GERAL: {scorecard.score_total}/40  [{scorecard.health}]",
            "",
        ])
        if scorecard.recommendations:
            lines.append("AÇÕES RECOMENDADAS:")
            for i, rec in enumerate(scorecard.recommendations, 1):
                lines.append(f"  {i}. {rec}")
        return "\n".join(lines)
