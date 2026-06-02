"""
src/services/implementer/agents.py
====================================
Implementers verticais — um por área (agents/backend/frontend/dashboard).

Cada subclasse só especializa o ``area`` e a estratégia de fallback.
Toda a lógica de lifecycle vive em ``base.BaseImplementer``.
"""

from __future__ import annotations

from typing import Any

from src.services.implementer import safety
from src.services.implementer.base import (
    BaseImplementer,
    ImplementerResult,
    ImplementerStatus,
    commit_on_branch,
    create_branch,
)
from src.services.implementer.layers import deterministic, llm, recipe


class _VerticalImplementer(BaseImplementer):
    """Lógica compartilhada entre todas as 4 verticais."""

    def analyze(self, brief: dict[str, Any], result: ImplementerResult) -> None:
        """Decide estratégia. Não fazemos area-match aqui — o ``router``
        já mapeou (ex: ``risk`` → BackendImplementer)."""
        result.status = ImplementerStatus.SKIPPED  # ainda não tentou — apply muda

    def apply(self, brief: dict[str, Any], result: ImplementerResult) -> None:
        rec_id = str(brief.get("rec_id") or brief.get("id") or "")
        branch = f"imp/IMP-{rec_id}"

        # ---- dry-run: NÃO escreve nada no working tree ----
        # Bug fix (2026-06-01): antes, deterministic/llm.try_apply escreviam os
        # arquivos ANTES do check de dry_run no _post_apply_commit — deixando o
        # tree sujo mesmo em modo manual (operation_mode=manual → worker dry-run).
        # Agora dry-run só DETECTA o que seria feito, sem tocar em disco.
        if self.dry_run:
            pattern = deterministic.detect_pattern(brief)
            result.layer_used = "deterministic" if pattern.matched else "none"
            result.status = ImplementerStatus.PARTIAL
            result.branch = branch
            result.reason = (
                f"dry-run: aplicaria padrão '{pattern.name}' (nada escrito)"
                if pattern.matched
                else "dry-run: nenhum padrão deterministic (nada escrito)"
            )
            return

        # ---- Step 1: tenta deterministic ----
        applied = deterministic.try_apply(brief, result)
        if result.status == ImplementerStatus.BLOCKED:
            return  # safety violation no apply do pattern
        if applied:
            self._post_apply_commit(branch, brief, result)
            return

        # ---- Step 2: tenta LLM (se habilitado e autorizado) ----
        applied = llm.try_apply(brief, result)
        if result.status == ImplementerStatus.BLOCKED:
            return
        if applied:
            self._post_apply_commit(branch, brief, result)
            return

        # ---- Step 3: fallback recipe ----
        recipe.write_recipe(brief, result)

    def _post_apply_commit(
        self, branch: str, brief: dict[str, Any], result: ImplementerResult,
    ) -> None:
        """Cria branch local + commit. Não faz push."""
        if self.dry_run:
            result.status = ImplementerStatus.PARTIAL
            result.reason = "dry-run: changes applied but not committed"
            result.branch = branch
            return

        # Blast radius check antes do commit
        ok, reason = safety.check_blast_radius(
            result.files_changed, result.lines_changed
        )
        if not ok:
            result.status = ImplementerStatus.BLOCKED
            result.reason = f"blast radius blocked commit: {reason}"
            return

        # Cria branch local (não faz checkout — opera no diretório atual)
        ok, branch_reason = create_branch(branch)
        if not ok and "exists" not in branch_reason:
            result.status = ImplementerStatus.FAILED
            result.reason = f"branch failed: {branch_reason}"
            return

        # Commit
        rec_id = str(brief.get("rec_id") or brief.get("id") or "")
        title = str(brief.get("title", "(no title)"))[:70]
        message = f"[IMP-{rec_id}] {title}\n\nAuto-implemented by {self.name} (layer={result.layer_used})"
        sha, commit_reason = commit_on_branch(branch, message, result.files_changed)
        if sha is None:
            result.status = ImplementerStatus.PARTIAL
            result.reason = f"changes applied but commit failed: {commit_reason}"
            result.branch = branch
            return

        result.commit_sha = sha
        result.branch = branch
        result.status = ImplementerStatus.SUCCESS
        result.reason = f"layer={result.layer_used} files={len(result.files_changed)} lines={result.lines_changed}"


# ---------------------------------------------------------------------------
# 4 verticais
# ---------------------------------------------------------------------------


class AgentsImplementer(_VerticalImplementer):
    name = "AgentsImplementer"
    area = "agents"


class BackendImplementer(_VerticalImplementer):
    name = "BackendImplementer"
    area = "backend"


class FrontendImplementer(_VerticalImplementer):
    name = "FrontendImplementer"
    area = "frontend"


class DashboardImplementer(_VerticalImplementer):
    name = "DashboardImplementer"
    area = "dashboard"
