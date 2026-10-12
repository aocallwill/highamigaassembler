"""Tests for #import bob|palette preprocessor directive."""
from pathlib import Path

import pytest

pytest.importorskip("PIL.Image")

from tests.tools_helpers import make_png  # noqa: E402
from hasc import parser, validator, codegen  # noqa: E402
from hasc.target import TargetSpec, CpuTarget  # noqa: E402
from hasc import asset_import as aim  # noqa: E402


def _compile(src: str, tmp_path: Path, base_dir: Path, force: bool = False):
    out_s = tmp_path / "out.s"
    gen_dir = tmp_path / "gen"
    mod = parser.parse(
        src,
        base_dir=str(base_dir),
        asset_outdir=str(gen_dir),
        force_assets=force,
    )
    val = validator.Validator(mod)
    warnings = val.validate()
    val.apply_resolutions()
    cg = codegen.CodeGen(mod, TargetSpec.for_cpu(CpuTarget.M68000.value))
    cg.output_path = str(out_s)
    asm = cg.gen()
    out_s.write_text(asm, encoding="utf-8")
    return mod, asm, gen_dir, warnings


class TestImportBob:
    def test_bob_generates_chip_section_and_label(self, tmp_path: Path):
        png = make_png(tmp_path / "player.png", 16, 4)
        src = (
            f'#import bob "{png.name}" as player_bob planes=2;\n'
            "code main:\n"
            "    proc main() -> int { return 0; }\n"
        )
        mod, asm, gen_dir, _ = _compile(src, tmp_path, tmp_path)
        assert len(mod.asset_imports) == 1
        assert mod.asset_imports[0].label == "player_bob"
        gen = gen_dir / "player_bob.s"
        assert gen.exists()
        text = gen.read_text(encoding="utf-8")
        assert "SECTION bobs,DATA_C" in text.replace("\t", " ")
        assert "player_bob:" in text
        assert "INCLUDE" in asm
        assert "player_bob.s" in asm

    def test_address_of_import_label(self, tmp_path: Path):
        png = make_png(tmp_path / "bob.png", 16, 2)
        src = (
            f'#import bob "{png.name}" as my_bob planes=2;\n'
            "code main:\n"
            "    proc main() -> int {\n"
            "        var p: int = &my_bob;\n"
            "        return p;\n"
            "    }\n"
        )
        _, asm, _, _ = _compile(src, tmp_path, tmp_path)
        assert "lea my_bob" in asm
        assert "my_bob.s" in asm


class TestImportPalette:
    def test_palette_emits_color_words(self, tmp_path: Path):
        png = make_png(tmp_path / "sky.png", 8, 8)
        src = (
            f'#import palette "{png.name}" as sky_pal colors=16 dither=none;\n'
            "code main:\n"
            "    proc main() -> int {\n"
            "        var p: int = &sky_pal;\n"
            "        return 0;\n"
            "    }\n"
        )
        _, asm, gen_dir, _ = _compile(src, tmp_path, tmp_path)
        text = (gen_dir / "sky_pal.s").read_text(encoding="utf-8")
        assert "sky_pal:" in text
        assert text.count("DC.W") == 16
        assert "lea sky_pal" in asm


class TestImportSprite:
    def test_sprite_16px_generates_template(self, tmp_path: Path):
        png = make_png(tmp_path / "bullet.png", 16, 8)
        src = (
            f'#import sprite "{png.name}" as bullet dither=none;\n'
            "code main:\n"
            "    proc main() -> int {\n"
            "        var p: int = &bullet;\n"
            "        return p;\n"
            "    }\n"
        )
        mod, asm, gen_dir, _ = _compile(src, tmp_path, tmp_path)
        assert mod.asset_imports[0].kind == "sprite"
        assert mod.asset_imports[0].options["planes"] == 2
        text = (gen_dir / "bullet.s").read_text(encoding="utf-8")
        assert "2 bitplanes" in text or "4 colors" in text.lower() or "4 colours" in text.lower()
        assert "bullet:" in text
        assert "sprite_templates" in text.replace("\t", " ")
        assert "lea bullet" in asm

    def test_sprite_rejects_non_16_width(self, tmp_path: Path):
        png = make_png(tmp_path / "wide.png", 32, 8)
        src = (
            f'#import sprite "{png.name}" as wide_spr;\n'
            "code main:\n"
            "    proc main() -> int { return 0; }\n"
        )
        with pytest.raises(SyntaxError, match="exactly 16 pixels wide"):
            parser.parse(src, base_dir=str(tmp_path), asset_outdir=str(tmp_path / "gen"))

    def test_sprite_rejects_planes_not_2(self, tmp_path: Path):
        png = make_png(tmp_path / "s.png", 16, 4)
        src = (
            f'#import sprite "{png.name}" as s planes=5;\n'
            "code main:\n"
            "    proc main() -> int { return 0; }\n"
        )
        with pytest.raises(SyntaxError, match="2 bitplanes"):
            parser.parse(src, base_dir=str(tmp_path), asset_outdir=str(tmp_path / "gen"))


