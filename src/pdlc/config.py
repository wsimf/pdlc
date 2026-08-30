"""Configuration values shared by the command-line boundary."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    repository: str | None = None
    project_number: str | None = None
    project_owner: str | None = None
    backend: str | None = None
    home: str | None = None

    @classmethod
    def from_environment(cls) -> "Config":
        return cls(
            repository=os.environ.get("PDLC_REPOSITORY"),
            project_number=os.environ.get("PDLC_PROJECT_NUMBER"),
            project_owner=os.environ.get("PDLC_PROJECT_OWNER"),
            backend=os.environ.get("PDLC_BACKEND"),
            home=os.environ.get("PDLC_HOME"),
        )
