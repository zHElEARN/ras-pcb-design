"""Project paths, configuration, and generated-file I/O."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Project:
    root: Path
    output: Path

    def __post_init__(self):
        if not (self.root / "config/board.json").is_file():
            raise ValueError(f"Not a RAS PCB project: {self.root}")
        if self.root.is_relative_to(self.output):
            raise ValueError("Output cannot be the project root or its ancestor.")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.board["name"]):
            raise ValueError("Board name must be a portable filename stem.")
        from .holes import validate

        validate(self.board)
        # Generated output may never replace the source layout or assets.
        for path in [
            self.root,
            *(self.root / p for p in ["layout", "config", "assets", "src"]),
        ]:
            if self.output == path or self.output.is_relative_to(path) and path != self.root:
                raise ValueError(f"Output must not overwrite project sources: {self.output}")

    @property
    def board(self):
        return read_json(self.root / "config/board.json")

    @property
    def rules(self):
        return read_json(self.root / "config/checks.json")

    @property
    def name(self):
        return self.board["name"]

    def inputs(self):
        paths = [
            "config/board.json",
            "config/checks.json",
            "layout/front.json",
            "layout/back.json",
        ]
        paths += [
            str(p.relative_to(self.root)) for p in sorted((self.root / "src/raspcb").glob("*.py"))
        ]
        return {p: digest(self.root / p) for p in paths}

    def mkdirs(self):
        for name in ["kicad", "gerber", "checks", "preview", "packages"]:
            (self.output / name).mkdir(parents=True, exist_ok=True)

    def clean_generated(self):
        """Clear only tool-owned outputs; keep other local files in build/."""
        for name in ("kicad", "gerber", "checks", "preview", "packages", "source", ".kicad-config"):
            shutil.rmtree(self.output / name, ignore_errors=True)
        for name in ("geometry.json", "report.html", "manifest.json", "build_identity.json"):
            (self.output / name).unlink(missing_ok=True)

    def clean_intermediates(self):
        shutil.rmtree(self.output / "checks", ignore_errors=True)
        shutil.rmtree(self.output / ".kicad-config", ignore_errors=True)
        (self.output / "geometry.json").unlink(missing_ok=True)
        for path in (self.output / "kicad").glob("*.kicad_prl"):
            path.unlink()
