"""Photo of the filled sheet -> one transparent PNG per character (alpha mask, trimmed sideways)."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from make_sheet import CELL, CELLS, H, MARKS, PAD, W, cell_origin

S = 2                  # flattened page is (W*S) x (H*S) = A4 at 300 DPI
MIN_GLYPHS = 20


class ExtractionError(Exception):
    """Raised with a message that is safe to show to the user."""


def _find_markers(gray):
    """Return the 4 corner square centres in the photo, ordered TL, TR, BL, BR."""
    h, w = gray.shape
    _, bw = cv2.threshold(cv2.GaussianBlur(gray, (5, 5), 0), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    found = []
    for c in cv2.findContours(bw, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, cw, ch = cv2.boundingRect(c)
        if ch and 0.8 < cw / ch < 1.25 and cv2.contourArea(c) > 0.85 * cw * ch and 0.01 * w < cw < 0.15 * w:
            found.append((cw, x + cw / 2, y + ch / 2))
    msg = "Could not find the 4 black corner squares. Show the whole page, flat, well lit, with nothing covering the corners."
    if len(found) < 4:
        raise ExtractionError(msg)
    biggest = max(f[0] for f in found)
    found = [f for f in found if f[0] > 0.5 * biggest]
    pts = [min(found, key=lambda f, c=corner: (f[1] - c[0]) ** 2 + (f[2] - c[1]) ** 2)[1:] for corner in ((0, 0), (w, 0), (0, h), (w, h))]
    if len(set(pts)) < 4:
        raise ExtractionError(msg)
    return np.float32(pts)


def _clean(crop):
    """Drop specks and leftover box edges. Returns None when the box is empty."""
    n, lab, stats, _ = cv2.connectedComponentsWithStats(crop, connectivity=8)
    ch, cw = crop.shape
    keep = np.zeros_like(crop)
    for k in range(1, n):
        _, _, w, h, area = stats[k]
        if area < 25 or (w >= 0.9 * cw and h <= 10) or (h >= 0.9 * ch and w <= 10):
            continue
        keep[lab == k] = 255
    return keep if keep.any() else None


def extract(image_bytes, out_dir):
    """Write char_<ascii>_<variant>.png files into out_dir. Returns {'found': [...], 'missing': [...]}."""
    gray = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ExtractionError("That file is not a readable image.")
    if max(gray.shape) > 3500:
        f = 3500 / max(gray.shape)
        gray = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)

    M = cv2.getPerspectiveTransform(_find_markers(gray), np.float32(MARKS) * S)
    page = cv2.warpPerspective(gray, M, (W * S, H * S), flags=cv2.INTER_CUBIC, borderValue=255)
    ink = cv2.adaptiveThreshold(cv2.GaussianBlur(page, (3, 3), 0), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY_INV, 61, 28)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    found, missing = [], []
    for i, (char, var) in enumerate(CELLS):
        x, y = cell_origin(i)
        crop = ink[(y + PAD) * S:(y + CELL - PAD) * S, (x + PAD) * S:(x + CELL - PAD) * S]
        mask = _clean(crop)
        if mask is None:
            if var == 0:
                missing.append(char)
            continue
        cols = np.flatnonzero(mask.any(axis=0))
        mask = mask[:, cols[0]:cols[-1] + 1]                  # trim sideways only: baseline row stays fixed
        alpha = cv2.GaussianBlur(mask, (3, 3), 0)
        rgba = np.dstack([np.zeros((*alpha.shape, 3), np.uint8), alpha])
        name = f"char_{ord(char)}_{var}.png"
        Image.fromarray(rgba).save(out / name)
        found.append({"char": char, "code": ord(char), "variant": var, "file": name})
    if len(found) < MIN_GLYPHS:
        raise ExtractionError(f"Only {len(found)} characters were readable. Use a dark pen and a brighter, flatter photo.")
    return {"found": found, "missing": missing}
