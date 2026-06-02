"""
src/prompt_engineering/auditor.py
==================================
Auditor determinístico de prompts segundo framework P.R.O.M.P.T.

100% Python — sem chamadas LLM. As regras são heurísticas explícitas
documentadas inline. Quem quiser ajustar pesos/thresholds edita aqui.

4 dimensões × 10 pontos = 40 max.
- CLARITY (P-Purpose, R-Role, O-Output)
- HALLUCINATION_RISK (M-Method anti-alucinação)
- TESTABILITY (T-Test)
- PROMPT_COVERAGE (cobertura geral dos 6 componentes)
"""

from __future__ import annotations

import re

from src.prompt_engineering.models import (
    AuditDimension,
    DimensionScore,
    ExtractedPrompt,
    Scorecard,
)

# ---------------------------------------------------------------------------
# Padrões linguísticos (PT-BR + EN) para detectar componentes P.R.O.M.P.T.
# ---------------------------------------------------------------------------

_ROLE_PATTERNS = re.compile(
    r"\b(você é|voce e|you are|act as|aja como|seu papel|your role|"
    r"persona|identidade)\b",
    re.IGNORECASE,
)
_PURPOSE_PATTERNS = re.compile(
    r"\b(objetivo|goal|purpose|missão|missao|task|tarefa|"
    r"responsável por|responsible for|deve|must|should)\b",
    re.IGNORECASE,
)
_OUTPUT_FORMAT_PATTERNS = re.compile(
    r"\b(json|xml|yaml|markdown|response_format|schema|"
    r"retorne|return|output|formato|format|estrutura|structure)\b",
    re.IGNORECASE,
)
_METHOD_PATTERNS = re.compile(
    r"\b(passo|step|primeiro|first|depois|then|analise|analyze|"
    r"considere|consider|raciocine|reason|workflow|processo|process)\b",
    re.IGNORECASE,
)
_PITFALL_PATTERNS = re.compile(
    r"\b(não|nao|never|nunca|evite|avoid|jamais|don't|do not|"
    r"é proibido|forbidden|prohibited)\b",
    re.IGNORECASE,
)
_TEST_PATTERNS = re.compile(
    r"\b(exemplo|example|aceit|accept|critério|criterion|verificar|verify|"
    r"validar|validate|caso de|test case)\b",
    re.IGNORECASE,
)

