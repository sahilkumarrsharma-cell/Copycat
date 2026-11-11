"""Handwriting glyph PNGs + text -> humanized A4 pages -> PDF."""
import base64
import io
import random
import re
import statistics
import unicodedata
import zlib
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from extractor import S
from make_sheet import BASE, H, W

PW, PH = W * S, H * S                                   # 2480 x 3508 = A4 at 300 DPI
INKS = {"blue": (28, 52, 160), "black": (20, 20, 24), "darkblue": (12, 24, 88)}
PAPERS = {"ruled": (210, 330), "margin": (400, 430), "blank": (230, 300)}   # (left margin, first baseline)
_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "."})


def _load(glyph_dir):
    glyphs = {}
    for f in sorted(Path(glyph_dir).glob("char_*_*.png")):
        m = re.fullmatch(r"char_(\d+)_(\d+)\.png", f.name)
        if m:
            glyphs.setdefault(int(m[1]), []).append(Image.open(f).getchannel("A"))
    return glyphs


def _cap_height(glyphs):
    """Median height of the user's capital letters above the baseline (px at 300 DPI)."""
    hs = []
    for code in range(65, 91):
        for a in glyphs.get(code, []):
            bb = a.point(lambda v: 255 if v > 64 else 0).getbbox()
            if bb:
                hs.append(BASE * S - bb[1])
    return max(10, statistics.median(hs)) if hs else BASE * S * 0.7


def _code(ch):
    ch = unicodedata.normalize("NFKD", ch.translate(_QUOTES))[:1]
    return ord(ch) if ch else -1


def _paper(kind, pitch, first):
    img = Image.new("RGB", (PW, PH), (253, 253, 251))
    d = ImageDraw.Draw(img)
    if kind != "blank":
        for y in range(first, PH - 120, pitch):
            d.line([(70, y + 5), (PW - 70, y + 5)], fill=(176, 194, 230), width=2)
    if kind == "margin":
        for x in (330, 344):
            d.line([(x, 0), (x, PH)], fill=(224, 120, 120), width=2)
        d.line([(0, first - pitch * 2 + 5), (PW, first - pitch * 2 + 5)], fill=(224, 120, 120), width=2)
    return img


def render_pages(glyph_dir, text, ink="blue", paper="ruled", font_size=16.0, jitter=50,
                 background=None, layout=None):
    """Return (list of PIL pages, set of characters the user's sheet did not contain)."""
    glyphs = _load(glyph_dir)
    if not glyphs:
        raise ValueError("No handwriting found for this session. Upload your sheet again.")
    rnd = random.Random(zlib.crc32(f"{text}|{ink}|{paper}|{font_size}|{jitter}".encode()))   # preview == PDF
    f = jitter / 50                                      # 1.0 = +-1.8 deg tilt, +-2 px (150 DPI) wobble
    cap = _cap_height(glyphs)
    photo_lines = (layout or {}).get("baselines") if background is not None else None
    if photo_lines:
        bg = Image.open(io.BytesIO(background)).convert("RGB")
        if bg.size != (PW, PH):
            bg = bg.resize((PW, PH), Image.LANCZOS)
        baselines = [int(y) for y in photo_lines]
        lm, right = int(layout["left"]), int(layout["right"])
        pitch = max(1, int(layout["pitch"]))
        scale = (float(font_size) / 16.0) * (pitch * 0.62) / cap
    else:
        scale = font_size * 2.917 / cap                  # font_size in pt -> capital-letter height
        pitch = max(94, round(cap * scale * 1.9))
        lm, first = PAPERS[paper]
        right, bottom = PW - 140, PH - 170
        bg = _paper(paper, pitch, first)
        baselines = list(range(first, bottom + 1, pitch))
    sc = {c: [a.resize((max(1, round(a.width * scale)), max(1, round(a.height * scale))), Image.LANCZOS) for a in v]
          for c, v in glyphs.items()}
    base, capp = BASE * S * scale, cap * scale           # baseline row inside a scaled glyph; capital height
    color = INKS[ink]
    pages, missing, last = [bg.copy()], set(), {}
    line_i = 0
    st = {"x": lm, "y": baselines[0], "slope": rnd.uniform(-0.0025, 0.0025) * f}

    def newline():
        nonlocal line_i
        line_i += 1
        st["slope"] = rnd.uniform(-0.0025, 0.0025) * f
        if line_i >= len(baselines):
            pages.append(bg.copy())
            line_i = 0
        st["x"], st["y"] = lm, baselines[line_i]

    paras = text.replace("\t", "    ").split("\n")
    for pi, para in enumerate(paras):
        for word in para.split(" "):
            items = []
            for ch in word:
                code = _code(ch)
                if code not in sc:
                    if not ch.isspace():
                        missing.add(ch)
                    continue
                n = len(sc[code])
                k = rnd.randrange(n)
                if n > 1 and k == last.get(code):        # never repeat the same variant back-to-back
                    k = (k + 1) % n
                last[code] = k
                items.append(sc[code][k])
            if items and st["x"] > lm and st["x"] + sum(a.width for a in items) + capp * 0.05 * len(items) > right:
                newline()
            word_dy = rnd.gauss(0, 1.2) * f
            for a in items:
                if st["x"] + a.width > right:
                    newline()
                ang = rnd.uniform(-1.8, 1.8) * f
                im = a.rotate(ang, resample=Image.BICUBIC, expand=True) if abs(ang) > 0.05 else a
                dy = rnd.uniform(-4, 4) * f + word_dy + st["slope"] * (st["x"] - lm)
                left = st["x"] - (im.width - a.width) / 2
                top = st["y"] + dy - base - (im.height - a.height) / 2
                pages[-1].paste(color, (round(left), round(top)), im)
                st["x"] += a.width + capp * max(0.0, 0.05 + 0.04 * f * rnd.uniform(-1, 1))
            st["x"] += capp * (0.55 + 0.12 * f * rnd.uniform(-1, 1))
        if pi < len(paras) - 1:
            newline()
    return pages, missing


def build_pdf(pages):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Assignment")
    for p in pages:
        j = io.BytesIO()
        p.save(j, "JPEG", quality=92, dpi=(300, 300))
        j.seek(0)
        c.drawImage(ImageReader(j), 0, 0, width=A4[0], height=A4[1])
        c.showPage()
    c.save()
    return buf.getvalue()


def preview_images(pages, width=900, limit=6):
    out = []
    for p in pages[:limit]:
        b = io.BytesIO()
        p.resize((width, round(width * PH / PW)), Image.LANCZOS).save(b, "JPEG", quality=80)
        out.append("data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode())
    return out
