"""Preview, build and verify the final decorative PCB."""

from __future__ import annotations

import argparse
from pathlib import Path

from .project import Project


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="raspcb", description="艺术 PCB：双面预览、KiCad/Gerber 构建及检查"
    )
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="项目根目录")
    parser.add_argument("--output", type=Path, help="生成目录，默认 <project>/build")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preview", help="从毫米布局生成双面预览")
    build = sub.add_parser("build", help="生成 KiCad、Gerber、预览和本地上传 ZIP")
    build.add_argument("--render-3d", action="store_true", help="附加 KiCad 三维渲染")
    sub.add_parser("check", help="按当前源文件复核现有 KiCad、Gerber 和钻孔")
    args = parser.parse_args(argv)
    root = args.project.resolve()
    output = (args.output or root / "build").resolve()
    project = None
    try:
        project = Project(root, output)
        from . import preview

        if args.command == "preview":
            print(f"双面布局预览：{preview.run(project)}")
            return 0

        from . import compile_layout, finalize, gerber, kicad, widths

        if args.command == "build":
            project.clean_generated()
        else:
            (output / "packages" / f"{project.name}_JLC_Gerber.zip").unlink(missing_ok=True)
        print("1/5 读取毫米布局并检查几何", flush=True)
        geometry = compile_layout.run(project)
        if args.command == "build":
            preview.run(project)
            print("2/5 生成 KiCad、Gerber 和钻孔", flush=True)
            drc = kicad.export(project, render_3d=args.render_3d)
        else:
            print("2/5 检查现有 KiCad PCB", flush=True)
            drc = kicad.drc(project)
            kicad.export_drills(project)
        print("3/5 独立回读 Gerber、板框和钻孔", flush=True)
        gerber_result = gerber.run(project)
        print("4/5 筛查局部细笔画", flush=True)
        width_result = widths.run(project)
        print("5/5 汇总校验结果并生成本地上传包", flush=True)
        status = finalize.run(project, geometry["audit"], drc, gerber_result, width_result)
        board = project.board
        print(
            f"板框 {board['length_mm']:g} × {board['width_mm']:g} mm；"
            f"NPTH {status['drill_count']} 孔；DRC {status['drc_violations']} 项；"
            "Gerber 回读通过。"
        )
        for issue in status["errors"]:
            print(f"错误：{issue}")
        for warning in status["warnings"]:
            print(f"提示：{warning}")
        if status["upload_package_generated"]:
            print(f"本地上传包：{output / 'packages' / (project.name + '_JLC_Gerber.zip')}")
        return 1 if status["errors"] else 0
    except (ValueError, RuntimeError, FileNotFoundError, AssertionError) as exc:
        parser.exit(1, f"raspcb: {exc}\n")
    finally:
        if project is not None and args.command != "preview":
            project.clean_intermediates()


if __name__ == "__main__":
    raise SystemExit(main())
