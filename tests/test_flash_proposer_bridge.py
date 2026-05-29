"""
tests/test_flash_proposer_bridge.py
=====================================
Cobertura do bridge Flash↔proposer adicionado no fix P0-2.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pytest


# --- Stubs do MomentumSignal (sem importar Flash real) -----------------


class _Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    SIDEWAYS = "SIDEWAYS"


@dataclass
class _MomentumStub:
    direction: _Direction
    confidence: float


# --- Tests --------------------------------------------------------------


class TestIsFlashProposerActive:
    def test_off_when_no_mode(self, monkeypatch):
        from src.services import flash_proposer_bridge as fpb
        monkeypatch.setattr(fpb, "get_params", lambda: {}, raising=False)
        # Force fall-through pelo import lazy
        import src.config.runtime_mode as rm
        monkeypatch.setattr(rm, "get_params", lambda: {})
        assert fpb.is_flash_proposer_active() is False

    def test_on_in_scalp(self, monkeypatch):
        from src.services import flash_proposer_bridge as fpb
        import src.config.runtime_mode as rm
        monkeypatch.setattr(rm, "get_params", lambda: {"flash_is_proposer": True})
        assert fpb.is_flash_proposer_active() is True


class TestSeverity:
    def test_none_when_momentum_none(self):
        from src.services.flash_proposer_bridge import flash_disagreement_severity, DisagreementSeverity
        assert flash_disagreement_severity(None, "LONG") == DisagreementSeverity.NONE

    def test_none_when_same_direction(self):
        from src.services.flash_proposer_bridge import flash_disagreement_severity, DisagreementSeverity
        m = _MomentumStub(_Direction.LONG, 0.9)
        assert flash_disagreement_severity(m, "LONG") == DisagreementSeverity.NONE

    def test_low_for_divergence_low_confidence(self):
        from src.services.flash_proposer_bridge import flash_disagreement_severity, DisagreementSeverity
        m = _MomentumStub(_Direction.LONG, 0.3)
        assert flash_disagreement_severity(m, "SHORT") == DisagreementSeverity.LOW

    def test_medium_for_divergence_medium_confidence(self):
        from src.services.flash_proposer_bridge import flash_disagreement_severity, DisagreementSeverity
        m = _MomentumStub(_Direction.SHORT, 0.7)
        assert flash_disagreement_severity(m, "LONG") == DisagreementSeverity.MEDIUM

    def test_high_for_divergence_high_confidence(self):
        from src.services.flash_proposer_bridge import flash_disagreement_severity, DisagreementSeverity
        m = _MomentumStub(_Direction.LONG, 0.85)
        assert flash_disagreement_severity(m, "SHORT") == DisagreementSeverity.HIGH

    def test_sideways_momentum_returns_none(self):
        from src.services.flash_proposer_bridge import flash_disagreement_severity, DisagreementSeverity
        m = _MomentumStub(_Direction.SIDEWAYS, 0.9)
        assert flash_disagreement_severity(m, "LONG") == DisagreementSeverity.NONE


class TestShouldBlock:
    def test_no_block_when_flash_not_proposer(self, monkeypatch):
        from src.services import flash_proposer_bridge as fpb
        import src.config.runtime_mode as rm
        monkeypatch.setattr(rm, "get_params", lambda: {"flash_is_proposer": False})
        m = _MomentumStub(_Direction.LONG, 0.95)
        ok, reason = fpb.should_block_for_disagreement(m, "SHORT")
        assert ok is False
        assert "not proposer" in reason

    def test_block_when_proposer_and_high_severity(self, monkeypatch):
        from src.services import flash_proposer_bridge as fpb
        import src.config.runtime_mode as rm
        monkeypatch.setattr(rm, "get_params", lambda: {"flash_is_proposer": True})
        m = _MomentumStub(_Direction.LONG, 0.95)
        ok, reason = fpb.should_block_for_disagreement(m, "SHORT")
        assert ok is True
        assert "disagreement" in reason

    def test_no_block_when_below_threshold(self, monkeypatch):
        from src.services import flash_proposer_bridge as fpb, flash_proposer_bridge
        import src.config.runtime_mode as rm
        monkeypatch.setattr(rm, "get_params", lambda: {"flash_is_proposer": True})
        m = _MomentumStub(_Direction.LONG, 0.5)  # LOW severity
        ok, reason = fpb.should_block_for_disagreement(
            m, "SHORT",
            severity_to_block=flash_proposer_bridge.DisagreementSeverity.HIGH,
        )
        assert ok is False

    def test_fail_silent_on_exception(self, monkeypatch):
        from src.services import flash_proposer_bridge as fpb
        import src.config.runtime_mode as rm
        def _broken():
            raise RuntimeError("oops")
        monkeypatch.setattr(rm, "get_params", _broken)
        assert fpb.is_flash_proposer_active() is False
