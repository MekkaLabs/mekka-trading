"""Tests — _build_global_alerts respeitando RELEASE posterior.

Bug fix 2026-05-25: o banner do dashboard surfaceava CYCLE_SKIPPED ou
KILL_SWITCH_ENGAGED dos últimos 10min, mesmo se um KILL_SWITCH_RELEASED
viesse depois. Resultado: operador via "KILL_SWITCH ATIVO" no banner
com o kill switch já liberado no disco — falso positivo recorrente.

Fix: o banner agora pega o evento KS MAIS RECENTE; se for RELEASED,
não emite banner. Só engages/skips ativos (sem release subsequente)
geram o alert.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


@dataclass
class _FakeAudit:
    """Stand-in for AuditRecord — only fields the function reads."""
    timestamp: datetime
    event: str
    agent: str = "NickFury"
    payload: dict | None = None
    symbol: str | None = None


def _alerts_with_no_ks_file(audits):
    """Run _build_global_alerts assuming the KILL_SWITCH_FILE doesn't exist
    (i.e., on-disk kill switch is OFF). We only care about the time-windowed
    audit-derived banner in this test."""
    from src.dashboard.server import _build_global_alerts, KILL_SWITCH_FILE
    # patch only existence — leave path untouched
    with patch.object(KILL_SWITCH_FILE.__class__, "exists", lambda self: False):
        return _build_global_alerts(audits, drawdown_pct=None)


def _now():
    return datetime.now(timezone.utc)


def test_banner_silenced_when_release_is_most_recent():
    """ENGAGED 5min atrás + RELEASED 2min atrás → SEM banner KS."""
    audits = [
        _FakeAudit(_now() - timedelta(minutes=5), "KILL_SWITCH_ENGAGED", "Dashboard"),
        _FakeAudit(_now() - timedelta(minutes=2), "KILL_SWITCH_RELEASED", "Dashboard"),
    ]
    alerts = _alerts_with_no_ks_file(audits)
    ks_alerts = [a for a in alerts if a["code"] == "KILL_SWITCH_EVENT"]
    assert len(ks_alerts) == 0, (
        f"Banner deveria estar silenciado após RELEASE, mas surgiu: {ks_alerts}"
    )


def test_banner_silenced_when_cycle_skipped_then_released():
    """CYCLE_SKIPPED 3min atrás + RELEASED 1min atrás → SEM banner."""
    audits = [
        _FakeAudit(_now() - timedelta(minutes=3), "CYCLE_SKIPPED", "NickFury"),
        _FakeAudit(_now() - timedelta(minutes=1), "KILL_SWITCH_RELEASED", "Dashboard"),
    ]
    alerts = _alerts_with_no_ks_file(audits)
    ks_alerts = [a for a in alerts if a["code"] == "KILL_SWITCH_EVENT"]
    assert len(ks_alerts) == 0


def test_banner_active_when_engage_is_most_recent():
    """RELEASED 5min atrás + ENGAGED 1min atrás → banner ATIVO."""
    audits = [
        _FakeAudit(_now() - timedelta(minutes=5), "KILL_SWITCH_RELEASED", "Dashboard"),
        _FakeAudit(_now() - timedelta(minutes=1), "KILL_SWITCH_ENGAGED", "Dashboard"),
    ]
    alerts = _alerts_with_no_ks_file(audits)
    ks_alerts = [a for a in alerts if a["code"] == "KILL_SWITCH_EVENT"]
    assert len(ks_alerts) == 1
    assert "ENGAGED" in ks_alerts[0]["message"]


def test_banner_active_when_only_engage_present():
    """Só engage na janela → banner aparece."""
    audits = [
        _FakeAudit(_now() - timedelta(minutes=2), "RISK_KILL_SWITCH", "Batman"),
    ]
    alerts = _alerts_with_no_ks_file(audits)
    ks_alerts = [a for a in alerts if a["code"] == "KILL_SWITCH_EVENT"]
    assert len(ks_alerts) == 1


def test_banner_silenced_when_events_outside_window():
    """ENGAGED 15min atrás (fora da janela de 10min) → sem banner."""
    audits = [
        _FakeAudit(_now() - timedelta(minutes=15), "KILL_SWITCH_ENGAGED", "Dashboard"),
    ]
    alerts = _alerts_with_no_ks_file(audits)
    ks_alerts = [a for a in alerts if a["code"] == "KILL_SWITCH_EVENT"]
    assert len(ks_alerts) == 0


def test_banner_picks_most_recent_engage_when_multiple():
    """3 engages na janela, último é o que aparece."""
    audits = [
        _FakeAudit(_now() - timedelta(minutes=8), "KILL_SWITCH_ENGAGED", "Dashboard"),
        _FakeAudit(_now() - timedelta(minutes=4), "RISK_KILL_SWITCH", "Batman"),
        _FakeAudit(_now() - timedelta(minutes=1), "CYCLE_SKIPPED", "NickFury"),
    ]
    alerts = _alerts_with_no_ks_file(audits)
    ks_alerts = [a for a in alerts if a["code"] == "KILL_SWITCH_EVENT"]
    assert len(ks_alerts) == 1
    assert "CYCLE_SKIPPED" in ks_alerts[0]["message"]
    assert "NickFury" in ks_alerts[0]["message"]
