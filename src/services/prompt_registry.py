"""
src/services/prompt_registry.py
================================
Story 143 — Prompt Versioning.

Fornece um fingerprint SHA-256 (16-char hex prefix) para qualquer
string de prompt, permitindo rastrear mudanças de prompt no audit log
sem armazenar o texto completo.

Uso
---
    from src.services.prompt_registry import prompt_version

    pv = prompt_version(my_system_prompt)
    # → "a3f2c8d914e60b7f"

O `prompt_version` é então passado para o log de auditoria:
    payload = {"prompt_version": pv, ...}

Arquitetura
-----------
- Stateless — apenas SHA-256 do conteúdo normalizado (strip + encode UTF-8).
- Normalização: strip() remove espaços/newlines externos; o hash muda
  somente quando o conteúdo real do prompt muda.
- 16-char hex prefix = 64 bits de colisão resistance: suficiente para
  identificar versões distintas num sistema de trading single-node.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache


@lru_cache(maxsize=256)
def prompt_version(prompt_text: str) -> str:
    """
    Retorna os primeiros 16 caracteres hexadecimais do SHA-256 do prompt.

    Cacheado via `lru_cache` — prompts idênticos são computados uma
    única vez por sessão. Cache limite de 256 entradas (suficiente para
    todos os system prompts do pipeline).

    Parâmetros
    ----------
    prompt_text : str
        Texto do prompt (system ou user). Será strip()'ado antes do hash.

    Retorna
    -------
    str
        16-char hex string, e.g. "a3f2c8d914e60b7f".
    """
    normalized = prompt_text.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def prompt_version_full(prompt_text: str) -> str:
    """
    Versão completa: 64 caracteres hexadecimais (SHA-256 completo).

    Use quando precisar de garantia máxima de unicidade — por exemplo
    em tests ou em comparações cross-sessão.
    """
    normalized = prompt_text.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
