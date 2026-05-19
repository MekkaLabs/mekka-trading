"""
tests/test_story_217_alert_throttle_manager.py
=================================================
Testes para Story 217 — AlertThrottleManager (Milestone 34).

Cobre:
- Primeiro envio sempre permitido
- Cooldown bloqueia envio dentro da janela
- Após cooldown expirado, envio é novamente permitido
- Diferentes event_keys são independentes
- record_sent() atualiza timestamp corretamente
- suppressed incrementado quando bloqueado
- get_stats() retorna estrutura correta
- reset() limpa todo o estado
- summary_line() retorna string válida
"""

from __future__ import annotations

import time
import pytest


class TestStory217AlertThrottleManager:

    def test_import(self):
        from src.services.alert_throttle_manager import AlertThrottleManager
        assert AlertThrottleManager is not None

    def test_first_send_always_allowed(self):
        from src.services.alert_throttle_manager import AlertThrottleManager
        manager = AlertThrottleManager()
        assert manager.is_allowed("DRAWDOWN_WARNING", cooldown_seconds=1800)

    def test_cooldown_blocks_repeat(self):
        from src.services.alert_throttle_manager import AlertThrottleManager
        manager = AlertThrottleManager()
        manager.record_sent("DRAWDOWN_WARNING")
        # Imediatamente após envio — cooldown ativo
        assert not manager.is_allowed("DRAWDOWN_WARNING", cooldown_seconds=1800)

    def test_after_cooldown_allowed_again(self):
        """Simula cooldown curto para testar expiração."""
        from src.services.alert_throttle_manager import AlertThrottleManager
        manager = AlertThrottleManager()
        manager.record_sent("DRAWDOWN_WARNING")
        # Forçar timestamp passado (simulando cooldown expirado)
        manager._records["DRAWDOWN_WARNING"].last_sent_ts = time.monotonic() - 3601
        assert manager.is_allowed("DRAWDOWN_WARNING", cooldown_seconds=3600)

    def test_different_event_keys_are_independent(self):
        from src.services.alert_throttle_manager import AlertThrottleManager
        manager = AlertThrottleManager()
        manager.record_sent("DRAWDOWN_WARNING")
        # Outro evento não afetado
        assert manager.is_allowed("FUNDING_HIGH_LONG_WARN", cooldown_seconds=1800)

    def test_suppressed_counter_increments(self):
        from src.services.alert_throttle_manager import AlertThrottleManager
        manager = AlertThrottleManager()
        manager.record_sent("DRAWDOWN_CRITICAL")
        # Chamar is_allowed 3x → 3 suprimidos
        manager.is_allowed("DRAWDOWN_CRITICAL", cooldown_seconds=1800)
        manager.is_allowed("DRAWDOWN_CRITICAL", cooldown_seconds=1800)
        manager.is_allowed("DRAWDOWN_CRITICAL", cooldown_seconds=1800)
        stats = manager.get_stats()
        assert stats["DRAWDOWN_CRITICAL"]["suppressed"] == 3

    def test_sent_counter_increments(self):
        from src.services.alert_throttle_manager import AlertThrottleManager
        manager = AlertThrottleManager()
        manager.record_sent("FUNDING_HIGH_LONG_BLOCK")
        manager._records["FUNDING_HIGH_LONG_BLOCK"].last_sent_ts = time.monotonic() - 9999
        manager.record_sent("FUNDING_HIGH_LONG_BLOCK")
        stats = manager.get_stats()
        assert stats["FUNDING_HIGH_LONG_BLOCK"]["sent"] == 2

    def test_get_stats_returns_correct_structure(self):
        from src.services.alert_throttle_manager import AlertThrottleManager
        manager = AlertThrottleManager()
        manager.record_sent("DRAWDOWN_WARNING")
        stats = manager.get_stats()
        assert "DRAWDOWN_WARNING" in stats
        assert "sent" in stats["DRAWDOWN_WARNING"]
        assert "suppressed" in stats["DRAWDOWN_WARNING"]
        assert "last_sent_ts" in stats["DRAWDOWN_WARNING"]

    def test_reset_clears_all_state(self):
        from src.services.alert_throttle_manager import AlertThrottleManager
        manager = AlertThrottleManager()
        manager.record_sent("DRAWDOWN_WARNING")
        manager.record_sent("FUNDING_HIGH_LONG_WARN")
        manager.reset()
        assert manager.total_sent == 0
        assert manager.total_suppressed == 0
        # Após reset, evento é permitido novamente
        assert manager.is_allowed("DRAWDOWN_WARNING", cooldown_seconds=1800)

    def test_summary_line_returns_string(self):
        from src.services.alert_throttle_manager import AlertThrottleManager
        manager = AlertThrottleManager()
        manager.record_sent("DRAWDOWN_WARNING")
        manager.is_allowed("DRAWDOWN_WARNING", cooldown_seconds=1800)  # suprime 1
        line = manager.summary_line()
        assert "enviados" in line
        assert "suprimidos" in line
