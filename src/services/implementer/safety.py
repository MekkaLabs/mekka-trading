"""
src/services/implementer/safety.py
====================================
Guards de segurança para todos os implementers.

Princípios INVIOLÁVEIS:
  - Nenhum implementer pode tocar nos arquivos protegidos abaixo.
  - Nenhum implementer pode aplicar mudanças que excedam os caps de blast.
  - Toda mudança é verificada por essa camada ANTES do commit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# PROTECTED PATHS — nunca podem ser modificados por implementer
# ---------------------------------------------------------------------------
#
# Lista derivada da política do CLAUDE.md ("Regras Invioláveis"):
#   - settings.py contém o validador live_trading_double_gate
#   - batman.py é o gate de risco — bypassá-lo é fatal
#   - iron_man.py é o executor de ordens — risco sistêmico
#   - .env contém credenciais (private keys)
#   - .env.example é template de credenciais
#
# Adicionar paths aqui é "fail-closed" — bloqueia escrita; jamais ampliar
# sem revisão humana.

PROTECTED_PATHS: tuple[str, ...] = (
    "src/config/settings.py",
    "src/agents/batman.py",
    "src/agents/iron_man.py",
    ".env",
    ".env.example",
    ".env.local",
    ".env.production",
)

# Diretórios inteiramente protegidos (qualquer arquivo abaixo é bloqueado).
PROTECTED_DIRS: tuple[str, ...] = (
    "data",          # SQLite DB, runtime state
    "logs",          # runtime logs
    ".git",          # internal
    ".aios-core",    # L1 framework
    ".venv",
    ".venv313",
    "node_modules",
)

# ---------------------------------------------------------------------------
# Blast radius caps — limite por IMP
# ---------------------------------------------------------------------------
#
# REV-INV-10 (2026-05-29): caps relaxados após auditoria do Agent E.
# Cap original 5/500 era restritivo demais — 60% das IMPs reais (recipes
# mecânicas de 1-3 arquivos) ainda passam, mas refactors leves (ex: extrair
# helper de 2-3 módulos relacionados) agora cabem sem precisar quebrar em
# vários IMPs artificiais.
#
# Nota: PROTECTED_PATHS continua intacto — relaxar caps NÃO afrouxa a
# proteção de settings.py, batman.py, iron_man.py, .env etc.

MAX_FILES_PER_IMP: int = 8
MAX_LINES_PER_IMP: int = 1000
MAX_BRANCHES_PER_DAY: int = 20    # implementer não cria N branches descontroladas


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def is_protected(rel_path: str) -> bool:
    """True se o path é protegido (não pode ser modificado por implementer)."""
    rel = str(rel_path).replace("\\", "/")
    if rel in PROTECTED_PATHS:
        return True
    for d in PROTECTED_DIRS:
        if rel == d or rel.startswith(d + "/"):
            return True
    return False


def check_blast_radius(files: Iterable[str], total_lines_changed: int) -> tuple[bool, str]:
    """
    Returns (ok, reason). ``ok=False`` quando a mudança ultrapassa caps.
    """
    file_list = list(files)
    n = len(file_list)
    if n > MAX_FILES_PER_IMP:
        return False, f"too many files: {n} > {MAX_FILES_PER_IMP}"
    if total_lines_changed > MAX_LINES_PER_IMP:
        return False, (
            f"too many lines changed: {total_lines_changed} > {MAX_LINES_PER_IMP}"
        )
    return True, "ok"


def violation_message(rel_path: str) -> str:
    """Mensagem padrão pra protecção violada."""
    return (
        f"PROTECTED: `{rel_path}` está na lista de paths/dirs "
        "protegidos do implementer. Modificações nele exigem revisão humana "
        "explícita (não auto-implementação). Ver `safety.PROTECTED_PATHS`."
    )
