"""
src/agents/ice_man.py
=====================
Ice Man — Continuous Improvement Department, external-research scanner.

The "look outside the system" scanner. Where the other scanners audit the
running system, Ice Man researches the *outside world* for things that should
change inside it. v1 focuses on the highest-signal, lowest-risk external check
for a live trading bot: **dependency freshness**.

  • Key deps installed vs. latest on PyPI (ccxt, pydantic, aiohttp, pandas-ta,
    openai, anthropic). A stale ``ccxt`` means stale exchange-API support — a
    real risk for live execution, so it is weighted HIGH.

Guard-rails (per design §3): research is **read-only** — Ice Man never installs
or changes anything. Every finding is just a proposal for the operator to
decide. Network calls are tightly time-boxed and fail-silent so a slow/blocked
PyPI never stalls the council scan.

(WebSearch/papers and financial-MCP research are future extensions; the running
app process cannot call the Claude Code WebSearch tool, so v1 uses direct,
auditable HTTP to PyPI.)
"""

from __future__ import annotations

import asyncio
import logging
from importlib import metadata as _md

from src.agents.beast import ImprovementProposal

logger = logging.getLogger("mekka.ice_man")

# Deps that matter most for a live trading bot. ccxt first — it tracks exchange
# APIs and moves fast; being behind can break orders/market data on mainnet.
_WATCHED = ("ccxt", "pydantic", "aiohttp", "pandas-ta", "openai", "anthropic")
_CRITICAL = {"ccxt"}  # outdated → HIGH (exchange API drift)
_PYPI_URL = "https://pypi.org/pypi/{pkg}/json"
# GitHub repos to watch for breaking-change/security release notes.
_GITHUB_REPOS = {
    "ccxt": "ccxt/ccxt",
    "pydantic": "pydantic/pydantic",
    "aiohttp": "aio-libs/aiohttp",
}
_GITHUB_RELEASES_URL = "https://api.github.com/repos/{repo}/releases?per_page=5"
_BREAKING_HINTS = ("breaking", "security", "deprecat", "removed", "vulnerab", "cve")
_HTTP_TIMEOUT_S = 8.0
_OVERALL_TIMEOUT_S = 14.0


def _installed_version(pkg: str) -> str | None:
    try:
        return _md.version(pkg)
    except Exception:  # noqa: BLE001  (PackageNotFoundError etc.)
        return None


def _parse_ver(v: str) -> tuple[int, ...]:
    out: list[int] = []
    for part in (v or "").split(".")[:4]:
        num = "".join(ch for ch in part if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out) or (0,)


