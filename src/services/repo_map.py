"""
src/services/repo_map.py
==========================
Story 160 — MekkaRepoMap: Compact Codebase Symbol Index for LLM Context.

Inspirado em:
  aider/repomap.py — "Aider builds a tree-sitter based repository map to
  give the LLM a compact overview of the codebase. This dramatically improves
  the LLM's ability to understand the structure and find relevant code."

  "The repo map shows the LLM which files exist, what classes and functions
  they contain, and their call signatures — without overwhelming the context
  window with full source code."

  "Aider uses tree-sitter to parse and extract symbols from every source file."

Adaptação para Mekka Trading:
  Sem dependência de tree-sitter — usa regex para extrair símbolos Python.
  Gera um mapa compacto de `arquivo → [Classe, função, async_fn]` para injetar
  no prompt do Vision, dando ao LLM contexto sobre quais agentes existem,
  quais serviços estão disponíveis e quais modelos são usados.

Problema resolvido:
  Vision e VisionMoA não sabem quais agentes existem no pipeline.
  O prompt atual descreve o pipeline em texto livre — o LLM pode alucinar
  agentes inexistentes ou ignorar os existentes.
  Com MekkaRepoMap, o Vision recebe: "batman.py: [Batman, analyze, _check_*]"
  e pode raciocinar com base em nomes reais de classes e funções.

Design:
  MekkaRepoMap — scanner de símbolos Python via regex
  RepoSymbol — dataclass de um símbolo extraído (nome, tipo, arquivo)
  FileSymbols — mapa de um arquivo (path → symbols)
  get_repo_map() — singleton com cache TTL configurável
  to_prompt_section() — pronto para BoundedOutput.bound_prompt_section()

Uso:
    from src.services.repo_map import get_repo_map

    rmap = get_repo_map()
    rmap.scan()  # escaneia src/

    # Injetar contexto no Vision
    prompt += rmap.to_prompt_section(max_chars=2000)

    # Mapa só dos agentes (para Batman gate de validação)
    agents_map = rmap.get_agent_map()
    # → {"batman.py": ["Batman", "analyze", "_check_geometry"], ...}
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Padrões regex para extração de símbolos Python
# ---------------------------------------------------------------------------

_CLASS_RE = re.compile(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
_DEF_RE = re.compile(
    r"^(?:    |\t)?(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE
)
_TOP_DEF_RE = re.compile(r"^(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)

# Símbolos a ignorar (dunder + genéricos)
_IGNORE_SYMBOLS: frozenset[str] = frozenset({
    "__init__", "__repr__", "__str__", "__eq__", "__hash__", "__len__",
    "__iter__", "__next__", "__enter__", "__exit__", "__call__",
    "__getattr__", "__setattr__", "__delattr__", "__contains__",
    "__aenter__", "__aexit__", "__aiter__", "__anext__",
    "test_", "setUp", "tearDown",
})


# ---------------------------------------------------------------------------
# RepoSymbol e FileSymbols
# ---------------------------------------------------------------------------

@dataclass
class RepoSymbol:
    """Um símbolo extraído de um arquivo Python."""
    name: str
    kind: str  # "class" | "def" | "async_def"
    line: int = 0


@dataclass
class FileSymbols:
    """Símbolos de um arquivo."""
    path: str           # relativo ao root
    symbols: list[RepoSymbol] = field(default_factory=list)

    @property
    def class_names(self) -> list[str]:
        return [s.name for s in self.symbols if s.kind == "class"]

    @property
    def function_names(self) -> list[str]:
        return [s.name for s in self.symbols if s.kind in ("def", "async_def")]

    def compact(self) -> str:
        """Formato compacto: `agents/batman.py: Batman, analyze, _check_leverage`"""
        names = [s.name for s in self.symbols if s.name not in _IGNORE_SYMBOLS]
        if not names:
            return ""
        return f"{self.path}: {', '.join(names[:30])}"  # cap a 30 símbolos por arquivo


# ---------------------------------------------------------------------------
# MekkaRepoMap
# ---------------------------------------------------------------------------

class MekkaRepoMap:
    """
    Scanner de símbolos Python para geração de repo map compacto.

    Inspirado no aider/repomap.py (Aider-AI/aider):
    - Sem tree-sitter — usa regex (sem dependência nova)
    - Cache com TTL configurável (default 300s)
    - Filtrável por subdiretório (agents/, services/, models/)
    - to_prompt_section() pronto para injeção no Vision
    - Fail-silent: erros de parse nunca interrompem o ciclo
    """

    _DEFAULT_TTL_S = 300  # 5 minutos
    _DEFAULT_DIRS = ("agents", "services", "models", "config")
    _SKIP_PATTERNS = ("__pycache__", ".pyc", "test_", "conftest")

    def __init__(
        self,
        root: str = ".",
        scan_dirs: tuple[str, ...] = _DEFAULT_DIRS,
        cache_ttl_s: float = _DEFAULT_TTL_S,
        max_files: int = 200,
    ) -> None:
        self._root = Path(root)
        self._scan_dirs = scan_dirs
        self._cache_ttl_s = cache_ttl_s
        self._max_files = max_files
        self._files: dict[str, FileSymbols] = {}
        self._last_scan: float = 0.0
        self._total_symbols: int = 0

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    def scan(self, force: bool = False) -> int:
        """
        Varre os diretórios configurados e extrai símbolos.

        Returns:
            Número de arquivos processados.
        """
        try:
            now = time.monotonic()
            if not force and (now - self._last_scan) < self._cache_ttl_s and self._files:
                return len(self._files)

            self._files = {}
            count = 0
            sym_count = 0

            for dir_name in self._scan_dirs:
                target = self._root / "src" / dir_name
                if not target.exists():
                    continue
                for py_file in sorted(target.rglob("*.py")):
                    if count >= self._max_files:
                        break
                    if any(p in str(py_file) for p in self._SKIP_PATTERNS):
                        continue
                    try:
                        rel = str(py_file.relative_to(self._root))
                        fs = self._parse_file(py_file, rel)
                        if fs.symbols:
                            self._files[rel] = fs
                            sym_count += len(fs.symbols)
                            count += 1
                    except Exception:  # noqa: BLE001
                        pass  # arquivo ilegível → skip

            self._last_scan = now
            self._total_symbols = sym_count
            logger.debug(
                f"[MekkaRepoMap] Scan: {count} files, {sym_count} symbols "
                f"in {time.monotonic() - now:.3f}s"
            )
            return count
        except Exception:  # noqa: BLE001
            return 0

    def _parse_file(self, path: Path, rel_path: str) -> FileSymbols:
        """Extrai classes e funções de um arquivo Python via regex."""
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            symbols: list[RepoSymbol] = []

            # Classes (top-level e nested)
            for m in _CLASS_RE.finditer(source):
                name = m.group(1)
                if not name.startswith("_") or name.startswith("__") is False:
                    line = source[:m.start()].count("\n") + 1
                    symbols.append(RepoSymbol(name=name, kind="class", line=line))

            # Funções top-level
            for m in _TOP_DEF_RE.finditer(source):
                name = m.group(1)
                if name not in _IGNORE_SYMBOLS and not name.startswith("__"):
                    line = source[:m.start()].count("\n") + 1
                    kind = "async_def" if "async" in source[m.start():m.start() + 10] else "def"
                    symbols.append(RepoSymbol(name=name, kind=kind, line=line))

            # Ordenar por linha
            symbols.sort(key=lambda s: s.line)
            # Deduplicar mantendo primeira ocorrência
            seen: set[str] = set()
            deduped: list[RepoSymbol] = []
            for s in symbols:
                if s.name not in seen:
                    seen.add(s.name)
                    deduped.append(s)

            return FileSymbols(path=rel_path, symbols=deduped)
        except Exception:  # noqa: BLE001
            return FileSymbols(path=rel_path)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_all_files(self) -> dict[str, FileSymbols]:
        """Retorna todos os arquivos escaneados."""
        try:
            if not self._files:
                self.scan()
            return dict(self._files)
        except Exception:  # noqa: BLE001
            return {}

    def get_agent_map(self) -> dict[str, list[str]]:
        """
        Retorna mapa só dos agentes (src/agents/).

        Inspirado em: Aider usa o repo map para focar em arquivos relevantes
        sem incluir toda a codebase no contexto.
        """
        try:
            if not self._files:
                self.scan()
            result: dict[str, list[str]] = {}
            for path, fs in self._files.items():
                if "agents/" in path:
                    names = [s.name for s in fs.symbols if s.name not in _IGNORE_SYMBOLS]
                    if names:
                        result[path] = names
            return result
        except Exception:  # noqa: BLE001
            return {}

    def get_service_map(self) -> dict[str, list[str]]:
        """Retorna mapa só dos serviços (src/services/)."""
        try:
            if not self._files:
                self.scan()
            result: dict[str, list[str]] = {}
            for path, fs in self._files.items():
                if "services/" in path:
                    names = [s.name for s in fs.symbols if s.name not in _IGNORE_SYMBOLS]
                    if names:
                        result[path] = names
            return result
        except Exception:  # noqa: BLE001
            return {}

    def find_symbol(self, symbol_name: str) -> list[str]:
        """
        Busca um símbolo pelo nome e retorna os arquivos que o contêm.

        Inspirado no aider/repomap.py symbol search —
        "find which file defines a given class or function".
        """
        try:
            if not self._files:
                self.scan()
            results = []
            for path, fs in self._files.items():
                for sym in fs.symbols:
                    if sym.name == symbol_name or symbol_name.lower() in sym.name.lower():
                        results.append(path)
                        break
            return results
        except Exception:  # noqa: BLE001
            return []

    # ------------------------------------------------------------------
    # Formatação para prompt LLM
    # ------------------------------------------------------------------

    def to_compact_string(
        self,
        dirs: Optional[tuple[str, ...]] = None,
        max_files: int = 30,
    ) -> str:
        """
        Formata o mapa como string compacta para injeção em prompt.

        Formato Aider:
          src/agents/batman.py: Batman, analyze, _check_geometry
          src/services/bounded_output.py: BoundedOutput, truncate_str, truncate_list
          ...

        Args:
            dirs: filtro de subdiretório (None = todos)
            max_files: limita número de arquivos na saída
        """
        try:
            if not self._files:
                self.scan()

            lines: list[str] = []
            for path, fs in list(self._files.items())[:max_files]:
                if dirs and not any(d in path for d in dirs):
                    continue
                compact = fs.compact()
                if compact:
                    lines.append(compact)

            return "\n".join(lines)
        except Exception:  # noqa: BLE001
            return ""

    def to_prompt_section(
        self,
        max_chars: int = 2000,
        dirs: Optional[tuple[str, ...]] = None,
    ) -> str:
        """
        Retorna seção de prompt pronta para injeção no Vision.

        Padrão Aider windowed viewer + bounded output (Story 157):
          ## Mekka Codebase Map
          ----------------------------------------
          src/agents/batman.py: Batman, analyze
          ...
          [N files, M symbols total]

        Uso no Vision:
            prompt += repo_map.to_prompt_section(max_chars=2000)
        """
        try:
            content = self.to_compact_string(dirs=dirs)
            if not content:
                return ""

            total_files = len(self._files)
            footer = f"\n[{total_files} files | {self._total_symbols} symbols total]"
            # Truncar conteúdo deixando espaço para footer
            max_content = max_chars - len(footer) - 80  # header overhead
            if len(content) > max_content:
                content = content[:max_content] + "\n... [truncated]"

            sep = "-" * 40
            return (
                f"\n{sep}\n## Mekka Codebase Map\n{sep}\n"
                f"{content}"
                f"{footer}\n"
            )
        except Exception:  # noqa: BLE001
            return ""

    def summary(self) -> dict[str, Any]:
        """Resumo para GET /api/repo-map."""
        try:
            if not self._files:
                self.scan()
            by_dir: dict[str, int] = {}
            for path in self._files:
                parts = path.split("/")
                key = parts[1] if len(parts) > 2 else parts[0]
                by_dir[key] = by_dir.get(key, 0) + 1
            return {
                "total_files": len(self._files),
                "total_symbols": self._total_symbols,
                "by_directory": by_dir,
                "last_scan_age_s": round(time.monotonic() - self._last_scan, 1),
                "cache_ttl_s": self._cache_ttl_s,
                "scan_dirs": list(self._scan_dirs),
            }
        except Exception:  # noqa: BLE001
            return {"error": "summary_failed"}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[MekkaRepoMap] = None


def get_repo_map(
    root: str = ".",
    cache_ttl_s: float = MekkaRepoMap._DEFAULT_TTL_S,
) -> MekkaRepoMap:
    """
    Retorna o MekkaRepoMap singleton.

    Parâmetros só têm efeito na primeira chamada.
    Na primeira chamada, escaneia automaticamente.
    """
    global _instance
    if _instance is None:
        _instance = MekkaRepoMap(root=root, cache_ttl_s=cache_ttl_s)
        _instance.scan()
    return _instance


def reset_repo_map() -> None:
    """Reset singleton — usado em testes."""
    global _instance
    _instance = None
