"""Run with KiCad's bundled Python (pcbnew). Input is audited mm geometry."""

import argparse
import json
import math
from pathlib import Path

import pcbnew


def point(x, y):
    return pcbnew.VECTOR2I(round(x * 1e6), round(y * 1e6))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    OUT = args.output
    OUT.mkdir(parents=True, exist_ok=True)
    data = json.loads(args.input.read_text())

    def xy(p, back=False):
        x, y = p
        if back:
            x = data["width_mm"] - x
        return data["kicad_origin_mm"][0] + data["length_mm"] - y, data["kicad_origin_mm"][1] + x

    b = pcbnew.BOARD()
    b.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(data["thickness_mm"]))
    settings = b.GetDesignSettings()
    settings.m_CopperEdgeClearance = pcbnew.FromMM(data["rules"]["copper_edge_mm"])
    settings.m_MinClearance = pcbnew.FromMM(data["rules"]["copper_gap_mm"])
    settings.m_SilkClearance = pcbnew.FromMM(data["rules"]["silk_to_mask_mm"])
    settings.m_MinSilkTextThickness = pcbnew.FromMM(data["rules"]["silk_stroke_mm"])
    for side, record in data["sides"].items():
        back = side == "back"
        for key, name in [("cu", "Cu"), ("mask", "Mask"), ("silk", "SilkS")]:
            layer = getattr(pcbnew, ("B_" if back else "F_") + name)
            for exterior, holes in record["layers"][key]:
                poly = pcbnew.SHAPE_POLY_SET()
                poly.NewOutline()
                for p in exterior[:-1]:
                    poly.Append(point(*xy(p, back)))
                for ring in holes:
                    index = poly.NewHole(0)
                    for p in ring[:-1]:
                        poly.Append(point(*xy(p, back)), 0, index)
                item = pcbnew.PCB_SHAPE(b)
                item.SetShape(pcbnew.SHAPE_T_POLY)
                item.SetPolyShape(poly)
                item.SetFilled(True)
                item.SetWidth(0)
                item.SetLayer(layer)
                b.Add(item)
    # NPTH pads have no copper annulus; matching mask apertures keep the holes open.
    for hole in data["drills"]:
        footprint = pcbnew.FOOTPRINT(b)
        footprint.SetReference(hole["id"])
        footprint.Reference().SetVisible(False)
        footprint.Value().SetVisible(False)
        footprint.SetPosition(point(*xy(hole["center_front_mm"])))
        pad = pcbnew.PAD(footprint)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        diameter = pcbnew.FromMM(hole["diameter_mm"])
        pad.SetSize(pcbnew.VECTOR2I(diameter, diameter))
        pad.SetDrillSize(pcbnew.VECTOR2I(diameter, diameter))
        pad.SetLayerSet(pcbnew.LSET.AllCuMask())
        pad.SetPosition(footprint.GetPosition())
        footprint.Add(pad)
        b.Add(footprint)
        # Explicit mask circles avoid inheriting KiCad's default hole-tenting setting.
        centre = point(*xy(hole["center_front_mm"]))
        for layer in [pcbnew.F_Mask, pcbnew.B_Mask]:
            polygon = pcbnew.SHAPE_POLY_SET()
            polygon.NewOutline()
            for index in range(384):
                angle = 2 * math.pi * index / 384
                polygon.Append(
                    pcbnew.VECTOR2I(
                        centre.x + round(diameter / 2 * math.cos(angle)),
                        centre.y + round(diameter / 2 * math.sin(angle)),
                    )
                )
            aperture = pcbnew.PCB_SHAPE(b)
            aperture.SetShape(pcbnew.SHAPE_T_POLY)
            aperture.SetPolyShape(polygon)
            aperture.SetFilled(True)
            aperture.SetWidth(0)
            aperture.SetLayer(layer)
            b.Add(aperture)
    # Outline is the approved vector art profile, including sampled circular notches.
    # Preserve all source vertices for board shape comparison; mechanical holes are exported separately as NPTH.
    pts = data["sides"]["front"]["edge_cuts_mm"]
    for index in range(len(pts) - 1):
        a, c = pts[index], pts[index + 1]
        if a == c:
            continue
        item = pcbnew.PCB_SHAPE(b)
        item.SetShape(pcbnew.SHAPE_T_SEGMENT)
        item.SetStart(point(*xy(a)))
        item.SetEnd(point(*xy(c)))
        item.SetWidth(pcbnew.FromMM(data["edge_line_width_mm"]))
        item.SetLayer(pcbnew.Edge_Cuts)
        b.Add(item)
    b.GetPlotOptions().SetCreateGerberJobFile(True)
    target = OUT / (data["name"] + ".kicad_pcb")
    pcbnew.SaveBoard(str(target), b)
    stack = f'''\n        (stackup
            (layer "F.SilkS" (type "Top Silk Screen") (color "{data["silkscreen"].title()}"))
            (layer "F.Mask" (type "Top Solder Mask") (thickness 0.01) (material "Epoxy") (color "{data["solder_mask"].title()}"))
            (layer "F.Cu" (type "copper") (thickness {0.035 * data["copper_oz"]}))
            (layer "dielectric 1" (type "core") (thickness {data["thickness_mm"] - 0.07 * data["copper_oz"]}) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
            (layer "B.Cu" (type "copper") (thickness {0.035 * data["copper_oz"]}))
            (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01) (material "Epoxy") (color "{data["solder_mask"].title()}"))
            (layer "B.SilkS" (type "Bottom Silk Screen") (color "{data["silkscreen"].title()}"))
            (copper_finish "{data["surface_finish"]}") (dielectric_constraints no)
        )'''
    text = target.read_text().replace("(setup", "(setup" + stack, 1)
    target.write_text(text)
    project = {
        "meta": {"filename": data["name"] + ".kicad_pro", "version": 1},
        "board": {
            "design_settings": {
                "rules": {
                    "min_clearance": data["rules"]["copper_gap_mm"],
                    "min_copper_edge_clearance": data["rules"]["copper_edge_mm"],
                    "min_track_width": data["rules"]["copper_gap_mm"],
                    "min_silk_clearance": data["rules"]["silk_to_mask_mm"],
                    "min_text_thickness": data["rules"]["silk_stroke_mm"],
                    "min_text_height": 1.0,
                },
                "rule_severities": {},
            }
        },
    }
    (OUT / (data["name"] + ".kicad_pro")).write_text(json.dumps(project, indent=2) + "\n")
    print("Saved", target, "graphics", len(list(b.GetDrawings())))


if __name__ == "__main__":
    main()