class IceMan:
    """External-research scanner. ``proposals = await IceMan().scan()``."""

    async def scan(self) -> list[ImprovementProposal]:
        try:
            return await asyncio.wait_for(self._scan_all(), timeout=_OVERALL_TIMEOUT_S)
        except asyncio.TimeoutError:
            logger.warning("[IceMan] research timed out — skipping this cycle")
            return []
        except Exception as exc:  # noqa: BLE001
            logger.warning("[IceMan] scan failed: %s", exc)
            return []

    async def _scan_all(self) -> list[ImprovementProposal]:
        out: list[ImprovementProposal] = []
        for fn in (self._scan_dependencies, self._scan_github_releases):
            try:
                out.extend(await fn())
            except Exception as exc:  # noqa: BLE001
                logger.warning("[IceMan] %s failed: %s", getattr(fn, "__name__", fn), exc)
        return out

    async def _scan_github_releases(self) -> list[ImprovementProposal]:
        """Check recent GitHub releases of critical deps for breaking/security
        notes. Read-only, fail-silent. Only proposes when the installed version
        is behind AND a recent release mentions breaking/security changes."""
        try:
            import aiohttp  # noqa: WPS433
        except ImportError:
            return []
        out: list[ImprovementProposal] = []
        timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_S)
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "mekka-iceman"}
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as sess:
                for pkg, repo in _GITHUB_REPOS.items():
                    cur = _installed_version(pkg)
                    if not cur:
                        continue
                    try:
                        async with sess.get(_GITHUB_RELEASES_URL.format(repo=repo)) as resp:
                            if resp.status != 200:
                                continue
                            releases = await resp.json()
                    except Exception:  # noqa: BLE001
                        continue
                    if not isinstance(releases, list):
                        continue
                    cur_t = _parse_ver(cur)
                    flagged: list[str] = []
                    for rel in releases[:5]:
                        tag = str((rel or {}).get("tag_name") or "").lstrip("v")
                        body = str((rel or {}).get("body") or "").lower()
                        if not tag or _parse_ver(tag) <= cur_t:
                            continue  # not newer than installed
                        if any(h in body for h in _BREAKING_HINTS):
                            flagged.append(tag)
                    if flagged:
                        out.append(ImprovementProposal(
                            title=f"{pkg}: releases novas com breaking/segurança ({', '.join(flagged[:3])})",
                            description=(
                                f"Há releases de `{pkg}` mais novas que a instalada ({cur}) cujas "
                                "notas mencionam breaking changes/segurança/deprecação. Revisar o "
                                "changelog antes de atualizar e validar em testnet."
                            ),
                            impact="MEDIUM",
                            area="research",
                            evidence=f"github.com/{repo}/releases — versões {', '.join(flagged[:5])} > instalada {cur}.",
                            suggested_story=f"Revisar breaking changes de {pkg} e atualizar",
                        ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[IceMan] GitHub releases fetch failed: %s", exc)
        return out

    async def _scan_dependencies(self) -> list[ImprovementProposal]:
        try:
            import aiohttp  # noqa: WPS433
        except ImportError:
            return []

        installed = {p: _installed_version(p) for p in _WATCHED}
        present = {p: v for p, v in installed.items() if v}
        if not present:
            return []

        latest: dict[str, str] = {}
        timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_S)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                async def _fetch(pkg: str) -> None:
                    try:
                        async with sess.get(_PYPI_URL.format(pkg=pkg)) as resp:
                            if resp.status != 200:
                                return
                            data = await resp.json()
                            v = (data.get("info") or {}).get("version")
                            if v:
                                latest[pkg] = v
                    except Exception:  # noqa: BLE001
                        return
                await asyncio.gather(*(_fetch(p) for p in present))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[IceMan] PyPI fetch failed: %s", exc)
            return []

        out: list[ImprovementProposal] = []
        outdated: list[str] = []
        for pkg, cur in present.items():
            new = latest.get(pkg)
            if not new or new == cur:
                continue
            cur_t, new_t = _parse_ver(cur), _parse_ver(new)
            if new_t <= cur_t:
                continue  # installed is same/newer (pre-release etc.)
            major_behind = new_t and cur_t and new_t[0] > cur_t[0]
            outdated.append(f"{pkg} {cur}→{new}")

            if pkg in _CRITICAL:
                out.append(ImprovementProposal(
                    title=f"Atualizar {pkg} {cur} → {new} (API de exchange)",
                    description=(
                        f"`{pkg}` está em {cur}; a última no PyPI é {new}. Para um bot "
                        "que opera ao vivo, um ccxt desatualizado pode ter suporte velho "
                        "a endpoints/símbolos das exchanges (Binance/Bybit). Revisar "
                        "changelog por breaking changes e atualizar com teste em testnet."
                    ),
                    impact="HIGH" if major_behind else "MEDIUM",
                    area="research",
                    evidence=f"PyPI: {pkg} instalado {cur}, latest {new}.",
                    suggested_story=f"Atualizar {pkg} para {new} (validar em testnet)",
                ))

        # Bundle non-critical outdated deps into one proposal (less noise).
        non_critical = [s for s in outdated if not s.split()[0] in _CRITICAL]
        if non_critical:
            out.append(ImprovementProposal(
                title=f"Dependências desatualizadas ({len(non_critical)})",
                description=(
                    "Bibliotecas do stack atrás da última versão do PyPI. Atualizar em "
                    "lote (com teste) reduz dívida e captura correções de segurança/bugs."
                ),
                impact="LOW",
                area="research",
                evidence="; ".join(non_critical[:8]),
                suggested_story="Atualizar dependências do stack (com testes)",
            ))
        return out
