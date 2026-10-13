"""Console-script wrappers for standalone HAS asset tools."""

import runpy
import sysconfig
from pathlib import Path


def _run_tool(filename: str) -> None:
    tool_path = (
        Path(sysconfig.get_path("data"))
        / "share"
        / "high-amiga-assembler"
        / "tools"
        / filename
    )
    if not tool_path.is_file():
        raise RuntimeError(f"Installed HAS tool not found: {tool_path}")

    runpy.run_path(str(tool_path), run_name="__main__")


def bob_importer() -> None:
    _run_tool("bob_importer.py")


def bob_strip_importer() -> None:
    _run_tool("bob_strip_importer.py")


def c64_font_converter() -> None:
    _run_tool("c64_font_converter.py")


def c64_sprites_to_bobs() -> None:
    _run_tool("c64_sprites_to_bobs.py")


def create_trackio_adf() -> None:
    _run_tool("create_trackio_adf.py")


def frame_merger() -> None:
    _run_tool("frame_merger.py")


def gif_splitter() -> None:
    _run_tool("gif_splitter.py")


def ham6_gen() -> None:
    _run_tool("ham6_gen.py")


def iff_importer() -> None:
    _run_tool("iff_importer.py")


def q16_helper() -> None:
    _run_tool("q16_helper.py")


def sprite_importer() -> None:
    _run_tool("sprite_importer.py")


def sprite_strip_importer() -> None:
    _run_tool("sprite_strip_importer.py")


def texturepacker_atlas_importer() -> None:
    _run_tool("texturepacker_atlas_importer.py")


def tile_importer() -> None:
    _run_tool("tile_importer.py")


def tiled_map_importer() -> None:
    _run_tool("tiled_map_importer.py")
