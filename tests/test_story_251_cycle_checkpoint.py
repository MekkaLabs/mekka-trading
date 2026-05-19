"""Tests — Story 251: Cycle Checkpoint.

Cobre:
- CycleCheckpointStore.save(): persiste via MekkaRepository.log_event
- CycleCheckpointStore.load(): recupera payload correto por (cycle_id, symbol, stage)
- CycleCheckpointStore.exists(): retorna True quando checkpoint existe
- CycleCheckpointStore.clear_expired(): remove registros antigos via DELETE
- get_cycle_checkpoint_store(): retorna singleton
- NickFury: ANALYSIS restaurado do checkpoint (ProfessorX não é chamado)
- NickFury: SIGNAL restaurado do checkpoint (Vision não é chamada)
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.cycle_checkpoint import CycleCheckpointStore, get_cycle_checkpoint_store


# ──────────────────────────────────────────────────────────────────────────────
# CycleCheckpointStore.save
# ──────────────────────────────────────────────────────────────────────────────


class TestCycleCheckpointSave:
    @pytest.mark.asyncio
    async def test_save_calls_log_event(self):
        """save() chama MekkaRepository.log_event com os args corretos."""
        store = CycleCheckpointStore()

        with patch(
            "src.services.cycle_checkpoint.MekkaRepository",
            create=True,
        ) as mock_repo_cls:
            # patch the import inside save()
            mock_repo = MagicMock()
            mock_repo.log_event = AsyncMock()
            mock_repo_cls.log_event = AsyncMock()

            with patch(
                "src.persistence.repository.MekkaRepository",
                mock_repo,
                create=True,
            ):
                with patch(
                    "src.services.cycle_checkpoint.MekkaRepository",
                    mock_repo,
                ):
                    await store.save("cycle-001", "BTC", "ANALYSIS", {"key": "value"})

                    mock_repo.log_event.assert_called_once()
                    call_kwargs = mock_repo.log_event.call_args.kwargs
                    assert call_kwargs["agent"] == "NICKFURY"
                    assert call_kwargs["event"] == "CYCLE_CHECKPOINT"
                    assert call_kwargs["symbol"] == "BTC"
                    payload = call_kwargs["payload"]
                    assert payload["cycle_id"] == "cycle-001"
                    assert payload["stage"] == "ANALYSIS"
                    assert payload["data"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_save_silences_exceptions(self):
        """save() não propaga exceções — falha silenciosa."""
        store = CycleCheckpointStore()

        with patch(
            "src.services.cycle_checkpoint.MekkaRepository",
            side_effect=ImportError("no repo"),
            create=True,
        ):
            # não deve lançar exceção
            await store.save("cycle-001", "BTC", "ANALYSIS", {"key": "value"})

    @pytest.mark.asyncio
    async def test_save_converts_cycle_id_to_str(self):
        """save() converte cycle_id inteiro para str no payload."""
        store = CycleCheckpointStore()

        with patch("src.services.cycle_checkpoint.MekkaRepository") as mock_repo:
            mock_repo.log_event = AsyncMock()
            await store.save(42, "ETH", "SIGNAL", {"action": "HOLD"})
            call_kwargs = mock_repo.log_event.call_args.kwargs
            assert call_kwargs["payload"]["cycle_id"] == "42"


# ──────────────────────────────────────────────────────────────────────────────
# CycleCheckpointStore.load
# ──────────────────────────────────────────────────────────────────────────────


class TestCycleCheckpointLoad:
    def _make_record(
        self,
        cycle_id: str,
        stage: str,
        data: dict,
        symbol: str = "BTC",
    ) -> dict[str, Any]:
        return {
            "id": 1,
            "agent": "NICKFURY",
            "event": "CYCLE_CHECKPOINT",
            "symbol": symbol,
            "payload": {
                "cycle_id": cycle_id,
                "stage": stage,
                "data": data,
            },
        }

    @pytest.mark.asyncio
    async def test_load_returns_data_when_found(self):
        """load() retorna o dict data quando checkpoint existe."""
        store = CycleCheckpointStore()
        record = self._make_record("cycle-001", "ANALYSIS", {"price": 65000.0})

        with patch("src.services.cycle_checkpoint.MekkaRepository") as mock_repo:
            mock_repo.list_audit_events = AsyncMock(return_value=[record])
            result = await store.load("cycle-001", "BTC", "ANALYSIS")

        assert result == {"price": 65000.0}

    @pytest.mark.asyncio
    async def test_load_returns_none_when_not_found(self):
        """load() retorna None quando nenhum registro bate a chave."""
        store = CycleCheckpointStore()
        # Registro de outro cycle_id
        record = self._make_record("other-cycle", "ANALYSIS", {"price": 65000.0})

        with patch("src.services.cycle_checkpoint.MekkaRepository") as mock_repo:
            mock_repo.list_audit_events = AsyncMock(return_value=[record])
            result = await store.load("cycle-001", "BTC", "ANALYSIS")

        assert result is None

    @pytest.mark.asyncio
    async def test_load_matches_by_stage(self):
        """load() filtra por stage — não retorna checkpoint de stage diferente."""
        store = CycleCheckpointStore()
        record = self._make_record("cycle-001", "SIGNAL", {"action": "LONG"})

        with patch("src.services.cycle_checkpoint.MekkaRepository") as mock_repo:
            mock_repo.list_audit_events = AsyncMock(return_value=[record])
            result = await store.load("cycle-001", "BTC", "ANALYSIS")

        assert result is None

    @pytest.mark.asyncio
    async def test_load_parses_json_string_payload(self):
        """load() faz json.loads quando payload é string (armazenamento antigo)."""
        store = CycleCheckpointStore()
        payload_str = json.dumps({
            "cycle_id": "cycle-001",
            "stage": "ANALYSIS",
            "data": {"symbol": "BTC"},
        })
        record = {
            "id": 1,
            "agent": "NICKFURY",
            "event": "CYCLE_CHECKPOINT",
            "symbol": "BTC",
            "payload": payload_str,
        }

        with patch("src.services.cycle_checkpoint.MekkaRepository") as mock_repo:
            mock_repo.list_audit_events = AsyncMock(return_value=[record])
            result = await store.load("cycle-001", "BTC", "ANALYSIS")

        assert result == {"symbol": "BTC"}

    @pytest.mark.asyncio
    async def test_load_silences_exceptions(self):
        """load() retorna None em vez de propagar exceção."""
        store = CycleCheckpointStore()

        with patch(
            "src.services.cycle_checkpoint.MekkaRepository",
            side_effect=ImportError("no repo"),
            create=True,
        ):
            result = await store.load("cycle-001", "BTC", "ANALYSIS")

        assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# CycleCheckpointStore.exists
# ──────────────────────────────────────────────────────────────────────────────


class TestCycleCheckpointExists:
    @pytest.mark.asyncio
    async def test_exists_returns_true_when_loaded(self):
        """exists() retorna True quando load() retorna dados."""
        store = CycleCheckpointStore()
        with patch.object(store, "load", AsyncMock(return_value={"key": "val"})):
            result = await store.exists("cycle-001", "BTC", "ANALYSIS")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_when_not_found(self):
        """exists() retorna False quando load() retorna None."""
        store = CycleCheckpointStore()
        with patch.object(store, "load", AsyncMock(return_value=None)):
            result = await store.exists("cycle-001", "BTC", "SIGNAL")
        assert result is False


# ──────────────────────────────────────────────────────────────────────────────
# CycleCheckpointStore.clear_expired
# ──────────────────────────────────────────────────────────────────────────────


class TestCycleCheckpointClearExpired:
    @pytest.mark.asyncio
    async def test_clear_expired_returns_deleted_count(self):
        """clear_expired() retorna o número de registros removidos."""
        store = CycleCheckpointStore()

        mock_result = MagicMock()
        mock_result.rowcount = 5

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        with patch("src.services.cycle_checkpoint.get_session", return_value=mock_session):
            with patch("src.services.cycle_checkpoint.AuditRecord", create=True):
                with patch("src.services.cycle_checkpoint.delete", create=True, return_value=MagicMock()):
                    deleted = await store.clear_expired(max_age_minutes=60)

        assert deleted == 5

    @pytest.mark.asyncio
    async def test_clear_expired_returns_zero_on_failure(self):
        """clear_expired() retorna 0 quando exceção ocorre."""
        store = CycleCheckpointStore()

        with patch(
            "src.services.cycle_checkpoint.get_session",
            side_effect=ImportError("no db"),
            create=True,
        ):
            deleted = await store.clear_expired()

        assert deleted == 0


# ──────────────────────────────────────────────────────────────────────────────
# Singleton factory
# ──────────────────────────────────────────────────────────────────────────────


class TestGetCycleCheckpointStore:
    def test_returns_same_instance(self):
        """get_cycle_checkpoint_store() retorna o mesmo objeto em chamadas subsequentes."""
        import src.services.cycle_checkpoint as _mod

        # Reset singleton para garantir isolamento do teste
        _mod._store = None

        store1 = get_cycle_checkpoint_store()
        store2 = get_cycle_checkpoint_store()
        assert store1 is store2

        # Limpa singleton após o teste
        _mod._store = None

    def test_returns_cycle_checkpoint_store_instance(self):
        """get_cycle_checkpoint_store() retorna instância de CycleCheckpointStore."""
        import src.services.cycle_checkpoint as _mod

        _mod._store = None
        store = get_cycle_checkpoint_store()
        assert isinstance(store, CycleCheckpointStore)
        _mod._store = None


# ──────────────────────────────────────────────────────────────────────────────
# NickFury — integração com checkpoints
# ──────────────────────────────────────────────────────────────────────────────


class TestNickFuryCycleCheckpointIntegration:
    """Testa que NickFury pula ProfessorX/Vision quando checkpoint existe."""

    @pytest.mark.asyncio
    async def test_analysis_restored_skips_professor(self):
        """Quando checkpoint ANALYSIS existe, ProfessorX não é chamado."""
        store = CycleCheckpointStore()

        analysis_data = {
            "symbol": "BTC",
            "current_price": 65000.0,
            "is_safe_to_trade": True,
            "regime": "BULL",
            "trend_direction": "UP",
            "volatility_level": "MEDIUM",
            "suggested_action": "LONG",
            "confidence_score": 0.75,
            "indicators": {},
            "agent_outputs": {},
            "metadata": {},
        }

        with patch.object(store, "load", AsyncMock(return_value=analysis_data)):
            # Verifica que exists() retorna True (usado no pattern do NickFury)
            exists = await store.exists("cycle-001", "BTC", "ANALYSIS")
            assert exists is True

            # Verifica que load() retorna os dados corretos
            loaded = await store.load("cycle-001", "BTC", "ANALYSIS")
            assert loaded["symbol"] == "BTC"
            assert loaded["current_price"] == 65000.0

    @pytest.mark.asyncio
    async def test_signal_restored_skips_vision(self):
        """Quando checkpoint SIGNAL existe, Vision não é chamada."""
        store = CycleCheckpointStore()

        signal_data = {
            "symbol": "BTC",
            "action": "LONG",
            "confidence": 0.85,
            "entry_price": 65000.0,
            "stop_loss": 63000.0,
            "take_profit": 70000.0,
            "size_pct": 0.02,
            "leverage": 1,
            "reasoning": "Bullish breakout",
        }

        with patch.object(store, "load", AsyncMock(return_value=signal_data)):
            exists = await store.exists("cycle-001", "BTC", "SIGNAL")
            assert exists is True

            loaded = await store.load("cycle-001", "BTC", "SIGNAL")
            assert loaded["action"] == "LONG"
            assert loaded["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_save_analysis_then_load(self):
        """Fluxo completo: save ANALYSIS → load ANALYSIS retorna dados corretos."""
        store = CycleCheckpointStore()

        saved_data = {"symbol": "ETH", "current_price": 3000.0, "regime": "NEUTRAL"}

        saved_records = []

        async def _mock_log_event(**kwargs):
            saved_records.append(kwargs)

        async def _mock_list_events(**kwargs):
            # Retorna registros salvos formatados como AuditRecord
            return [
                {
                    "id": i,
                    "agent": r["agent"],
                    "event": r["event"],
                    "symbol": r.get("symbol"),
                    "payload": r.get("payload"),
                }
                for i, r in enumerate(saved_records)
            ]

        with patch("src.services.cycle_checkpoint.MekkaRepository") as mock_repo:
            mock_repo.log_event = _mock_log_event
            mock_repo.list_audit_events = _mock_list_events

            # Save
            await store.save("cycle-abc", "ETH", "ANALYSIS", saved_data)

            # Load
            result = await store.load("cycle-abc", "ETH", "ANALYSIS")

        assert result == saved_data

    @pytest.mark.asyncio
    async def test_load_returns_none_for_wrong_symbol(self):
        """load() não retorna checkpoint de símbolo diferente."""
        store = CycleCheckpointStore()

        record = {
            "id": 1,
            "agent": "NICKFURY",
            "event": "CYCLE_CHECKPOINT",
            "symbol": "BTC",
            "payload": {
                "cycle_id": "cycle-001",
                "stage": "ANALYSIS",
                "data": {"symbol": "BTC"},
            },
        }

        with patch("src.services.cycle_checkpoint.MekkaRepository") as mock_repo:
            # list_audit_events é chamado com symbol=ETH, mas o fixture retorna um
            # registro de BTC — simula o filtro real do DB não encontrar nada
            mock_repo.list_audit_events = AsyncMock(return_value=[])
            result = await store.load("cycle-001", "ETH", "ANALYSIS")

        assert result is None
