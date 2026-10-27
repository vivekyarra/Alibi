"""Engine pipeline: one `Job` holds the state of an analysis; each public method is one stage group and
backs one MCP tool (SPEC 9.2). `run_default` is the plain non-adaptive sequence (tests, bench)."""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from gridprint_engine import continuity as s11
from gridprint_engine import facecheck as s12
from gridprint_engine import io as s1
from gridprint_engine import match as s10
from gridprint_engine import motion as s4
from gridprint_engine import patches as s6
from gridprint_engine import phase as s8
from gridprint_engine import readout as s3
from gridprint_engine import rowsignal as s7
from gridprint_engine import segment as s5
from gridprint_engine import verdict as s13
from gridprint_engine.adapters import GridLogAdapter
from gridprint_engine.config import Settings, settings
from gridprint_engine.schemas import (
    AnalysisResult,
    CaptureSidecar,
    Claim,
    FaceStats,
    LifecycleState,
    MatchStats,
    Reason,
    Verdict,
)

ORIENTATIONS = ["rows+", "rows-", "cols+", "cols-"]


@dataclass
class FlickerTrack:
    id: str
    orientation: str
    f0: float
    readout_s: float
    patch_ids: list[int]
    frame_subset: list[int] | None
    rs: np.ndarray
    mask: np.ndarray
    t_rows: np.ndarray
    fits: s8.FrameFits
    track: s8.Track
    dft: s8.DftEstimate
    snr_db: float
    estimators_agree: bool
    reasons: set[Reason]
    candidates: dict[str, float] = field(default_factory=dict)


class JobError(RuntimeError):
    pass


