"""Recompose the existing band vector mark into clear front silkscreen space."""

from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path import parse_path
from shapely.affinity import affine_transform, scale, translate
from shapely.geometry import LineString, box
from shapely.ops import unary_union

from raspcb import geom, holes
from raspcb.glyphs import _rings_from_pen, rings_to_multi
from raspcb.layout import from_polygons, to_polygons

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/vectors/raise-a-suilen-logo.svg"
IDS = ("front_band_wordmark", "front_headphone_badge")


def place(g, left, top, factor):
    x0,y0,_,_ = g.bounds
    return translate(scale(g,xfact=factor,yfact=factor,origin=(x0,y0)),
                     xoff=left-x0,yoff=top-y0)


def to_board(g):
    # Landscape (u right, v down) -> face-on board (x down,y left).
    return affine_transform(g,[0,1,-1,0,0,109])


def main():
    pieces=[]
    for e in ET.parse(SOURCE).iter("{http://www.w3.org/2000/svg}path"):
        pen=RecordingPen();parse_path(e.attrib["d"],pen)
        pieces.extend(geom.iterate(rings_to_multi(_rings_from_pen(pen,steps=18))))
    headphone=unary_union([p for p in pieces if p.bounds[2]<130 and p.bounds[3]<110])
    lettering=unary_union([p for p in pieces if not (p.bounds[2]<130 and p.bounds[3]<110)])
    assert not headphone.is_empty and not lettering.is_empty
    # Keep a shared transform, then open two tight seams in the source mark:
    # upper R/A letter spacing and the waveform inside the large A.
    lx,ly,_,_=lettering.bounds
    word_pieces=[]
    for p in geom.iterate(lettering):
        part=affine_transform(p,[0.057,0,0,0.057,73.5-lx*0.057,1.8-ly*0.057])
        x0,y0,x1,y1=p.bounds
        if 130<x0<140 and x1<195 and y1<105:
            part=translate(part,xoff=-0.25)
        if x0>390 and y0>70 and y1<130:
            part=part.buffer(-0.065,quad_segs=8)
        word_pieces.append(part)
    word=unary_union(word_pieces)
    phone=place(headphone,65.7,3.0,6.5/(headphone.bounds[2]-headphone.bounds[0]))
    # Four equal-width open corner brackets, echoing back-side label geometry.
    corners=[[(64.9,4.3),(64.9,2.2),(67.0,2.2)],
             [(70.9,2.2),(73.0,2.2),(73.0,4.3)],
             [(64.9,6.8),(64.9,8.9),(67.0,8.9)],
             [(70.9,8.9),(73.0,8.9),(73.0,6.8)]]
    brackets=unary_union([LineString(p).buffer(0.11,cap_style=2,join_style=2) for p in corners])
    bars=[];u=65.1
    for width in [0.25,0.5,0.25,0.25,0.5,0.25,0.5,0.25,0.25,0.5,0.25,0.25]:
        bars.append(box(u,10.0,u+width,11.4));u+=width+0.28
    badge=unary_union([phone,brackets,*bars])
    layouts=ROOT/"layout/front.json"
    layout=json.loads(layouts.read_text())
    layout["groups"]=[g for g in layout["groups"] if g["id"] not in IDS]
    existing=unary_union([from_polygons(g["geometry"].get("silk",[]))
                          for g in layout["groups"] if g.get("enabled",True)])
    mask=unary_union([from_polygons(g["geometry"].get("mask",[]))
                      for g in layout["groups"] if g.get("enabled",True)])
    board=json.loads((ROOT/"config/board.json").read_text())
    report={}
    for name,art in zip(IDS,(word,badge)):
        art=to_board(art).simplify(0.001,preserve_topology=True)
        assert art.is_valid
        assert art.distance(existing)>=0.5, (name,art.distance(existing))
        assert art.distance(mask)>=0.3
        assert art.distance(holes.geometry(board,"front"))>=0.3
        report[name]={"existing_silk_clearance_mm":art.distance(existing),
                      "mask_clearance_mm":art.distance(mask),
                      "bounds_xyxy_mm":list(art.bounds)}
        layout["groups"].append({"id":name,"enabled":True,
            "metadata":{"layer":"F.SilkS","source_svg":str(SOURCE.relative_to(ROOT)),
                        "source_sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest()},
            "geometry":{"silk":to_polygons(art)}})
        existing=unary_union([existing,art])
    layouts.write_text(json.dumps(layout,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
