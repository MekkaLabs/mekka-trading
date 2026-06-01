"""Regressão da revisão de memória/Obsidian (2026-06-01).

- Mentor: _enqueue_in_inbox usa os atributos certos (reason/evidence dict) e
  inclui o contrato do applier (direction/confidence/suggested_value/can_auto_apply).
  Antes usava s.rationale/s.evidence_n (inexistentes) → AttributeError engolido →
  o loop de aprendizado morria silenciosamente.
- vault_auditor: scanners (Cypher/Domino/Forge) e Trade Outcome Resolver não são
  mais reportados como agentes-vault-sem-código (falsos órfãos).
"""
from __future__ import annotations


def test_mentor_uses_correct_suggestion_attributes():
    import inspect
    from src.agents.mentor import Mentor

    src = inspect.getsource(Mentor._enqueue_in_inbox)
    # Atributos corretos do ParameterSuggestion.
    assert "s.reason" in src
    assert "s.evidence" in src
    # Contrato exigido pelo mentor_applier.apply_inbox.
    assert '"suggested_value": s.suggested_value' in src
    assert '"confidence": float(s.confidence)' in src
    assert '"can_auto_apply": bool(s.can_auto_apply)' in src
    assert '"direction": s.direction' in src
    # Os USOS reais (não os comentários) dos atributos antigos sumiram:
    assert '"description": s.rationale' not in src
    assert "n={s.evidence_n}" not in src


def test_parameter_suggestion_has_expected_fields():
    from src.agents.mentor import ParameterSuggestion
    s = ParameterSuggestion(
        parameter_name="min_confidence", current_value=0.6, suggested_value=0.7,
        direction="tighten", reason="x", evidence={"n": 10, "period": "7d"},
        confidence=0.9, can_auto_apply=True,
    )
    # Os campos que o código novo acessa existem.
    assert s.reason == "x"
    assert s.evidence["n"] == 10
    assert s.direction == "tighten"
    assert s.can_auto_apply is True
    # E os antigos NÃO existem.
    assert not hasattr(s, "rationale")
    assert not hasattr(s, "evidence_n")


def test_vault_auditor_no_false_orphan_agents():
    """Cypher/Domino/Forge (codenames dos scanners) + Trade Outcome Resolver
    não devem aparecer como agentes-vault-sem-código."""
    from pathlib import Path
    from src.services.vault_auditor import _detect_agents_code_vs_vault

    vault = Path.home() / "Documents" / "mekka-trading-obsidian"
    if not vault.exists():
        import pytest
        pytest.skip("vault canônico ausente neste ambiente")

    repo_root = Path(__file__).resolve().parents[1]
    code, vault_set = _detect_agents_code_vs_vault(vault, repo_root)
    vault_only = vault_set - code
    # Os 4 falsos órfãos não podem mais estar na diferença.
    for false_orphan in ("Cypher", "Domino", "Forge", "Trade Outcome Resolver"):
        # após normalização o alias mapeia p/ a forma do código
        assert false_orphan not in vault_only, f"{false_orphan} reportado como órfão"


def test_vault_auditor_aliases_map_codenames():
    import inspect
    from src.services import vault_auditor as va
    src = inspect.getsource(va._detect_agents_code_vs_vault)
    assert '"Cypher": "Code Auditor"' in src
    assert '"Domino": "Risk Scanner"' in src
    assert '"Forge": "Ops Scanner"' in src
