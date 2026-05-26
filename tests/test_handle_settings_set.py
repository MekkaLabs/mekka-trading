"""Tests — POST /api/settings (bug fix 2026-05-25).

Background: o endpoint aceitava qualquer body e só lia ``super_aggressive``
e ``altcoins_enabled``. Quando o operador enviava ``global_mode`` no body
(achando que o endpoint mudaria o Modo Global), o campo era silenciosamente
ignorado e o servidor respondia ``status: ok`` — o operador ficava sem
saber que o modo não tinha mudado.

Fix:
  1. Campos não reconhecidos retornam 400 com lista de aceitos
  2. ``mode`` ou ``global_mode`` no body delega para runtime_mode.set_mode
     (mesmo comportamento de POST /api/mode), emite MODE_CHANGED audit
  3. Resposta inclui ``mode_changed`` para confirmação explícita
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp.test_utils import TestClient, TestServer


def _make_server():
    from src.dashboard.server import MekkaDashboardServer
    return MekkaDashboardServer()


async def _post(server, path: str, body: dict):
    client = TestClient(TestServer(server.app))
    await client.start_server()
    try:
        resp = await client.post(path, json=body)
        data = await resp.json()
        return resp.status, data
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_settings_set_rejects_unknown_fields(tmp_path, monkeypatch):
    """Body com campo desconhecido → 400 com lista de campos aceitos."""
    from src.persistence.repository import MekkaRepository
    await MekkaRepository.initialize()

    server = _make_server()
    # Isolar arquivo de settings runtime — não contamina projeto real
    monkeypatch.setattr(server, "_load_runtime_settings", lambda: {
        "super_aggressive": False, "altcoins_enabled": False
    })
    monkeypatch.setattr(server, "_save_runtime_settings", lambda c: None)

    status, data = await _post(server, "/api/settings", {
        "super_aggressive": True,
        "unknown_field": "x",
        "yet_another": 42,
    })

    assert status == 400
    assert "unknown_field" in data.get("unknown_fields", [])
    assert "yet_another" in data.get("unknown_fields", [])
    assert "super_aggressive" in data.get("accepted_fields", [])
    assert "mode" in data.get("accepted_fields", [])


@pytest.mark.asyncio
async def test_settings_set_accepts_mode_field(tmp_path, monkeypatch):
    """``mode`` no body delega para runtime_mode.set_mode."""
    from src.persistence.repository import MekkaRepository
    await MekkaRepository.initialize()

    server = _make_server()
    monkeypatch.setattr(server, "_load_runtime_settings", lambda: {
        "super_aggressive": False, "altcoins_enabled": False
    })
    monkeypatch.setattr(server, "_save_runtime_settings", lambda c: None)

    mock_set_mode = MagicMock(return_value={"label": "Conservative", "max_position_size_pct": 0.005})
    monkeypatch.setattr("src.config.runtime_mode.set_mode", mock_set_mode)

    status, data = await _post(server, "/api/settings", {
        "mode": "conservative",
    })

    assert status == 200, f"esperado 200, recebido {status}: {data}"
    assert data.get("status") == "ok"
    assert data.get("mode_changed") == "conservative"
    mock_set_mode.assert_called_once_with("conservative")


@pytest.mark.asyncio
async def test_settings_set_accepts_global_mode_alias(tmp_path, monkeypatch):
    """``global_mode`` é alias de ``mode`` (compatibilidade com UI)."""
    from src.persistence.repository import MekkaRepository
    await MekkaRepository.initialize()

    server = _make_server()
    monkeypatch.setattr(server, "_load_runtime_settings", lambda: {
        "super_aggressive": False, "altcoins_enabled": False
    })
    monkeypatch.setattr(server, "_save_runtime_settings", lambda c: None)

    mock_set_mode = MagicMock(return_value={"label": "Balanced"})
    monkeypatch.setattr("src.config.runtime_mode.set_mode", mock_set_mode)

    status, data = await _post(server, "/api/settings", {
        "global_mode": "balanced",
    })

    assert status == 200
    assert data.get("mode_changed") == "balanced"
    mock_set_mode.assert_called_once_with("balanced")


@pytest.mark.asyncio
async def test_settings_set_invalid_mode_returns_400(tmp_path, monkeypatch):
    """Modo inválido → 400 com lista de modos aceitos."""
    from src.persistence.repository import MekkaRepository
    await MekkaRepository.initialize()

    server = _make_server()
    monkeypatch.setattr(server, "_load_runtime_settings", lambda: {
        "super_aggressive": False, "altcoins_enabled": False
    })
    monkeypatch.setattr(server, "_save_runtime_settings", lambda c: None)

    status, data = await _post(server, "/api/settings", {
        "mode": "yolo",  # not in VALID_MODES
    })

    assert status == 400
    assert "yolo" in data.get("error", "").lower() or "inválido" in data.get("error", "").lower()


@pytest.mark.asyncio
async def test_settings_set_toggles_only_still_works(tmp_path, monkeypatch):
    """Body só com toggles (backward compat) — ainda funciona."""
    from src.persistence.repository import MekkaRepository
    await MekkaRepository.initialize()

    server = _make_server()
    saved = {}
    monkeypatch.setattr(server, "_load_runtime_settings", lambda: {
        "super_aggressive": False, "altcoins_enabled": False
    })
    monkeypatch.setattr(server, "_save_runtime_settings", lambda c: saved.update(c))

    status, data = await _post(server, "/api/settings", {
        "super_aggressive": True,
        "altcoins_enabled": True,
    })

    assert status == 200
    assert data.get("settings", {}).get("super_aggressive") is True
    assert data.get("settings", {}).get("altcoins_enabled") is True
    assert data.get("mode_changed") is None  # não mexeu no modo
    assert saved.get("super_aggressive") is True
