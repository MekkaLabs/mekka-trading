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


# ---------------------------------------------------------------------------
# Prometheus bridge — opt-in, NUNCA bloqueia o trading loop.
# ---------------------------------------------------------------------------
#
# A função abaixo é uma "ponte" para o módulo `src.prompt_engineering`
# (agente Prometheus). Se o módulo estiver disponível E o catálogo estiver
# habilitado via `PROMETHEUS_CATALOG_ENABLED=true`, registra o prompt no
# catálogo persistente. Senão, é no-op silencioso.
#
# Garantias:
# - prompt_version() acima permanece 100% inalterado.
# - Esta função é OPCIONAL e nunca chamada automaticamente.
# - Falha em importar/registrar nunca propaga exceção.
# - Custo zero quando desabilitado (early return).


def register_prompt_for_audit(
    prompt_text: str,
    *,
    name: str | None = None,
    source_hint: str | None = None,
) -> str:
    """
    Registra um prompt para auditoria offline pelo Prometheus.

    Sempre retorna o fingerprint (compatível com prompt_version()).
    O registro no catálogo é best-effort — falha silencia.

    Parameters
    ----------
    prompt_text : str
        Texto do prompt.
    name : str, optional
        Nome canônico no catálogo (ex.: "vision_system_prompt").
    source_hint : str, optional
        Caminho relativo do arquivo de origem (ex.: "src/agents/vision.py").

    Returns
    -------
    str
        Fingerprint 16-char hex (mesmo que prompt_version()).
    """
    fp = prompt_version(prompt_text)

    # Early return se Prometheus desabilitado — custo zero no trading loop.
    import os
    if os.environ.get("PROMETHEUS_CATALOG_ENABLED", "false").lower() not in (
        "1", "true", "yes", "on"
    ):
        return fp

    try:
        # Import lazy: nunca falha o arquivo se o módulo não existir.
        from src.prompt_engineering import Prometheus
        from src.prompt_engineering.models import ExtractedPrompt

        prompt = ExtractedPrompt(
            source_file=source_hint or "runtime",
            variable_name=name or "anonymous_prompt",
            line_number=0,
            content=prompt_text,
            fingerprint=fp,
            detected_role="",
        )
        p = Prometheus()
        sc = p.audit(prompt)
        p.register(prompt, scorecard=sc, name=name)
    except Exception as exc:  # noqa: BLE001 — registro nunca pode quebrar trading
        # Log de DEBUG apenas (loguru não é mandatório aqui)
        try:
            from loguru import logger
            logger.debug(f"[prompt_registry] Prometheus register no-op: {exc}")
        except ImportError:
            pass

    return fp
