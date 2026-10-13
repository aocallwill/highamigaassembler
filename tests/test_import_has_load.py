"""Compile the three HAS #import bob/sprite load examples (both CPU targets)."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL.Image")

from hasc import parser, validator, codegen  # noqa: E402
from hasc.target import CpuTarget, TargetSpec  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COMPILER_TESTS = ROOT / "examples" / "tests" / "compiler"
ASSETS = COMPILER_TESTS / "assets"

BOB_HAS = COMPILER_TESTS / "import_bob_load_test.has"
SPRITE_HAS = COMPILER_TESTS / "import_sprite_load_test.has"
BOTH_HAS = COMPILER_TESTS / "import_bob_sprite_load_test.has"
ATLAS_HAS = COMPILER_TESTS / "import_atlas_load_test.has"
TILES_HAS = COMPILER_TESTS / "import_tiles_load_test.has"


def _compile_has(src_path: Path, out_dir: Path, cpu: str) -> str:
    text = src_path.read_text(encoding="utf-8")
    gen_dir = out_dir / "gen"
    out_s = out_dir / f"{src_path.stem}_{cpu}.s"
    mod = parser.parse(
        text,
        base_dir=str(src_path.parent),
        asset_outdir=str(gen_dir),
        force_assets=True,
    )
    val = validator.Validator(mod)
    val.validate()
    val.apply_resolutions()
    cg = codegen.CodeGen(mod, TargetSpec.for_cpu(cpu))
    cg.output_path = str(out_s)
    asm = cg.gen()
    out_s.write_text(asm, encoding="utf-8")
    return asm


@pytest.mark.parametrize("cpu", [CpuTarget.M68000.value, CpuTarget.M68020.value])
def test_import_bob_load_has(tmp_path: Path, cpu: str):
    assert (ASSETS / "import_bob_player.png").is_file()
    asm = _compile_has(BOB_HAS, tmp_path / "bob", cpu)

    assert "CreateBob" in asm
    assert "DestroyBob" in asm
    assert "lea import_bob_player" in asm
    assert "INCLUDE" in asm
    assert "import_bob_player.s" in asm
    assert (tmp_path / "bob" / "gen" / "import_bob_player.s").is_file()
    gen = (tmp_path / "bob" / "gen" / "import_bob_player.s").read_text(encoding="utf-8")
    assert "DATA_C" in gen.replace("\t", " ")
    assert "converted width=32px" in gen  # 16 + add_word


@pytest.mark.parametrize("cpu", [CpuTarget.M68000.value, CpuTarget.M68020.value])
def test_import_sprite_load_has(tmp_path: Path, cpu: str):
    assert (ASSETS / "import_sprite_bullet.png").is_file()
    asm = _compile_has(SPRITE_HAS, tmp_path / "sprite", cpu)

    assert "CreateSprite" in asm
    assert "lea import_sprite_bullet" in asm
    assert "INCLUDE" in asm
    assert "import_sprite_bullet.s" in asm
    gen = (tmp_path / "sprite" / "gen" / "import_sprite_bullet.s").read_text(encoding="utf-8")
    assert "sprite_templates" in gen.replace("\t", " ")
    assert "2 bitplanes" in gen or "4 colors" in gen.lower()


@pytest.mark.parametrize("cpu", [CpuTarget.M68000.value, CpuTarget.M68020.value])
def test_import_bob_and_sprite_load_has(tmp_path: Path, cpu: str):
    asm = _compile_has(BOTH_HAS, tmp_path / "both", cpu)

    assert "CreateBob" in asm
    assert "CreateSprite" in asm
    assert "DestroyBob" in asm
    assert "lea import_combo_bob" in asm
    assert "lea import_combo_sprite" in asm
    assert "import_combo_bob.s" in asm
    assert "import_combo_sprite.s" in asm
    # Both INCLUDEs present
    assert asm.count("INCLUDE") >= 2


@pytest.mark.parametrize("cpu", [CpuTarget.M68000.value, CpuTarget.M68020.value])
def test_import_atlas_load_has(tmp_path: Path, cpu: str):
    assert (ASSETS / "mini_atlas.xml").is_file()
    assert (ASSETS / "mini_atlas.png").is_file()
    asm = _compile_has(ATLAS_HAS, tmp_path / "atlas", cpu)

    assert "LoadPalette" in asm
    assert "CreateBob" in asm
    assert "lea walk_palette" in asm
    assert "lea walk_frame_0" in asm
    assert "lea walk_frame_1" in asm
    assert "walk_atlas.s" in asm
    gen = tmp_path / "atlas" / "gen"
    assert (gen / "walk_atlas.s").is_file()
    assert (gen / "walk_palette.s").is_file()
    assert (gen / "walk_frame_0.s").is_file()
    assert (gen / "walk_frame_1.s").is_file()


@pytest.mark.parametrize("cpu", [CpuTarget.M68000.value, CpuTarget.M68020.value])
def test_import_tileset_tilemap_load_has(tmp_path: Path, cpu: str):
    assert (ASSETS / "mini_tiles.png").is_file()
    assert (ASSETS / "mini_map.tmx").is_file()
    asm = _compile_has(TILES_HAS, tmp_path / "tiles", cpu)

    assert "LoadPalette" in asm
    assert "lea level_pal" in asm
    assert "lea level_tiles" in asm
    assert "lea level_map" in asm
    assert "level_pal.s" in asm
    assert "level_tiles.s" in asm
    assert "level_map.s" in asm
    gen = tmp_path / "tiles" / "gen"
    tiles = (gen / "level_tiles.s").read_text(encoding="utf-8")
    assert "DATA_C" in tiles.replace("\t", " ")
    assert "level_tiles_palette:" not in tiles
    mmap = (gen / "level_map.s").read_text(encoding="utf-8")
    assert "SECTION tilemap,DATA" in mmap.replace("\t", " ")
    assert "DATA_C" not in mmap
