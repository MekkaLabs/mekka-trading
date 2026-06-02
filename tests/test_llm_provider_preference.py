"""
tests/test_llm_provider_preference.py
=====================================
Preferência de provider do LLMClient (2026-06-02): Anthropic preferencial,
OpenAI como fallback (configurável via settings.llm_prefer_anthropic).
"""

from __future__ import annotations

import pytest

from src.agents.llm_client import LLMClient


def test_prefer_anthropic_order_when_both_present():
    c = LLMClient(openai_key="sk-x", anthropic_key="sk-ant-x", prefer_anthropic=True)
    assert c._provider_order() == ["anthropic", "openai"]
    assert c.active_provider.startswith("anthropic/")


def test_prefer_openai_order_when_flag_false():
    c = LLMClient(openai_key="sk-x", anthropic_key="sk-ant-x", prefer_anthropic=False)
    assert c._provider_order() == ["openai", "anthropic"]
    assert c.active_provider.startswith("openai/")


def test_falls_through_to_available_provider():
    # prefere anthropic mas só openai está configurado → usa openai
    c = LLMClient(openai_key="sk-x", anthropic_key="", prefer_anthropic=True)
    assert c._provider_order() == ["openai"]
    assert c.active_provider.startswith("openai/")


def test_only_anthropic_configured():
    c = LLMClient(openai_key="", anthropic_key="sk-ant-x", prefer_anthropic=True)
    assert c._provider_order() == ["anthropic"]


def test_no_provider_configured():
    c = LLMClient(openai_key="", anthropic_key="", prefer_anthropic=True)
    assert c._provider_order() == []
    assert c.active_provider == "none"


@pytest.mark.asyncio
async def test_chat_tries_anthropic_first_then_falls_back(monkeypatch):
    """Anthropic falha → cai para OpenAI; o conteúdo da OpenAI é retornado."""
    c = LLMClient(openai_key="sk-x", anthropic_key="sk-ant-x", prefer_anthropic=True)
    calls = []

    async def fake_anthropic(sp, up, model_override=None):
        calls.append("anthropic")
        raise RuntimeError("anthropic indisponível")

    async def fake_openai(sp, up, model_override=None):
        calls.append("openai")
        return '{"ok": true}', 10, 5

    monkeypatch.setattr(c, "_call_anthropic", fake_anthropic)
    monkeypatch.setattr(c, "_call_openai", fake_openai)

    out = await c.chat("sys", "user")
    assert out == '{"ok": true}'
    assert calls == ["anthropic", "openai"]   # tentou anthropic primeiro


@pytest.mark.asyncio
async def test_chat_uses_anthropic_when_it_succeeds(monkeypatch):
    c = LLMClient(openai_key="sk-x", anthropic_key="sk-ant-x", prefer_anthropic=True)
    calls = []

    async def fake_anthropic(sp, up, model_override=None):
        calls.append("anthropic")
        return '{"from": "claude"}', 8, 4

    async def fake_openai(sp, up, model_override=None):
        calls.append("openai")
        return '{"from": "gpt"}', 8, 4

    monkeypatch.setattr(c, "_call_anthropic", fake_anthropic)
    monkeypatch.setattr(c, "_call_openai", fake_openai)

    out = await c.chat("sys", "user")
    assert out == '{"from": "claude"}'
    assert calls == ["anthropic"]   # nem chamou openai
