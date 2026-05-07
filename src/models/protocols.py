"""
src/models/protocols.py
=======================
Structural typing protocols for cross-agent communication.

These are PEP-544 Protocol classes — duck-typed interfaces that don't
require explicit inheritance. Any class that implements the listed
methods satisfies the protocol.

Use cases
---------
- Vision wants to render any Layer-1 output as a prompt section. Today
  this is a tacit convention (the model has `to_prompt_section()`).
  Making it a Protocol lets us write `isinstance(obj, Promptable)` and
  fail loudly on contract drift.
- Future: similar protocol for `Persistable` (anything with
  `to_audit_payload()`).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Promptable(Protocol):
    """Anything that can be rendered as a section in an LLM prompt."""

    def to_prompt_section(self) -> str:
        ...


@runtime_checkable
class AuditPayloadable(Protocol):
    """Anything that can be serialized into an `audit_log.payload` dict."""

    def to_audit_payload(self) -> dict:
        ...
