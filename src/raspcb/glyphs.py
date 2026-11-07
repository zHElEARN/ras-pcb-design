"""Convert SVG path commands into polygon rings with preserved counters."""

from __future__ import annotations

import numpy as np
from fontTools.pens.recordingPen import RecordingPen
from shapely.geometry import MultiPolygon, Polygon


def _quad(p0, c, p1, n=14):
    t = np.linspace(0, 1, n)[1:, None]
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * c + t**2 * p1


def _cubic(p0, c1, c2, p1, n=18):
    t = np.linspace(0, 1, n)[1:, None]
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * c1 + 3 * (1 - t) * t**2 * c2 + t**3 * p1


def _rings_from_pen(rec: RecordingPen, steps: int = 14) -> list[np.ndarray]:
    rings: list[np.ndarray] = []
    cur: list[np.ndarray] = []
    start = None
    for op, args in rec.value:
        if op == "moveTo":
            if len(cur) > 2:
                rings.append(np.array(cur))
            start = np.array(args[0], dtype=float)
            cur = [start]
        elif op == "lineTo":
            cur.append(np.array(args[0], dtype=float))
        elif op == "qCurveTo":
            pts = [None if a is None else np.array(a, dtype=float) for a in args]
            end = pts[-1] if pts[-1] is not None else start
            ctrls = pts[:-1]
            p0 = cur[-1]
            for i, c in enumerate(ctrls):
                if i + 1 < len(ctrls):
                    mid = (c + ctrls[i + 1]) / 2.0
                    cur.extend(_quad(p0, c, mid, steps))
                    p0 = mid
                else:
                    cur.extend(_quad(p0, c, end, steps))
        elif op == "curveTo":
            p0 = cur[-1]
            c1, c2, p1 = (np.array(a, dtype=float) for a in args)
            cur.extend(_cubic(p0, c1, c2, p1, steps))
        elif op in ("closePath", "endPath"):
            if len(cur) > 2:
                rings.append(np.array(cur))
            cur = []
    if len(cur) > 2:
        rings.append(np.array(cur))
    return rings


def rings_to_multi(rings: list[np.ndarray]) -> MultiPolygon:
    """Build polygons with proper counters using even-odd nesting."""
    from .geom import assemble

    polys = []
    for ring in rings:
        polygon = Polygon(ring)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.is_empty:
            continue
        if polygon.geom_type == "MultiPolygon":
            polys.extend(part for part in polygon.geoms if not part.is_empty)
        else:
            polys.append(polygon)
    return assemble(polys)
