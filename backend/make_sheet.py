"""Calibration sheet generator. The geometry here is shared with extractor.py and generator.py."""
import string
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1240, 1754                                          # A4 at 150 DPI
MARKS = [(45, 45), (1195, 45), (45, 1709), (1195, 1709)]   # marker centres: TL, TR, BL, BR
MARK_SIZE = 50
COLS, CELL, PITCH_X, PITCH_Y, X0, Y0 = 9, 114, 120, 134, 83, 190
PAD, BASE = 8, 68          # crop inset inside a box; baseline row inside the cropped box

PUNCT = ".,?!-()'\":;"
NAMES = {".": "dot", ",": "comma", "?": "question", "!": "exclaim", "-": "dash", "(": "open",
         ")": "close", "'": "apostrophe", '"': "quote", ":": "colon", ";": "semicolon"}
VARIANT_CHARS = "aeioustrn"   # these get 2 extra boxes so repeated letters differ

CELLS = [(c, 0) for c in string.ascii_uppercase + string.ascii_lowercase + string.digits + PUNCT]
CELLS += [(c, v) for v in (1, 2) for c in VARIANT_CHARS]


def cell_origin(i):
    """Top-left corner (150 DPI px) of box number i."""
    return X0 + (i % COLS) * PITCH_X, Y0 + (i // COLS) * PITCH_Y


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                      # very old Pillow
        return ImageFont.load_default()


def create_sheet(path="copycat_sheet.png"):
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    for cx, cy in MARKS:
        h = MARK_SIZE // 2
        d.rectangle([cx - h, cy - h, cx + h, cy + h], fill="black")
    d.text((110, 66), "CopyCat calibration sheet: write ONE character in each box with a dark pen.", fill="#444", font=_font(22))
    d.text((110, 98), "Sit letters on the faint line. Keep every stroke inside its box.", fill="#444", font=_font(20))
    label_font = _font(14)
    for i, (ch, var) in enumerate(CELLS):
        x, y = cell_origin(i)
        label = NAMES.get(ch, ch)
        label = f"{ch} {label}" if ch in NAMES else label
        if var:
            label += f"  (style {var + 1})"
        d.text((x + 2, y - 18), label, fill="#777", font=label_font)
        d.rectangle([x, y, x + CELL, y + CELL], outline="#bdbdbd", width=2)
        gy = y + PAD + BASE
        d.line([(x + PAD, gy), (x + CELL - PAD, gy)], fill="#e6e6e6", width=2)   # baseline guide
    d.text((110, 1668), "Photograph the whole page flat and well lit. All 4 black squares must be visible.", fill="#444", font=_font(20))
    img.save(path)
    return path


if __name__ == "__main__":
    print("Wrote", create_sheet(sys.argv[1] if len(sys.argv) > 1 else "copycat_sheet.png"))
