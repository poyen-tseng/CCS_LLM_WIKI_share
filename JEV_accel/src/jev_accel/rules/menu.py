"""D: side-menu detection on a BLACK-background screenshot (:DISP:DATA? ON,OFF,BMP).

The open menu draws a blue border around x 850-862. A row counts as a hit when any pixel in that band
has b > b_min, r < r_max, b-g > bg_min. Calibrated on the real scope 2026-10-07: the Measure menu border
is (0,44,90), so the wiki's b>120 matched 0 rows open AND closed; b>70 gives 341 open vs 0 closed.
"""
from __future__ import annotations

import io
import struct

import numpy as np
from PIL import Image


def bmp_to_array(bmp: bytes) -> np.ndarray:
    """Decode the screenshot bytes (BMP from the MSO5000, or PNG/any Pillow format) to HxWx3 RGB."""
    if bmp[:2] != b"BM":
        return np.asarray(Image.open(io.BytesIO(bmp)).convert("RGB"))
    offset = struct.unpack_from("<I", bmp, 10)[0]
    width, height = struct.unpack_from("<ii", bmp, 18)
    bpp = struct.unpack_from("<H", bmp, 28)[0]
    if bpp not in (24, 32):
        raise ValueError(f"unsupported BMP bit depth {bpp}")
    bottom_up = height > 0
    height = abs(height)
    bytes_pp = bpp // 8
    stride = (width * bytes_pp + 3) & ~3
    rows = np.frombuffer(bmp, dtype=np.uint8, count=stride * height, offset=offset).reshape(height, stride)
    px = rows[:, : width * bytes_pp].reshape(height, width, bytes_pp)[:, :, 2::-1]
    return px[::-1] if bottom_up else px


def stats(rgb: np.ndarray, cfg: dict) -> dict:
    c = cfg["menu"]
    band = rgb[c["y0"]: c["y1"], c["x0"]: c["x1"] + 1].astype(np.int16)
    r, g, b = band[..., 0], band[..., 1], band[..., 2]
    hit = (b > c["b_min"]) & (r < c["r_max"]) & (b - g > c["bg_min"])
    rows = int(hit.any(axis=1).sum())
    return {
        "hit_rows": rows,
        "band_rows": int(band.shape[0]),
        "hit_frac": round(rows / max(band.shape[0], 1), 3),
        "mean_blue": round(float(b.mean()), 1),
        "image_size": [int(rgb.shape[1]), int(rgb.shape[0])],
    }


def classify(s: dict, cfg: dict) -> bool | None:
    """True = open, False = closed, None = ambiguous (ask Jev)."""
    c = cfg["menu"]
    if s["hit_rows"] > c["open_rows"]:
        return True
    if s["hit_rows"] < c["closed_rows"]:
        return False
    return None
