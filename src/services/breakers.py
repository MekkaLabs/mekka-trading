"""
src/services/breakers.py
========================
Consecutive-event circuit breakers (Story 029a — Safety Net).

A `ConsecutiveBreaker` watches a stream of boolean observations (hit /
no-hit). Each `observe(hit=True)` increments an internal streak; each
`observe(hit=False)` resets it. When the streak reaches `threshold`,
the breaker is **TRIPPED** and the caller is expected to take action
(typically engage the kill switch).

The breaker itself is **passive** — it does not engage the kill switch
or write to audit log. Separation of concerns: the breaker counts; the
orchestrator decides what to do when it trips. This keeps the service
free of agent dependencies and easier to test.

Usage
-----
    breaker = ConsecutiveBreaker(name="exec_error", threshold=3)
    if breaker.observe(execution.status == ExecutionStatus.ERROR):
        engage_kill_switch(f"3 consecutive exec errors")
        await audit.log_event(...)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConsecutiveBreaker:
    """Stateful counter of consecutive boolean hits."""

    name: str
    threshold: int
    streak: int = 0
    trip_count: int = 0  # how many times the breaker has tripped lifetime

    def __post_init__(self) -> None:
        if self.threshold < 1:
            raise ValueError(f"threshold must be >= 1, got {self.threshold}")

    def observe(self, hit: bool) -> bool:
        """
        Record one observation. Returns True iff this observation tripped
        the breaker (i.e. streak crossed threshold on this call).
        """
        if hit:
            self.streak += 1
            if self.streak == self.threshold:
                # Trip exactly once per crossing; further hits keep streak
                # incrementing but don't re-trip until a reset happens.
                self.trip_count += 1
                return True
            return False
        # Non-hit resets the streak
        self.streak = 0
        return False

    def reset(self) -> None:
        """Manually clear the streak (used after kill switch is released)."""
        self.streak = 0

    @property
    def is_armed(self) -> bool:
        """True when the breaker is currently above zero (warm)."""
        return self.streak > 0

    def summary(self) -> str:
        return (
            f"[Breaker:{self.name}] streak={self.streak}/{self.threshold} "
            f"trips_lifetime={self.trip_count}"
        )
