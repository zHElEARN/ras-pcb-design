"""One place for KiCad discovery and subprocesses; no shell or system-Python imports."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .project import read_json


def tools():
    cli = os.environ.get("KICAD_CLI") or shutil.which("kicad-cli")
    if not cli:
        mac = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
        if mac.exists():
            cli = str(mac)
    if not cli or not Path(cli).is_file():
        raise FileNotFoundError("Set KICAD_CLI to the KiCad CLI executable.")
    python = os.environ.get("KICAD_PYTHON")
    if not python:
        framework = Path(cli).resolve().parent.parent / "Frameworks/Python.framework/Versions"
        candidates = sorted(framework.glob("*/bin/python3"))
        if candidates:
            python = str(candidates[-1])
    if not python or not Path(python).is_file():
        raise FileNotFoundError(
            "Set KICAD_PYTHON to a Python interpreter containing pcbnew (KiCad bundled Python on macOS)."
        )
    return str(cli), str(python)


def run(project, command, log_name):
    env = dict(os.environ)
    env["KICAD_CONFIG_HOME"] = str(project.output / ".kicad-config")
    result = subprocess.run(
        [str(p) for p in command],
        cwd=project.root,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode:
        details = (result.stderr or result.stdout).strip()[-1000:]
        raise RuntimeError(f"KiCad command failed ({result.returncode}) in {log_name}: {details}")
    return result.stdout


def export(project, render_3d=False):
    cli, python = tools()
    name = project.name
    board = project.output / "kicad" / f"{name}.kicad_pcb"
    run(
        project,
        [
            python,
            Path(__file__).with_name("kicad_worker.py"),
            "--input",
            project.output / "geometry.json",
            "--output",
            project.output / "kicad",
        ],
        "kicad_build.log",
    )
    run(
        project,
        [
            cli,
            "pcb",
            "export",
            "gerbers",
            board,
            "-o",
            str(project.output / "gerber") + "/",
            "-l",
            "F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,Edge.Cuts",
            "--no-netlist",
            "--precision",
            "6",
        ],
        "gerber_export.log",
    )
    drc_result = drc(project, cli)
    export_drills(project, cli)
    # Do not package stale drill files when a later design removes its holes.
    for path in (project.output / "gerber").glob(f"{name}-*.drl"):
        path.unlink()
    if project.board["drills"]:
        source = project.output / f"checks/drill_export/{name}-NPTH.drl"
        shutil.copy2(source, project.output / "gerber" / source.name)
    if render_3d:
        for side, camera in [("front", "top"), ("back", "bottom")]:
            run(
                project,
                [
                    cli,
                    "pcb",
                    "render",
                    board,
                    "-o",
                    project.output / f"preview/kicad_3d_{side}.png",
                    "--side",
                    camera,
                    "--width",
                    "2400",
                    "--height",
                    "850",
                    "--quality",
                    "high",
                    "--background",
                    "opaque",
                    "--use-board-stackup-colors",
                    "--zoom",
                    "2.5",
                ],
                f"render_{side}.log",
            )
    return drc_result


def export_drills(project, cli=None):
    cli = cli or tools()[0]
    run(
        project,
        [
            cli,
            "pcb",
            "export",
            "drill",
            project.output / f"kicad/{project.name}.kicad_pcb",
            "-o",
            str(project.output / "checks/drill_export") + "/",
            "--excellon-separate-th",
        ],
        "drill_export.log",
    )


def drc(project, cli=None):
    cli = cli or tools()[0]
    run(
        project,
        [
            cli,
            "pcb",
            "drc",
            project.output / f"kicad/{project.name}.kicad_pcb",
            "--format",
            "json",
            "--severity-all",
            "-o",
            project.output / "checks/kicad_drc.json",
        ],
        "kicad_drc.log",
    )
    return read_json(project.output / "checks/kicad_drc.json")
