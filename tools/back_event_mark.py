"""Place the existing event SVG in the clear lower strip of the back PCB."""

from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path import parse_path
from shapely.affinity import affine_transform
from shapely.geometry import Polygon
from shapely.ops import unary_union

from raspcb import holes
from raspcb.glyphs import _rings_from_pen, rings_to_multi
from raspcb.layout import from_polygons, to_polygons

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"assets/vectors/boot-ignition-hong-kong.svg"
GROUP="back_boot_ignition_hong_kong"


def main():
    parts=[]
    for path in ET.parse(SOURCE).iter("{http://www.w3.org/2000/svg}path"):
        pen=RecordingPen();parse_path(path.attrib["d"],pen)
        parts.append(rings_to_multi(_rings_from_pen(pen,steps=18)))
    source=unary_union(parts)
    u0,v0,u1,v1=source.bounds
    factor=26/(u1-u0)
    # Uniform 26 mm width; landscape left=47, top=25.4 mm.
    matrix=[0,factor,-factor,0,25.4-v0*factor,109-47+u0*factor]
    mark=affine_transform(source,matrix)
    path=ROOT/"layout/back.json"
    data=json.loads(path.read_text())
    data["groups"]=[g for g in data["groups"] if g["id"]!=GROUP]
    enabled=[g for g in data["groups"] if g.get("enabled",True)]
    layers={k:unary_union([from_polygons(g["geometry"].get(k,[])) for g in enabled])
            for k in ("cu","mask","silk")}
    board=json.loads((ROOT/"config/board.json").read_text())
    # Back face-on outline reflects only the across-width axis.
    outline=affine_transform(Polygon(board["outline_front_mm"]),[-1,0,0,1,30,0])
    result={"bounds_xyxy_mm":list(mark.bounds),"width_mm":26,
            "height_mm":(v1-v0)*factor,
            "silk_clearance_mm":mark.distance(layers["silk"]),
            "copper_clearance_mm":mark.distance(layers["cu"]),
            "mask_clearance_mm":mark.distance(layers["mask"]),
            "edge_clearance_mm":mark.distance(outline.boundary),
            "hole_clearance_mm":mark.distance(holes.geometry(board,"back"))}
    assert mark.is_valid and outline.covers(mark)
    assert min(result[k] for k in ("silk_clearance_mm","copper_clearance_mm"))>=0.4
    assert result["mask_clearance_mm"]>=0.15
    assert result["hole_clearance_mm"]>=0.15
    assert result["edge_clearance_mm"]>=0.5
    data["groups"].append({"id":GROUP,"enabled":True,
        "metadata":{"layer":"B.SilkS","source_svg":str(SOURCE.relative_to(ROOT)),
                    "source_sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                    "svg_to_face_on_board_matrix":matrix},
        "geometry":{"silk":to_polygons(mark)}})
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
