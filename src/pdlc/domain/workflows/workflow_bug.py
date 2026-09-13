"""Bug pipeline wiring.

The Bug vocabulary and evidence contract are intentionally not guessed from
Feature. Keeping a registered unavailable entry makes resolution explicit
while the real Bug pipeline is designed.
"""

from __future__ import annotations

from pdlc.domain.workflow import Pipeline, WorkType

BUG_PIPELINE = Pipeline(work_type=WorkType.BUG, stages=(), available=False)
