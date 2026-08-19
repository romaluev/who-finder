"""A small typesetting PDF writer, standard library only.

The tool's promise is clone-and-run, so a report format that needs
`pip install weasyprint` — or a headless Chrome that is not on the machine —
is not a format this tool can offer. PDF is a text-based container and the
fourteen base fonts are guaranteed present in every reader, so a good-looking
document is reachable with no dependencies at all.

Scope is deliberately narrow: one column, base fonts, rules and fills, and
automatic pagination. No images, no tables with borders, no font embedding.
Anything beyond that belongs in the HTML renderer, which the browser can print
far better than this ever will.

Coordinates are PDF points with the origin bottom-left, but the cursor here
runs top-down because documents do.
"""

from __future__ import annotations

import zlib

# Widths per 1000 units of em for the two base fonts we use, from the standard
# Adobe metrics. Real widths rather than an average: line breaking computed
# against a guess produces visibly ragged right edges and overset lines.
_HELV = (
    "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 "
    "1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 "
    "333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 "
    "556 556 333 500 278 556 500 722 500 500 500 334 260 334 584"
)
_HELV_BOLD = (
    "278 333 474 556 556 889 722 238 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 333 333 584 584 584 611 "
    "975 722 722 722 722 667 611 778 722 278 556 722 611 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 333 278 333 584 556 "
    "333 556 611 556 611 556 333 611 611 278 278 556 278 889 611 611 "
    "611 611 389 556 333 611 556 778 556 556 500 389 280 389 584"
)


def _widths(spec: str) -> dict[int, int]:
    # The tables start at space (32) and run contiguously to tilde (126).
    return {32 + i: int(w) for i, w in enumerate(spec.split())}


WIDTHS = {"r": _widths(_HELV), "b": _widths(_HELV_BOLD)}
_FALLBACK = 556

# Characters a reader may not have in WinAnsi, mapped to something that always
# renders. Silently dropping them would eat punctuation mid-sentence.
TRANSLITERATE = str.maketrans({
    "\u2014": "-", "\u2013": "-", "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"', "\u2022": "-", "\u2026": "...",
    "\u00a0": " ", "\u2192": "->", "\u2265": ">=", "\u2264": "<=",
    "\u00b7": "-", "\u2713": "x", "\u00d7": "x",
})


def sanitize(text: str) -> str:
    out = (text or "").translate(TRANSLITERATE)
    # WinAnsi is a superset of latin-1 for our purposes; anything outside it
    # would render as garbage, so drop it rather than corrupt the line.
    return out.encode("latin-1", "replace").decode("latin-1")


def text_width(text: str, size: float, bold: bool = False) -> float:
    table = WIDTHS["b" if bold else "r"]
    return sum(table.get(ord(c), _FALLBACK) for c in text) * size / 1000.0


def wrap(text: str, size: float, max_w: float, bold: bool = False) -> list[str]:
    """Greedy wrap against real glyph widths."""
    lines, cur = [], ""
    for w in (text or "").split():
        trial = f"{cur} {w}".strip()
        if cur and text_width(trial, size, bold) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = trial
        # A token with no break opportunity — a long URL, most often — has to be
        # cut mid-word or it runs past the margin and off the page.
        while text_width(cur, size, bold) > max_w and len(cur) > 1:
            cut = len(cur) - 1
            while cut > 1 and text_width(cur[:cut], size, bold) > max_w:
                cut -= 1
            lines.append(cur[:cut])
            cur = cur[cut:]
    if cur:
        lines.append(cur)
    return lines or [""]


def _esc(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


class Page:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def text(self, x: float, y: float, s: str, size: float, bold: bool, rgb: tuple) -> None:
        font = "F2" if bold else "F1"
        r, g, b = rgb
        self.ops.append(
            f"BT /{font} {size:.2f} Tf {r:.3f} {g:.3f} {b:.3f} rg "
            f"1 0 0 1 {x:.2f} {y:.2f} Tm ({_esc(s)}) Tj ET"
        )

    def rect(self, x: float, y: float, w: float, h: float, rgb: tuple) -> None:
        r, g, b = rgb
        self.ops.append(f"{r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")

    def line(self, x1: float, y1: float, x2: float, y2: float, rgb: tuple, width: float = 0.6) -> None:
        r, g, b = rgb
        self.ops.append(
            f"{r:.3f} {g:.3f} {b:.3f} RG {width:.2f} w "
            f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S"
        )

    def stream(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1", "replace")


class Canvas:
    """Top-down cursor over a sequence of pages."""

    def __init__(self, width: float = 595.0, height: float = 842.0, margin: float = 54.0):
        self.w, self.h, self.margin = width, height, margin
        self.pages: list[Page] = []
        self.y = 0.0
        self._new_page()

    @property
    def col(self) -> float:
        return self.w - 2 * self.margin

    @property
    def page(self) -> Page:
        return self.pages[-1]

    def _new_page(self) -> None:
        self.pages.append(Page())
        self.y = self.h - self.margin

    def space(self, dy: float) -> None:
        self.y -= dy

    def need(self, dy: float) -> None:
        """Break the page when the next block would not fit whole."""
        if self.y - dy < self.margin:
            self._new_page()

    def para(self, text: str, *, size: float = 9.5, bold: bool = False,
             rgb: tuple = (0.1, 0.1, 0.12), leading: float = 1.45,
             indent: float = 0.0, gap: float = 0.0) -> None:
        lh = size * leading
        for line in wrap(sanitize(text), size, self.col - indent, bold):
            self.need(lh)
            self.y -= lh
            self.page.text(self.margin + indent, self.y, line, size, bold, rgb)
        if gap:
            self.space(gap)

    def label(self, key: str, value: str, *, key_w: float = 52.0, size: float = 9.0,
              key_rgb: tuple = (0.45, 0.47, 0.52), val_rgb: tuple = (0.1, 0.1, 0.12),
              x: float | None = None) -> None:
        """Two-column key/value row, value wrapping under itself."""
        x0 = self.margin if x is None else x
        lh = size * 1.45
        lines = wrap(sanitize(value), size, self.w - self.margin - x0 - key_w, False)
        self.need(lh * len(lines))
        for i, line in enumerate(lines):
            self.y -= lh
            if i == 0:
                self.page.text(x0, self.y, sanitize(key), size, False, key_rgb)
            self.page.text(x0 + key_w, self.y, line, size, False, val_rgb)

    def rule(self, *, gap: float = 6.0, rgb: tuple = (0.85, 0.86, 0.89)) -> None:
        self.need(gap * 2)
        self.y -= gap
        self.page.line(self.margin, self.y, self.w - self.margin, self.y, rgb)
        self.y -= gap

    def render(self) -> bytes:
        return _build(self.pages, self.w, self.h)


def _build(pages: list[Page], width: float, height: float) -> bytes:
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font_r = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                 b"/Encoding /WinAnsiEncoding >>")
    font_b = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                 b"/Encoding /WinAnsiEncoding >>")

    pages_id = len(objects) + 1 + 2 * len(pages) + 1
    kids, page_ids = [], []
    for pg in pages:
        raw = zlib.compress(pg.stream())
        content_id = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(raw)
                         + raw + b"\nendstream")
        pid = add(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] "
            b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
            % (pages_id, width, height, font_r, font_b, content_id)
        )
        page_ids.append(pid)
        kids.append(b"%d 0 R" % pid)

    tree = add(b"<< /Type /Pages /Kids [%s] /Count %d >>"
               % (b" ".join(kids), len(page_ids)))
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % tree)

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"

    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, catalog, xref_at))
    return bytes(out)
