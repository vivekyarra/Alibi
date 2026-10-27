"""Unit tests for engine stages on synthetic arrays (no video decoding)."""

from __future__ import annotations

import numpy as np
import pytest

from gridprint_engine import color, continuity, enf, match, phase, readout, rowsignal
from gridprint_engine.schemas import CaptureSidecar, GapEvent, Reason

THR = {"signal": {"snr_absent_db": 3.0, "snr_weak_db": 8.0},
       "match": {"min_track_s": 20, "rho1_min": 0.8, "margin_min": 0.05},
       "continuity": {"edit_significance_sigma": 6.0, "edit_min_rad": 0.15},
       "facecheck": {"ratio_anomaly": 0.5}}
MCFG = {"min_search_window_s": 600, "sidecar_window_s": 3600, "max_search_window_s": 172800, "exclusion_s": 10,
        "segment_length_s": 30, "segment_offset_tolerance_s": 3, "claim_min_tolerance_s": 60}


# ---------------------------------------------------------------- S2 linear light (R7)
def test_bt709_inverse_lut_inverts_oetf():
    lut = color.inverse_lut("bt709")[0]
    lin = lut.astype(np.float64)
    code = np.where(lin < 0.018, 4.5 * lin, 1.099 * lin ** 0.45 - 0.099) * 255
    assert np.max(np.abs(code - np.arange(256))) < 1e-3
    assert lut.dtype == np.float32


def test_linear_light_output_is_float32_and_monotone():
    g = np.arange(256, dtype=np.uint8).reshape(16, 16)
    out = color.to_linear(g, color.inverse_lut("srgb"))
    assert out.dtype == np.float32
    assert np.all(np.diff(out.ravel()) > 0)


def test_transfer_classification():
    assert color.classify_transfer(18) == ("hlg", False)
    assert color.classify_transfer(16) == ("pq", False)
    assert color.classify_transfer(1) == ("bt709", False)
    assert color.classify_transfer(2) == ("bt709", True)  # unspecified → TRANSFER_ASSUMED
    assert color.classify_transfer(None) == ("bt709", True)


def test_valid_mask_excludes_saturated_and_dark():
    g = np.array([[0, 5, 6, 128, 249, 250, 255]], np.uint8)
    v = color.valid_mask(g, 0.98, 0.02)
    assert v.tolist() == [[False, False, True, True, True, False, False]]


# ---------------------------------------------------------------- S3 / S8 timing and phase
def _signal(k=300, r=120, fps=30.0, T=0.025, f=100.04, amp=0.05, noise=0.002, seed=0):
    rng = np.random.default_rng(seed)
    t_frame = np.arange(k) / fps
    trows = phase.row_times(t_frame, np.zeros(k), np.arange(r, dtype=float), r, T)
    rs = amp * np.cos(2 * np.pi * f * trows + 0.3) + rng.normal(0, noise, trows.shape)
    return t_frame, trows, rs.astype(np.float32), np.ones(rs.shape, bool)


def test_row_time_model():
    t = phase.row_times(np.array([1.0]), np.array([0.002]), np.array([0.0, 99.0]), 100, 0.03)
    assert t.dtype == np.float64
    assert t[0, 0] == pytest.approx(1.001)
    assert t[0, 1] == pytest.approx(1.031)


def test_frame_fit_recovers_phase_and_track():
    t_frame, trows, rs, mk = _signal()
    ff = phase.frame_fits(rs, mk, trows, 100.0)
    assert ff.amp.dtype == np.float64 and ff.phi.dtype == np.float64  # R6
    assert np.median(ff.amp) == pytest.approx(0.05, rel=0.05)
    tk = phase.phase_track(ff, t_frame, 100.0, 4.0, 1.0, 0.0, mk.sum(1))
    assert np.allclose(tk.flicker_hz, 100.04, atol=2e-3)
    assert np.allclose(tk.enf_hz, 50.02, atol=1e-3)