class TestImportBobAddWord:
    def test_add_word_widens_stored_header(self, tmp_path: Path):
        png = make_png(tmp_path / "shift.png", 16, 2)
        src = (
            f'#import bob "{png.name}" as shift_bob planes=2 add_word;\n'
            "code main:\n"
            "    proc main() -> int { return 0; }\n"
        )
        _, _, gen_dir, _ = _compile(src, tmp_path, tmp_path)
        text = (gen_dir / "shift_bob.s").read_text(encoding="utf-8")
        # Header stores original width + 16 when add_word; planar rows pad to 32px.
        assert "converted width=32px" in text or "converted width=32" in text
        # Data header first DC.W after label_data should be 32 (16+16).
        assert "shift_bob_data:" in text


class TestImportCacheAndErrors:
    def test_cache_skips_rewrite(self, tmp_path: Path):
        png = make_png(tmp_path / "c.png", 16, 2)
        src = (
            f'#import bob "{png.name}" as c_bob planes=2;\n'
            "code main:\n"
            "    proc main() -> int { return 0; }\n"
        )
        mod1, _, gen_dir, _ = _compile(src, tmp_path, tmp_path, force=True)
        gen = Path(mod1.asset_imports[0].gen_path)
        mtime1 = gen.stat().st_mtime
        import time
        time.sleep(0.05)
        mod2, _, _, _ = _compile(src, tmp_path, tmp_path, force=False)
        mtime2 = Path(mod2.asset_imports[0].gen_path).stat().st_mtime
        assert mtime2 == mtime1

    def test_missing_as_errors(self, tmp_path: Path):
        png = make_png(tmp_path / "x.png", 8, 2)
        src = (
            f'#import bob "{png.name}" planes=2;\n'
            "code main:\n"
            "    proc main() -> int { return 0; }\n"
        )
        with pytest.raises(SyntaxError, match="as <label>"):
            parser.parse(src, base_dir=str(tmp_path), asset_outdir=str(tmp_path / "gen"))

    def test_unknown_kind_errors(self, tmp_path: Path):
        png = make_png(tmp_path / "x.png", 8, 2)
        src = (
            f'#import tiles "{png.name}" as t;\n'
            "code main:\n"
            "    proc main() -> int { return 0; }\n"
        )
        with pytest.raises(SyntaxError, match="invalid #import"):
            parser.parse(src, base_dir=str(tmp_path), asset_outdir=str(tmp_path / "gen"))

    def test_missing_file_errors(self, tmp_path: Path):
        src = (
            '#import bob "nope.png" as missing_bob;\n'
            "code main:\n"
            "    proc main() -> int { return 0; }\n"
        )
        with pytest.raises(SyntaxError, match="not found"):
            parser.parse(src, base_dir=str(tmp_path), asset_outdir=str(tmp_path / "gen"))

    def test_ifdef_inactive_skips_import(self, tmp_path: Path):
        png = make_png(tmp_path / "hidden.png", 8, 2)
        src = (
            "#ifdef NEVER_DEFINED\n"
            f'#import bob "{png.name}" as hidden_bob planes=2;\n'
            "#endif\n"
            "code main:\n"
            "    proc main() -> int { return 0; }\n"
        )
        mod = parser.parse(src, base_dir=str(tmp_path), asset_outdir=str(tmp_path / "gen"))
        assert mod.asset_imports == []
        assert not (tmp_path / "gen" / "hidden_bob.s").exists()


class TestAssetImportHelpers:
    def test_parse_import_line_flags(self):
        kind, path, label, opts = aim.parse_import_line(
            '#import bob "a.png" as bob1 planes=4 add_word;',
            1,
        )
        assert (kind, path, label) == ("bob", "a.png", "bob1")
        assert opts["planes"] == "4"
        assert opts["add_word"] is True
