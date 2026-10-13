"""Unit tests for tools/tiled_map_importer.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools import tiled_map_importer as tmap

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "examples" / "tests" / "compiler" / "assets"


def test_export_tmx_csv_indices():
    asm, meta = tmap.export_tilemap_asm(
        str(ASSETS / "mini_map.tmx"),
        "level_map",
        layer="Ground",
    )
    assert meta["width"] == 4
    assert meta["height"] == 3
    assert meta["firstgid"] == 1
    assert "SECTION tilemap,DATA" in asm.replace("\t", " ")
    assert "level_map:" in asm
    assert "DC.W\t4, 3" in asm or "DC.W 4, 3" in asm.replace("\t", " ")
    # GIDs 1,2 → indices 0,1
    assert "$0000" in asm
    assert "$0001" in asm


def test_export_json_array_indices():
    asm, meta = tmap.export_tilemap_asm(
        str(ASSETS / "mini_map.json"),
        "jmap",
        layer="Ground",
        index_size="b",
    )
    assert meta["index_size"] == "b"
    assert "DC.B" in asm
    assert "jmap:" in asm


def test_flip_flags_rejected(tmp_path: Path):
    tmx = tmp_path / "flip.tmx"
    tmx.write_text(
        '<?xml version="1.0"?>\n'
        '<map orientation="orthogonal" width="1" height="1" '
        'tilewidth="16" tileheight="16">\n'
        ' <tileset firstgid="1" name="t" tilewidth="16" tileheight="16"/>\n'
        ' <layer name="L" width="1" height="1">\n'
        '  <data encoding="csv">2147483649</data>\n'  # 0x80000001
        " </layer>\n"
        "</map>\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="flip"):
        tmap.export_tilemap_asm(str(tmx), "m")


def test_allow_flip_strips_flags(tmp_path: Path):
    tmx = tmp_path / "flip.tmx"
    tmx.write_text(
        '<?xml version="1.0"?>\n'
        '<map orientation="orthogonal" width="1" height="1" '
        'tilewidth="16" tileheight="16">\n'
        ' <tileset firstgid="1" name="t" tilewidth="16" tileheight="16"/>\n'
        ' <layer name="L" width="1" height="1">\n'
        '  <data encoding="csv">2147483649</data>\n'
        " </layer>\n"
        "</map>\n",
        encoding="utf-8",
    )
    asm, _ = tmap.export_tilemap_asm(str(tmx), "m", allow_flip=True)
    assert "$0000" in asm  # 1 - firstgid 1 = 0
