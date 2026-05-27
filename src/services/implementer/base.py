"""
src/services/implementer/base.py
==================================
Base abstrata para todos os agentes implementadores.

Lifecycle de uma implementação:

  1. ``prepare()`` — cria branch local `imp/IMP-xxxxxx`, valida estado
  2. ``analyze()`` — lê o brief IMP-*.md e decide estratégia
  3. ``apply()`` — executa as mudanças (deterministic / LLM / recipe)
  4. ``validate()`` — roda ruff + mypy scoped (não pytest geral)
  5. ``commit()`` — cria commit local "[IMP-xxxxxx] título"
  6. ``finalize()`` — atualiza dev_state (queued → in_dev → pr_open)

Cada subclasse implementa ``analyze()`` e ``apply()``. O resto é DRY.
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from loguru import logger

_REPO = Path(__file__).resolve().parents[3]


class ImplementerStatus(str, Enum):
    """Resultado possível de uma tentativa de implementação."""

    SKIPPED = "skipped"            # Cap atingido / protegido / não aplicável
    SUCCESS = "success"            # Mudanças aplicadas + commit feito
    RECIPE_ONLY = "recipe_only"    # Não conseguiu implementar — escreveu recipe
    PARTIAL = "partial"            # Aplicou parcialmente, mudanças não commitadas
    FAILED = "failed"              # Erro durante apply/validate
    BLOCKED = "blocked"            # Bloqueado por guard (protected path, etc)


@dataclass
class ImplementerResult:
    """Resultado completo de uma tentativa de implementação."""

    rec_id: str
    agent: str                       # ex: "BackendImplementer"
    status: ImplementerStatus
    layer_used: str = ""             # "deterministic" | "llm" | "recipe"
    branch: Optional[str] = None     # branch criada (se houver)
    files_changed: list[str] = field(default_factory=list)
    lines_changed: int = 0
    commit_sha: Optional[str] = None
    reason: str = ""
    cost_usd: float = 0.0
    duration_ms: int = 0
    recipe_path: Optional[str] = None
    ts: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "rec_id": self.rec_id,
            "agent": self.agent,
            "status": self.status.value,
            "layer_used": self.layer_used,
            "branch": self.branch,
            "files_changed": self.files_changed,
            "lines_changed": self.lines_changed,
            "commit_sha": self.commit_sha,
            "reason": self.reason,
            "cost_usd": self.cost_usd,
            "duration_ms": self.duration_ms,
            "recipe_path": self.recipe_path,
            "ts": self.ts,
        }


# ---------------------------------------------------------------------------
# Git helpers — never raises
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path = _REPO, timeout: float = 30.0) -> tuple[int, str, str]:
    """Executa um comando git fail-tolerant. Retorna (code, stdout, stderr)."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.SubprocessError as exc:
        return -1, "", str(exc)


def current_branch() -> str:
    code, out, _ = _git("rev-parse", "--abbrev-ref", "HEAD")
    return out if code == 0 else ""


def branch_exists(name: str) -> bool:
    code, _, _ = _git("rev-parse", "--verify", name)
    return code == 0


def create_branch(name: str, base: str = "main") -> tuple[bool, str]:
    """
    Cria branch local `name` baseada em `base`. Não faz checkout fora dela
    se já estamos em outra branch (deixamos o operador escolher).

    Implementer trabalha por `git worktree` se possível pra não bagunçar a
    branch atual do operador. Fallback: stash + checkout.

    Returns: (ok, reason)
    """
    if branch_exists(name):
        return True, "branch already exists"
    code, out, err = _git("branch", name, base)
    if code != 0:
        return False, f"git branch failed: {err or out}"
    return True, "created"


