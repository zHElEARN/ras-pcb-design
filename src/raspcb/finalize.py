"""Gate a minimal local fabrication archive on all verification results."""

from __future__ import annotations

import zipfile

GERBER_SUFFIXES = (
    "F_Cu.gtl",
    "B_Cu.gbl",
    "F_Mask.gts",
    "B_Mask.gbs",
    "F_Silkscreen.gto",
    "B_Silkscreen.gbo",
    "Edge_Cuts.gm1",
)


def run(project, audit, drc, gerber, widths):
    errors = []
    if drc["violations"] or drc["unconnected_items"]:
        errors.append("KiCad DRC 有未解决项目")
    limits = project.rules["limits"]
    for side, record in audit.items():
        checks = record["after"]
        if checks["copper_gap_violations"] or checks["mask_gap_violations"]:
            errors.append(f"{side}: 铜或开窗间距不足")
        if checks["cu"]["edge_clearance_mm"] < limits["copper_edge_mm"] - 1e-6:
            errors.append(f"{side}: 铜到板边不足")
        if checks["silk_to_mask_gap_mm"] < limits["silk_to_mask_mm"] - 1e-6:
            errors.append(f"{side}: 丝印到开窗不足")
        if widths["results"][side]["cu"]:
            errors.append(f"{side}: 局部铜宽筛查需要复核")
    warnings = []
    for side, record in widths["results"].items():
        if record["silk"]:
            warnings.append(
                f"{side}: {len(record['silk'])} 个丝印连通块存在持续细笔画候选；"
                "数值筛查不等于严格最小宽度证明。"
            )
    assert gerber["outline"]["closed_contours"] == 1
    assert gerber["drills"]["count"] == len(project.board["drills"])
    status = {
        "errors": errors,
        "warnings": warnings,
        "drc_violations": len(drc["violations"]),
        "gerber_verified": True,
        "drill_count": gerber["drills"]["count"],
        "upload_package_generated": not errors,
    }

    # KiCad's job metadata is not a Gerber layer or an upload document.
    out = project.output
    job = out / f"gerber/{project.name}-job.gbrjob"
    job.unlink(missing_ok=True)
    (out / f"gerber/FAB_NOTES.txt").unlink(missing_ok=True)
    upload = out / "packages" / f"{project.name}_JLC_Gerber.zip"
    upload.unlink(missing_ok=True)
    if not errors:
        suffixes = [*GERBER_SUFFIXES]
        if project.board["drills"]:
            suffixes.append("NPTH.drl")
        with zipfile.ZipFile(upload, "w", zipfile.ZIP_DEFLATED) as archive:
            for suffix in suffixes:
                path = out / "gerber" / f"{project.name}-{suffix}"
                archive.write(path, path.name)
    return status
