#!/usr/bin/env python3
"""
Convert a many-colour PNG to an Amiga OCS/ECS 16- or 32-colour palette.

Palette-first tool (no planar BOB packing). Emits:
  - Amiga RGB4 palette assembly (DC.W $0RGB) for LoadPalette / SetColor
  - Optional mode-P preview PNG

Examples:
  .venv/bin/python3 tools/png_to_amiga_palette.py art.png --colors 32 \\
      --palette-out build/art_palette.s --png-out build/art_32.png

  .venv/bin/python3 tools/png_to_amiga_palette.py ui.png --colors 16 \\
      --dither ordered --index0 backdrop --label ui_palette

  .venv/bin/python3 tools/png_to_amiga_palette.py sprite.png --planes 5 \\
      --index0 transparent --dither fs --requantize
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python tools/png_to_amiga_palette.py` from repo root.
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

try:
    import amiga_palette as ap
except ImportError:  # pragma: no cover
    from tools import amiga_palette as ap  # type: ignore


def _default_label(png_path: Path, prefix: str) -> str:
    safe = png_path.stem.replace(' ', '_').replace('-', '_')
    return f'{prefix}_{safe}_palette' if prefix else f'{safe}_palette'


def convert_file(
    png_path: Path,
    *,
    colors: int,
    dither: str,
    index0: str,
    label: str,
    palette_out: Path,
    png_out: Path | None,
    match_palette: Path | None,
    match_palette_label: str | None,
    requantize: bool,
    ordered_size: int,
    section: str,
) -> dict:
    match_words = None
    if match_palette is not None:
        match_words = ap.parse_palette_from_asm(str(match_palette), match_palette_label)

    result = ap.convert_image(
        png_path,
        colors=colors,
        dither=dither,
        index0=index0,
        match_palette_words=match_words,
        requantize=requantize,
        ordered_size=ordered_size,
    )

    ap.write_palette_asm(
        palette_out,
        label,
        result['palette_words'],
        source_name=png_path.name,
        num_colors=colors,
        section=section,
    )

    if png_out is not None:
        ap.write_paletted_png(
            png_out,
            result['width'],
            result['height'],
            result['indices_by_row'],
            result['palette_rgb8'],
            colors,
        )

    result['palette_out'] = str(palette_out)
    result['png_out'] = str(png_out) if png_out else None
    result['label'] = label
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Convert PNG to Amiga 16/32-colour palette (RGB4) + optional preview PNG',
    )
    parser.add_argument('png', help='Source PNG (any colour depth)')

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--colors', type=int, choices=[2, 4, 8, 16, 32],
        help='Target colour count (default: 32). Prefer 32 for mode 0, 16 for hires/HAM base.',
    )
    group.add_argument(
        '--planes', type=int, choices=[1, 2, 3, 4, 5],
        help='Bitplanes instead of --colors (colors = 2^planes)',
    )

    parser.add_argument(
        '--dither', choices=['none', 'fs', 'ordered'], default='none',
        help='Dither mode: none, Floyd–Steinberg (fs), or Bayer ordered (default: none)',
    )
    parser.add_argument(
        '--ordered-size', type=int, choices=[4, 8], default=4,
        help='Bayer matrix size when --dither ordered (default: 4)',
    )
    parser.add_argument(
        '--index0', choices=['backdrop', 'transparent', 'none'], default='backdrop',
        help='Index 0 policy: backdrop/none = playfield COLOR0; transparent = alpha mask slot',
    )
    parser.add_argument(
        '--requantize', action='store_true',
        help='Ignore source indexed palette and always rebuild colours',
    )
    parser.add_argument(
        '--match-palette', metavar='PATH',
        help='Remap onto an existing palette .s (DC.W $RGB) instead of building a new one',
    )
    parser.add_argument(
        '--match-palette-label', metavar='LABEL',
        help='Specific palette label inside --match-palette file',
    )
    parser.add_argument(
        '--label', default=None,
        help='Assembly symbol for the palette (default: <stem>_palette)',
    )
    parser.add_argument(
        '--label-prefix', default='',
        help='Optional prefix when deriving the default label',
    )
    parser.add_argument(
        '--palette-out', metavar='PATH', default=None,
        help='Output palette .s path (default: <stem>_palette.s beside the PNG)',
    )
    parser.add_argument(
        '--png-out', metavar='PATH', default=None,
        help='Optional mode-P preview PNG path',
    )
    parser.add_argument(
        '--outdir', metavar='DIR', default=None,
        help='Directory for default palette/png outputs',
    )
    parser.add_argument(
        '--section', default='data,DATA',
        help='SECTION for palette ASM (default: data,DATA — not chip; copper/CPU writes only)',
    )
    parser.add_argument(
        '-q', '--quiet', action='store_true',
        help='Suppress summary line',
    )

    args = parser.parse_args(argv)
    png_path = Path(args.png)
    if not png_path.exists():
        parser.error(f'PNG not found: {png_path}')

    if args.planes is not None:
        colors = ap.colors_from_planes(args.planes)
    elif args.colors is not None:
        colors = args.colors
    else:
        colors = 32

    label = args.label or _default_label(png_path, args.label_prefix)

    outdir = Path(args.outdir) if args.outdir else png_path.parent
    palette_out = Path(args.palette_out) if args.palette_out else outdir / f'{label}.s'
    png_out = Path(args.png_out) if args.png_out else None
    # If --outdir is set and --png-out omitted, still only emit PNG when explicitly requested.
    # Callers who want both should pass --png-out (absolute or relative).

    try:
        result = convert_file(
            png_path,
            colors=colors,
            dither=args.dither,
            index0=args.index0,
            label=label,
            palette_out=palette_out,
            png_out=png_out,
            match_palette=Path(args.match_palette) if args.match_palette else None,
            match_palette_label=args.match_palette_label,
            requantize=args.requantize,
            ordered_size=args.ordered_size,
            section=args.section,
        )
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

    if not args.quiet:
        parts = [
            f'[amiga_palette] {png_path.name}',
            f'{result["width"]}x{result["height"]}',
            f'colors={colors}',
            f'dither={args.dither}',
            f'index0={args.index0}',
            f'palette={palette_out}',
        ]
        if png_out:
            parts.append(f'png={png_out}')
        if result.get('reserved_transparent'):
            parts.append('transparent=1')
        print(' | '.join(parts))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
