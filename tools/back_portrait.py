"""Place the existing CHU2 SVG as a cropped, white B.SilkS portrait.

Only the included SVG vector contours enter the layout.
Run from the repository root with uv run python tools/back_portrait.py.
"""

from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path import parse_path
from shapely.affinity import affine_transform
from shapely.geometry import box
from shapely.ops import unary_union

from raspcb import geom
from raspcb.glyphs import _rings_from_pen, rings_to_multi
from raspcb.layout import from_polygons, to_polygons


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/lineart/chu2/chu2-lineart.svg"
GROUP = "chu2_back_portrait"


def main():
    tree = ET.parse(SOURCE)
    pen = RecordingPen()
    for path in tree.iter("{http://www.w3.org/2000/svg}path"):
        parse_path(path.attrib["d"], pen)
    source = rings_to_multi(_rings_from_pen(pen, steps=12))
    # SVG (u right, v down) -> face-on board (x down, y left).
    # Uniform scale, no distortion or reflection in the face-on preview.
    # Enlarge the face by 25.6% over the first trial, allowing the ahoge
    # to cross the top crop rather than spending face area on its full arc.
    scale = 0.054
    matrix = [0, scale, -scale, 0, -2.0, 51.85]
    placed = affine_transform(source, matrix).simplify(0.001, preserve_topology=True)
    crop = box(2.48, 11.85, 24.58, 38.7)
    # Modest contour growth improves thin ink while retaining eye counters.
    ink = placed.buffer(0.018, quad_segs=6).intersection(crop)
    ink = unary_union([p for p in geom.iterate(ink) if p.area >= 0.002])
    layout_path = ROOT / "layout/back.json"
    layout = json.loads(layout_path.read_text())
    other = [g for g in layout["groups"] if g["id"] != GROUP]
    mask = unary_union([
        from_polygons(g["geometry"].get("mask", []))
        for g in other if g.get("enabled", True)
    ])
    assert ink.is_valid
    assert ink.distance(mask) >= 0.15
    layout["groups"] = other + [{
        "id": GROUP,
        "enabled": True,
        "metadata": {
            "layer": "B.SilkS",
            "source_svg": str(SOURCE.relative_to(ROOT)),
            "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            "svg_to_face_on_board_matrix": matrix,
            "crop_xyxy_mm": list(crop.bounds),
            "contour_growth_mm": 0.018,
            "curve_samples_per_segment": 12,
            "simplify_tolerance_mm": 0.001,
            "minimum_component_area_mm2": 0.002,
        },
        "geometry": {"silk": to_polygons(ink)},
    }]
    layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"bounds_mm": ink.bounds, "components": len(geom.iterate(ink)),
                      "area_mm2": ink.area, "silk_to_mask_mm": ink.distance(mask)}, indent=2))


if __name__ == "__main__":
    main()