def test_estimators_agree_on_clean_data():
    t_frame, trows, rs, mk = _signal(k=600)
    ff = phase.frame_fits(rs, mk, trows, 100.0)
    tk = phase.phase_track(ff, t_frame, 100.0, 4.0, 1.0, 0.0, mk.sum(1))
    d = phase.dft_estimate(rs, mk, trows, 100.0, 8)
    assert abs(d.peak_hz - tk.mean_flicker_hz) <= 0.01


def test_idle_gaps_are_zero_filled_not_interpolated():
    t_frame, trows, rs, mk = _signal(k=20, T=0.020)  # 20 ms readout, 33 ms frame → 13 ms idle per frame
    x, filled = phase.virtual_time_grid(rs, mk, trows, 800.0)
    assert (~filled).sum() > 0
    assert np.all(x[~filled] == 0.0)
    # every idle stretch lies between frames: no filled bin falls inside an idle interval
    tb = np.arange(len(x)) / 800.0 + trows.min()
    for k in range(19):
        idle = (tb > trows[k, -1] + 1 / 800.0) & (tb < trows[k + 1, 0] - 1 / 800.0)
        assert not np.any(filled & idle)


def test_blind_readout_finds_true_value():
    t_frame, trows, rs, mk = _signal(k=150, T=0.021)
    r = readout.blind_estimate(rs, mk, t_frame, np.zeros(150), np.arange(120, dtype=float), 120, 100.0, 0.004,
                               1 / 30, 40)
    assert r.reason == Reason.READOUT_ESTIMATED
    assert r.readout_s == pytest.approx(0.021, rel=0.03)


def test_readout_priority_sidecar_then_profile():
    sc = CaptureSidecar(app_version="t", device_model="X", sensor_orientation=90, frame_sensor_timestamps_ns=[0],
                        frame_exposure_ns=[1], frame_duration_ns=[1], rolling_shutter_skew_ns=24_000_000, iso=100,
                        wall_clock_start_utc="2026-01-01T00:00:00+00:00", wall_clock_source="t", zone="IN",
                        video_sha256="0" * 64)
    assert readout.from_sidecar(sc).reason == Reason.READOUT_FROM_SIDECAR
    prof = {readout.profile_key("X", 1920, 1080, 30.0): {"readout_s": 0.03, "uncertainty_s": 0.001}}
    r = readout.from_profile(prof, "X", 1920, 1080, 29.97)
    assert r is not None and r.reason == Reason.READOUT_FROM_PROFILE and r.readout_s == 0.03
    assert readout.from_profile(prof, "Y", 1920, 1080, 30) is None


# ---------------------------------------------------------------- S7 row signal
def test_fractional_modulation_float32_and_static_scene():
    rng = np.random.default_rng(1)
    k, h, w = 30, 12, 10
    scene = rng.uniform(0.2, 0.8, (h, w)).astype(np.float32)
    gain = (1 + 0.1 * np.cos(np.arange(k)[:, None] * 2.1 + np.arange(h)[None, :] * 0.5)).astype(np.float32)
    lin = scene[None] * gain[:, :, None]
    mod = rowsignal.fractional_modulation(lin, np.ones(lin.shape, bool), None, None, 15)
    assert mod.m.dtype == np.float32
    rs, mk = rowsignal.row_signal(mod, np.ones(lin.shape, bool), "rows", 4, 0)
    assert rs.shape == (k, h) and mk.all()
    # columns axis reduces the other way
    rs2, _ = rowsignal.row_signal(mod, np.ones(lin.shape, bool), "cols", 4, 0)
    assert rs2.shape == (k, w)


def test_window_mean_compensation_removes_residual():
    k, r = 40, 50
    t = phase.row_times(np.arange(k) / 30.0, np.zeros(k), np.arange(r, dtype=float), r, 0.025)
    g = 1 + 0.1 * np.cos(2 * np.pi * 100 * t)
    keep = np.ones(k, bool)
    keep[18:23] = False  # dropped frames break the cancellation of the window mean
    g = g[keep]
    mk = np.ones(g.shape, bool)
    from gridprint_engine.rowsignal import _window_mean

    gbar = _window_mean(g.astype(np.float32)[:, :, None], mk.astype(np.float32)[:, :, None], 15)[:, :, 0]
    m = g / gbar - 1
    model = g - 1
    fixed = rowsignal.compensate_window_mean(m.astype(np.float32), mk, model, 15)
    assert np.max(np.abs(fixed - model)) < 1e-5
    assert np.max(np.abs(m - model)) > 1e-3


