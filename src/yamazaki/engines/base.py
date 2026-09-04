"""Engine adapter input records that may briefly contain restricted SQL."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from yamazaki.contracts import EngineKind, QueryState

COLLECTOR_MARKER = "yamazaki-read-only-collector"


@dataclass(frozen=True, slots=True)
class RawQueryRecord:
    """Transient engine record; raw_sql must never be logged or persisted."""

    engine: EngineKind
    cluster_id: str
    query_id: str
    fingerprint: str | None
    state: QueryState
    started_at: datetime
    finished_at: datetime | None
    observed_at: datetime
    duration_ms: int
    queue_time_ms: int | None = None
    cpu_time_ms: int | None = None
    peak_memory_bytes: int | None = None
    scanned_rows: int | None = None
    returned_rows: int | None = None
    shuffle_bytes: int | None = None
    spill_bytes: int | None = None
    progress: float | None = None
    raw_sql: str | None = field(default=None, repr=False)
    native: dict[str, str | int | float | bool | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RawEvidence:
    """Transient evidence returned only by a fixed adapter operation."""

    source_kind: str
    summary: str
    facts: dict[str, int | float | str | bool | None]
    restricted_payload: dict[str, Any] = field(default_factory=dict, repr=False)
    available: bool = True
    gap: str | None = None