# Sinais de risco de alucinação (penalidade)
_VAGUE_PATTERNS = re.compile(
    r"\b(talvez|maybe|possivelmente|possibly|geralmente|generally|"
    r"normalmente|usually|às vezes|sometimes)\b",
    re.IGNORECASE,
)
_HEDGE_INSTRUCTIONS = re.compile(
    r"\b(se possível|if possible|tente|try to|preferencialmente|preferably)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------


def _score_clarity(text: str) -> DimensionScore:
    """Avalia presença explícita de Role + Purpose + Output."""
    findings: list[str] = []
    score = 0

    if _ROLE_PATTERNS.search(text):
        score += 4
    else:
        findings.append("Sem definição explícita de papel (R-Role).")

    if _PURPOSE_PATTERNS.search(text):
        score += 3
    else:
        findings.append("Objetivo (P-Purpose) não declarado claramente.")

    if _OUTPUT_FORMAT_PATTERNS.search(text):
        score += 3
    else:
        findings.append("Formato de saída (O-Output) não especificado.")

    return DimensionScore(
        dimension=AuditDimension.CLARITY,
        score=min(score, 10),
        findings=findings,
    )


def _score_hallucination_risk(text: str) -> DimensionScore:
    """Mais alto = menos risco. 10 = sem risco, 0 = risco alto."""
    findings: list[str] = []
    score = 10  # começa em 10, penaliza

    # Penalidades
    n_vague = len(_VAGUE_PATTERNS.findall(text))
    n_hedge = len(_HEDGE_INSTRUCTIONS.findall(text))
    n_pitfall = len(_PITFALL_PATTERNS.findall(text))

    if n_vague > 3:
        score -= 3
        findings.append(f"Linguagem vaga em excesso ({n_vague} ocorrências de 'talvez/maybe/usually').")
    elif n_vague > 0:
        score -= 1
        findings.append(f"Algumas expressões vagas ({n_vague}).")

    if n_hedge > 2:
        score -= 2
        findings.append(f"Instruções fracas/hesitantes ({n_hedge} 'se possível/tente').")

    # Bonificações: pitfalls explícitos reduzem risco
    if n_pitfall == 0:
        score -= 3
        findings.append("Nenhum pitfall declarado (sem 'nunca/não/evite').")
    elif n_pitfall < 3:
        score -= 1
        findings.append(f"Poucos pitfalls declarados ({n_pitfall}).")

    # Schema strict (JSON, XML) reduz alucinação
    if not re.search(r"\b(json|xml|schema|response_format)\b", text, re.IGNORECASE):
        score -= 1
        findings.append("Sem schema estrito declarado (json/xml/schema).")

    score = max(score, 0)
    if score == 10:
        findings.append("OK — proteção contra alucinação robusta.")

    return DimensionScore(
        dimension=AuditDimension.HALLUCINATION_RISK,
        score=score,
        findings=findings,
    )


def _score_testability(text: str) -> DimensionScore:
    """Tem exemplo, critério de aceite ou caso de teste?"""
    findings: list[str] = []
    score = 0

    test_hits = len(_TEST_PATTERNS.findall(text))

    if test_hits >= 3:
        score += 7
    elif test_hits >= 1:
        score += 4
    else:
        findings.append("Sem exemplo, critério de aceite ou caso de teste explícito.")

    # Bonifica blocos de código que parecem exemplos
    if "```" in text or "<example>" in text.lower():
        score += 3
    else:
        findings.append("Nenhum bloco de exemplo (```...``` ou <example>).")

    score = min(score, 10)
    return DimensionScore(
        dimension=AuditDimension.TESTABILITY,
        score=score,
        findings=findings,
    )


def _score_prompt_coverage(text: str) -> DimensionScore:
    """
    Cobertura geral dos 6 componentes P.R.O.M.P.T.
    Pontua presença de cada um (max 10).
    """
    components_present: dict[str, bool] = {
        "Purpose": bool(_PURPOSE_PATTERNS.search(text)),
        "Role": bool(_ROLE_PATTERNS.search(text)),
        "Output": bool(_OUTPUT_FORMAT_PATTERNS.search(text)),
        "Method": bool(_METHOD_PATTERNS.search(text)),
        "Pitfalls": bool(_PITFALL_PATTERNS.search(text)),
        "Test": bool(_TEST_PATTERNS.search(text)),
    }
    found = sum(components_present.values())
    # 6 componentes → 10 pontos: cada um vale ~1.67
    score = round(found * (10 / 6))
    findings: list[str] = []
    missing = [k for k, v in components_present.items() if not v]
    if missing:
        findings.append(f"Componentes ausentes: {', '.join(missing)}.")
    else:
        findings.append("OK — todos os 6 componentes P.R.O.M.P.T. presentes.")
    return DimensionScore(
        dimension=AuditDimension.PROMPT_COVERAGE,
        score=score,
        findings=findings,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def audit_text(text: str) -> Scorecard:
    """Audita um texto arbitrário e retorna Scorecard /40."""
    dimensions = [
        _score_clarity(text),
        _score_hallucination_risk(text),
        _score_testability(text),
        _score_prompt_coverage(text),
    ]
    total = sum(d.score for d in dimensions)
    return Scorecard(
        dimensions=dimensions,
        score_total=total,
        recommendations=_build_recommendations(dimensions),
    )


def audit_prompt(prompt: ExtractedPrompt) -> Scorecard:
    """Conveniência: audita um ExtractedPrompt."""
    return audit_text(prompt.content)


def _build_recommendations(dims: list[DimensionScore]) -> list[str]:
    """Top-3 ações a partir das dimensões com menor score."""
    sorted_dims = sorted(dims, key=lambda d: d.score)
    recs: list[str] = []
    for d in sorted_dims[:3]:
        if d.score >= 8:
            continue  # dimensão já boa
        if d.findings:
            recs.append(f"[{d.dimension.value} {d.score}/10] {d.findings[0]}")
    return recs
