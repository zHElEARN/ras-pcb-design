#!/usr/bin/env python3
"""Rebuild the final front white-fill portrait from the included SVG."""

from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path import parse_path
from shapely.affinity import affine_transform
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from raspcb import geom, holes
from raspcb.glyphs import _rings_from_pen, rings_to_multi
from raspcb.layout import from_polygons, to_polygons

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/lineart/chu2/chu2-lineart.svg"
GROUP = "front_person_fill"


def main():
    pen = RecordingPen()
    for path in ET.parse(SOURCE).iter("{http://www.w3.org/2000/svg}path"):
        parse_path(path.attrib["d"], pen)
    ink = rings_to_multi(_rings_from_pen(pen, steps=12))
    silhouette = unary_union([Polygon(part.exterior) for part in geom.iterate(ink)])
    matrix = [-0.054, 0, 0, -0.054, 44.5, 102.1]
    ink = affine_transform(ink, matrix).simplify(0.001, preserve_topology=True)
    artwork = affine_transform(silhouette, matrix).difference(ink)

    board = json.loads((ROOT / "config/board.json").read_text())
    layout_path = ROOT / "layout/front.json"
    layout = json.loads(layout_path.read_text())
    other = [group for group in layout["groups"] if group["id"] != GROUP]
    mask = unary_union([
        from_polygons(group["geometry"].get("mask", []))
        for group in other if group.get("enabled", True)
    ])
    outline = Polygon(board["outline_front_mm"])
    allowed = outline.buffer(-0.4).intersection(box(0.65, 7.0, 29.35, 103.5))
    allowed = allowed.difference(mask.buffer(0.2, quad_segs=12))
    for _, hole in holes.circles(board, "front"):
        allowed = allowed.difference(hole.buffer(0.2, quad_segs=12))
    artwork = artwork.intersection(allowed)
    artwork = unary_union([part for part in geom.iterate(artwork) if part.area >= 0.0002])
    assert artwork.is_valid and outline.covers(artwork)
    assert artwork.distance(mask) >= 0.199

    group = {
        "id": GROUP,
        "enabled": True,
        "metadata": {
            "layer": "F.SilkS",
            "source_svg": str(SOURCE.relative_to(ROOT)),
            "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            "svg_to_face_on_board_matrix": matrix,
            "mask_clearance_mm": 0.2,
            "hole_clearance_mm": 0.2,
        },
        "geometry": {"silk": to_polygons(artwork)},
    }
    layout["groups"] = other + [group]
    layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + "\n")
    print(f"{GROUP}: {artwork.area:.3f} mm2, mask gap {artwork.distance(mask):.3f} mm")


if __name__ == "__main__":
    main()
