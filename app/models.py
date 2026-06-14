from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


@dataclass
class DailySales:
    gross: float = 0.0
    vat20: float = 0.0
    vat10: float = 0.0
    vat5: float = 0.0
    vat7: float = 0.0
    checks: int = 0
    positions: int = 0

    @property
    def net(self) -> float:
        return self.gross - self.vat20 - self.vat10 - self.vat5 - self.vat7


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"


@dataclass
class ReportJob:
    id: str
    store: str
    month: str
    source: str
    status: JobStatus = JobStatus.queued
    file_path: Path | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None
