"""Mechanical-hole validation and no-artwork-modification regressions."""

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from raspcb.compile_layout import run
from raspcb.holes import circles, validate
from raspcb.layout import from_polygons, load, mirror
from raspcb.project import Project, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


class HoleTests(unittest.TestCase):
    def test_two_sides_share_one_mechanical_hole(self):
        board = read_json(ROOT / "config/board.json")
        self.assertEqual(len(board["drills"]), 2)
        front, back = circles(board, "front"), circles(board, "back")
        for (f, fg), (b, bg) in zip(front, back, strict=True):
            self.assertEqual(f["id"], b["id"])
            self.assertLess(fg.symmetric_difference(mirror(bg, board["width_mm"])).area, 1e-12)
            self.assertEqual(f["diameter_mm"], 2.3)

    def test_plated_hole_is_not_silently_accepted(self):
        board = read_json(ROOT / "config/board.json")
        board["drills"][0]["type"] = "pth"
        with self.assertRaisesRegex(ValueError, "NPTH"):
            validate(board)

    def test_duplicate_hole_rejected(self):
        board = read_json(ROOT / "config/board.json")
        board["drills"].append(copy.deepcopy(board["drills"][0]))
        with self.assertRaisesRegex(ValueError, "unique"):
            validate(board)

    def test_adding_holes_never_trims_artwork(self):
        project = Project(ROOT, ROOT / "build")
        source = load(project)
        before = {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "layout").glob("*.json")
        }
        with tempfile.TemporaryDirectory() as folder:
            result = run(Project(ROOT, Path(folder)))
        for side in ["front", "back"]:
            for layer in ["cu", "mask", "silk"]:
                self.assertLess(
                    from_polygons(source[side]["layers"][layer])
                    .symmetric_difference(from_polygons(result["sides"][side]["layers"][layer]))
                    .area,
                    1e-10,
                )
        for name, expected in before.items():
            self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(), expected)

    def test_hole_over_copper_fails_instead_of_cutting_line(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for relative in [
                "config/board.json",
                "config/checks.json",
                "layout/front.json",
                "layout/back.json",
            ]:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / relative).read_bytes())
            p = Project(root, root / "build")
            source = load(p)
            point = from_polygons(source["front"]["layers"]["cu"]).representative_point()
            board = p.board
            board["drills"][0]["center_front_mm"] = [point.x, point.y]
            write_json(root / "config/board.json", board)
            before = (root / "layout/front.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "clearance violation"):
                run(p)
            self.assertEqual((root / "layout/front.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
