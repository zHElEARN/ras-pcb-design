"""PCB vector contour assembly, including holes, and iteration helpers."""

from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union


def assemble(rings: list[Polygon], tol: float = 0.0, min_area: float = 0.0) -> MultiPolygon:
    """Turn a soup of boundary rings into polygons with proper holes.

    A point strictly ON a ring's own boundary can never fall inside one of its
    children, so it is a reliable probe for nesting depth (an interior point is
    not: it can land inside a hole).  Even depth = solid, odd depth = hole.
    """
    if not rings:
        return MultiPolygon()

    rings = sorted(rings, key=lambda p: p.area, reverse=True)
    probes = [Point(p.exterior.coords[0]) for p in rings]
    depth = [
        sum(1 for j, q in enumerate(rings) if j != i and q.contains(probes[i]))
        for i in range(len(rings))
    ]

    outers, holes = [], {}
    for i, p in enumerate(rings):
        if depth[i] % 2 == 0:
            outers.append((i, p))
        else:
            for j, q in outers:
                if q.contains(probes[i]):
                    holes.setdefault(j, []).append(p)
                    break

    polys = []
    for i, p in outers:
        poly = Polygon(p.exterior, [h.exterior for h in holes.get(i, [])])
        if not poly.is_valid:
            poly = poly.buffer(0)
        if tol > 0:
            poly = poly.simplify(tol, preserve_topology=True)
        if poly.area >= min_area:
            polys.append(poly)

    return unary_union(polys) if polys else MultiPolygon()


def iterate(polys) -> list[Polygon]:
    if polys is None or polys.is_empty:
        return []
    if isinstance(polys, Polygon):
        return [polys]
    return [g for g in polys.geoms if isinstance(g, Polygon) and not g.is_empty]
