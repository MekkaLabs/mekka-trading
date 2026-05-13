"""
tests/test_phase19_dashboard_v2.py
===================================
Story 040 — Dashboard v2: TradeNow endpoints + guardrails + audit trail.

Tests cover:
  - POST /api/trade/analyze — guardrail evaluation, recommendation shape
  - POST /api/trade/execute — confirmed=True required, kill-switch block,
    paper mode marker, audit log entries
  - Audit trail events: TRADE_NOW_REQUESTED, TRADE_NOW_RECOMMENDED,
    TRADE_NOW_BLOCKED, TRADE_NOW_EXECUTED
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_server():
    """Return an initialised MekkaDashboardServer with in-memory SQLite."""
    from src.dashboard.server import MekkaDashboardServer
    return MekkaDashboardServer()


async def _post(server, path: str, body: dict):
    """Simulate POST via aiohttp test client (minimal shim)."""
    from aiohttp.test_utils import TestClient, TestServer
    client = TestClient(TestServer(server.app))
    await client.start_server()
    try:
        resp = await client.post(path, json=body)
        data = await resp.json()
        return resp.status, data
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Suite 1 — /api/trade/analyze
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestTradeAnalyze:

    async def test_analyze_returns_recommendation_shape(self):
        """Response must include recommendation_id, guardrails, recommendation, is_paper."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        server = _make_server()
        status, data = await _post(server, '/api/trade/analyze', {})

        assert status == 200, f"Expected 200, got {status}: {data}"
        assert 'recommendation_id' in data
        assert isinstance(data['recommendation_id'], str)
        assert 'guardrails' in data
        assert 'passed' in data['guardrails']
        assert 'checks' in data['guardrails']
        assert 'is_paper' in data
        assert 'generated_at' in data

    async def test_analyze_guardrail_checks_have_required_fields(self):
        """Every guardrail check must have name, ok, detail."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        server = _make_server()
        _, data = await _post(server, '/api/trade/analyze', {})

        for check in data['guardrails']['checks']:
            assert 'name' in check, f"Missing 'name' in check: {check}"
            assert 'ok' in check, f"Missing 'ok' in check: {check}"
            assert 'detail' in check, f"Missing 'detail' in check: {check}"
            assert isinstance(check['ok'], bool)

    async def test_analyze_kill_switch_blocks_guardrail(self):
        """When kill switch is active, kill_switch_clear guardrail must be False
        and recommendation must be None."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        with patch('src.agents.batman.is_kill_switch_active', return_value=True):
            server = _make_server()
            _, data = await _post(server, '/api/trade/analyze', {})

        ks_check = next((c for c in data['guardrails']['checks'] if c['name'] == 'kill_switch_clear'), None)
        assert ks_check is not None, "kill_switch_clear check must be present"
        assert ks_check['ok'] is False, "kill_switch_clear must be False when KS active"
        assert data['recommendation'] is None, "recommendation must be None when guardrails fail"
        assert data['guardrails']['passed'] is False

    async def test_analyze_recommendation_shape_when_guardrails_pass(self):
        """When all guardrails pass and a signal exists, recommendation has expected fields."""
        from src.persistence.repository import MekkaRepository
        from src.persistence.models import SignalRecord
        from src.persistence.db import get_session
        from datetime import datetime, timezone

        await MekkaRepository.initialize()

        # Insert a fake actionable signal
        async with get_session() as session:
            sig = SignalRecord(
                timestamp=datetime.now(timezone.utc),
                symbol='BTC',
                action='LONG',
                confidence=0.85,
                entry_price=65000.0,
                stop_loss=63000.0,
                take_profit=70000.0,
                size_pct=0.02,
                leverage=5,
                risk_reward=2.5,
                reasoning='Test signal — high confidence bullish breakout',
                is_actionable=True,
            )
            session.add(sig)
            await session.commit()

        with patch('src.agents.batman.is_kill_switch_active', return_value=False):
            server = _make_server()
            _, data = await _post(server, '/api/trade/analyze', {})

        if data['recommendation'] is not None:
            rec = data['recommendation']
            for field in ['symbol', 'direction', 'entry_price', 'stop_loss',
                          'take_profit', 'size_pct', 'confidence', 'risk_usd',
                          'justification', 'source', 'agents_consensus']:
                assert field in rec, f"Missing field '{field}' in recommendation"

    async def test_analyze_mock_recommendation_when_no_signal(self):
        """When no actionable signal exists, source must be 'mock'."""
        from src.persistence.repository import MekkaRepository
        from src.persistence.db import get_session
        from src.persistence.models import SignalRecord
        from sqlalchemy import delete

        await MekkaRepository.initialize()

        # Wipe all signals
        async with get_session() as session:
            await session.execute(delete(SignalRecord))
            await session.commit()

        with patch('src.agents.batman.is_kill_switch_active', return_value=False):
            server = _make_server()
            _, data = await _post(server, '/api/trade/analyze', {})

        # May be None if guardrails fail; if recommendation exists, must be mock
        if data['recommendation'] is not None:
            assert data['recommendation']['source'] == 'mock'
            assert data['recommendation']['agents_consensus'] is False

    async def test_analyze_logs_trade_now_requested(self):
        """TRADE_NOW_REQUESTED audit event must be created."""
        from src.persistence.repository import MekkaRepository
        from src.persistence.db import get_session
        from src.persistence.models import AuditRecord
        from sqlalchemy import select, desc

        await MekkaRepository.initialize()

        server = _make_server()
        _, data = await _post(server, '/api/trade/analyze', {})
        rec_id = data.get('recommendation_id', '')

        async with get_session() as session:
            rows = (await session.execute(
                select(AuditRecord)
                .where(AuditRecord.event == 'TRADE_NOW_REQUESTED')
                .order_by(desc(AuditRecord.timestamp))
                .limit(5)
            )).scalars().all()

        assert len(rows) > 0, "TRADE_NOW_REQUESTED audit event must exist"
        payloads = [r.payload for r in rows]
        assert any(p and p.get('recommendation_id') == rec_id for p in payloads), \
            "TRADE_NOW_REQUESTED must reference the recommendation_id"


