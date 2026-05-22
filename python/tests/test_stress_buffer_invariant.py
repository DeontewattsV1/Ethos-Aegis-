"""
Regression test for PR #27 review finding 🟡:

> "Stress buffer blocked verdict has is_condemned=True but
>  sovereignty_depth=GRAVE, violating the invariant"

The rest of the pipeline keeps two fields in lockstep:

    is_condemned  ⇔  sovereignty_depth.value >= CorruptionDepth.CONDEMNED.value

The NeuroStressBuffer block path in AegisVitality.adjudicate_with_vitality()
was producing a synthetic verdict that set is_condemned=True but kept
sovereignty_depth=GRAVE (value 3), breaking that invariant. Downstream
telemetry (e.g. sentinel_ai.summary()) reads sovereignty_depth and would
report "GRAVE" while the verdict was treated as condemned, creating
inconsistent monitoring data.

The fix is to set sovereignty_depth=CONDEMNED on the rate-limited verdict.
This test pins that.
"""
from __future__ import annotations

import pytest

from ethos_aegis.core.aegis import CorruptionDepth
from ethos_aegis.vitality.protocol import AegisVitality, NeuroStressBuffer


@pytest.fixture
def vitality_with_jammed_buffer(monkeypatch):
    """
    Build an AegisVitality whose NeuroStressBuffer always denies acquisition,
    forcing the synthetic-condemned-verdict path that the invariant guards.
    """
    av = AegisVitality()

    def deny(self) -> tuple[bool, float]:
        return False, 0.0

    monkeypatch.setattr(NeuroStressBuffer, "acquire", deny, raising=True)
    return av


def test_rate_limited_verdict_keeps_is_condemned_in_sync_with_depth(
    vitality_with_jammed_buffer,
):
    av = vitality_with_jammed_buffer
    verdict, _observations = av.adjudicate_with_vitality("anything")

    # 1. The verdict is treated as condemned by the calling pipeline.
    assert verdict.is_condemned is True

    # 2. The invariant is satisfied: depth.value >= CONDEMNED.value.
    assert (
        verdict.sovereignty_depth.value >= CorruptionDepth.CONDEMNED.value
    ), (
        f"is_condemned=True but sovereignty_depth={verdict.sovereignty_depth!r} "
        f"(value={verdict.sovereignty_depth.value}) — must be >= "
        f"CONDEMNED (value={CorruptionDepth.CONDEMNED.value}). "
        "This is the exact invariant violation PR #27 flagged."
    )

    # 3. The verdict explicitly carries the CONDEMNED depth (not just any
    #    value above the threshold) — this is what downstream telemetry reads.
    assert verdict.sovereignty_depth == CorruptionDepth.CONDEMNED


def test_rate_limited_verdict_is_not_sanctified(vitality_with_jammed_buffer):
    """Sanity check: a blocked request must never be sanctified."""
    av = vitality_with_jammed_buffer
    verdict, _ = av.adjudicate_with_vitality("anything")
    assert verdict.is_sanctified is False
