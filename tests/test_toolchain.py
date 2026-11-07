"""Checks for source preservation, contour holes and read-only layout compilation."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon

from raspcb import geom
from raspcb.layout import from_polygons, load, mirror, to_polygons
from raspcb.compile_layout import run as prepare
from raspcb.project import Project, read_json, write_json
from raspcb.widths import skeletonize

ROOT = Path(__file__).resolve().parents[1]


class GeometryTests(unittest.TestCase):
    def test_counter_before_outer_contour(self):
        hole = Polygon([(1, 1), (2, 1), (2, 2), (1, 2)])
        outer = Polygon([(0, 0), (3, 0), (3, 3), (0, 3)])
        result = geom.assemble([hole, outer])
        self.assertEqual(len(result.interiors), 1)
        self.assertEqual(result.area, 8)
        self.assertTrue(from_polygons(to_polygons(result)).equals(result))

    def test_back_reflection_is_involution(self):
        shape = Polygon([(2, 4), (3, 4), (4, 5)])
        self.assertLess(mirror(mirror(shape)).hausdorff_distance(shape), 1e-12)

    def test_width_skeleton_removes_filled_interior(self):
        fixture = np.zeros((20, 20), dtype=bool)
        fixture[3:17, 3:17] = True
        self.assertLess(skeletonize(fixture).sum(), 20)


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for path in [
            "config/board.json",
            "config/checks.json",
            "layout/front.json",
            "layout/back.json",
        ]:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / path).read_bytes())
        self.project = Project(self.root, self.root / "build")

    def test_compilation_preserves_all_source_layers(self):
        source = load(self.project)
        output = prepare(self.project)
        for side in ["front", "back"]:
            for layer in ["cu", "mask", "silk"]:
                self.assertLess(
                    from_polygons(source[side]["layers"][layer])
                    .symmetric_difference(from_polygons(output["sides"][side]["layers"][layer]))
                    .area,
                    1e-10,
                )

    def test_fabrication_preserves_source_files_and_silk(self):
        before = self.project.inputs()
        source = load(self.project)
        output = prepare(self.project)
        self.assertEqual(before, self.project.inputs())
        for side in ["front", "back"]:
            self.assertTrue(
                from_polygons(source[side]["layers"]["silk"]).equals(
                    from_polygons(output["sides"][side]["layers"]["silk"])
                )
            )
        self.assertNotIn("ring_adjustments", output)
        self.assertNotIn("pad_adjustments", output)

    def test_layout_group_can_be_disabled(self):
        before = load(self.project)
        path = self.root / "layout/front.json"
        source = read_json(path)
        # Historical wordmark groups may already be disabled in the current design.
        next(g for g in source["groups"]
             if g.get("enabled", True) and g["geometry"].get("silk"))["enabled"] = False
        write_json(path, source)
        after = load(self.project)
        self.assertLess(
            from_polygons(after["front"]["layers"]["silk"]).area,
            from_polygons(before["front"]["layers"]["silk"]).area,
        )

    def test_default_preview_needs_no_scan_assets(self):
        from raspcb import preview

        # setUp copies vector layouts/config only, with no photos or scans.
        preview.run(self.project)
        destination = self.project.output / "preview"
        self.assertTrue((destination / "artwork_both_sides.png").is_file())
        self.assertFalse(list(destination.glob("*_compare*.png")))
        self.assertFalse(list(destination.glob("*_overlay*.png")))

    def test_duplicate_group_rejected(self):
        path = self.root / "layout/front.json"
        source = read_json(path)
        source["groups"].append(source["groups"][0])
        write_json(path, source)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            load(self.project)

    def test_output_cannot_overwrite_sources(self):
        with self.assertRaises(ValueError):
            Project(self.root, self.root / "layout")
        with self.assertRaises(ValueError):
            Project(self.root, self.root)

if __name__ == "__main__":
    unittest.main()
