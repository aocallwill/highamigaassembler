"""Tests for tools/amiga_palette.py and tools/png_to_amiga_palette.py."""
from pathlib import Path

import pytest

pytest.importorskip("PIL.Image")

from PIL import Image  # noqa: E402

from tests.tools_helpers import assert_section_cnop_invariant, make_png  # noqa: E402
from tools import amiga_palette as ap  # noqa: E402
from tools.png_to_amiga_palette import convert_file, main  # noqa: E402


class TestRgb4RoundTrip:
    def test_known_amiga_steps(self):
        assert ap.rgb8_to_rgb4(0) == 0
        assert ap.rgb8_to_rgb4(255) == 15
        assert ap.rgb4_to_rgb8(15) == 255
        assert ap.rgb4_to_rgb8(1) == 17

    def test_snap_collapses_near_8bit_values(self):
        assert ap.snap_rgb8_to_amiga(16, 16, 16) == ap.snap_rgb8_to_amiga(17, 17, 17)

    def test_word_packing(self):
        assert ap.rgb8_to_word(255, 0, 0) == 0xF00
        assert ap.word_to_rgb8(0x0F0) == (0, 255, 0)


class TestConvert:
    def test_reduces_to_requested_color_count(self, tmp_path: Path):
        # Many distinct colours in a small image.
        colors = [(i * 8, (255 - i * 8) % 256, (i * 16) % 256, 255) for i in range(32)]
        png = make_png(tmp_path / "many.png", 32, 8, colors=colors)
        result = ap.convert_image(png, colors=16, dither="none", index0="backdrop")
        assert result["max_colors"] == 16
        assert len(result["palette_words"]) == 16
        used = {idx for row in result["indices_by_row"] for idx in row}
        assert max(used) < 16
        assert all(0 <= w <= 0xFFF for w in result["palette_words"])

    def test_transparent_reserves_index_zero(self, tmp_path: Path):
        png = make_png(
            tmp_path / "alpha.png",
            8,
            2,
            colors=[(255, 0, 0, 255), (0, 0, 0, 0)],
        )
        result = ap.convert_image(png, colors=16, index0="transparent", dither="none")
        assert result["reserved_transparent"] is True
        assert result["palette_words"][0] == 0
        # Transparent pixels must be index 0; opaque must not be.
        for y, row in enumerate(result["indices_by_row"]):
            for x, idx in enumerate(row):
                # make_png cycles colours by (x+y) % len
                is_clear = ((x + y) % 2) == 1
                if is_clear:
                    assert idx == 0
                else:
                    assert idx != 0

    def test_backdrop_allows_nonzero_index0_color(self, tmp_path: Path):
        png = make_png(
            tmp_path / "bg.png",
            4,
            4,
            colors=[(255, 0, 0, 255), (0, 255, 0, 255)],
        )
        result = ap.convert_image(png, colors=16, index0="backdrop", dither="none")
        assert result["reserved_transparent"] is False
        # Index 0 is a real palette entry (snapped), not forced black unless source chose black.
        assert result["palette_words"][0] in (0xF00, 0x0F0, 0x000)

    def test_match_palette_forces_words(self, tmp_path: Path):
        png = make_png(tmp_path / "src.png", 8, 8)
        forced = [0x000, 0xF00, 0x0F0, 0x00F] + [0] * 12
        result = ap.convert_image(
            png, colors=16, index0="backdrop", match_palette_words=forced, dither="none"
        )
        assert result["palette_words"] == forced

    def test_ordered_and_fs_dither_run(self, tmp_path: Path):
        png = make_png(tmp_path / "d.png", 16, 16)
        for mode in ("fs", "ordered"):
            result = ap.convert_image(png, colors=8, dither=mode, index0="backdrop")
            assert result["dither"] == mode
            assert len(result["indices_by_row"]) == 16

    def test_rgb4_unique_source_fills_slots_without_dup_black(self, tmp_path: Path):
        # 8 distinct Amiga red steps → 8-colour palette should keep them all.
        colors = [(n * 17, 0, 0, 255) for n in range(8)]
        png = make_png(tmp_path / "steps.png", 8, 1, colors=colors)
        result = ap.convert_image(png, colors=8, dither="none", index0="backdrop", requantize=True)
        unique = set(result["palette_words"])
        assert len(unique) == 8
        assert 0x000 in unique
        assert 0x700 in unique  # n=7 → channel 119 → RGB4 7


class TestAsmAndCli:
    def test_palette_asm_has_section_cnop_and_words(self, tmp_path: Path):
        words = [0x000, 0xF00, 0x0F0, 0x00F]
        asm = ap.format_palette_asm("test_palette", words, source_name="x.png", num_colors=4)
        assert_section_cnop_invariant(asm)
        assert "\tXDEF\ttest_palette" in asm
        assert "DC.W\t$F00" in asm
        out = ap.write_palette_asm(tmp_path / "p.s", "test_palette", words, num_colors=4)
        parsed = ap.parse_palette_from_asm(str(out), "test_palette")
        assert parsed == words

    def test_write_preview_png_is_mode_p(self, tmp_path: Path):
        png = make_png(tmp_path / "in.png", 8, 4)
        result = ap.convert_image(png, colors=8, index0="backdrop")
        out = tmp_path / "out.png"
        ap.write_paletted_png(
            out,
            result["width"],
            result["height"],
            result["indices_by_row"],
            result["palette_rgb8"],
            8,
        )
        img = Image.open(out)
        assert img.mode == "P"
        assert img.size == (8, 4)

    def test_cli_writes_palette_and_png(self, tmp_path: Path):
        png = make_png(tmp_path / "art.png", 16, 8)
        palette_out = tmp_path / "art_palette.s"
        png_out = tmp_path / "art_16.png"
        rc = main([
            str(png),
            "--colors", "16",
            "--dither", "ordered",
            "--index0", "backdrop",
            "--palette-out", str(palette_out),
            "--png-out", str(png_out),
            "--label", "art_palette",
            "-q",
        ])
        assert rc == 0
        assert palette_out.exists()
        assert png_out.exists()
        text = palette_out.read_text(encoding="utf-8")
        assert "art_palette:" in text
        assert text.count("DC.W") == 16

    def test_convert_file_helper(self, tmp_path: Path):
        png = make_png(tmp_path / "bobish.png", 16, 4)
        result = convert_file(
            png,
            colors=32,
            dither="none",
            index0="transparent",
            label="bobish_palette",
            palette_out=tmp_path / "bobish_palette.s",
            png_out=None,
            match_palette=None,
            match_palette_label=None,
            requantize=True,
            ordered_size=4,
            section="data,DATA",
        )
        assert result["max_colors"] == 32
        assert Path(result["palette_out"]).exists()
