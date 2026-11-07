"""Independently parse exported Gerbers with gerbonara, compare geometry and render."""

import numpy as np
from gerbonara import GerberFile, ExcellonFile
from gerbonara.utils import MM
from PIL import Image, ImageDraw
from shapely.affinity import affine_transform
from shapely.geometry import LineString, Polygon, Point
from shapely.ops import polygonize, unary_union

from . import geom, raster, holes
from .layout import from_polygons
from .project import read_json
from .raster import Frame
from .text import with_header


def read_regions(p):
    f = GerberFile.open(p)
    dark = []
    clear = []
    for obj in f.objects:
        for primitive in obj.to_primitives(MM):
            if type(primitive).__name__ == "Circle":
                poly = Point(primitive.x, primitive.y).buffer(primitive.r, quad_segs=96)
            else:
                assert type(primitive).__name__ == "ArcPoly", type(primitive)
                assert all(a is None for a in primitive.arc_centers), "unexpected Gerber arc"
                poly = Polygon(primitive.outline).buffer(0)
            (dark if primitive.polarity_dark else clear).append(poly)
    return unary_union(dark).difference(unary_union(clear)), f


def verify_drills(project):
    board = project.board
    expected = board["drills"]
    path = project.output / f"gerber/{project.name}-NPTH.drl"
    drill_export = project.output / f"checks/drill_export/{project.name}"
    pth = ExcellonFile.open(drill_export.with_name(drill_export.name + "-PTH.drl"))
    assert not pth.objects, "Unexpected plated holes"
    if not expected:
        assert not path.exists(), "Unexpected drill data for a hole-free layout"
        return {"count": 0, "holes": []}
    parsed = ExcellonFile.open(path)
    fresh = ExcellonFile.open(drill_export.with_name(drill_export.name + "-NPTH.drl"))

    def hits(file):
        result = []
        for obj in file.objects:
            assert not obj.plated, "A mechanical hole was exported as plated"
            primitives = list(obj.to_primitives(MM))
            assert len(primitives) == 1 and type(primitives[0]).__name__ == "Circle"
            circle = primitives[0]
            result.append((circle.x, circle.y, circle.r))
        return sorted(result)

    packaged_hits = hits(parsed)
    fresh_hits = hits(fresh)
    assert len(packaged_hits) == len(fresh_hits)
    assert all(np.allclose(a, b, atol=1e-6, rtol=0) for a, b in zip(packaged_hits, fresh_hits)), (
        "Gerber drill file differs from current KiCad PCB"
    )
    actual = []
    ox, oy = board["kicad_origin_mm"]
    for x, y, radius in packaged_hits:
        actual.append(
            {
                "center_front_mm": [-y - oy, ox + board["length_mm"] - x],
                "diameter_mm": 2 * radius,
            }
        )
    assert len(actual) == len(expected), "Drill hit count mismatch"
    remaining = list(actual)
    matches = []
    for hole in expected:
        match = min(
            remaining,
            key=lambda v: np.linalg.norm(np.array(v["center_front_mm"]) - hole["center_front_mm"]),
        )
        error = float(np.linalg.norm(np.array(match["center_front_mm"]) - hole["center_front_mm"]))
        assert error < 0.001 and abs(match["diameter_mm"] - hole["diameter_mm"]) < 1e-6
        matches.append({"id": hole["id"], **match, "centre_error_mm": error})
        remaining.remove(match)
    return {
        "count": len(actual),
        "file": path.name,
        "type": "NPTH",
        "holes": matches,
        "plated_count": 0,
    }


