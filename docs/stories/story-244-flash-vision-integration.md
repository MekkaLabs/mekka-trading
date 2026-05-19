# Story 244 — Flash → Vision Integration

**Milestone:** 40 — Agent Communication Upgrade  
**Status:** ✅ Implemented  
**Priority:** High  

## Problem

Flash (intra-candle momentum scalper) feeds its `MomentumSignal` into `MarketAnalysis.momentum`, and this data is rendered in the Vision prompt via `_momentum_prompt_section()`. However, Vision had **no behavioral instructions** on how to act on Flash's output. The data was displayed but never translated into actionable guidance.

Additionally, Vision's `_SYSTEM_PROMPT` listed only 6 agents — Flash was invisible to Vision's reasoning framework.

## Solution

### `src/models/market_data.py` — `_momentum_prompt_section()`
Enhanced to include explicit behavioral instructions after the data block:

- **Flash STRONG UP + LONG signal** → entry timing confirmed, no size adjustment
- **Flash STRONG UP + SHORT signal** → reduce `size_pct` by 20% (momentum divergence)
- **Flash STRONG DOWN + SHORT signal** → entry timing confirmed
- **Flash STRONG DOWN + LONG signal** → reduce `size_pct` by 20%
- **Flash SIDEWAYS** → reduce confidence by 0.05 for any directional trade
- **Flash weak signal** → treat as mild supporting signal only

### `src/agents/vision.py` — `_SYSTEM_PROMPT`
- Added Flash as the **7th agent** in the agent roster
- Added **Decision Principle #8** formalizing Flash momentum guidance

## Tests
- `tests/agents/test_vision_prompt.py` — verify Flash behavioral guidance appears in prompt
- `tests/models/test_market_data_prompt.py` — verify all Flash direction scenarios render correctly

## Impact
Vision now has a clear, rule-based framework for integrating intra-candle momentum into its decisions, reducing momentum divergence trades.
