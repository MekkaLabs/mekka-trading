# Story 005 - Exchange Capability Validator

## Goal

Introduce exchange capability contract validation before execution routing, with hard blocking on incompatibility.

## Delivered

- Hyperliquid capability contract v1
- Connector handshake capabilities payload
- Capability validator with version and feature checks
- Runtime integration with pre-execution validation gate
- Automatic mission blocking and kill switch on incompatibility
- Unit tests for validator and runtime compatibility signal

## Checklist

- [x] Capability contract defined
- [x] Handshake implemented in connector
- [x] Validator implemented
- [x] Runtime gate integrated pre-execution
- [x] Hard block on incompatibility
- [x] Tests added
- [x] Paper-only safety preserved

## Next

- Add signed capability manifests
- Add compatibility matrix by exchange adapter version
- Add preflight report export for mission approval