def run(project):
    OUT = project.output
    PREVIEW = OUT / "preview"
    name = project.name
    board = project.board
    width = board["width_mm"]
    length = board["length_mm"]
    ox, oy = board["kicad_origin_mm"]
    data = read_json(OUT / "geometry.json")
    results = {}
    parsed = {}
    files = {
        "front": {"cu": "F_Cu.gtl", "mask": "F_Mask.gts", "silk": "F_Silkscreen.gto"},
        "back": {"cu": "B_Cu.gbl", "mask": "B_Mask.gbs", "silk": "B_Silkscreen.gbo"},
    }
    for side, items in files.items():
        transform = (
            [0, -1, -1, 0, -oy, ox + length]
            if side == "front"
            else [0, 1, -1, 0, width + oy, ox + length]
        )
        parsed[side] = {}
        results[side] = {}
        for key, suffix in items.items():
            p = OUT / "gerber" / (name + "-" + suffix)
            raw, f = read_regions(p)
            g = affine_transform(raw, transform)
            expected = from_polygons(data["sides"][side]["layers"][key])
            if key == "mask":
                # NPTH mask apertures occupy only the physical void; the artwork is unchanged.
                expected = expected.union(holes.geometry(board, side))
            err = g.hausdorff_distance(expected)
            area = g.symmetric_difference(expected).area
            assert g.is_valid and err < 0.00001 and area < 0.001, (side, key, err, area)
            assert len(geom.iterate(g)) == len(geom.iterate(expected)), (side, key, "components")
            assert sum(len(p.interiors) for p in geom.iterate(g)) == sum(
                len(p.interiors) for p in geom.iterate(expected)
            ), (side, key, "holes")
            parsed[side][key] = g
            results[side][key] = {
                "file": p.name,
                "valid": g.is_valid,
                "objects": len(f.objects),
                "components": len(geom.iterate(g)),
                "holes": sum(len(p.interiors) for p in geom.iterate(g)),
                "hausdorff_mm": err,
                "symmetric_difference_mm2": area,
            }
    edgefile = OUT / ("gerber/" + name + "-Edge_Cuts.gm1")
    edge = GerberFile.open(edgefile)
    segments = []
    for obj in edge.objects:
        assert type(obj).__name__ == "Line", type(obj)
        segments.append(LineString([(obj.x1, obj.y1), (obj.x2, obj.y2)]))
    polys = list(polygonize(segments))
    assert len(polys) == 1
    outline_front = affine_transform(polys[0], [0, -1, -1, 0, -oy, ox + length])
    expected = Polygon(data["sides"]["front"]["edge_cuts_mm"])
    assert outline_front.hausdorff_distance(expected) < 0.00001
    assert np.allclose(outline_front.bounds, [0, 0, width, length], atol=1e-6)
    results["outline"] = {
        "closed_contours": 1,
        "internal_holes": len(outline_front.interiors),
        "width_mm": width,
        "length_mm": length,
        "hausdorff_mm": outline_front.hausdorff_distance(expected),
        "drill_count": len(board["drills"]),
    }
    results["drills"] = verify_drills(project)
    frame = Frame(40, 3, length_mm=length, width_mm=width)
    region = (0, 0, frame.h, frame.w)
    renders = {}
    for side, g in parsed.items():
        outline = (
            outline_front
            if side == "front"
            else affine_transform(outline_front, [-1, 0, 0, 1, width, 0])
        )
        base = frame.blank((14, 14, 17))
        ImageDraw.Draw(base).polygon(
            frame.poly(outline.exterior.coords), fill=(30, 30, 33), outline=(180, 180, 185)
        )
        full = base
        for geometry, color in [
            (g["cu"].difference(g["mask"]), (109, 119, 124)),
            (g["cu"].intersection(g["mask"]), (208, 170, 60)),
            (g["silk"], (241, 241, 239)),
        ]:
            full = raster.render_aa(geometry, frame, region, base=full, fill=color)
        full = holes.paint(full, board, side, frame, region)
        renders[side] = full
    both = Image.new("RGB", (frame.w, frame.h * 2), (14, 14, 17))
    for i, side in enumerate(["front", "back"]):
        both.paste(renders[side], (0, i * frame.h))
    with_header(
        both,
        "ART PCB V1 - actual Gerber / FRONT above, BACK below",
        f"{length:g} x {width:g} mm | 2 layers | {board['thickness_mm']:g} mm FR4 | covered copper / ENIG / silk",
    )[0].save(PREVIEW / "gerber_both_sides.png")
    results["input_sha256"] = project.inputs()
    return results
