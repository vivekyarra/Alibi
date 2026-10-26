"""Deterministic fallback planner: behaviors B1–B6 as rules over OpenCV stage outputs (SPEC 9.3, 9.6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.policies import Action


@dataclass
class Step:
    tool: str
    args: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None = None


class FallbackPlanner:
    kind = "fallback"
    model_id: str | None = None

    def next_action(self, history: list[Step]) -> Action:
        def last(tool: str, **match: Any) -> Step | None:
            for s in reversed(history):
                if s.tool == tool and all(s.args.get(k) == v for k, v in match.items()):
                    return s
            return None

        def done(tool: str, **match: Any) -> bool:
            return last(tool, **match) is not None

        def res(s: Step | None) -> dict[str, Any]:
            return (s.result or {}) if s is not None else {}

        requested = {s.args.get("kind") for s in history if s.tool == "request_user_input"}
        verdict = last("compute_verdict")

        # ---- after the verdict: B6 or final report
        if verdict is not None:
            v = res(verdict).get("verdict")
            if v == "CONTRADICTED" and not done("request_human_review"):
                return Action("request_human_review", {}, "B6: verdict CONTRADICTED needs human approval")
            if not done("render_report"):
                final = v != "CONTRADICTED"
                return Action("render_report", {"final": final},
                              "render report" + ("" if final else " as PENDING_REVIEW (B6)"))
            return Action(None, {}, "job complete")

        probe = last("probe_video")
        if probe is None:
            return Action("probe_video", {}, "start: read metadata and timing")
        p = res(probe)
        if probe.error or p.get("hdr"):
            return Action("compute_verdict", {}, "HDR or unreadable input: stop analysis (S13 rule 1)")

        ro = last("estimate_readout")
        if ro is None:
            return Action("estimate_readout", {"method": "auto"}, "readout: sidecar, then profile, then blind")
        r = res(ro)
        if r.get("source") == "READOUT_UNKNOWN" or ro.error:
            if "camera_model" not in requested:
                return Action("request_user_input", {"kind": "camera_model", "message":
                              "Readout time is unknown. Please give the camera model and video mode."},
                              "B2: readout unknown after blind estimation")
            return Action("compute_verdict", {}, "B2: readout unknown; cannot model row timing")
        if r.get("low_confidence") and "camera_model" not in requested:
            return Action("request_user_input", {"kind": "camera_model", "message":
                          "The readout time was estimated with low confidence. Please give the camera model."},
                          f"B2: blind readout confidence {r.get('confidence')} is low")

        mo = last("analyze_motion")
        if mo is None:
            return Action("analyze_motion", {"strictness": "normal"}, "find static background")
        strict = last("analyze_motion", strictness="strict")
        if res(mo).get("high_motion") and strict is None:
            return Action("analyze_motion", {"strictness": "strict"},
                          f"B3: HIGH_MOTION (motion level {res(mo).get('motion_level')} px/frame)")
        subset = "low_motion" if strict is not None else None

        pa = last("propose_patches", strategy="all")
        if pa is None:
            return Action("propose_patches", {"strategy": "all"}, "rank light patches")
        extracts = [s for s in history if s.tool == "extract_flicker" and s.result and "track_id" in s.result]
        if not any(s.tool == "extract_flicker" for s in history):
            ids = res(pa).get("selected") or None
            return Action("extract_flicker", {"patch_ids": ids, "frame_subset": subset},
                          "first extraction on all eligible patches")
        best = max(extracts, key=lambda s: res(s).get("band_snr_db", -99)) if extracts else None
        b = res(best)
        weak = (best is None or "SIGNAL_WEAK" in b.get("reasons", []) or "SIGNAL_ABSENT" in b.get("reasons", []))
        if weak:
            if p.get("high_compression") and "original_file" not in requested:
                return Action("request_user_input", {"kind": "original_file", "message":
                              "The file is strongly compressed and the flicker signal is weak. "
                              "Please upload the original file."}, "B4: HIGH_COMPRESSION and weak signal")
            snr = b.get("band_snr_db")
            top = last("propose_patches", strategy="top")
            if top is None:
                return Action("propose_patches", {"strategy": "top"},
                              f"B1: signal weak (band SNR {snr} dB); re-rank patches")
            top_ids = res(top).get("selected") or []
            if top_ids and not any(s.args.get("patch_ids") == top_ids for s in history
                                   if s.tool == "extract_flicker"):
                return Action("extract_flicker", {"patch_ids": top_ids, "frame_subset": subset},
                              f"B1: re-extract on the {len(top_ids)} highest-SNR patches")
            f0 = b.get("nominal_flicker_hz")
            other_nominal = 60.0 if f0 == 100.0 else 50.0
            if not done("extract_flicker", nominal_hz=other_nominal):
                return Action("extract_flicker", {"patch_ids": top_ids or None, "nominal_hz": other_nominal,
                                                  "frame_subset": subset},
                              f"B1: switch nominal frequency to {other_nominal:g} Hz")
            axis = b.get("axis") or "rows+"
            other_axis = "cols+" if axis.startswith("rows") else "rows+"
            if not done("extract_flicker", axis=other_axis):
                return Action("extract_flicker", {"patch_ids": top_ids or None, "axis": other_axis,
                                                  "frame_subset": subset}, f"B1: switch sensor axis to {other_axis}")
            return Action("compute_verdict", {}, "B5: no usable signal after the alternatives")

        tid = b["track_id"]
        if not done("match_reference", track_id=tid):
            return Action("match_reference", {"track_id": tid}, f"signal usable (band SNR {b.get('band_snr_db')} "
                          "dB); match against the reference")
        if not done("check_continuity", track_id=tid):
            return Action("check_continuity", {"track_id": tid}, "check phase continuity for edits")
        if not done("face_region_check", track_id=tid):
            return Action("face_region_check", {"track_id": tid}, "experimental face-region check")
        return Action("compute_verdict", {}, "evidence complete; deterministic verdict")
