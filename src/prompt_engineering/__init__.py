"""
src/prompt_engineering/
=======================
Prometheus — agente de engenharia de prompts do Mekka.

Opera EXCLUSIVAMENTE offline / via CLI. NUNCA participa do loop de
trading. NUNCA chama LLM em runtime. O auditor é 100% determinístico
(regras Python sobre texto).

Submodules
----------
- models     : Pydantic models (PromptRecord, Scorecard, AuditDimension)
- extractor  : extrai prompts hardcoded de arquivos Python
- auditor    : aplica framework P.R.O.M.P.T. e produz scorecard
- catalog    : persistência JSON em data/prompts/catalog.json
- prometheus : orchestrator de alto nível
"""

from src.prompt_engineering.adapter import Provider, adapt, adapt_to_anthropic, adapt_to_openai
from src.prompt_engineering.models import (
    AuditDimension,
    PromptRecord,
    Scorecard,
    ExtractedPrompt,
)
from src.prompt_engineering.prometheus import Prometheus

__all__ = [
    "AuditDimension",
    "PromptRecord",
    "Scorecard",
    "ExtractedPrompt",
    "Prometheus",
    "Provider",
    "adapt",
    "adapt_to_anthropic",
    "adapt_to_openai",
]
