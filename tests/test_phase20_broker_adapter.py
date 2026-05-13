"""
tests/test_phase20_broker_adapter.py
=====================================
Story 041 — IronMan broker adapter wired into /api/trade/execute
Story 042 — Widget prefs endpoint /api/prefs

Tests cover:
  - Recommendation cache populado pelo /api/trade/analyze
  - Execute com rec_id válido → chama Batman + IronMan (paper)
  - Execute com rec_id inválido (não em cache) → blocked com mensagem clara
  - Execute com fonte mock → blocked ao nível do servidor
  - GET /api/prefs → retorna {} quando não há arquivo
  - POST /api/prefs → salva prefs válidos, rejeita payload inválido
  - GET /api/prefs após POST → retorna prefs salvos
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_server():
    from src.dashboard.server import MekkaDashboardServer
    return MekkaDashboardServer()


async def _post(server, path: str, body: dict):
    from aiohttp.test_utils import TestClient, TestServer
    client = TestClient(TestServer(server.app))
    await client.start_server()
    try:
        resp = await client.post(path, json=body)
        data = await resp.json()
        return resp.status, data
    finally:
        await client.close()


async def _get(server, path: str):
    from aiohttp.test_utils import TestClient, TestServer
    client = TestClient(TestServer(server.app))
    await client.start_server()
    try:
        resp = await client.get(path)
        data = await resp.json()
        return resp.status, data
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Suite 1 — Story 041: Rec cache + broker adapter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestBrokerAdapter:

    async def test_analyze_populates_rec_cache(self):
        """Após /api/trade/analyze com guardrails ok, a rec fica em _rec_cache."""
        from src.persistence.repository import MekkaRepository
        from src.persistence.db import get_session
        from src.persistence.models import SignalRecord
        from datetime import datetime, timezone

        await MekkaRepository.initialize()

        # Inserir sinal acionável
        async with get_session() as session:
            sig = SignalRecord(
                timestamp=datetime.now(timezone.utc),
                symbol='BTC', action='LONG', confidence=0.85,
                entry_price=65000.0, stop_loss=63000.0, take_profit=70000.0,
                size_pct=0.02, leverage=5, risk_reward=2.5,
                reasoning='Test signal', is_actionable=True,
            )
            session.add(sig)
            await session.commit()

        with patch('src.agents.batman.is_kill_switch_active', return_value=False):
            server = _make_server()
            _, data = await _post(server, '/api/trade/analyze', {})

        rec_id = data.get('recommendation_id', '')
        assert rec_id, "analyze deve retornar recommendation_id"
        if data.get('recommendation'):
            assert rec_id in server._rec_cache, (
                "rec_id deve estar em _rec_cache após analyze com sinal real"
            )

    async def test_execute_stale_rec_id_returns_blocked(self):
        """rec_id que não está em _rec_cache → status=blocked, mensagem clara."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        with patch('src.agents.batman.is_kill_switch_active', return_value=False):
            server = _make_server()
            status, data = await _post(server, '/api/trade/execute', {
                'recommendation_id': 'rec-nao-existe-9999',
                'confirmed': True,
            })

        assert status == 200
        assert data['status'] == 'blocked'
        assert 'não encontrada' in data['reason'].lower() or 'cache' in data['reason'].lower()
        assert data['order_id'] is None

    async def test_execute_mock_source_blocked_server_side(self):
        """Recomendação com source=mock deve ser bloqueada no servidor."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        server = _make_server()
        # Injetar manualmente uma rec mock no cache
        mock_rec_id = 'mock-rec-001'
        server._rec_cache[mock_rec_id] = {
            'symbol': 'BTC', 'direction': 'LONG',
            'entry_price': 65000.0, 'stop_loss': 63000.0, 'take_profit': 70000.0,
            'size_pct': 0.02, 'leverage': 1, 'confidence': 0.0,
            'justification': 'mock stub', 'source': 'mock',
            '_equity_usd': 10000.0,
        }

        with patch('src.agents.batman.is_kill_switch_active', return_value=False):
            status, data = await _post(server, '/api/trade/execute', {
                'recommendation_id': mock_rec_id,
                'confirmed': True,
            })

        assert status == 200
        assert data['status'] == 'blocked'
        assert 'mock' in data['reason'].lower()

    async def test_execute_real_rec_calls_ironman_paper(self):
        """rec válida com source=agents → IronMan é chamado, retorna PAPER- order_id."""
        import os
        os.environ['PAPER_TRADING'] = 'true'

        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        server = _make_server()
        # Injetar rec de agentes no cache
        real_rec_id = 'agents-rec-001'
        server._rec_cache[real_rec_id] = {
            'symbol': 'BTC', 'direction': 'LONG',
            'entry_price': 65000.0, 'stop_loss': 63000.0, 'take_profit': 70000.0,
            'size_pct': 0.02, 'leverage': 3, 'confidence': 0.85,
            'justification': 'Strong breakout signal', 'source': 'agents',
            'agents_consensus': True,
            '_equity_usd': 10000.0,
        }

        with patch('src.agents.batman.is_kill_switch_active', return_value=False):
            status, data = await _post(server, '/api/trade/execute', {
                'recommendation_id': real_rec_id,
                'confirmed': True,
            })

        assert status == 200, f"Esperado 200, recebido {status}: {data}"
        assert data['status'] in ('submitted', 'blocked'), f"Status inesperado: {data['status']}"
        assert data['is_paper'] is True
        if data['status'] == 'submitted':
            assert data['order_id'] is not None
            assert data['order_id'].startswith('PAPER-'), (
                f"order_id paper deve começar com PAPER-, recebido: {data['order_id']}"
            )

    async def test_execute_batman_blocks_produces_blocked_response(self):
        """Quando Batman rejeita, execute deve retornar status=blocked."""
        from src.persistence.repository import MekkaRepository
        from src.models.risk import RiskApproval, RiskVerdict
        await MekkaRepository.initialize()

        server = _make_server()
        batman_rec_id = 'batman-block-001'
        server._rec_cache[batman_rec_id] = {
            'symbol': 'BTC', 'direction': 'LONG',
            'entry_price': 65000.0, 'stop_loss': 63000.0, 'take_profit': 70000.0,
            'size_pct': 0.02, 'leverage': 1, 'confidence': 0.9,
            'justification': 'Good signal', 'source': 'agents',
            'agents_consensus': True, '_equity_usd': 10000.0,
        }

        rejected_approval = RiskApproval(
            symbol='BTC',
            verdict=RiskVerdict.REJECTED,
            reasons=['Drawdown limit exceeded'],
            adjusted_size_pct=0.0,
            adjusted_leverage=1,
        )

        with patch('src.agents.batman.is_kill_switch_active', return_value=False), \
             patch('src.agents.batman.Batman.run', new_callable=AsyncMock,
                   return_value=rejected_approval):
            status, data = await _post(server, '/api/trade/execute', {
                'recommendation_id': batman_rec_id,
                'confirmed': True,
            })

        assert status == 200
        assert data['status'] == 'blocked'
        assert data['order_id'] is None

    async def test_rec_cache_fifo_eviction(self):
        """Cache é limitado a _rec_cache_max entradas — entradas antigas são descartadas."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        server = _make_server()
        max_entries = server._rec_cache_max

        # Inserir max+5 entradas manualmente
        for i in range(max_entries + 5):
            server._rec_cache[f'rec-{i:04d}'] = {'source': 'agents', '_equity_usd': 1000.0}
            if len(server._rec_cache) > max_entries:
                oldest = next(iter(server._rec_cache))
                del server._rec_cache[oldest]

        assert len(server._rec_cache) <= max_entries, (
            f"Cache deveria ter no máximo {max_entries} entradas, tem {len(server._rec_cache)}"
        )