# ---------------------------------------------------------------------------
# Suite 2 — /api/trade/execute
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestTradeExecute:

    async def test_execute_requires_confirmed_true(self):
        """Body without confirmed=True must return 400 rejected."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        server = _make_server()

        # Missing confirmed
        status, data = await _post(server, '/api/trade/execute', {'recommendation_id': 'test-001'})
        assert status == 400, f"Expected 400, got {status}"
        assert data['status'] == 'rejected'

    async def test_execute_confirmed_false_is_rejected(self):
        """confirmed=False must also return 400 rejected."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        server = _make_server()
        status, data = await _post(server, '/api/trade/execute', {
            'recommendation_id': 'test-002',
            'confirmed': False,
        })
        assert status == 400
        assert data['status'] == 'rejected'

    async def test_execute_confirmed_string_is_rejected(self):
        """confirmed='true' (string) must be rejected — only bool True passes."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        server = _make_server()
        status, data = await _post(server, '/api/trade/execute', {
            'recommendation_id': 'test-003',
            'confirmed': 'true',
        })
        assert status == 400
        assert data['status'] == 'rejected'

    async def test_execute_kill_switch_blocks(self):
        """Kill switch active → status=blocked, no order_id."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        with patch('src.agents.batman.is_kill_switch_active', return_value=True):
            server = _make_server()
            status, data = await _post(server, '/api/trade/execute', {
                'recommendation_id': 'test-ks-001',
                'confirmed': True,
            })

        assert status == 200
        assert data['status'] == 'blocked'
        assert data['order_id'] is None

    async def test_execute_paper_mode_returns_paper_order_id(self):
        """In paper mode, order_id must start with PAPER-."""
        import os
        os.environ['PAPER_TRADING'] = 'true'

        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        with patch('src.agents.batman.is_kill_switch_active', return_value=False):
            server = _make_server()
            status, data = await _post(server, '/api/trade/execute', {
                'recommendation_id': 'test-paper-001',
                'confirmed': True,
            })

        assert status == 200, f"Expected 200, got {status}: {data}"
        assert data['status'] == 'submitted'
        assert data['is_paper'] is True
        assert data['order_id'] is not None
        assert data['order_id'].startswith('PAPER-'), \
            f"Paper order_id must start with PAPER-, got: {data['order_id']}"

    async def test_execute_logs_trade_now_executed(self):
        """TRADE_NOW_EXECUTED audit event must be created on success."""
        from src.persistence.repository import MekkaRepository
        from src.persistence.db import get_session
        from src.persistence.models import AuditRecord
        from sqlalchemy import select, desc

        await MekkaRepository.initialize()

        with patch('src.agents.batman.is_kill_switch_active', return_value=False):
            server = _make_server()
            _, data = await _post(server, '/api/trade/execute', {
                'recommendation_id': 'test-audit-001',
                'confirmed': True,
            })

        async with get_session() as session:
            rows = (await session.execute(
                select(AuditRecord)
                .where(AuditRecord.event == 'TRADE_NOW_EXECUTED')
                .order_by(desc(AuditRecord.timestamp))
                .limit(5)
            )).scalars().all()

        assert len(rows) > 0, "TRADE_NOW_EXECUTED audit event must exist"

    async def test_execute_blocked_logs_trade_now_blocked(self):
        """TRADE_NOW_BLOCKED audit event must be created when execution is blocked."""
        from src.persistence.repository import MekkaRepository
        from src.persistence.db import get_session
        from src.persistence.models import AuditRecord
        from sqlalchemy import select, desc

        await MekkaRepository.initialize()

        with patch('src.agents.batman.is_kill_switch_active', return_value=True):
            server = _make_server()
            await _post(server, '/api/trade/execute', {
                'recommendation_id': 'test-blocked-001',
                'confirmed': True,
            })

        async with get_session() as session:
            rows = (await session.execute(
                select(AuditRecord)
                .where(AuditRecord.event == 'TRADE_NOW_BLOCKED')
                .order_by(desc(AuditRecord.timestamp))
                .limit(5)
            )).scalars().all()

        assert len(rows) > 0, "TRADE_NOW_BLOCKED audit event must exist"

    async def test_execute_no_secrets_in_response(self):
        """Execute response must not contain any API keys or secrets."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        with patch('src.agents.batman.is_kill_switch_active', return_value=False):
            server = _make_server()
            _, data = await _post(server, '/api/trade/execute', {
                'recommendation_id': 'test-secrets-001',
                'confirmed': True,
            })

        response_str = json.dumps(data).lower()
        for secret_indicator in ['sk-', 'private_key', 'api_key', 'password', 'secret']:
            assert secret_indicator not in response_str, \
                f"Response must not contain '{secret_indicator}'"


# ---------------------------------------------------------------------------
# Suite 3 — Full flow: analyze → execute
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestTradeFullFlow:

    async def test_analyze_then_execute_full_flow(self):
        """Analyze followed by execute with the returned rec_id should succeed."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        with patch('src.agents.batman.is_kill_switch_active', return_value=False):
            server = _make_server()

            # Step 1: analyze
            a_status, a_data = await _post(server, '/api/trade/analyze', {})
            assert a_status == 200
            rec_id = a_data.get('recommendation_id')
            assert rec_id

            # Step 2: execute (regardless of guardrail result — we test the flow)
            e_status, e_data = await _post(server, '/api/trade/execute', {
                'recommendation_id': rec_id,
                'confirmed': True,
            })
            assert e_status in (200, 400), f"Unexpected status: {e_status}"
            # If guardrails passed → submitted; if not → still graceful
            assert 'status' in e_data
            assert 'is_paper' in e_data

    async def test_double_execute_with_different_rec_ids(self):
        """Two different executes should produce two independent audit entries."""
        from src.persistence.repository import MekkaRepository
        from src.persistence.db import get_session
        from src.persistence.models import AuditRecord
        from sqlalchemy import select, desc

        await MekkaRepository.initialize()

        with patch('src.agents.batman.is_kill_switch_active', return_value=False):
            server = _make_server()
            await _post(server, '/api/trade/execute', {
                'recommendation_id': 'flow-001',
                'confirmed': True,
            })
            await _post(server, '/api/trade/execute', {
                'recommendation_id': 'flow-002',
                'confirmed': True,
            })

        async with get_session() as session:
            rows = (await session.execute(
                select(AuditRecord)
                .where(AuditRecord.event == 'TRADE_NOW_EXECUTED')
                .order_by(desc(AuditRecord.timestamp))
                .limit(10)
            )).scalars().all()

        rec_ids = {r.payload.get('recommendation_id') for r in rows if r.payload}
        assert 'flow-001' in rec_ids
        assert 'flow-002' in rec_ids
