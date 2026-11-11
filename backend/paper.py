"""Photo of a university assignment sheet -> flat A4 page plus the printed writing lines."""
import base64
import io

import cv2
import numpy as np
from PIL import Image, ImageOps

from generator import PH, PW

MIN_LINES = 4


class PaperError(Exception):
    """Raised with a message that is safe to show to the user."""


def _decode(image_bytes):
    try:
        pil = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    except Exception as exc:
        raise PaperError("That file is not a readable image.") from exc
    bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    if max(h, w) > 4000:
        f = 4000 / max(h, w)
        bgr = cv2.resize(bgr, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    if min(bgr.shape[:2]) < 400:
        raise PaperError("That photo is too small. Photograph the whole assignment sheet.")
    return bgr


def _order_corners(pts):
    pts = np.asarray(pts, np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).reshape(-1)
    return np.float32([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]])


def _quads(bgr):
    """Candidate page corners, largest first. Each item is (area_fraction, 4 points)."""
    h, w = bgr.shape[:2]
    gray = cv2.GaussianBlur(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    _, bright = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    edges = cv2.Canny(gray, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    found = []
    for mask in (bright, edges):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:6]:
            area = cv2.contourArea(contour)
            if area < 0.18 * h * w:
                continue
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
            if len(approx) == 4:
                found.append((area / (h * w), approx.reshape(4, 2)))
                continue
            rect = cv2.minAreaRect(contour)
            rw, rh = rect[1]
            if min(rw, rh) < 1:
                continue
            aspect = max(rw, rh) / min(rw, rh)
            if 1.15 <= aspect <= 1.75:
                found.append((area / (h * w), cv2.boxPoints(rect)))
    found.sort(key=lambda item: item[0], reverse=True)
    return found


def _flatten(bgr):
    """Straighten the sheet to A4. A photo that is already the full page is only resized."""
    h, w = bgr.shape[:2]
    for fraction, pts in _quads(bgr):
        if fraction > 0.93:
            break
        ordered = _order_corners(pts)
        if cv2.contourArea(ordered) < 0.18 * h * w:
            continue
        dest = np.float32([[0, 0], [PW - 1, 0], [PW - 1, PH - 1], [0, PH - 1]])
        matrix = cv2.getPerspectiveTransform(ordered, dest)
        return cv2.warpPerspective(bgr, matrix, (PW, PH), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
    scale = max(PW / w, PH / h)
    resized = cv2.resize(bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_CUBIC)
    x = max(0, (resized.shape[1] - PW) // 2)
    y = max(0, (resized.shape[0] - PH) // 2)
    return resized[y:y + PH, x:x + PW]


def _line_mask(page):
    hsv = cv2.cvtColor(page, cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(hsv, (80, 25, 70), (140, 255, 255))
    gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
    dark = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 10)
    ink = cv2.bitwise_or(blue, dark)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(50, PW // 18), 1))
    horiz = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel)
    return cv2.morphologyEx(horiz, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (31, 1)))


def _centers(mask):
    counts = (mask > 0).sum(axis=1)
    ys = np.flatnonzero(counts > PW * 0.28)
    if len(ys) == 0:
        return []
    groups, start = [], ys[0]
    prev = ys[0]
    for y in ys[1:]:
        if y - prev > 6:
            groups.append((start, prev))
            start = y
        prev = y
    groups.append((start, prev))
    return [int((a + b) / 2) for a, b in groups]


def _body_lines(centers):
    if len(centers) < 2:
        return [], 0
    gaps = np.diff(centers)
    usable = [int(g) for g in gaps if 70 <= g <= 220]
    pitch = int(np.median(usable or gaps))
    if pitch < 1:
        return [], 0
    best, run = [], [centers[0]]
    for y, gap in zip(centers[1:], gaps):
        if 0.72 * pitch <= gap <= 1.35 * pitch:
            run.append(int(y))
        else:
            if len(run) > len(best) or (len(run) == len(best) and run and run[0] > best[0]):
                best = run
            run = [int(y)]
    if len(run) > len(best) or (len(run) == len(best) and run and run[0] > best[0]):
        best = run
    return (best, pitch) if len(best) >= MIN_LINES else ([], 0)


def _margins(page, mask, baselines):
    hsv = cv2.cvtColor(page, cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 60, 60), (12, 255, 255)) | cv2.inRange(hsv, (168, 60, 60), (180, 255, 255))
    cols = (red > 0).sum(axis=0)
    red_x = None
    if cols.max() > 0.25 * PH:
        x = int(np.argmax(cols[: PW // 3]))
        if cols[x] > 0.25 * PH:
            red_x = x
    lefts, rights = [], []
    for y in baselines:
        band = mask[max(0, y - 2):y + 3]
        xs = np.flatnonzero(band.any(axis=0))
        if len(xs):
            lefts.append(int(xs[0]))
            rights.append(int(xs[-1]))
    left = int(np.median(lefts)) if lefts else 210
    right = int(np.median(rights)) if rights else PW - 140
    if red_x is not None:
        left = max(left, red_x + 28)
    left = int(np.clip(left + 14, 40, PW // 2))
    right = int(np.clip(right - 14, left + 400, PW - 40))
    return left, right


def _fallback():
    pitch = 110
    first, bottom = int(PH * 0.22), PH - 170
    return {
        "baselines": list(range(first, bottom + 1, pitch)),
        "left": 210,
        "right": PW - 140,
        "pitch": pitch,
        "detected": False,
    }


def prepare_paper(image_bytes):
    """Return JPEG bytes of the flattened sheet and the writing-line layout."""
    page = _flatten(_decode(image_bytes))
    mask = _line_mask(page)
    lines, pitch = _body_lines(_centers(mask))
    if lines:
        left, right = _margins(page, mask, lines)
        layout = {"baselines": lines, "left": left, "right": right, "pitch": int(pitch), "detected": True}
    else:
        layout = _fallback()
    ok, encoded = cv2.imencode(".jpg", page, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not ok:
        raise PaperError("Could not read that assignment sheet. Try a brighter photo of the full page.")
    return encoded.tobytes(), layout


def preview_jpeg(page_jpeg, width=720):
    image = Image.open(io.BytesIO(page_jpeg)).convert("RGB")
    image.thumbnail((width, width * 2))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()
