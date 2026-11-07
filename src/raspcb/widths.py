"""Raster-medial-axis screening of vector local widths, not a manufacturing proof."""

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt, label


from . import geom
from .layout import from_polygons
from .project import read_json


def skeletonize(image):
    # NumPy Zhang-Suen thinning; avoids native extension incompatibilities.
    a = np.pad(image.astype(np.uint8), 1)
    while True:
        changed = False
        for phase in (0, 1):
            p = [
                a[:-2, 1:-1],
                a[:-2, 2:],
                a[1:-1, 2:],
                a[2:, 2:],
                a[2:, 1:-1],
                a[2:, :-2],
                a[1:-1, :-2],
                a[:-2, :-2],
            ]
            count = sum(p)
            transitions = sum(
                ((p[i] == 0) & (p[(i + 1) % 8] != 0)).astype(np.uint8) for i in range(8)
            )
            if phase == 0:
                cond = (p[0] * p[2] * p[4] == 0) & (p[2] * p[4] * p[6] == 0)
            else:
                cond = (p[0] * p[2] * p[6] == 0) & (p[0] * p[4] * p[6] == 0)
            remove = (a[1:-1, 1:-1] != 0) & (count >= 2) & (count <= 6) & (transitions == 1) & cond
            if remove.any():
                a[1:-1, 1:-1][remove] = 0
                changed = True
        if not changed:
            break
    return a[1:-1, 1:-1].astype(bool)


def run(project):
    OUT = project.output
    limits = project.rules["limits"]
    SCALE = limits["screening_scale_px_per_mm"]
    fixture = np.zeros((20, 20), dtype=bool)
    fixture[3:17, 3:17] = True
    assert skeletonize(fixture).sum() < 20
    d = read_json(OUT / "geometry.json")
    report = {}
    for side, record in d["sides"].items():
        report[side] = {}
        for key in ["cu", "silk"]:
            candidates = []
            for i, p in enumerate(geom.iterate(from_polygons(record["layers"][key]))):
                x0, y0, x1, y1 = p.bounds
                pad = 4
                im = Image.new(
                    "1",
                    (int((y1 - y0) * SCALE) + 2 * pad + 2, int((x1 - x0) * SCALE) + 2 * pad + 2),
                    0,
                )

                def pts(r, x0=x0, y0=y0, pad=pad):
                    return [((y - y0) * SCALE + pad, (x - x0) * SCALE + pad) for x, y in r.coords]

                dr = ImageDraw.Draw(im)
                dr.polygon(pts(p.exterior), fill=1)
                for r in p.interiors:
                    dr.polygon(pts(r), fill=0)
                m = np.array(im, dtype=bool, copy=True)
                dist = distance_transform_edt(m)
                skel = skeletonize(m)
                thin = skel & (2 * dist / SCALE < limits["screening_width_mm"])
                labels, n = label(thin, structure=np.ones((3, 3)))
                features = []
                for j in range(1, n + 1):
                    yy, xx = np.where(labels == j)
                    # Exclude tiny corner tapers; keep sustained thin lines or small solid glyphs.
                    span = max(np.ptp(yy), np.ptp(xx)) / SCALE
                    if span < limits["screening_span_mm"]:
                        continue
                    widths = 2 * dist[yy, xx] / SCALE
                    features.append(
                        {
                            "screening_width_mm": float(np.median(widths)),
                            "span_mm": float(span),
                            "centre_art_mm": [
                                float(x0 + (np.median(yy) - pad) / SCALE),
                                float(y0 + (np.median(xx) - pad) / SCALE),
                            ],
                        }
                    )
                if features:
                    candidates.append(
                        {"component": i, "bounds_mm": list(p.bounds), "features": features}
                    )
            report[side][key] = candidates
    result = {
        "method": "raster skeleton screening, not a strict width proof",
        "limits": limits,
        "input_sha256": project.inputs(),
        "results": report,
    }
    return result
