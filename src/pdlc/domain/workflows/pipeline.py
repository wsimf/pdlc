"""Whole-pipeline registration.

Every work type's pipeline data (`workflow_feature.py`, `workflow_bug.py`,
...) is declared independently; this module is the single place they're
gathered into the registry callers actually resolve against.
"""

from __future__ import annotations

from pdlc.domain.workflow import PipelineRegistry, WorkType
from pdlc.domain.workflows.workflow_bug import BUG_PIPELINE
from pdlc.domain.workflows.workflow_feature import FEATURE_PIPELINE

PIPELINE_REGISTRY = PipelineRegistry({WorkType.FEATURE: FEATURE_PIPELINE, WorkType.BUG: BUG_PIPELINE})
PIPELINES = PIPELINE_REGISTRY
