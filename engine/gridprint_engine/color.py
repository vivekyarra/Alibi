"""Stage S2 — linear light (SPEC 8.3, R7).

Luma code values are converted to linear luminance with an inverse-transfer lookup table
(`cv2.LUT`, float32). HDR transfers stop the analysis.
"""

from __future__ import annotations

import cv2
import numpy as np

# FFmpeg AVColorTransferCharacteristic codes (verified in docs/VERIFICATION.md V10)
TRC_BT709 = 1
TRC_UNSPECIFIED = 2
TRC_SMPTE170M = 6
TRC_LINEAR = 8
TRC_SRGB = 13
TRC_BT2020_10 = 14
TRC_BT2020_12 = 15
TRC_PQ = 16
TRC_HLG = 18
HDR_TRC = {TRC_PQ, TRC_HLG}
BT709_LIKE = {TRC_BT709, TRC_SMPTE170M, TRC_BT2020_10, TRC_BT2020_12}


def classify_transfer(trc: int | None) -> tuple[str, bool]:
    """Return (transfer name used, assumed?)."""
    if trc in HDR_TRC:
        return ("pq" if trc == TRC_PQ else "hlg"), False
    if trc in BT709_LIKE:
        return "bt709", False
    if trc == TRC_SRGB:
        return "srgb", False
    if trc == TRC_LINEAR:
        return "linear", False
    return "bt709", True


def inverse_lut(transfer: str) -> np.ndarray:
    """256-entry float32 table: full-range 8-bit luma code → linear luminance."""
    v = np.arange(256, dtype=np.float64) / 255.0
    if transfer == "bt709":
        lin = np.where(v < 0.081, v / 4.5, np.power((v + 0.099) / 1.099, 1 / 0.45))
    elif transfer == "srgb":
        lin = np.where(v <= 0.04045, v / 12.92, np.power((v + 0.055) / 1.055, 2.4))
    elif transfer == "linear":
        lin = v
    else:
        raise ValueError(f"no SDR inverse for transfer {transfer}")
    return lin.astype(np.float32).reshape(1, 256)


def to_linear(gray_u8: np.ndarray, lut: np.ndarray) -> np.ndarray:
    """Apply the inverse transfer with OpenCV LUT. Output float32 (R6)."""
    out = cv2.LUT(gray_u8, lut)
    assert out.dtype == np.float32
    return out


def valid_mask(gray_u8: np.ndarray, saturation_cutoff: float, noise_floor: float) -> np.ndarray:
    hi = int(np.ceil(saturation_cutoff * 255))
    lo = int(np.floor(noise_floor * 255))
    return (gray_u8 < hi) & (gray_u8 > lo)