class Job:
    def __init__(self, video: Path, workdir: Path, gridlog: GridLogAdapter, job_id: str | None = None,
                 sidecar: Path | None = None, claim: Claim | None = None, device_model: str | None = None,
                 cfg: Settings | None = None):
        self.id = job_id or uuid.uuid4().hex[:12]
        self.video = Path(video)
        self.workdir = Path(workdir) / self.id
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.gridlog = gridlog
        self.sidecar_path = Path(sidecar) if sidecar else None
        self.claim = claim or Claim()
        self.device_model = device_model
        self.cfg = cfg or settings()
        self.E = self.cfg.engine
        self.reasons: set[Reason] = set()
        self.notes: list[str] = []
        self.timings: dict[str, float] = {}
        self.quality: dict[str, Any] = {}
        self.sha256 = ""
        self.sidecar: CaptureSidecar | None = None
        self.probe: s1.Probe | None = None
        self.timing: s1.Timing | None = None
        self.stack: s1.FrameStack | None = None
        self.readout: s3.Readout | None = None
        self.motion: s4.MotionResult | None = None
        self.seg: s5.SegmentationResult | None = None
        self.mod: s7.Modulation | None = None
        self.static_sel: np.ndarray | None = None
        self.patchset: s6.PatchSet | None = None
        self.tracks: dict[str, FlickerTrack] = {}
        self.matches: dict[str, tuple[MatchStats, list[Reason], Any]] = {}
        self.continuity: dict[str, s11.ContinuityResult] = {}
        self.faces: dict[str, FaceStats] = {}
        self.stopped = False
        self.result: AnalysisResult | None = None
        self.artifacts: dict[str, str] = {}
        self.reviewer: dict[str, Any] | None = None

    # ------------------------------------------------------------------ helpers
    @contextmanager
    def _timed(self, stage: str):  # type: ignore[no-untyped-def]
        t = time.perf_counter()
        try:
            yield
        finally:
            self.timings[stage] = self.timings.get(stage, 0.0) + time.perf_counter() - t

    def _require(self, *names: str) -> None:
        for n in names:
            if getattr(self, n) is None:
                raise JobError(f"stage order: '{n}' is not available yet")

    @property
    def zone_hint(self) -> str | None:
        if self.claim.claimed_zone:
            return self.claim.claimed_zone
        if self.sidecar is not None:
            return self.sidecar.zone
        return None

    # ------------------------------------------------------------------ S1 + S2
    def probe_video(self) -> dict[str, Any]:
        with self._timed("S1_ingest"):
            self.sha256 = s1.sha256_file(self.video)
            sc, notes = s1.load_sidecar(self.sidecar_path, self.sha256)
            self.sidecar = sc
            self.notes += notes
            self.probe = pr = s1.probe_video(self.video)
            pts = s1.read_pts(self.video)
            self.timing = tm = s1.compute_timing(pts, sc, self.E["gap_factor"])
            if tm.jitter_p95_ms > self.E["timestamp_jitter_p95_limit_ms"]:
                self.reasons.add(Reason.TIMESTAMP_JITTER_HIGH)
            if pr.transfer_assumed:
                self.reasons.add(Reason.TRANSFER_ASSUMED)
            if pr.bits_per_pixel() < self.E["compression"]["high_bits_per_pixel"]:
                self.reasons.add(Reason.HIGH_COMPRESSION)
        self.quality.update({
            "codec": pr.codec, "width": pr.width, "height": pr.height, "frames": len(tm.t_s),
            "bitrate": pr.bitrate, "bits_per_pixel": pr.bits_per_pixel(), "transfer": pr.transfer,
            "rotation_metadata_deg": pr.rotation, "timestamp_source": tm.source,
            "jitter_p50_ms": tm.jitter_p50_ms, "jitter_p95_ms": tm.jitter_p95_ms,
            "timing_assumption": tm.assumption, "opencv_frame_count": pr.cv_frame_count,
            "gaps": [g.model_dump() for g in tm.gaps],
        })
        out = {"metadata": {k: self.quality[k] for k in ("codec", "width", "height", "frames", "bitrate",
                                                         "transfer", "rotation_metadata_deg")},
               "timestamp_source": tm.source, "jitter_p95_ms": round(tm.jitter_p95_ms, 3),
               "gaps": len(tm.gaps), "hdr": pr.hdr, "high_compression": Reason.HIGH_COMPRESSION in self.reasons,
               "sidecar": sc is not None, "notes": notes,
               "axis_info": "sidecar: sensor rows = coded rows" if sc else "unknown: both axes tested in S8"}
        if pr.hdr:
            self.reasons.add(Reason.HDR_UNSUPPORTED)
            self.stopped = True
            return out
        with self._timed("S2_linear"):
            self.stack = s1.decode_frames(self.video, pr.transfer, self.E["analysis_max_height"],
                                          self.E["analysis_max_width"], self.E["saturation_cutoff"],
                                          self.E["noise_floor"])
        if self.stack.lin.shape[0] != len(tm.t_s):
            raise JobError("decoded frame count differs from timestamp count")
        return out

    # ------------------------------------------------------------------ S3
    def estimate_readout(self, method: str = "auto") -> dict[str, Any]:
        self._require("probe")
        assert self.probe is not None
        if self.stopped:
            return {"stopped": True}
        r: s3.Readout | None = None
        with self._timed("S3_readout"):
            if method in ("auto", "sidecar"):
                r = s3.from_sidecar(self.sidecar)
            if r is None and method in ("auto", "profile"):
                dev = self.sidecar.device_model if self.sidecar else self.device_model
                r = s3.from_profile(self.cfg.profiles, dev, self.probe.width, self.probe.height,
                                    self.probe.avg_fps)
            if r is None and method in ("auto", "blind"):
                r = self._blind_readout()
        if r is None:
            r = s3.Readout(None, Reason.READOUT_UNKNOWN, 0.0)
        for rr in (Reason.READOUT_FROM_SIDECAR, Reason.READOUT_FROM_PROFILE, Reason.READOUT_ESTIMATED,
                   Reason.READOUT_UNKNOWN):
            self.reasons.discard(rr)
        self.reasons.add(r.reason)
        self.readout = r
        self.quality["readout_s"] = r.readout_s
        self.quality["readout_source"] = r.reason.value
        low = r.reason == Reason.READOUT_ESTIMATED and r.confidence < self.E["readout_estimated_min_coherence"]
        return {"readout_s": r.readout_s, "source": r.reason.value, "confidence": round(r.confidence, 4),
                "low_confidence": low}

    def _blind_readout(self) -> s3.Readout:
        self._ensure_modulation()
        assert self.stack is not None and self.timing is not None and self.mod is not None
        frame_period = self.timing.median_dt_s
        best: s3.Readout | None = None
        for f0 in self._f0_candidates():
            for ori in self._orientation_candidates():
                rs, mk, pos, n = self._rows_for(ori, self._full_selection(), None)
                est = s3.blind_estimate(rs, mk, self.timing.t_s, self.timing.exposure_s, pos, n, f0,
                                        self.E["readout_min_s"], frame_period, self.E["readout_search_steps"])
                if est.readout_s is not None and (best is None or est.confidence > best.confidence):
                    best = est
        return best or s3.Readout(None, Reason.READOUT_UNKNOWN, 0.0)

    # ------------------------------------------------------------------ S4 + S5 (+ S7 modulation)
    def analyze_motion(self, strictness: str = "normal") -> dict[str, Any]:
        self._require("stack")
        assert self.stack is not None
        mc = self.E["motion"]
        with self._timed("S4_motion"):
            self.motion = s4.analyze_motion(self.stack.lin, mc["residual_limit_px"], mc["high_motion_px"],
                                            mc["max_features"], strictness, mc["strict_residual_limit_px"],
                                            mc["camera_static_px"], mc["downscale_width"])
        with self._timed("S5_segment"):
            if self.seg is None:
                sc = self.E["segmentation"]
                self.seg = s5.segment_people(self.stack.gray8, sc["model_path"], tuple(sc["input_size"]),
                                             sc["every_n_frames"])
        self.reasons.discard(Reason.HIGH_MOTION)
        if self.motion.high_motion:
            self.reasons.add(Reason.HIGH_MOTION)
        self.mod = None
        self._ensure_modulation()
        self.quality.update({"motion_level_px": self.motion.motion_level_px,
                             "camera_motion_px": self.motion.camera_motion_px,
                             "static_fraction": self.motion.static_fraction,
                             "segmentation": self.seg.status if self.seg else "skipped",
                             "foreground_fraction": self.seg.foreground_fraction if self.seg else 0.0})
        return {"motion_level": round(self.motion.motion_level_px, 4),
                "static_fraction": round(self.motion.static_fraction, 4),
                "high_motion": self.motion.high_motion, "strictness": strictness,
                "mask_id": f"{self.id}:{strictness}", "segmentation": self.seg.status if self.seg else "skipped",
                "low_motion_frames": None if self.motion.frame_subset is None else len(self.motion.frame_subset)}

    def _ensure_modulation(self) -> None:
        if self.mod is not None:
            return
        assert self.stack is not None
        static = None
        homs = None
        if self.motion is not None:
            static = self.motion.static.copy()
            homs = self.motion.homs
            if self.seg is not None and self.seg.foreground is not None:
                static &= ~self.seg.foreground
        with self._timed("S7_rowsignal"):
            self.mod = s7.fractional_modulation(self.stack.lin, self.stack.valid, static, homs,
                                                self.E["rowsignal"]["window_frames"])
        self.static_sel = static if static is not None else np.ones_like(self.stack.valid)

    def _full_selection(self) -> np.ndarray:
        assert self.stack is not None
        return np.ones(self.stack.lin.shape, bool)

    def _f0_candidates(self, nominal_hz: float | None = None) -> list[float]:
        if nominal_hz:
            return [2.0 * float(nominal_hz)]
        nz = self.cfg.nominal_hz(self.zone_hint)
        return [2.0 * nz] if nz else [100.0, 120.0]

    def _orientation_candidates(self) -> list[str]:
        return ["rows+"] if self.sidecar is not None else list(ORIENTATIONS)

    def _rows_for(self, ori: str, sel: np.ndarray,
                  frame_subset: list[int] | None) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
        assert self.stack is not None and self.mod is not None
        axis = "rows" if ori.startswith("rows") else "cols"
        rc = self.E["rowsignal"]
        rs, mk = s7.row_signal(self.mod, sel, axis, rc["min_pixels_per_row"], rc["detrend_order"])
        if frame_subset is not None:
            keep = np.zeros(rs.shape[0], bool)
            keep[np.asarray(frame_subset, int)] = True
            mk &= keep[:, None]
        if axis == "rows":
            idx, n = self.stack.row_index, self.stack.n_rows
        else:
            idx, n = self.stack.col_index, self.stack.n_cols
        pos = idx if ori.endswith("+") else (n - 1) - idx
        return rs, mk, pos, n

    # ------------------------------------------------------------------ S6
    def propose_patches(self, strategy: str = "all") -> dict[str, Any]:
        self._require("stack", "readout")
        assert self.stack is not None and self.readout is not None
        self._ensure_modulation()
        assert self.mod is not None
        pc = self.E["patches"]
        with self._timed("S6_patches"):
            if self.patchset is None:
                self.patchset = s6.make_patches(self.stack.lin, self.mod.ok, self.stack.sat, tuple(pc["grid"]),
                                                pc["min_static_fraction"], pc["min_mean_linear"],
                                                pc["max_saturation_fraction"])
                if self.readout.readout_s is not None:
                    first = self._extract(None, None, None, None, store=False)
                    if first is not None:
                        sel = self._full_selection()
                        axis = "rows" if first.orientation.startswith("rows") else "cols"
                        s6.score_patches(self.patchset, self.mod, sel, axis, first.t_rows, first.fits.phi,
                                         first.fits.ok, first.f0)
            ids = s6.choose(self.patchset, strategy)
        ranked = [{"id": p, "score_db": round(next(q.score_db for q in self.patchset.patches if q.id == p) or -99, 2)}
                  for p in self.patchset.ranked]
        return {"strategy": strategy, "selected": ids, "ranked": ranked[:16],
                "eligible": sum(p.eligible for p in self.patchset.patches),
                "total": len(self.patchset.patches)}

    # ------------------------------------------------------------------ S7 + S8
    def extract_flicker(self, patch_ids: list[int] | None = None, axis: str | None = None,
                        nominal_hz: float | None = None, frame_subset: list[int] | str | None = None
                        ) -> dict[str, Any]:
        self._require("stack", "readout")
        assert self.readout is not None
        if self.readout.readout_s is None:
            return {"error": "readout unknown", "reasons": [Reason.READOUT_UNKNOWN.value]}
        if frame_subset == "low_motion":
            frame_subset = None if self.motion is None or self.motion.frame_subset is None \
                else [int(i) for i in self.motion.frame_subset]
        with self._timed("S8_phase"):
            tr = self._extract(patch_ids, axis, nominal_hz,
                               frame_subset if isinstance(frame_subset, list) else None, store=True)
        assert tr is not None
        return {"track_id": tr.id, "band_snr_db": round(tr.snr_db, 3), "axis": tr.orientation,
                "nominal_flicker_hz": tr.f0, "frames_used": int(tr.fits.ok.sum()),
                "track_samples": len(tr.track.tau_s), "mean_flicker_hz": round(tr.track.mean_flicker_hz, 5),
                "dft_peak_hz": round(tr.dft.peak_hz, 5), "estimators_agree": tr.estimators_agree,
                "reasons": sorted(r.value for r in tr.reasons), "candidates": tr.candidates}

    def _extract(self, patch_ids: list[int] | None, axis: str | None, nominal_hz: float | None,
                 frame_subset: list[int] | None, store: bool) -> FlickerTrack | None:
        assert self.stack is not None and self.timing is not None and self.readout is not None
        assert self.readout.readout_s is not None
        self._ensure_modulation()
        if patch_ids is not None and self.patchset is not None:
            sel = s6.selection_mask(self.patchset, patch_ids,
                                    self.motion.homs if self.motion else None, self.stack.lin.shape[0])
        else:
            sel = self._full_selection()
        oris = [axis] if axis in ORIENTATIONS else self._orientation_candidates()
        T = self.readout.readout_s
        pc = self.E["phase"]
        jit = self.timing.jitter_p50_ms * 1e-3
        cands: list[tuple[bool, float, str, float, Any]] = []
        for f0 in self._f0_candidates(nominal_hz):
            for ori in oris:
                rs, mk, pos, n = self._rows_for(ori, sel, frame_subset)
                trows = s8.row_times(self.timing.t_s, self.timing.exposure_s, pos, n, T)
                ffb = s8.frame_fits(rs, mk, trows, f0, use_opencv=False)
                tk = s8.phase_track(ffb, self.timing.t_s, f0, pc["window_s"], pc["hop_s"], jit, mk.sum(1))
                # Per-frame fits cannot tell the readout direction (phase is free per frame); the wrong
                # direction shows up as a track offset by the flicker alias rate. A grid deviates by
                # well under 1 Hz, so a flicker track more than 2 Hz from f0 is not plausible.
                plausible = bool(np.isfinite(tk.mean_flicker_hz) and abs(tk.mean_flicker_hz - f0) <= 2.0)
                cands.append((plausible, s8.band_snr_db(ffb), ori, f0, (rs, mk, trows)))
        cands.sort(key=lambda c: (not c[0], -c[1]))
        _, snr, ori, f0, (rs, mk, trows) = cands[0]
        # flicker-compensated temporal mean (DECISIONS D-015): two correction passes, then the final fit
        win = self.E["rowsignal"]["window_frames"]
        rs0 = rs
        for _ in range(2):
            ffc = s8.frame_fits(rs, mk, trows, f0, use_opencv=False)
            model = s8.flicker_model(ffc, trows, f0)
            rs = s7.compensate_window_mean(rs0, mk, model, win)
        ff = s8.frame_fits(rs, mk, trows, f0, use_opencv=True)  # final fit with cv2.solve
        snr = s8.band_snr_db(ff)
        reasons: set[Reason] = set()
        if len(oris) > 1:
            other = [c for c in cands if c[2][:4] != ori[:4] and c[3] == f0 and c[0]]
            if other and 10 ** ((snr - other[0][1]) / 10) < self.E["axis_ambiguity_margin"]:
                reasons.add(Reason.AXIS_AMBIGUOUS)
        thr = self.cfg.thresholds["signal"]
        if snr < thr["snr_absent_db"]:
            reasons.add(Reason.SIGNAL_ABSENT)
        elif snr < thr["snr_weak_db"]:
            reasons.add(Reason.SIGNAL_WEAK)
        track = s8.phase_track(ff, self.timing.t_s, f0, pc["window_s"], pc["hop_s"], jit, mk.sum(1))
        dft = s8.dft_estimate(rs, mk, trows, f0, pc["dft_virtual_rate_factor"])
        agree = bool(abs(dft.peak_hz - track.mean_flicker_hz) <= pc["estimator_agreement_hz"])
        tid = f"t{len(self.tracks) + 1}"
        ft = FlickerTrack(id=tid, orientation=ori, f0=f0, readout_s=T, patch_ids=list(patch_ids or []),
                          frame_subset=frame_subset, rs=rs, mask=mk, t_rows=trows, fits=ff, track=track, dft=dft,
                          snr_db=float(snr), estimators_agree=agree, reasons=reasons,
                          candidates={f"{c[2]}@{c[3]:g}": round(c[1], 2) for c in cands})
        if not agree and Reason.SIGNAL_ABSENT not in reasons:
            self.notes.append(f"{tid}: phase and DFT estimators differ by "
                              f"{abs(dft.peak_hz - track.mean_flicker_hz):.4f} Hz; confidence lowered")
        if store:
            self.tracks[tid] = ft
        return ft

    def primary_track(self) -> FlickerTrack | None:
        if not self.tracks:
            return None
        return max(self.tracks.values(), key=lambda t: t.snr_db)

    # ------------------------------------------------------------------ S9 + S10
    def match_reference(self, track_id: str | None = None, zone: str | None = None,
                        window: tuple[float, float] | None = None) -> dict[str, Any]:
        tr = self.tracks.get(track_id) if track_id else self.primary_track()
        if tr is None:
            raise JobError("no flicker track")
        if Reason.SIGNAL_ABSENT in tr.reasons or len(tr.track.tau_s) < 3:
            ms = MatchStats(zone=zone or self.zone_hint or "unknown", window_start_utc=0, window_end_utc=0,
                            track_length_s=float(len(tr.track.tau_s)))
            rs = [Reason.TRACK_TOO_SHORT] if Reason.SIGNAL_ABSENT not in tr.reasons else []
            self.matches[tr.id] = (ms, rs, None)
            return {"track_id": tr.id, "passes": False, "reasons": [r.value for r in rs], "skipped": "no signal"}
        mc = self.E["match"]
        zones = [zone] if zone else ([self.zone_hint] if self.zone_hint else
                                     [z for z, d in self.cfg.zones.items() if 2 * d["nominal_hz"] == tr.f0])
        best: tuple[MatchStats, list[Reason], Any] | None = None
        claim_t = _parse_utc(self.claim.claimed_time_utc)
        wall = self.timing.wall_start_utc if self.timing else None
        with self._timed("S10_match"):
            for z in zones:
                if z is None:
                    continue
                if window is not None:
                    w = s10.Window(window[0], window[1], "agent")
                else:
                    latest = self._latest_reference(z)
                    w0 = s10.search_window(claim_t, self.claim.claimed_time_tolerance_s, wall, latest, mc)
                    if w0 is None:
                        continue
                    w = w0
                ref_t, ref_f = self.gridlog.read(z, w.start_utc - 10, w.end_utc + tr.track.tau_s[-1] + 10)
                ms, rs, scan = s10.match_track(tr.track.tau_s, tr.track.enf_hz, ref_t, ref_f, z, w, mc,
                                               self.cfg.thresholds, self.E["phase"]["window_s"])
                if best is None or (ms.rho1 or -2) > (best[0].rho1 or -2):
                    best = (ms, rs, scan)
        if best is None:
            ms = MatchStats(zone=zone or self.zone_hint or "unknown", window_start_utc=0, window_end_utc=0)
            best = (ms, [Reason.NO_REFERENCE_COVERAGE], None)
        self.matches[tr.id] = best
        ms, rs, _ = best
        return {"track_id": tr.id, "zone": ms.zone, "passes": ms.passes, "best_offset_utc": ms.best_offset_utc,
                "rho1": ms.rho1, "rho2": ms.rho2, "margin": ms.margin, "psr": ms.psr,
                "track_length_s": ms.track_length_s, "time_uncertainty_s": ms.time_uncertainty_s,
                "segments_consistent": ms.segments_consistent, "reasons": [r.value for r in rs]}

    def _latest_reference(self, zone: str) -> float | None:
        latest = getattr(self.gridlog, "latest", None)
        if callable(latest):
            v = latest(zone)
            return float(v) if v is not None else None
        return None

    # ------------------------------------------------------------------ S11
    def check_continuity(self, track_id: str | None = None) -> dict[str, Any]:
        tr = self.tracks.get(track_id) if track_id else self.primary_track()
        if tr is None or self.timing is None:
            raise JobError("no flicker track")
        if Reason.SIGNAL_ABSENT in tr.reasons:
            # without a signal the phase is noise; reporting phase breaks would be meaningless (and R2)
            res = s11.ContinuityResult([], np.zeros(0), np.zeros(0), [])
            self.continuity[tr.id] = res
            return {"track_id": tr.id, "events": [], "edit_candidates": 0, "dropped_explained": 0, "reasons": [],
                    "skipped": "no signal"}
        # only frames whose own flicker fit is usable enter the phase series
        phi = np.where(tr.fits.snr >= self.E["continuity"]["min_frame_snr"], tr.track.phase_unwrapped, np.nan)
        with self._timed("S11_continuity"):
            res = s11.check_continuity(self.timing.t_s, phi, self.timing.gaps,
                                       self.E["continuity"]["jump_window_s"], self.cfg.thresholds["continuity"])
        self.continuity[tr.id] = res
        return {"track_id": tr.id, "events": [e.model_dump() for e in res.events][:50],
                "edit_candidates": sum(e.kind == "EDIT_CANDIDATE" for e in res.events),
                "dropped_explained": sum(e.kind == "DROPPED_FRAMES_EXPLAINED" for e in res.events),
                "reasons": [r.value for r in res.reasons]}

    # ------------------------------------------------------------------ S12
    def face_region_check(self, track_id: str | None = None) -> dict[str, Any]:
        tr = self.tracks.get(track_id) if track_id else self.primary_track()
        if tr is None or self.stack is None or self.mod is None:
            raise JobError("no flicker track")
        fc = self.E["facecheck"]
        with self._timed("S12_face"):
            faces = s12.detect_faces(self.stack.gray8, fc["model_path"], fc["score_threshold"], fc["every_n_frames"])
            axis = "rows" if tr.orientation.startswith("rows") else "cols"
            assert self.static_sel is not None
            st = s12.face_region_check(self.mod, self.static_sel, faces, axis, tr.t_rows, tr.fits.phi, tr.fits.ok,
                                       tr.f0, self.cfg.thresholds["facecheck"]["ratio_anomaly"])
        self.faces[tr.id] = st
        return {"track_id": tr.id, **st.model_dump()}

    # ------------------------------------------------------------------ S13
    def compute_verdict(self, extra_reasons: list[Reason] | None = None) -> dict[str, Any]:
        reasons = set(self.reasons) | set(extra_reasons or [])
        tr = self.primary_track()
        match_passes = False
        significant_edit = False
        ms: MatchStats | None = None
        face: FaceStats | None = None
        within: bool | None = None
        events = []
        if not (self.stopped or tr is None):  # without a track, rule 5 (INCONCLUSIVE) applies
            assert tr is not None
            reasons |= tr.reasons
            if tr.id in self.matches:
                ms, mr, _ = self.matches[tr.id]
                reasons |= set(mr)
                match_passes = ms.passes
            if tr.id in self.continuity:
                c = self.continuity[tr.id]
                reasons |= set(c.reasons)
                events = c.events
                significant_edit = any(e.kind == "EDIT_CANDIDATE" and e.significant for e in c.events)
            face = self.faces.get(tr.id)
            claim_t = _parse_utc(self.claim.claimed_time_utc)
            if claim_t is not None and ms is not None and ms.best_offset_utc is not None:
                tol = self.claim.claimed_time_tolerance_s or self.E["match"]["claim_min_tolerance_s"]
                within = abs(ms.best_offset_utc - claim_t) <= tol + (ms.time_uncertainty_s or 0.0)
        out = s13.decide(s13.VerdictInputs(
            reasons=reasons, match_passes=match_passes, claim_present=self.claim.claimed_time_utc is not None,
            claim_within_tolerance=within, significant_edit=significant_edit,
            face_anomaly=bool(face and face.anomaly)))
        t_est = ms.best_offset_utc if (ms is not None and ms.passes) else None
        self.result = AnalysisResult(
            job_id=self.id, file_sha256=self.sha256, engine_version=self.E["version"],
            config_hash=self.cfg.config_hash, thresholds_hash=self.cfg.thresholds_hash,
            verdict=out.verdict, lifecycle_state=out.state, reasons=out.reasons,
            time_estimate_utc=t_est,
            time_estimate_iso=datetime.fromtimestamp(t_est, tz=UTC).isoformat() if t_est is not None else None,
            time_uncertainty_s=ms.time_uncertainty_s if (ms is not None and ms.passes) else None,
            zone=ms.zone if (ms is not None and ms.passes) else None, match=ms, continuity_events=events,
            face_region=face, quality={**self.quality, **self._track_quality(tr)},
            stage_timings_s={k: round(v, 4) for k, v in self.timings.items()}, artifacts=dict(self.artifacts),
            notes=list(self.notes))
        self.result.quality["verdict_rule"] = out.rule
        from gridprint_engine import report as s15

        s15.write_json(self, self.workdir)  # the verdict is stored even if no report is rendered
        return {"verdict": out.verdict.value, "lifecycle_state": out.state.value,
                "reasons": [r.value for r in out.reasons], "rule": out.rule}

    def _track_quality(self, tr: FlickerTrack | None) -> dict[str, Any]:
        if tr is None:
            return {}
        return {"track_id": tr.id, "axis": tr.orientation, "nominal_flicker_hz": tr.f0, "band_snr_db": tr.snr_db,
                "estimators_agree": tr.estimators_agree, "dft_peak_hz": tr.dft.peak_hz,
                "phase_mean_flicker_hz": tr.track.mean_flicker_hz, "patch_ids": tr.patch_ids,
                "track_samples": int(len(tr.track.tau_s)), "readout_s": tr.readout_s}

    # ------------------------------------------------------------------ S14 + S15
    def render_report(self, final: bool = True) -> dict[str, Any]:
        if self.result is None:
            raise JobError("compute_verdict must run before render_report")
        from gridprint_engine import overlay as s14
        from gridprint_engine import report as s15

        if final:
            if self.result.lifecycle_state == LifecycleState.PENDING_REVIEW:
                raise JobError("FINAL report blocked: CONTRADICTED requires human review (R3)")
            self.result.lifecycle_state = s13.finalize_without_review(self.result.verdict,
                                                                      self.result.lifecycle_state)
        with self._timed("S14_overlay"):
            if self.stack is not None and self.mod is not None:
                ov = s14.render_overlay(self, self.workdir / "overlay.mp4")
                if ov:
                    self.artifacts["overlay_mp4"] = str(ov)
        with self._timed("S15_report"):
            self.artifacts.update(s15.write_report(self, self.workdir))
        self.result.artifacts = dict(self.artifacts)
        self.result.stage_timings_s = {k: round(v, 4) for k, v in self.timings.items()}
        s15.write_json(self, self.workdir)
        return {"artifacts": dict(self.artifacts), "lifecycle_state": self.result.lifecycle_state.value}

    def apply_review(self, approve: bool, reviewer: str, note: str) -> AnalysisResult:
        assert self.result is not None
        v, st, rs = s13.apply_review(self.result.verdict, self.result.lifecycle_state, approve, self.result.reasons)
        self.result.verdict, self.result.lifecycle_state, self.result.reasons = v, st, rs
        self.reviewer = {"name": reviewer, "time_utc": datetime.now(tz=UTC).isoformat(), "note": note,
                         "decision": "approve" if approve else "reject"}
        self.result.reviewer = self.reviewer
        return self.result


def _parse_utc(s: str | None) -> float | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def run_default(video: Path, workdir: Path, gridlog: GridLogAdapter, sidecar: Path | None = None,
                claim: Claim | None = None, render: bool = False, cfg: Settings | None = None,
                job_id: str | None = None) -> Job:
    """Plain sequence S1–S13 (+S14/S15 if render). No adaptation; the agent adds that (Part 9)."""
    job = Job(video, workdir, gridlog, sidecar=sidecar, claim=claim, cfg=cfg, job_id=job_id)
    job.probe_video()
    if not job.stopped:
        job.estimate_readout("auto")
        if job.readout and job.readout.readout_s is not None:
            job.analyze_motion("normal")
            job.propose_patches("all")
            job.extract_flicker()
            job.match_reference()
            job.check_continuity()
            job.face_region_check()
    job.compute_verdict()
    if render and job.result is not None and job.result.verdict != Verdict.CONTRADICTED:
        job.render_report(final=True)
    elif render:
        job.render_report(final=False)
    return job
