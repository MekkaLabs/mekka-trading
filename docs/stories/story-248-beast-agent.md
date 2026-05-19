# Story 248 — Beast: Continuous System Improvement Agent

**Milestone:** 40 — Agent Communication Upgrade  
**Status:** ✅ Implemented  
**Priority:** Medium  

## Motivation

The Mekka Trading system lacked any mechanism to continuously audit itself and surface improvement opportunities. Beast fills this gap as a read-only intelligence layer that observes system behavior and proposes evidence-based improvements.

## Character

**Beast (Dr. Hank McCoy)** — X-Men scientist. Brilliant, analytical, methodical. Observes, theorizes, proposes — never acts unilaterally.

## Architecture

```
Beast (read-only)
  ├── _analyze_trades()         → win rate, profit factor, symbol concentration
  ├── _analyze_batman_gates()   → gate firing frequency (which gates block most)
  ├── _analyze_latency()        → P50/P95/P99 pipeline latency from audit log
  ├── _analyze_signal_quality() → Vision high-conf vs low-conf win rates
  └── _send_report()            → Telegram (TelegramAlerter) if telegram_enabled
```

## Output: `BeastReport`

```python
@dataclass
class BeastReport:
    generated_at: datetime
    period_days: int
    proposals: list[ImprovementProposal]   # sorted by priority
    stats_summary: dict                    # raw stats for debugging
    total_trades_analyzed: int
    system_health_score: float             # 0-100 heuristic
```

Each `ImprovementProposal` has:
- `title`, `description`, `evidence`
- `impact`: HIGH / MEDIUM / LOW
- `area`: signal_quality / risk_gates / latency / ux / infra
- `suggested_story`: optional story candidate name

## Activation

```env
BEAST_ENABLED=true
BEAST_ANALYSIS_PERIOD_DAYS=7
BEAST_SCHEDULE_CRON=0 9 * * 1  # Monday 09:00 UTC
```

## Integration with NickFury

Beast runs out-of-band — not in the critical trading cycle. NickFury (or a separate scheduler) calls:

```python
report = await Beast().run(period_days=settings.beast_analysis_period_days)
```

## File

`src/agents/beast.py`

## Tests
- `tests/agents/test_beast.py` — unit tests for all proposal generators
- Mock `MekkaRepository` to return synthetic trade data
- Verify proposals are generated for known bad scenarios (win_rate < 0.45, etc.)
