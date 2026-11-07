"""Render the current two-sided vector layout without reference images."""

from __future__ import annotations

from PIL import Image, ImageDraw
from shapely.geometry import Polygon

from . import holes, raster
from .layout import from_polygons, load
from .raster import Frame
from .text import with_header


def run(project):
    project.mkdirs()
    board = project.board
    frame = Frame(40, 3, length_mm=board["length_mm"], width_mm=board["width_mm"])
    region = (0, 0, frame.h, frame.w)
    renders = {}
    for side, record in load(project).items():
        layers = {key: from_polygons(value) for key, value in record["layers"].items()}
        outline = Polygon(record["edge_cuts_mm"])
        full = frame.blank((14, 14, 17))
        ImageDraw.Draw(full).polygon(
            frame.poly(outline.exterior.coords), fill=raster.BOARD, outline=raster.EDGE
        )
        for geometry, color in [
            (layers["cu"].difference(layers["mask"]), (109, 119, 124)),
            (layers["cu"].intersection(layers["mask"]), (208, 170, 60)),
            (layers["silk"], (241, 241, 239)),
        ]:
            full = raster.render_aa(geometry, frame, region, base=full, fill=color)
        renders[side] = holes.paint(full, board, side, frame, region)

    both = Image.new("RGB", (frame.w, frame.h * 2), (14, 14, 17))
    for index, side in enumerate(("front", "back")):
        both.paste(renders[side], (0, index * frame.h))
    output = project.output / "preview" / "artwork_both_sides.png"
    with_header(both, "ARTWORK - FRONT above / BACK below")[0].save(output)
    return output
