"""Data schemas for GRIDPRINT (SPEC 8.0, 8.1, 1.5).

R1: exactly three verdicts. R4: the only location field is `zone`.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Verdict(str, Enum):
    VERIFIED = "VERIFIED"
    CONTRADICTED = "CONTRADICTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class LifecycleState(str, Enum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    FINAL = "FINAL"


class Reason(str, Enum):
    SIGNAL_ABSENT = "SIGNAL_ABSENT"
    SIGNAL_WEAK = "SIGNAL_WEAK"
    READOUT_FROM_SIDECAR = "READOUT_FROM_SIDECAR"
    READOUT_FROM_PROFILE = "READOUT_FROM_PROFILE"
    READOUT_ESTIMATED = "READOUT_ESTIMATED"
    READOUT_UNKNOWN = "READOUT_UNKNOWN"
    HDR_UNSUPPORTED = "HDR_UNSUPPORTED"
    TRANSFER_ASSUMED = "TRANSFER_ASSUMED"
    TRACK_TOO_SHORT = "TRACK_TOO_SHORT"
    NO_REFERENCE_COVERAGE = "NO_REFERENCE_COVERAGE"
    NO_UNIQUE_MATCH = "NO_UNIQUE_MATCH"
    MATCH_OK = "MATCH_OK"
    CLAIM_TIME_MISMATCH = "CLAIM_TIME_MISMATCH"
    CLAIM_TIME_MATCH = "CLAIM_TIME_MATCH"
    EDIT_CANDIDATE = "EDIT_CANDIDATE"
    SEGMENT_OFFSET_INCONSISTENT = "SEGMENT_OFFSET_INCONSISTENT"
    DROPPED_FRAMES_EXPLAINED = "DROPPED_FRAMES_EXPLAINED"
    HIGH_MOTION = "HIGH_MOTION"
    HIGH_COMPRESSION = "HIGH_COMPRESSION"
    TIMESTAMP_JITTER_HIGH = "TIMESTAMP_JITTER_HIGH"
    AXIS_AMBIGUOUS = "AXIS_AMBIGUOUS"
    FACE_REGION_ANOMALY_EXPERIMENTAL = "FACE_REGION_ANOMALY_EXPERIMENTAL"
    REVIEWER_APPROVED = "REVIEWER_APPROVED"
    REVIEWER_REJECTED = "REVIEWER_REJECTED"
    USER_INPUT_REQUESTED = "USER_INPUT_REQUESTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class CaptureSidecar(BaseModel):
    """Sidecar written by GRIDPRINT Capture (SPEC 8.0, 10.3). No GPS location field (R4)."""

    model_config = ConfigDict(extra="forbid")

    app_version: str
    device_model: str
    sensor_orientation: int = Field(description="Degrees, 0/90/180/270")
    frame_sensor_timestamps_ns: list[int] = Field(description="Start of exposure of first row, per frame")
    frame_exposure_ns: list[int]
    frame_duration_ns: list[int]
    rolling_shutter_skew_ns: int
    iso: list[int] | int
    wall_clock_start_utc: str
    wall_clock_source: str
    sensor_timestamp_wall_offset_ns: int | None = Field(
        default=None, description="wall_clock_ns - sensor_timestamp_ns at start, when the source is REALTIME")
    zone: str
    video_sha256: str


class Claim(BaseModel):
    claimed_zone: str | None = None
    claimed_time_utc: str | None = None
    claimed_time_tolerance_s: float | None = None


class GapEvent(BaseModel):
    frame_index: int  # gap lies between frame_index-1 and frame_index
    t_s: float
    size_s: float


class ContinuityEvent(BaseModel):
    kind: str  # "EDIT_CANDIDATE" | "DROPPED_FRAMES_EXPLAINED"
    frame_index: int
    t_s: float
    magnitude_rad: float
    significance: float
    significant: bool
    gap_s: float | None = None


class SegmentMatch(BaseModel):
    start_s: float
    end_s: float
    offset_s: float | None
    rho1: float | None
    passes: bool


class MatchStats(BaseModel):
    zone: str
    window_start_utc: float
    window_end_utc: float
    best_offset_utc: float | None = None
    rho1: float | None = None
    rho2: float | None = None
    margin: float | None = None
    psr: float | None = None
    track_length_s: float = 0.0
    time_uncertainty_s: float | None = None
    passes: bool = False
    segments: list[SegmentMatch] = Field(default_factory=list)
    segments_consistent: bool | None = None


class FaceStats(BaseModel):
    status: str  # "ok" | "no_faces" | "model_unavailable" | "skipped"
    label: str = "EXPERIMENTAL"
    ratio: float | None = None
    significance: float | None = None
    frames_with_faces: int = 0
    anomaly: bool = False


class AnalysisResult(BaseModel):
    job_id: str
    file_sha256: str
    engine_version: str
    config_hash: str
    thresholds_hash: str
    verdict: Verdict
    lifecycle_state: LifecycleState
    reasons: list[Reason]
    time_estimate_utc: float | None = None
    time_estimate_iso: str | None = None
    time_uncertainty_s: float | None = None
    zone: str | None = None
    match: MatchStats | None = None
    continuity_events: list[ContinuityEvent] = Field(default_factory=list)
    face_region: FaceStats | None = None
    quality: dict[str, Any] = Field(default_factory=dict)
    stage_timings_s: dict[str, float] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)
    reviewer: dict[str, Any] | None = None
    notes: list[str] = Field(default_factory=list)
