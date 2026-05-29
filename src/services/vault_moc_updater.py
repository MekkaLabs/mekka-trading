"""
src/services/vault_moc_updater.py
==================================
VAULT-INTEG-2 (2026-05-29) — Mantém MOCs vivos via writers.

ANTES: cada writer (Cyclops/Mentor/Prometheus/Strategy/Cable) escrevia uma
nota nova no vault mas não atualizava o MOC correspondente. Resultado:
notas órfãs no graph view, MOCs estáticos, operador não percebia atividade.

DEPOIS: helper `record_to_moc()` adiciona uma linha em seção dedicada
``## 📜 Logs Recentes (auto-mantido)`` no MOC apropriado. Idempotente:
mesma entry (timestamp + link) só é adicionada 1x. Mantém últimas N entries
(default 20) — anteriores ficam históricas via VCS.

Fail-silent. Não bloqueia o writer original.

Uso típico nos writers:

    from src.services.vault_moc_updater import record_to_moc
    record_to_moc(
        moc_name="MOC - Aprendizados",
        entry_link=f"[[{stem}]]",
        summary=f"Prometheus learning ({n_obs} obs, {n_err} errs)",
    )
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger


_DEFAULT_VAULT = Path.home() / "Documents" / "mekka-trading-obsidian"
_MOC_FOLDER = "50 - MOCs"
_SECTION_HEADER = "## 📜 Logs Recentes (auto-mantido)"
_SECTION_NOTE = (
    "_Mantido automaticamente por `vault_moc_updater.py`. "
    "Editar manualmente apenas para curar/expurgar entradas antigas._"
)

MAX_ENTRIES = int(os.environ.get("VAULT_MOC_MAX_ENTRIES", "20"))


def _vault_path() -> Path:
    raw = os.environ.get("MEKKA_VAULT_PATH")
    return Path(raw).expanduser() if raw else _DEFAULT_VAULT


def is_enabled() -> bool:
    """Opt-in via VAULT_MOC_UPDATER_ENABLED. Default off para evitar I/O
    em pacientes que não usam vault."""
    return os.environ.get("VAULT_MOC_UPDATER_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )


def _resolve_moc_path(moc_name: str) -> Optional[Path]:
    vault = _vault_path()
    moc_dir = vault / _MOC_FOLDER
    if not moc_dir.exists():
        return None
    # tenta exact e suffix .md
    candidates = [
        moc_dir / f"{moc_name}.md",
        moc_dir / moc_name,
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def record_to_moc(
    moc_name: str,
    entry_link: str,
    summary: str = "",
    timestamp: Optional[datetime] = None,
) -> Optional[Path]:
    """Adiciona uma entry no MOC. Idempotente.

    Args:
        moc_name: nome do MOC (ex: "MOC - Aprendizados"). Suffixo .md opcional.
        entry_link: wiki link já formatado (ex: "[[2026-05-29-prometheus-learnings]]").
        summary: 1-line description que aparece após o link.
        timestamp: usa now() se None.

    Returns:
        Path do MOC atualizado, ou None se desabilitado/inacessível.
    """
    if not is_enabled():
        return None

    ts = timestamp or datetime.now(timezone.utc)
    iso_min = ts.strftime("%Y-%m-%d %H:%M")

    path = _resolve_moc_path(moc_name)
    if path is None:
        logger.debug(
            f"[moc_updater] MOC {moc_name!r} não encontrado em "
            f"{_vault_path() / _MOC_FOLDER}"
        )
        return None

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug(f"[moc_updater] read failed: {exc}")
        return None

    # Constrói nova entry
    suffix = f" — {summary}" if summary else ""
    new_line = f"- `{iso_min}` {entry_link}{suffix}"

    # Idempotente: skip se entry exata já está lá
    if entry_link in content and iso_min in content:
        return path

    # Constrói/atualiza seção
    section_re = re.compile(
        rf"({re.escape(_SECTION_HEADER)}.*?)(?=\n##\s|\Z)",
        re.DOTALL,
    )
    m = section_re.search(content)

    if m:
        # Section exists — append within
        section_body = m.group(1)
        lines = section_body.splitlines()
        # Entries existentes (linhas que começam com "- `")
        entries = [l for l in lines if l.strip().startswith("- `")]
        # Dedupe por entry_link+timestamp (mantém só a 1ª ocorrência)
        seen = set()
        # Insere nova no topo, depois dedup
        all_entries = [new_line] + entries
        deduped: list[str] = []
        for e in all_entries:
            key = (entry_link, iso_min) if e == new_line else (e[:90],)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(e)
        deduped = deduped[:MAX_ENTRIES]
        # Rebuild seção com header + note + entries
        new_section = (
            f"{_SECTION_HEADER}\n\n"
            f"{_SECTION_NOTE}\n\n"
            + "\n".join(deduped)
            + "\n"
        )
        new_content = content[: m.start()] + new_section + content[m.end():]
    else:
        # Section doesn't exist — append at end
        sep = "" if content.endswith("\n") else "\n"
        new_section = (
            f"{sep}\n---\n\n{_SECTION_HEADER}\n\n"
            f"{_SECTION_NOTE}\n\n{new_line}\n"
        )
        new_content = content + new_section

    try:
        path.write_text(new_content, encoding="utf-8")
        return path
    except OSError as exc:
        logger.debug(f"[moc_updater] write failed: {exc}")
        return None
