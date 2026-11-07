"""Landscape rendering helpers for face-on millimetre board coordinates.

The connector end (y=0) is on the right; x=0 is the upper image edge.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

BG = (16, 16, 18)
BOARD = (30, 30, 33)
EDGE = (210, 210, 214)
ART_LINE = (70, 140, 210)
FINGER = (58, 46, 22)
GRID = (46, 46, 52)


@dataclass
class Frame:
    scale: float  # px per mm
    margin_mm: float = 1.5
    length_mm: float = 109.0
    width_mm: float = 30.0

    @property
    def w(self) -> int:
        return int(round((self.length_mm + 2 * self.margin_mm) * self.scale))

    @property
    def h(self) -> int:
        return int(round((self.width_mm + 2 * self.margin_mm) * self.scale))

    def px(self, x_mm: float, y_mm: float) -> tuple[float, float]:
        ix = (self.margin_mm + (self.length_mm - y_mm)) * self.scale
        iy = (x_mm + self.margin_mm) * self.scale
        return ix, iy

    def poly(self, pts: np.ndarray) -> list[tuple[float, float]]:
        return [self.px(float(x), float(y)) for x, y in pts]

    def blank(self, color=BG) -> Image.Image:
        return Image.new("RGB", (self.w, self.h), color)

    def mm_rect(self, x0: float, y0: float, x1: float, y1: float):
        a = self.px(x0, y0)
        b = self.px(x1, y1)
        return (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))


def render_aa(
    polys,
    frame,
    box_px,
    bg=(30, 30, 33),
    fill=(240, 240, 238),
    ss: int = 4,
    base: Image.Image | None = None,
) -> Image.Image:
    """Anti-aliased render of polygons inside a pixel box of the frame."""
    from . import geom

    r0, c0, r1, c1 = box_px
    W, H = (c1 - c0) * ss, (r1 - r0) * ss
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    # Draw enclosing rings before islands inside their holes (e.g. text inside
    # an outline frame), so punching a frame hole cannot erase the text.
    for poly in sorted(geom.iterate(polys), key=lambda p: p.envelope.area, reverse=True):
        d.polygon(
            [
                ((frame.px(x, y)[0] - c0) * ss, (frame.px(x, y)[1] - r0) * ss)
                for x, y in poly.exterior.coords
            ],
            fill=255,
        )
        for ring in poly.interiors:
            d.polygon(
                [
                    ((frame.px(x, y)[0] - c0) * ss, (frame.px(x, y)[1] - r0) * ss)
                    for x, y in ring.coords
                ],
                fill=0,
            )
    img = base.resize((W, H), Image.LANCZOS) if base is not None else Image.new("RGB", (W, H), bg)
    img.paste(fill, mask=m)
    return img.resize((c1 - c0, r1 - r0), Image.LANCZOS)
