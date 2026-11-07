"""Read-only compilation of the authoritative layout, without geometry correction."""

from __future__ import annotations

from shapely.geometry import Polygon

from .checks import metrics
from .holes import measurements
from .layout import LAYERS, from_polygons, load, to_polygons
from .project import write_json


def run(project):
    board = project.board
    source = load(project)
    sides, audit = {}, {}
    for side, record in source.items():
        geometry = {key: from_polygons(record["layers"][key]) for key in LAYERS}
        audit[side] = {
            "after": metrics(geometry, Polygon(record["edge_cuts_mm"]), project.rules["limits"])
        }
        audit[side]["after"]["drills"] = measurements(
            board, side, geometry, Polygon(record["edge_cuts_mm"]), project.rules["limits"]
        )
        if any(not hole["passed"] for hole in audit[side]["after"]["drills"]):
            raise ValueError(
                f"Mechanical hole clearance violation on {side}; source layout remains unchanged."
            )
        # Union only changes contour encoding, never the physical area or dimensions.
        sides[side] = {
            "layers": {key: to_polygons(g) for key, g in geometry.items()},
            "edge_cuts_mm": record["edge_cuts_mm"],
        }
    result = {
        key: board[key]
        for key in [
            "units",
            "name",
            "width_mm",
            "length_mm",
            "thickness_mm",
            "copper_oz",
            "solder_mask",
            "silkscreen",
            "surface_finish",
            "drills",
            "kicad_origin_mm",
            "edge_line_width_mm",
        ]
    }
    result.update(input_sha256=project.inputs(), sides=sides, rules=project.rules["limits"])
    result["audit"] = audit
    project.mkdirs()
    write_json(project.output / "geometry.json", result)
    return result
