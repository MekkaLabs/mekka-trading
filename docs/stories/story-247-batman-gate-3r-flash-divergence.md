# Story 247 — Batman Gate 3r: Flash Momentum Divergence

**Milestone:** 40 — Agent Communication Upgrade  
**Status:** ✅ Implemented  
**Priority:** High  

## Problem

Flash's STRONG momentum signal opposing a trade direction was a known risk factor but had no enforcement at the Batman risk gate level. Vision might produce a LONG signal while Flash signals STRONG DOWN — Batman had no mechanism to respond to this divergence.

## Solution

### `src/agents/batman.py` — Gate 3r (after gate 3q)

**New soft gate** that checks Flash divergence:
- Gets `analysis.momentum` (MomentumSignal from Flash)
- If Flash is STRONG and its direction opposes the signal action:
  - Records advisory reason `[3r]` in `reasons`
  - Sets `_flash_size_reduction_pct = settings.flash_divergence_size_reduction` (default 30%)
- In **Section 5** (size adjustment), applies the reduction: `size_pct × (1 - 0.30)`
- Gate is **soft** — it adjusts size but does NOT veto/reject the trade
- Fails open on any error (missing data, import error, etc.)

### `_run()` signature
Added `analysis: Optional[object] = None` parameter so NickFury can pass the full `MarketAnalysis`.

### `src/agents/nick_fury.py`
Updated `self._batman.run(...)` call to pass `analysis=analysis`.

### `src/config/settings.py`
Added `flash_divergence_size_reduction: float = 0.30` (configurable, 0.0 disables gate).

## Tests
- `tests/agents/test_batman_gate_3r.py` — verify size reduction on divergence, no reduction on confirmation

## Configuration
```env
FLASH_DIVERGENCE_SIZE_REDUCTION=0.30  # 30% size reduction on Flash divergence
```

## Impact
When Flash signals STRONG momentum opposing the trade, position size is automatically reduced by 30%, limiting exposure to momentum-divergence risk without blocking the trade entirely.
