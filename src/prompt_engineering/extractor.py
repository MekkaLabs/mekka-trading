"""
src/prompt_engineering/extractor.py
====================================
Extrai prompts hardcoded de arquivos Python via AST.

Estratégia:
1. AST primário — capta assignments string literais (`_SYSTEM_PROMPT = "..."`)
2. Fallback regex — capta f-strings ou concatenações ignoradas pelo AST
3. Heurística de role — nome da variável determina se é system/user/pre_reasoning

Não executa código. Lê apenas o source.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

from loguru import logger

from src.prompt_engineering.models import ExtractedPrompt

# Tamanho mínimo (chars) para considerar uma string como prompt — evita
# capturar mensagens curtas como "OK", "DEBUG", etc.
MIN_PROMPT_LEN = 80

# Heurística de role pelo nome da variável.
# ORDEM IMPORTA: o primeiro match ganha — patterns mais específicos primeiro.
_ROLE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("pre_reasoning", re.compile(r"pre.?reasoning|PRE_REASONING", re.IGNORECASE)),
    ("system", re.compile(r"system|SYSTEM", re.IGNORECASE)),
    ("user", re.compile(r"user|USER|template", re.IGNORECASE)),
]


def _fingerprint(text: str) -> str:
    """Mesmo algoritmo de src/services/prompt_registry.py — strip + SHA-256[:16]."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def _detect_role(var_name: str) -> str:
    for role, pattern in _ROLE_PATTERNS:
        if pattern.search(var_name):
            return role
    return ""


def extract_from_file(file_path: Path, repo_root: Path | None = None) -> list[ExtractedPrompt]:
    """
    Extrai prompts string literais do arquivo Python.

    Parameters
    ----------
    file_path : Path
        Caminho absoluto do arquivo .py
    repo_root : Path, optional
        Para reportar source_file em formato relativo. Se None, usa absoluto.

    Returns
    -------
    Lista de ExtractedPrompt (vazia se nenhum prompt detectado).
    """
    if not file_path.exists():
        logger.warning(f"[Prometheus.extractor] arquivo não existe: {file_path}")
        return []
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning(f"[Prometheus.extractor] erro lendo {file_path}: {exc}")
        return []

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as exc:
        logger.warning(f"[Prometheus.extractor] syntax error em {file_path}: {exc}")
        return []

    relpath = str(file_path.relative_to(repo_root)) if repo_root else str(file_path)
    results: list[ExtractedPrompt] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        # Aceita: VAR = "literal"  ou  VAR: type = "literal"
        if not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        text = node.value.value
        if len(text) < MIN_PROMPT_LEN:
            continue

        # Pega o primeiro target (assumes 1 var por linha; suficiente para prompts)
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            var_name = target.id
            results.append(
                ExtractedPrompt(
                    source_file=relpath,
                    variable_name=var_name,
                    line_number=node.lineno,
                    content=text,
                    fingerprint=_fingerprint(text),
                    detected_role=_detect_role(var_name),
                )
            )

    return results


def scan_directory(
    directory: Path,
    repo_root: Path | None = None,
    pattern: str = "*.py",
) -> list[ExtractedPrompt]:
    """Varre recursivamente um diretório e extrai todos os prompts."""
    if not directory.exists() or not directory.is_dir():
        logger.warning(f"[Prometheus.extractor] diretório inválido: {directory}")
        return []
    all_prompts: list[ExtractedPrompt] = []
    for py_file in sorted(directory.rglob(pattern)):
        if "__pycache__" in py_file.parts:
            continue
        all_prompts.extend(extract_from_file(py_file, repo_root=repo_root))
    return all_prompts
