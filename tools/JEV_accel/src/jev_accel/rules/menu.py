"""D: menu detection on a BLACK-background screenshot.

Keysight DSO-X 4034A (menu.kind = "dialog_text"): see text_stats(); a dialog over the graticule is what
spoils a report screenshot there (the softkeys and side bar sit outside the graticule).

RIGOL MSO5104 (:DISP:DATA? ON,OFF,BMP): the open menu draws a blue border around x 850-862. A row counts
as a hit when any pixel in that band has b > b_min, r < r_max, b-g > bg_min. Calibrated on the real scope 2026-10-07: the Measure menu border
is (0,44,90), so the wiki's b>120 matched 0 rows open AND closed; b>70 gives 341 open vs 0 closed.

Tektronix TDS2014B (menu.kind = "tek_graticule"): see tek_stats().
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


def text_stats(rgb: np.ndarray, c: dict) -> dict:
    """Keysight: a dialog over the graticule is transparent on the black screen (frame, title bar and
    white text; the trace shows through). A graticule row is a hit when it holds at least min_px bright
    neutral pixels (min channel >= text_min, max-min <= text_spread). Traces are colored and grid lines
    are (50,50,50). Calibrated 2026-10-12 with the LAN dialog: 203 rows open, 0 closed."""
    band = rgb[c["y0"]: c["y1"], c["x0"]: c["x1"] + 1].astype(np.int16)
    lo, hi = band.min(axis=2), band.max(axis=2)
    bright = (lo >= c["text_min"]) & (hi - lo <= c["text_spread"])
    per_row = bright.sum(axis=1)
    rows = int((per_row >= c["min_px"]).sum())
    return {
        "hit_rows": rows,
        "band_rows": int(band.shape[0]),
        "hit_frac": round(rows / max(band.shape[0], 1), 3),
        "bright_px": int(bright.sum()),
        "image_size": [int(rgb.shape[1]), int(rgb.shape[0])],
    }

def tek_stats(rgb: np.ndarray, c: dict) -> dict:
    """Tektronix TDS2014B (320x240 hardcopy, native white background HARDC:INKS ON by default, or black INKS OFF).
    The side menu has its own column right of the graticule (x 262-319), so it never covers a trace; what can
    spoil a report frame is a message or help box over the graticule. The graticule lattice sits on fixed
    coordinates (dotted lines and ticks on x % 5 == 0, major horizontal lines on y % 25 == 12, center axes on
    x 132-138 and y 111-113, frame ticks on y 13-14 / 210-211) and is masked out first. On a native white-background
    hardcopy (median > 128) a message box draws dark neutral text/frame (max channel <= 220); on a black-background
    hardcopy it draws bright neutral pixels (min channel >= text_min). Calibrated 2026-11-03 on real white and
    black screens (CH1 menu open): 0 rows; traces are colored."""
    h, w = rgb.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    lattice = ((xs % 5 == 0) | ((xs >= 132) & (xs <= 138)) | (ys % 25 == 12)
               | np.isin(ys, (13, 14, 111, 112, 113, 210, 211)))
    px = rgb.astype(np.int16)
    lo, hi = px.min(axis=2), px.max(axis=2)
    white_bg = float(np.median(px[c["y0"]: c["y1"], c["x0"]: c["x1"] + 1])) > 128.0
    level = (hi <= c.get("white_text_max", 220)) if white_bg else (lo >= c["text_min"])
    neutral = level & (hi - lo <= c["text_spread"]) & ~lattice
    band = neutral[c["y0"]: c["y1"], c["x0"]: c["x1"] + 1]
    rows = int((band.sum(axis=1) >= c["min_px"]).sum())
    return {
        "hit_rows": rows,
        "band_rows": int(band.shape[0]),
        "hit_frac": round(rows / max(band.shape[0], 1), 3),
        "bright_px": int(band.sum()),
        "image_size": [int(w), int(h)],
    }


def stats(rgb: np.ndarray, cfg: dict) -> dict:
    c = cfg["menu"]
    if c.get("kind") == "dialog_text":
        return text_stats(rgb, c)
    if c.get("kind") == "tek_graticule":
        return tek_stats(rgb, c)
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
