"""Vector manufacturing checks independent of KiCad electrical DRC."""

from shapely.ops import nearest_points

from . import geom


def gaps(g, limit):
    ps = geom.iterate(g)
    rows = []
    for i, p in enumerate(ps):
        for j in range(i + 1, len(ps)):
            q = ps[j]
            d = p.distance(q)
            if d < limit - 1e-6:
                a, b = nearest_points(p, q)
                rows.append(
                    {
                        "gap_mm": d,
                        "point_a_mm": list(a.coords[0]),
                        "point_b_mm": list(b.coords[0]),
                        "components": [i, j],
                    }
                )
    return sorted(rows, key=lambda r: r["gap_mm"])


def metrics(g, outline, limits):
    out = {}
    for k, v in g.items():
        ps = geom.iterate(v)
        out[k] = {
            "valid": v.is_valid,
            "components": len(ps),
            "holes": sum(len(p.interiors) for p in ps),
            "area_mm2": v.area,
            "edge_clearance_mm": v.distance(outline.boundary),
            "outside_area_mm2": v.difference(outline).area,
            "small_components_below_0_002mm2": [
                list(p.centroid.coords[0]) for p in ps if p.area < 0.002
            ],
        }
    out["copper_gap_violations"] = gaps(g["cu"], limits["copper_gap_mm"])
    out["mask_gap_violations"] = gaps(g["mask"], limits["mask_gap_mm"])
    out["silk_to_mask_gap_mm"] = g["silk"].distance(g["mask"])
    out["silk_mask_overlap_mm2"] = g["silk"].intersection(g["mask"]).area
    out["silk_to_outline_gap_mm"] = g["silk"].distance(outline.boundary)
    out["mask_without_copper_area_mm2"] = g["mask"].difference(g["cu"]).area
    return out