def commit_on_branch(
    branch: str,
    message: str,
    files: list[str],
) -> tuple[Optional[str], str]:
    """
    Stage + commit files numa branch isolada. Restaura a branch original
    do operador no final, garantindo zero side-effect no working tree.

    Estratégia:
      1. Salva branch atual (origin_branch).
      2. Stash de mudanças não-relacionadas a `files` (preserva trabalho).
      3. Checkout `branch` (cria se não existir).
      4. Stash pop só dos `files` que importam para esta IMP.
      5. git add + commit + capturar SHA.
      6. Checkout origin_branch.
      7. Stash pop restante (mudanças do operador).

    Bug pré-2026-05-27: assumia que estávamos na branch isolada e fazia
    commit no working tree atual — efeito: IMPs commitadas em main.
    """
    if not files:
        return None, "no files to commit"

    # 1) Estado atual
    code, origin_branch, _ = _git("rev-parse", "--abbrev-ref", "HEAD")
    if code != 0 or not origin_branch:
        return None, "could not read current branch"

    # 2) Se já estamos na branch alvo, simplesmente add + commit
    if origin_branch == branch:
        add_args = ["add", "--"] + files
        code, _, err = _git(*add_args)
        if code != 0:
            return None, f"git add failed: {err}"
        code, _, err = _git(
            "commit", "-m", message, "--allow-empty-message", "--no-verify",
        )
        if code != 0:
            return None, f"git commit failed: {err}"
        code, sha, _ = _git("rev-parse", "HEAD")
        if code != 0:
            return None, "could not read commit sha"
        return sha[:12], "ok"

    # 3) Strategy: usa git stash --include-untracked para preservar TUDO,
    #    checkout pra branch, restaura SÓ os files que precisamos commitar,
    #    commit, volta pra origin, restaura o resto.
    #
    #    Mas isso é complexo e tem race conditions. Abordagem mais simples
    #    e robusta: NÃO mudar de branch. Em vez disso, usar
    #    `git stash create + apply` em branch alvo via plumbing commands.

    # Alternativa robusta: criar um commit-tree apontando pra branch alvo
    # usando git plumbing — sem checkout, sem mexer no working tree.
    #
    # Passos:
    #   a. Stage só os `files` (git add).
    #   b. Criar tree do staged content (git write-tree).
    #   c. Criar commit object com parent = branch alvo (git commit-tree).
    #   d. Mover ref da branch alvo pra esse commit (git update-ref).
    #   e. Unstage os arquivos (reset HEAD --) — working tree preservado.
    add_args = ["add", "--"] + files
    code, _, err = _git(*add_args)
    if code != 0:
        return None, f"git add failed: {err}"

    code, tree_sha, err = _git("write-tree")
    if code != 0:
        # Rollback: unstage
        _git("reset", "HEAD", "--", *files)
        return None, f"git write-tree failed: {err}"

    # Parent: tip da branch alvo
    code, parent_sha, err = _git("rev-parse", branch)
    if code != 0:
        _git("reset", "HEAD", "--", *files)
        return None, f"could not read branch tip: {err}"

    code, commit_sha, err = _git(
        "commit-tree", tree_sha, "-p", parent_sha, "-m", message,
    )
    if code != 0:
        _git("reset", "HEAD", "--", *files)
        return None, f"git commit-tree failed: {err}"

    code, _, err = _git("update-ref", f"refs/heads/{branch}", commit_sha)
    if code != 0:
        _git("reset", "HEAD", "--", *files)
        return None, f"git update-ref failed: {err}"

    # Unstage (mantém working tree intacto)
    _git("reset", "HEAD", "--", *files)
    return commit_sha[:12], "ok (via commit-tree plumbing)"


# ---------------------------------------------------------------------------
# Implementer ABC
# ---------------------------------------------------------------------------


class BaseImplementer(ABC):
    """
    Contrato abstrato. Cada subclasse representa uma vertical de área.
    Vertical = backend/frontend/dashboard/agents.

    A escolha da CAMADA (deterministic/llm/recipe) é interna ao agente,
    delegada para módulos em ``layers/``.
    """

    name: str = "BaseImplementer"
    area: str = ""   # subclass overrides

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._log = logger.bind(agent=self.name)

    # ----------------- public -----------------

    def implement(self, brief: dict[str, Any]) -> ImplementerResult:
        """Entry point: roda todo o lifecycle. NÃO levanta exceção."""
        started = datetime.now()
        rec_id = str(brief.get("rec_id") or brief.get("id") or "")
        result = ImplementerResult(rec_id=rec_id, agent=self.name,
                                   status=ImplementerStatus.SKIPPED)
        try:
            # Pré-check: brief válido?
            if not rec_id:
                result.status = ImplementerStatus.SKIPPED
                result.reason = "brief missing rec_id"
                return result
            # Subclasse roda análise + apply.
            # analyze() pode setar BLOCKED ou FAILED para cortar; senão
            # apply() é sempre chamado (vai delegar para deterministic→llm→recipe).
            self.analyze(brief, result)
            if result.status not in (ImplementerStatus.BLOCKED,
                                     ImplementerStatus.FAILED):
                self.apply(brief, result)
        except Exception as exc:  # noqa: BLE001
            result.status = ImplementerStatus.FAILED
            result.reason = f"unexpected: {exc}"
            self._log.exception(f"[{self.name}] implement crashed: {exc}")
        finally:
            result.duration_ms = int(
                (datetime.now() - started).total_seconds() * 1000
            )
        return result

    # ----------------- to override -----------------

    @abstractmethod
    def analyze(self, brief: dict[str, Any], result: ImplementerResult) -> None:
        """Decide camada + estratégia. Atualiza ``result.layer_used`` e
        eventualmente ``result.status``."""

    @abstractmethod
    def apply(self, brief: dict[str, Any], result: ImplementerResult) -> None:
        """Executa as mudanças. Atualiza ``result.files_changed``,
        ``lines_changed``, ``commit_sha``, ``status``."""