# ---------------------------------------------------------------- S9 / S10
def _ref(n=7200, seed=3, t0=1_700_000_000):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = 0.98 * x[i - 1] + rng.normal(0, 0.004)
    return np.arange(t0, t0 + n, dtype=np.int64), 50 + x


def test_clock_bias_removal():
    x = np.array([50.01, 50.02, 50.03])
    assert np.allclose(enf.remove_clock_bias(x), [-0.01, 0, 0.01])
    assert enf.remove_clock_bias(x).dtype == np.float64


def test_reference_window_mean_exact_and_gap_aware():
    t = np.arange(100, 110, dtype=np.int64)
    f = np.arange(10, dtype=np.float64)
    assert enf.reference_window_mean(t, f, np.array([102.0]), 2.0)[0] == pytest.approx(1.5)
    t2 = np.delete(t, 5)
    f2 = np.delete(f, 5)
    assert np.isnan(enf.reference_window_mean(t2, f2, np.array([105.0]), 2.0)[0])


def test_match_finds_offset_with_clock_bias():
    ref_t, ref_f = _ref()
    start = float(ref_t[3000]) + 0.0
    tau = np.arange(2.0, 118.0, 1.0)
    true = enf.reference_window_mean(ref_t, ref_f, start + tau, 4.0)
    rng = np.random.default_rng(9)
    video = true + 0.0025 + rng.normal(0, 0.0004, len(tau))  # constant clock bias + noise
    w = match.Window(float(ref_t[0]) + 10, float(ref_t[-1]) - 200, "max")
    ms, reasons, _ = match.match_track(tau, video, ref_t, ref_f, "SIM50", w, MCFG, THR, 4.0)
    assert ms.passes and Reason.MATCH_OK in reasons
    assert ms.best_offset_utc == pytest.approx(start, abs=1.0)


def test_match_no_coverage():
    ref_t, ref_f = _ref(n=100)
    tau = np.arange(2.0, 40.0)
    w = match.Window(1.0, 50.0, "max")
    _, reasons, _ = match.match_track(tau, np.full(len(tau), 50.0), ref_t, ref_f, "SIM50", w, MCFG, THR, 4.0)
    assert reasons == [Reason.NO_REFERENCE_COVERAGE]


def test_search_window_priority():
    assert match.search_window(1000.0, 30.0, 5000.0, 9000.0, MCFG).source == "claim"
    w = match.search_window(1000.0, 30.0, None, None, MCFG)
    assert (w.start_utc, w.end_utc) == (400.0, 1600.0)  # max(tol, minimum)
    assert match.search_window(None, None, 5000.0, 9000.0, MCFG).source == "sidecar"
    assert match.search_window(None, None, None, 9000.0, MCFG).source == "max"
    assert match.search_window(None, None, None, None, MCFG) is None


# ---------------------------------------------------------------- S11 continuity
def _phase_series(k=900, fps=30.0, jump_at=None, jump=0.0, gap_at=None, seed=2):
    rng = np.random.default_rng(seed)
    t = np.arange(k) / fps
    if gap_at is not None:
        t = np.delete(t, range(gap_at, gap_at + 5))  # dropped frames, true timestamps kept
    phi = 2 * np.pi * 0.02 * t + rng.normal(0, 0.01, len(t))
    if jump_at is not None:
        phi[jump_at:] += jump
    return t, phi


def test_cut_is_edit_candidate():
    t, phi = _phase_series(jump_at=400, jump=0.6)
    res = continuity.check_continuity(t, phi, [], 4.0, THR["continuity"])
    ed = [e for e in res.events if e.kind == "EDIT_CANDIDATE"]
    assert len(ed) == 1 and ed[0].frame_index == 400
    assert Reason.EDIT_CANDIDATE in res.reasons


