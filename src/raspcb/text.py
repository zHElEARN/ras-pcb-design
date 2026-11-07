"""Tiny text helpers for the review sheets."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

_CANDIDATES = (
    "/System/Library/Fonts/SFNSMono.ttf",
    "/System/Library/Fonts/Supplemental/Menlo.ttc",
    "/System/Library/Fonts/Menlo.ttc",
)


def font(size: int) -> ImageFont.FreeTypeFont:
    for p in _CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def with_header(
    img: Image.Image,
    title: str,
    subtitle: str = "",
    height: int = 78,
    bg: tuple[int, int, int] = (10, 10, 12),
) -> tuple[Image.Image, int]:
    """Paste the image under a header band and draw the captions there."""
    out = Image.new("RGB", (img.width, img.height + height), bg)
    out.paste(img, (0, height))
    d = ImageDraw.Draw(out)
    d.text((14, 12), title, font=font(21), fill=(238, 238, 242))
    if subtitle:
        d.text((14, 42), subtitle, font=font(14), fill=(146, 146, 158))
    return out, height
