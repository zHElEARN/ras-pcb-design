"""Explicit NPTH mechanical holes, shared by previews, checks and drill export."""

from __future__ import annotations

import math

from shapely.geometry import Point
from shapely.ops import unary_union


def validate(board):
    ids = set()
    for item in board["drills"]:
        if item.get("type") != "npth":
            raise ValueError("Only round NPTH mechanical holes are supported.")
        if not item.get("id") or item["id"] in ids:
            raise ValueError("Mechanical hole IDs must be nonempty and unique.")
        ids.add(item["id"])
        centre = item.get("center_front_mm", [])
        diameter = item.get("diameter_mm", 0)
        if (
            len(centre) != 2
            or not all(math.isfinite(v) for v in [*centre, diameter])
            or diameter <= 0
        ):
            raise ValueError(f"Invalid mechanical hole geometry: {item['id']}")


def circles(board, side="front"):
    result = []
    for item in board["drills"]:
        x, y = item["center_front_mm"]
        if side == "back":
            x = board["width_mm"] - x
        result.append((item, Point(x, y).buffer(item["diameter_mm"] / 2, quad_segs=96)))
    return result


def geometry(board, side="front"):
    return unary_union([g for _, g in circles(board, side)])


def measurements(board, side, layers, outline, limits):
    result = []
    entries = circles(board, side)
    for item, circle in entries:
        row = {
            "id": item["id"],
            "type": item["type"],
            "diameter_mm": item["diameter_mm"],
            "inside_outline": outline.covers(circle),
            "edge_web_mm": circle.distance(outline.boundary),
            "copper_clearance_mm": circle.distance(layers["cu"]),
            "silk_clearance_mm": circle.distance(layers["silk"]),
            "mask_clearance_mm": circle.distance(layers["mask"]),
            "other_hole_clearance_mm": min(
                (circle.distance(g) for other, g in entries if other["id"] != item["id"]),
                default=None,
            ),
        }
        row["passed"] = (
            row["inside_outline"]
            and row["edge_web_mm"] >= limits["hole_edge_mm"] - 1e-6
            and row["copper_clearance_mm"] >= limits["hole_to_copper_mm"] - 1e-6
            and row["silk_clearance_mm"] >= limits["hole_to_silk_mm"] - 1e-6
            and row["mask_clearance_mm"] >= limits["mask_gap_mm"] - 1e-6
            and (
                row["other_hole_clearance_mm"] is None
                or row["other_hole_clearance_mm"] >= limits["hole_to_hole_mm"] - 1e-6
            )
        )
        result.append(row)
    return result


def paint(image, board, side, frame, region):
    """Cut the complete board rendering using the mechanical drill geometry."""
    from .raster import render_aa

    if not board["drills"]:
        return image
    return render_aa(geometry(board, side), frame, region, base=image, fill=(14, 14, 17))