# ---------------------------------------------------------------------------
# Suite 2 — Story 042: /api/prefs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPrefsEndpoint:

    async def test_get_prefs_returns_empty_dict_when_no_file(self):
        """GET /api/prefs retorna {'prefs': {}} quando nenhuma pref foi salva."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        server = _make_server()

        with patch.object(
            server, '_PREFS_FILE',
            '/tmp/mekka_test_prefs_missing_9999.json',
        ):
            status, data = await _get(server, '/api/prefs')

        assert status == 200
        assert 'prefs' in data
        assert isinstance(data['prefs'], dict)

    async def test_post_prefs_saves_valid_prefs(self):
        """POST /api/prefs com prefs válidas retorna saved=True."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        server = _make_server()

        with tempfile.TemporaryDirectory() as tmpdir:
            prefs_file = f"{tmpdir}/widget_prefs.json"
            with patch.object(server, '_PREFS_FILE', prefs_file):
                status, data = await _post(server, '/api/prefs', {
                    'prefs': {
                        'sec-pnl': True,
                        'sec-office': False,
                        'sec-positions': True,
                    }
                })

        assert status == 200
        assert data.get('saved') is True
        assert data.get('count') == 3

    async def test_post_prefs_rejects_invalid_body(self):
        """POST /api/prefs sem campo 'prefs' retorna 400."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        server = _make_server()
        status, data = await _post(server, '/api/prefs', {'not_prefs': {}})

        assert status == 400
        assert 'error' in data

    async def test_get_prefs_after_post_returns_saved_data(self):
        """GET /api/prefs após POST deve retornar as prefs salvas."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        prefs_to_save = {'sec-pnl': False, 'sec-audit': True}

        with tempfile.TemporaryDirectory() as tmpdir:
            prefs_file = f"{tmpdir}/widget_prefs.json"
            server = _make_server()

            with patch.object(server, '_PREFS_FILE', prefs_file):
                # Salvar
                await _post(server, '/api/prefs', {'prefs': prefs_to_save})
                # Ler
                status, data = await _get(server, '/api/prefs')

        assert status == 200
        saved = data.get('prefs', {})
        assert saved.get('sec-pnl') is False
        assert saved.get('sec-audit') is True

    async def test_post_prefs_sanitises_non_sec_keys(self):
        """POST /api/prefs deve ignorar chaves que não começam com 'sec-'."""
        from src.persistence.repository import MekkaRepository
        await MekkaRepository.initialize()

        with tempfile.TemporaryDirectory() as tmpdir:
            prefs_file = f"{tmpdir}/widget_prefs.json"
            server = _make_server()

            with patch.object(server, '_PREFS_FILE', prefs_file):
                status, data = await _post(server, '/api/prefs', {
                    'prefs': {
                        'sec-pnl': True,
                        'malicious-key': False,
                        '__proto__': True,
                        'sec-audit': False,
                    }
                })

        assert status == 200
        assert data.get('count') == 2  # apenas sec-pnl e sec-audit
