"""Read the two authoritative, grouped millimetre vector layouts."""

from __future__ import annotations

from shapely.affinity import affine_transform
from shapely.geometry import Polygon
from shapely.ops import unary_union

from . import geom
from .project import read_json

LAYERS = ("cu", "mask", "silk")


def from_polygons(items):
    return unary_union([Polygon(exterior, holes) for exterior, holes in items])


def to_polygons(geometry):
    """Keep all approved vertices; never simplify implicitly during a build."""
    return [
        [list(map(list, p.exterior.coords)), [list(map(list, r.coords)) for r in p.interiors]]
        for p in geom.iterate(geometry)
    ]


def mirror(geometry, width=22):
    return affine_transform(geometry, [-1, 0, 0, 1, width, 0])


def load(project):
    result = {}
    width = project.board["width_mm"]
    front_outline = Polygon(project.board["outline_front_mm"])
    if not front_outline.is_valid or front_outline.interiors:
        raise ValueError("Board outline must be a single valid exterior without drill holes.")
    for side in ["front", "back"]:
        data = read_json(project.root / f"layout/{side}.json")
        if data["schema_version"] != 1 or data["units"] != "mm" or data["side"] != side:
            raise ValueError(f"Unsupported layout schema: {side}")
        names = [g["id"] for g in data["groups"]]
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate layout group IDs: {side}")
        layers = {key: [] for key in LAYERS}
        for group in data["groups"]:
            if not group.get("enabled", True):
                continue
            for key, polygons in group["geometry"].items():
                if key not in LAYERS:
                    raise ValueError(f"Unknown PCB layer key: {key}")
                for exterior, holes in polygons:
                    if not Polygon(exterior, holes).is_valid:
                        raise ValueError(f"Invalid vector contour: {side}/{group['id']}/{key}")
                layers[key].extend(polygons)
        outline = front_outline if side == "front" else mirror(front_outline, width)
        for key, polygons in layers.items():
            if not outline.buffer(1e-8).covers(from_polygons(polygons)):
                raise ValueError(f"Artwork outside outline: {side}/{key}")
        result[side] = {"layers": layers, "edge_cuts_mm": list(map(list, outline.exterior.coords))}
    return result
