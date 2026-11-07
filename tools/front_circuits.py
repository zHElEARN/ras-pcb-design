"""Decorative covered-copper routes in front-side negative space only."""

from pathlib import Path
import json

from shapely.affinity import affine_transform
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from raspcb import geom, holes
from raspcb.checks import gaps
from raspcb.layout import from_polygons, to_polygons

ROOT=Path(__file__).resolve().parents[1]
PREFIX="front_decorative_circuit_"
WIDTH=0.22


def route(points, index):
    line=LineString(points).buffer(WIDTH/2,cap_style=1,join_style=1,quad_segs=12)
    end=Point(points[-1]).buffer(0.36,quad_segs=32)
    if index%2==0:
        end=end.difference(Point(points[-1]).buffer(0.14,quad_segs=32))
        # Keep the line from filling the deliberate copper-ring centre.
        line=line.difference(Point(points[-1]).buffer(0.14,quad_segs=32))
    start=Point(points[0]).buffer(0.31,quad_segs=32)
    return unary_union([line,start,end])


def main():
    paths={
        "left":[[(4.6+0.9*i,10.8),(4.6+0.9*i,17.5),
                 (7.6+0.9*i,20.5),(7.6+0.9*i,22.2)] for i in range(3)],
        "middle":[[(65.6,17.0+0.8*i),(67.8,17.0+0.8*i),
                   (71.0,13.8+0.8*i),(77.8-1.6*i,13.8+0.8*i)] for i in range(3)],
        "lower_right":[[(68+2*i,28.5-0.8*i),(94-0.8*i,28.5-0.8*i),
                        (98-0.8*i,24.5-0.8*i),(98-0.8*i,20.5-0.8*i)] for i in range(3)],
    }
    p=ROOT/"layout/front.json"
    layout=json.loads(p.read_text())
    layout["groups"]=[g for g in layout["groups"] if not g["id"].startswith(PREFIX)]
    enabled=[g for g in layout["groups"] if g.get("enabled",True)]
    silk=unary_union([from_polygons(g["geometry"].get("silk",[])) for g in enabled])
    old_cu=unary_union([from_polygons(g["geometry"].get("cu",[])) for g in enabled])
    board=json.loads((ROOT/"config/board.json").read_text())
    edge=Polygon(board["outline_front_mm"])
    all_cu=[]
    for name,lines in paths.items():
        art=unary_union([route(points,i) for i,points in enumerate(lines)])
        art=affine_transform(art,[0,1,-1,0,0,109])
        metrics={"silk_clearance_mm":art.distance(silk),
                 "old_copper_clearance_mm":art.distance(old_cu),
                 "hole_clearance_mm":art.distance(holes.geometry(board,"front")),
                 "edge_clearance_mm":art.distance(edge.boundary)}
        print(name,json.dumps(metrics),flush=True)
        assert edge.covers(art)
        assert metrics["silk_clearance_mm"]>=0.4, name
        assert metrics["old_copper_clearance_mm"]>=0.2, name
        assert metrics["hole_clearance_mm"]>=0.3, name
        assert metrics["edge_clearance_mm"]>=0.25, name
        assert len(geom.iterate(art))==len(lines),name
        assert not gaps(art,0.15),name
        all_cu.append(art)
        layout["groups"].append({"id":PREFIX+name,"enabled":True,
            "metadata":{"layer":"F.Cu","line_width_mm":WIDTH,
                "landscape_routes_mm":lines,"endpoint_outer_diameter_mm":0.72,
                "endpoint_inner_diameter_mm":0.28},
            "geometry":{"cu":to_polygons(art)}})
    assert not gaps(unary_union([old_cu,*all_cu]),0.1)
    p.write_text(json.dumps(layout,ensure_ascii=False,indent=2)+"\n")


if __name__=="__main__":
    main()
