"""Tests — runtime_overrides helper (toggles UI cabeados no loop, 2026-05-25).

Background: UI tinha 2 toggles ("Super Agressivo" + "Altcoins") que diziam
afetar o trader autônomo, mas só afetavam o TradeNow manual. Este helper
centraliza a leitura e expõe API para Batman/NickFury honrarem.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.config.runtime_overrides import (
    ALTCOINS,
    SUPER_AGGRESSIVE_MIN_LEVERAGE,
    SUPER_AGGRESSIVE_MIN_SIZE_PCT,
    apply_super_aggressive_to_size_lev,
    expand_assets_with_altcoins,
    get_runtime_overrides,
)


def test_get_overrides_missing_file_returns_defaults(tmp_path, monkeypatch):
    """Arquivo ausente → defaults seguros (toggles OFF)."""
    from src.config import runtime_overrides as ro

    monkeypatch.setattr(ro, "_RUNTIME_SETTINGS", tmp_path / "nope.json")
    out = get_runtime_overrides()
    assert out == {"super_aggressive": False, "altcoins_enabled": False}


def test_get_overrides_reads_real_file(tmp_path, monkeypatch):
    from src.config import runtime_overrides as ro

    f = tmp_path / "settings.json"
    f.write_text('{"super_aggressive": true, "altcoins_enabled": true}')
    monkeypatch.setattr(ro, "_RUNTIME_SETTINGS", f)
    out = get_runtime_overrides()
    assert out["super_aggressive"] is True
    assert out["altcoins_enabled"] is True


def test_get_overrides_corrupted_json_returns_defaults(tmp_path, monkeypatch):
    """JSON corrompido → defaults seguros (NUNCA expor risco por bug de I/O)."""
    from src.config import runtime_overrides as ro

    f = tmp_path / "settings.json"
    f.write_text("not valid json {")
    monkeypatch.setattr(ro, "_RUNTIME_SETTINGS", f)
    out = get_runtime_overrides()
    assert out["super_aggressive"] is False
    assert out["altcoins_enabled"] is False


def test_super_aggressive_off_returns_unchanged(tmp_path, monkeypatch):
    from src.config import runtime_overrides as ro

    f = tmp_path / "settings.json"
    f.write_text('{"super_aggressive": false}')
    monkeypatch.setattr(ro, "_RUNTIME_SETTINGS", f)
    new_size, new_lev = apply_super_aggressive_to_size_lev(0.01, 2, 0.10, 20)
    assert new_size == 0.01
    assert new_lev == 2


def test_super_aggressive_on_forces_minimum(tmp_path, monkeypatch):
    """ON: size sobe para min 5%, leverage sobe para min 10x."""
    from src.config import runtime_overrides as ro

    f = tmp_path / "settings.json"
    f.write_text('{"super_aggressive": true}')
    monkeypatch.setattr(ro, "_RUNTIME_SETTINGS", f)
    new_size, new_lev = apply_super_aggressive_to_size_lev(0.01, 2, 0.10, 20)
    assert new_size == SUPER_AGGRESSIVE_MIN_SIZE_PCT  # 0.05
    assert new_lev == SUPER_AGGRESSIVE_MIN_LEVERAGE  # 10


def test_super_aggressive_respects_global_cap(tmp_path, monkeypatch):
    """Modo Global conservative (max 2%/2x) — super_aggressive NÃO viola cap."""
    from src.config import runtime_overrides as ro

    f = tmp_path / "settings.json"
    f.write_text('{"super_aggressive": true}')
    monkeypatch.setattr(ro, "_RUNTIME_SETTINGS", f)
    # Modo Global conservative: max_size_pct=0.02, max_leverage=2
    new_size, new_lev = apply_super_aggressive_to_size_lev(0.01, 1, 0.02, 2)
    # Super aggressive quer 5%/10x, mas cap é 2%/2x → fica em 2%/2x
    assert new_size == 0.02
    assert new_lev == 2


def test_super_aggressive_preserves_higher_input(tmp_path, monkeypatch):
    """Se input já é > 5%/10x, mantém (não reduz)."""
    from src.config import runtime_overrides as ro

    f = tmp_path / "settings.json"
    f.write_text('{"super_aggressive": true}')
    monkeypatch.setattr(ro, "_RUNTIME_SETTINGS", f)
    new_size, new_lev = apply_super_aggressive_to_size_lev(0.08, 15, 0.10, 20)
    assert new_size == 0.08  # input maior, preserva
    assert new_lev == 15


def test_altcoins_off_returns_original(tmp_path, monkeypatch):
    from src.config import runtime_overrides as ro

    f = tmp_path / "settings.json"
    f.write_text('{"altcoins_enabled": false}')
    monkeypatch.setattr(ro, "_RUNTIME_SETTINGS", f)
    out = expand_assets_with_altcoins(["BTC"])
    assert out == ["BTC"]


def test_altcoins_on_expands_assets(tmp_path, monkeypatch):
    from src.config import runtime_overrides as ro

    f = tmp_path / "settings.json"
    f.write_text('{"altcoins_enabled": true}')
    monkeypatch.setattr(ro, "_RUNTIME_SETTINGS", f)
    out = expand_assets_with_altcoins(["BTC"])
    assert out[0] == "BTC"  # base preservada
    for alt in ALTCOINS:
        assert alt in out


def test_altcoins_dedup_existing(tmp_path, monkeypatch):
    """Se base já tem alguma altcoin, não duplica."""
    from src.config import runtime_overrides as ro

    f = tmp_path / "settings.json"
    f.write_text('{"altcoins_enabled": true}')
    monkeypatch.setattr(ro, "_RUNTIME_SETTINGS", f)
    out = expand_assets_with_altcoins(["BTC", "ETH"])
    # ETH aparece só uma vez
    assert out.count("ETH") == 1
    assert "BTC" in out
    assert "SOL" in out


def test_altcoins_case_insensitive_dedup(tmp_path, monkeypatch):
    from src.config import runtime_overrides as ro

    f = tmp_path / "settings.json"
    f.write_text('{"altcoins_enabled": true}')
    monkeypatch.setattr(ro, "_RUNTIME_SETTINGS", f)
    out = expand_assets_with_altcoins(["btc", "sol"])  # lowercase
    # SOL não deve aparecer 2x mesmo com case diff
    upper_count = sum(1 for s in out if s.upper() == "SOL")
    assert upper_count == 1