def test_dropped_frames_with_true_timestamps_not_flagged():
    t, phi = _phase_series(gap_at=300)
    gaps = [GapEvent(frame_index=300, t_s=float(t[300]), size_s=float(t[300] - t[299] - 1 / 30))]
    res = continuity.check_continuity(t, phi, gaps, 4.0, THR["continuity"])
    assert not any(e.kind == "EDIT_CANDIDATE" for e in res.events)
    assert Reason.DROPPED_FRAMES_EXPLAINED in res.reasons



def test_edit_event_time_is_in_clip_time_not_sensor_time():
    # spliced clip: sensor timestamps come from another recording (offset by about -1470 s); the reported event
    # time must be the boundary's position inside the clip (eval defect B, insert_other_time__s1191)
    t, phi = _phase_series(jump_at=400, jump=0.6)
    res = continuity.check_continuity(t - 1470.0, phi, [], 4.0, THR["continuity"], t_clip=t)
    ed = [e for e in res.events if e.kind == "EDIT_CANDIDATE"]
    assert len(ed) == 1 and ed[0].frame_index == 400
    assert ed[0].t_s == pytest.approx(t[400])
    assert all(b["t_s"] >= 0 for b in res.boundaries)
    assert res.residual_t.min() >= 0


def test_timing_clip_times_follow_pts_when_sensor_timestamps_jump():
    from gridprint_engine import io

    k, dt = 120, 1 / 30
    pts = np.arange(k) * dt
    sensor_s = pts.copy()
    sensor_s[60:] = pts[60:] - 1500.0  # inserted footage keeps its own (earlier) sensor timestamps
    ns = [int(round((v + 2000.0) * 1e9)) for v in sensor_s]
    sc = CaptureSidecar(app_version="t", device_model="t", sensor_orientation=0, frame_sensor_timestamps_ns=ns,
                        frame_exposure_ns=[1_000_000] * k, frame_duration_ns=[33_333_333] * k,
                        rolling_shutter_skew_ns=25_000_000, iso=100, wall_clock_start_utc="2026-01-01T00:00:00+00:00",
                        wall_clock_source="test", zone="SIM50", video_sha256="0" * 64)
    tm = io.compute_timing(pts, sc, 1.5)
    assert tm.source == "sensor" and tm.t_s[60] < -1000
    np.testing.assert_allclose(tm.clip_times(), pts)
    assert all(0 <= g.t_s <= pts[-1] for g in tm.gaps)

# ---------------------------------------------------------------- S4 motion
def test_motion_static_scene_with_moving_bands_is_static():
    from gridprint_engine import motion

    rng = np.random.default_rng(4)
    import cv2

    scene = cv2.GaussianBlur(rng.uniform(0.2, 0.8, (240, 320)).astype(np.float32), (0, 0), 2)
    k = 12
    rows = np.arange(240)[None, :, None]
    gain = 1 + 0.1 * np.cos(2 * np.pi * (rows / 60.0 + np.arange(k)[:, None, None] / 3.0))
    lin = (scene[None] * gain).astype(np.float32)
    m = motion.analyze_motion(lin, 1.0, 1.5, 400, downscale_width=160)
    assert m.static.shape == lin.shape
    assert m.static_fraction > 0.9 and not m.high_motion and m.homs is None


def test_motion_camera_pan_gives_homographies():
    import cv2

    from gridprint_engine import motion

    rng = np.random.default_rng(5)
    world = cv2.GaussianBlur(rng.uniform(0.2, 0.8, (300, 400)).astype(np.float32), (0, 0), 1.5)
    lin = np.stack([world[20:260, 20 + 2 * i:340 + 2 * i] for i in range(10)]).astype(np.float32)
    m = motion.analyze_motion(lin, 1.0, 1.5, 400, downscale_width=160)
    assert m.homs is not None
    assert abs(m.homs[0][0, 2] - m.homs[-1][0, 2]) > 10  # ~18 px pan over 9 frames
