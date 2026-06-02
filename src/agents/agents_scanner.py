"""
src/agents/agents_scanner.py
==============================
AgentsScanner — Continuous Improvement Department, agents-vertical scanner.

Read-only, fail-silent auditor focado nos agentes em ``src/agents/``.
Detecta padrões problemáticos por inspeção estática + métricas SQLite:

  • **God-files** — agente > 1500 linhas (limite IDS) ou > 2000 (alto risco)
  • **Bare except** — `except Exception` ou `except:` sem typing específico
  • **TODO/FIXME inline** — débito técnico explícito no código
  • **Sem BaseAgent** — agente que não herda do contrato canônico
  • **Sem persist** — agente que muta estado mas só em RAM (sem write_text)
  • **Sem testes** — agente sem arquivo `tests/test_<agent>.py`
  • **Agentes com low win_rate** — quando agent_memories tem amostra suficiente

Devolve ``list[ImprovementProposal]`` compatível com o council Mekka.
Não escreve em lugar nenhum — read-only. Fail-silent.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.agents.beast import ImprovementProposal

logger = logging.getLogger("mekka.agents_scanner")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parents[2]
_AGENTS_DIR = _REPO / "src" / "agents"
_TESTS_DIR = _REPO / "tests"
_DB_PATH = _REPO / "data" / "mekka_trading.db"

# Limites IDS — alinhados com `30 - Resources/Guia de Manutenção do Segundo Cérebro`
_FILE_LINES_WARN = 1500
_FILE_LINES_CRIT = 2000
_FILE_LINES_HUGE = 4000

# Skip files não-agentes (helpers internos, base, modulos auxiliares).
_NON_AGENT_FILES = {
    "__init__.py",
    "base.py",
    "llm_client.py",
}

# Min sample size pra considerar win_rate confiável.
_MIN_MEMORIES_FOR_WIN_RATE = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _AgentFile:
    name: str            # ex: "iron_man"
    path: Path
    rel: str             # ex: "src/agents/iron_man.py"
    line_count: int
    text: str            # conteúdo
    has_base_agent: bool


def _iter_agents() -> list[_AgentFile]:
    """Lista todos os arquivos *.py em src/agents/ exceto helpers."""
    out: list[_AgentFile] = []
    if not _AGENTS_DIR.exists():
        return out
    for p in sorted(_AGENTS_DIR.glob("*.py")):
        if p.name in _NON_AGENT_FILES:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        out.append(_AgentFile(
            name=p.stem,
            path=p,
            rel=str(p.relative_to(_REPO)),
            line_count=text.count("\n") + 1,
            text=text,
            has_base_agent=("BaseAgent" in text and "class " in text),
        ))
    return out


def _has_test(agent_name: str) -> bool:
    """True se ``tests/test_<agent>.py`` existe."""
    if not _TESTS_DIR.exists():
        return False
    candidates = [
        _TESTS_DIR / f"test_{agent_name}.py",
        _TESTS_DIR / "unit" / f"test_{agent_name}.py",
        _TESTS_DIR / "integration" / f"test_{agent_name}.py",
    ]
    return any(c.exists() for c in candidates)


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


def _detect_god_files(agents: list[_AgentFile]) -> list[ImprovementProposal]:
    out: list[ImprovementProposal] = []
    for a in agents:
        if a.line_count < _FILE_LINES_WARN:
            continue
        if a.line_count >= _FILE_LINES_HUGE:
            impact = "HIGH"
            desc = (
                f"`{a.rel}` tem **{a.line_count} linhas** — muito acima do "
                f"limite saudável de {_FILE_LINES_WARN}. Concentra risco, "
                "dificulta revisão e degrada testabilidade. Quebrar em módulos "
                "coesos por responsabilidade."
            )
        elif a.line_count >= _FILE_LINES_CRIT:
            impact = "MEDIUM"
            desc = (
                f"`{a.rel}` tem {a.line_count} linhas (acima de "
                f"{_FILE_LINES_CRIT}). Considere extrair responsabilidades."
            )
        else:
            impact = "LOW"
            desc = (
                f"`{a.rel}` tem {a.line_count} linhas (acima do warn "
                f"{_FILE_LINES_WARN}). Monitorar crescimento."
            )
        out.append(ImprovementProposal(
            title=f"Refatorar {a.name}.py ({a.line_count} linhas)",
            description=desc,
            impact=impact,
            area="agents",
            evidence=f"{a.rel}: {a.line_count} linhas "
                     f"(limite {_FILE_LINES_WARN}, enorme ≥{_FILE_LINES_HUGE}).",
            suggested_story=f"Quebrar `{a.name}.py` em módulos menores",
        ))
    return out


_BARE_EXCEPT_RE = re.compile(r"^\s*except\s+Exception\s*(?:as\s+\w+)?\s*:(?!\s*#\s*noqa)",
                             re.MULTILINE)
_TRULY_BARE_RE = re.compile(r"^\s*except\s*:(?!\s*#\s*noqa)", re.MULTILINE)


def _detect_bare_excepts(agents: list[_AgentFile]) -> list[ImprovementProposal]:
    out: list[ImprovementProposal] = []
    for a in agents:
        bare = len(_TRULY_BARE_RE.findall(a.text))
        broad = len(_BARE_EXCEPT_RE.findall(a.text))
        total = bare + broad
        if total < 5:
            continue  # poucos é aceitável (alguns agentes precisam ser robustos)
        out.append(ImprovementProposal(
            title=f"Reduzir captura genérica de exceção em {a.name}.py",
            description=(
                f"`{a.rel}` tem **{total} `except Exception`** "
                f"(sendo {bare} truly-bare). Captura genérica dificulta "
                "diagnóstico — substituir por tipos específicos onde possível, "
                "marcar `# noqa: BLE001` onde o try-broad é intencional."
            ),
            impact="LOW",
            area="agents",
            evidence=f"{a.rel}: {bare} bare + {broad} broad except = {total}",
            suggested_story=f"Tipar exceções em `{a.name}.py`",
        ))
    return out


_TODO_RE = re.compile(r"^\s*#\s*(TODO|FIXME|XXX|HACK)[\s:]+(.+)$",
                      re.IGNORECASE | re.MULTILINE)


def _detect_inline_todos(agents: list[_AgentFile]) -> list[ImprovementProposal]:
    out: list[ImprovementProposal] = []
    for a in agents:
        matches = _TODO_RE.findall(a.text)
        if len(matches) < 3:
            continue  # 1-2 todos é normal; >=3 começa a virar débito acumulado
        sample = matches[0]
        out.append(ImprovementProposal(
            title=f"Endereçar {len(matches)} TODOs/FIXMEs em {a.name}.py",
            description=(
                f"`{a.rel}` tem **{len(matches)} marcações TODO/FIXME** "
                "inline. Cada uma é débito acumulado que ninguém endereçou. "
                f"Primeiro exemplo: *\"{sample[0]}: {sample[1].strip()[:100]}\"*."
            ),
            impact="LOW",
            area="agents",
            evidence=f"{a.rel}: {len(matches)} marcações inline detectadas",
            suggested_story=f"Triar e resolver TODOs em `{a.name}.py`",
        ))
    return out


def _detect_missing_tests(agents: list[_AgentFile]) -> list[ImprovementProposal]:
    out: list[ImprovementProposal] = []
    missing: list[_AgentFile] = []
    for a in agents:
        if not _has_test(a.name):
            missing.append(a)
    if not missing:
        return out
    # Agrega em UMA proposal (não inundar o council com 1 por agente).
    names = ", ".join(f"`{a.name}.py`" for a in missing[:8])
    if len(missing) > 8:
        names += f", … (+{len(missing) - 8} outros)"
    out.append(ImprovementProposal(
        title=f"Cobertura de testes: {len(missing)} agentes sem `tests/test_*.py`",
        description=(
            f"{len(missing)} agentes não têm arquivo de teste correspondente. "
            f"Faltam: {names}. Cada agente sem teste é risco silencioso — "
            "regressão só aparece em produção."
        ),
        impact="MEDIUM" if len(missing) >= 5 else "LOW",
        area="agents",
        evidence=f"{len(missing)} agentes em src/agents/ sem teste em tests/",
        suggested_story="Adicionar coverage mínimo aos agentes órfãos",
    ))
    return out


def _detect_no_base_agent(agents: list[_AgentFile]) -> list[ImprovementProposal]:
    out: list[ImprovementProposal] = []
    orphan = [a for a in agents if not a.has_base_agent
              and a.name not in ("__init__", "base")]
    if not orphan:
        return out
    # Filtrar serviços que parecem helpers (não-Agent)
    real_orphans = []
    for a in orphan:
        # Heurística: tem `class Xxx(BaseAgent[` → tem; senão, talvez não seja agente
        if re.search(r"class\s+\w+\s*\(\s*\w*Agent", a.text):
            real_orphans.append(a)
    if not real_orphans:
        return out
    names = ", ".join(f"`{a.name}`" for a in real_orphans)
    out.append(ImprovementProposal(
        title=f"Agentes fora do contrato BaseAgent ({len(real_orphans)})",
        description=(
            f"Agentes que parecem herdar Agent mas não BaseAgent: {names}. "
            "Padronizar para o contrato canônico ajuda observabilidade "
            "(timing, logging, AgentError uniformes)."
        ),
        impact="LOW",
        area="agents",
        evidence=f"{len(real_orphans)} agentes sem `BaseAgent[T]`",
        suggested_story="Migrar agentes órfãos para BaseAgent",
    ))
    return out


def _detect_low_win_rate() -> list[ImprovementProposal]:
    """
    Cruza ``agent_memories`` para detectar combinações
    (symbol, trend, action) com win_rate baixo + amostra suficiente.
    """
    out: list[ImprovementProposal] = []
    if not _DB_PATH.exists():
        return out
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        try:
            cur = conn.execute("""
                SELECT symbol, trend, action,
                       SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) wins,
                       SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) losses,
                       COUNT(*) total
                FROM agent_memories
                WHERE outcome IN ('WIN','LOSS')
                GROUP BY symbol, trend, action
                HAVING total >= ?
            """, (_MIN_MEMORIES_FOR_WIN_RATE,))
            for row in cur.fetchall():
                sym, trend, action, wins, losses, total = row
                if total == 0:
                    continue
                win_rate = wins / total
                if win_rate >= 0.45:
                    continue  # acima de 45% não é alarmante
                out.append(ImprovementProposal(
                    title=f"Win-rate baixo: {sym} {trend} {action} ({win_rate:.0%})",
                    description=(
                        f"Combinação `{sym}/{trend}/{action}` tem win-rate de "
                        f"**{win_rate:.0%}** ({wins}W/{losses}L em {total} signals). "
                        "Vale revisar critério de entrada do Vision ou suprimir "
                        "essa combinação via filtro do Batman."
                    ),
                    impact="MEDIUM" if total >= 30 else "LOW",
                    area="agents",
                    evidence=f"agent_memories: {wins}W/{losses}L em {total} signals",
                    suggested_story=f"Investigar perda sistemática em {sym}/{trend}",
                ))
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.debug(f"[agents_scanner] sqlite error: {exc}")
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_proposals(max_proposals: int = 20) -> list[ImprovementProposal]:
    """
    Roda todos os detectors, retorna até ``max_proposals`` propostas
    priorizadas por impact (HIGH > MEDIUM > LOW). Fail-silent.
    """
    try:
        agents = _iter_agents()
        proposals: list[ImprovementProposal] = []
        proposals.extend(_detect_god_files(agents))
        proposals.extend(_detect_bare_excepts(agents))
        proposals.extend(_detect_inline_todos(agents))
        proposals.extend(_detect_missing_tests(agents))
        proposals.extend(_detect_no_base_agent(agents))
        proposals.extend(_detect_low_win_rate())
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[agents_scanner] scan failed: {exc}")
        return []

    # Priorizar por impact, devolver top N
    impact_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    proposals.sort(key=lambda p: impact_rank.get(p.impact, 3))

    logger.info(
        f"[agents_scanner] {len(agents)} agentes inspecionados → "
        f"{len(proposals)} proposals (top {max_proposals} retornadas)"
    )
    return proposals[:max_proposals]


def summary() -> dict:
    """Métricas leves para o dashboard."""
    agents = _iter_agents()
    return {
        "agents_inspected": len(agents),
        "agents_dir": str(_AGENTS_DIR),
        "tests_dir_exists": _TESTS_DIR.exists(),
        "db_available": _DB_PATH.exists(),
        "max_proposals_cap": 20,
    }
