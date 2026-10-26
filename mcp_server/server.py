"""`gridprint-engine` MCP server, stdio transport (SPEC 5, 9.2). Run: python -m mcp_server.server"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from mcp_server.tools import EngineTools  # noqa: E402

mcp = FastMCP("gridprint-engine")
_tools: EngineTools | None = None


def tools() -> EngineTools:
    global _tools
    if _tools is None:
        _tools = EngineTools.from_env()
    return _tools


def _out(x: dict[str, Any]) -> str:
    return json.dumps(x, default=str)


@mcp.tool()
def probe_video(job_id: str) -> str:
    """S1/S2: metadata, timestamp source, jitter, gaps, HDR flag, axis info."""
    return _out(tools().probe_video(job_id))


@mcp.tool()
def estimate_readout(job_id: str, method: str = "auto") -> str:
    """S3: readout time. method: auto | sidecar | profile | blind."""
    return _out(tools().estimate_readout(job_id, method))


@mcp.tool()
def analyze_motion(job_id: str, strictness: str = "normal") -> str:
    """S4/S5: motion level, static fraction, mask id. strictness: normal | strict."""
    return _out(tools().analyze_motion(job_id, strictness))


@mcp.tool()
def propose_patches(job_id: str, strategy: str = "all") -> str:
    """S6: ranked light patches. strategy: all | top | coherent | bright."""
    return _out(tools().propose_patches(job_id, strategy))


@mcp.tool()
def extract_flicker(job_id: str, patch_ids: list[int] | None = None, axis: str | None = None,
                    nominal_hz: float | None = None, frame_subset: list[int] | str | None = None) -> str:
    """S7/S8: band SNR, per-frame stats, track id. axis: rows+ | rows- | cols+ | cols- | auto.
    nominal_hz: grid nominal 50 or 60. frame_subset: list of frame indices or "low_motion"."""
    return _out(tools().extract_flicker(job_id, patch_ids, axis, nominal_hz, frame_subset))


@mcp.tool()
def match_reference(job_id: str, track_id: str | None = None, zone: str | None = None,
                    window: list[float] | None = None) -> str:
    """S9/S10: match statistics against the reference grid log."""
    return _out(tools().match_reference(job_id, track_id, zone, window))


@mcp.tool()
def check_continuity(job_id: str, track_id: str | None = None) -> str:
    """S11: continuity events (edit candidates, explained dropped frames)."""
    return _out(tools().check_continuity(job_id, track_id))


@mcp.tool()
def face_region_check(job_id: str, track_id: str | None = None) -> str:
    """S12 (EXPERIMENTAL): face/background band ratio."""
    return _out(tools().face_region_check(job_id, track_id))


@mcp.tool()
def compute_verdict(job_id: str, budget_exhausted: bool = False) -> str:
    """S13: deterministic verdict and reasons. Must be the last analysis call."""
    return _out(tools().compute_verdict(job_id, budget_exhausted))


@mcp.tool()
def request_user_input(job_id: str, kind: str, message: str) -> str:
    """Create a request: original_file | camera_model | claimed_time | longer_clip."""
    return _out(tools().request_user_input(job_id, kind, message))


@mcp.tool()
def request_human_review(job_id: str) -> str:
    """Create a review task for a CONTRADICTED verdict."""
    return _out(tools().request_human_review(job_id))


@mcp.tool()
def render_report(job_id: str, final: bool = True) -> str:
    """S14/S15: overlay, plots, HTML/PDF/JSON report. FINAL is blocked for PENDING_REVIEW."""
    return _out(tools().render_report(job_id, final))


if __name__ == "__main__":
    mcp.run("stdio")
