#!/usr/bin/env python3
"""
Amiga OCS/ECS palette helpers: 12-bit RGB4 quantization, dithering, ASM/PNG export.

Used by png_to_amiga_palette.py and available for other asset tools.
COLOR words match bob_importer / LoadPalette: DC.W $0RGB with channels 0..15
via round(channel / 17.0).
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

ALPHA_THRESHOLD = 128

# 4x4 and 8x8 Bayer matrices (standard ordered-dither thresholds).
BAYER_4 = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)
BAYER_8 = (
    (0, 48, 12, 60, 3, 51, 15, 63),
    (32, 16, 44, 28, 35, 19, 47, 31),
    (8, 56, 4, 52, 11, 59, 7, 55),
    (40, 24, 36, 20, 43, 27, 39, 23),
    (2, 50, 14, 62, 1, 49, 13, 61),
    (34, 18, 46, 30, 33, 17, 45, 29),
    (10, 58, 6, 54, 9, 57, 5, 53),
    (42, 26, 38, 22, 41, 25, 37, 21),
)


def flatten_image_pixels(img):
    """Flat pixel list across Pillow versions (getdata removed in Pillow 14)."""
    if hasattr(img, 'get_flattened_data'):
        return list(img.get_flattened_data())
    return list(img.getdata())


def rgb8_to_rgb4(channel: int) -> int:
    """Map 0..255 to Amiga 0..15 (same rounding as bob_importer / amigeconv)."""
    return int(round(max(0, min(255, int(channel))) / 17.0)) & 0xF


def rgb4_to_rgb8(nibble: int) -> int:
    """Expand 0..15 to the matching 0..255 Amiga step (n*17)."""
    return (int(nibble) & 0xF) * 17


def rgb8_to_word(r: int, g: int, b: int) -> int:
    return (rgb8_to_rgb4(r) << 8) | (rgb8_to_rgb4(g) << 4) | rgb8_to_rgb4(b)


def word_to_rgb8(word: int) -> Tuple[int, int, int]:
    w = int(word) & 0xFFF
    return (rgb4_to_rgb8((w >> 8) & 0xF),
            rgb4_to_rgb8((w >> 4) & 0xF),
            rgb4_to_rgb8(w & 0xF))


def snap_rgb8_to_amiga(r: int, g: int, b: int) -> Tuple[int, int, int]:
    """Snap an 8-bit triple onto the Amiga 12-bit colour cube."""
    return word_to_rgb8(rgb8_to_word(r, g, b))


def palette_rgb8_to_words(flat_rgb: Sequence[int], num_colors: int) -> List[int]:
    words = []
    for i in range(num_colors):
        base = i * 3
        if base + 2 < len(flat_rgb):
            words.append(rgb8_to_word(flat_rgb[base], flat_rgb[base + 1], flat_rgb[base + 2]))
        else:
            words.append(0)
    return words


def words_to_flat_rgb8(words: Sequence[int]) -> List[int]:
    flat: List[int] = []
    for w in words:
        flat.extend(word_to_rgb8(w))
    return flat


def parse_palette_from_asm(asm_path: str, palette_label: Optional[str] = None) -> List[int]:
    """
    Parse a DC.W $RGB palette block from an assembler include.

    Returns a list of 12-bit colour words.
    """
    path = Path(asm_path)
    if not path.exists():
        raise FileNotFoundError(asm_path)

    text = path.read_text(encoding='utf-8')
    if palette_label:
        wanted = palette_label[:-1] if palette_label.endswith(':') else palette_label
        pattern = rf'^({re.escape(wanted)}):\s*$'
        match = re.search(pattern, text, flags=re.MULTILINE)
        if not match:
            raise ValueError(f"Palette label '{wanted}' not found in {asm_path}")
    else:
        match = re.search(r'^([A-Za-z_][A-Za-z0-9_]*_palette):\s*$', text, flags=re.MULTILINE)
        if not match:
            # Also accept a bare label that is not necessarily *_palette.
            match = re.search(r'^([A-Za-z_][A-Za-z0-9_]*):\s*$', text, flags=re.MULTILINE)
        if not match:
            raise ValueError(f"No palette label found in {asm_path}")

    following = text[match.end():]
    values: List[int] = []
    for line in following.splitlines():
        m = re.match(r'\s*DC\.W\s+\$([0-9A-Fa-f]{1,3})\b', line)
        if m:
            values.append(int(m.group(1), 16) & 0xFFF)
            continue
        if values:
            break
        if line.strip() == '' or line.lstrip().startswith(';'):
            continue
        raise ValueError(f"Palette label found in {asm_path}, but no DC.W palette values followed")

    if not values:
        raise ValueError(f"No palette DC.W values found in {asm_path}")
    return values


def format_palette_asm(
    label: str,
    words: Sequence[int],
    *,
    source_name: Optional[str] = None,
    num_colors: Optional[int] = None,
    section: str = 'data,DATA',
) -> str:
    """Emit a HAS-friendly palette assembly fragment (XDEF + DC.W $RGB)."""
    count = num_colors if num_colors is not None else len(words)
    lines = []
    if source_name:
        lines.append(f'; Amiga RGB4 palette generated from {source_name}')
    else:
        lines.append('; Amiga RGB4 palette')
    lines.append(f'; {count} colors (12-bit $0RGB), for LoadPalette / SetColor')
    lines.append(f'\tSECTION\t{section}')
    lines.append('\tCNOP\t0,4')
    lines.append(f'\tXDEF\t{label}')
    lines.append(f'{label}:')
    for i in range(count):
        word = int(words[i]) & 0xFFF if i < len(words) else 0
        lines.append(f'\tDC.W\t${word:03X}\t; color {i}')
    lines.append('')
    return '\n'.join(lines)


def write_palette_asm(path: Path, label: str, words: Sequence[int], **kwargs) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_palette_asm(label, words, **kwargs), encoding='utf-8')
    return path


def write_paletted_png(
    path: Path,
    width: int,
    height: int,
    indices_by_row: Sequence[Sequence[int]],
    flat_palette_rgb8: Sequence[int],
    num_colors: int,
) -> Path:
    """Write a mode-P PNG for artist preview / further tooling."""
    if Image is None:
        raise RuntimeError('Pillow is required (pip install pillow)')

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    palette = list(flat_palette_rgb8[: num_colors * 3])
    if len(palette) < 256 * 3:
        palette = palette + [0] * (256 * 3 - len(palette))

    img = Image.new('P', (width, height))
    img.putpalette(palette)
    pixels = []
    for y in range(height):
        row = indices_by_row[y] if y < len(indices_by_row) else [0] * width
        for x in range(width):
            pixels.append(int(row[x]) if x < len(row) else 0)
    img.putdata(pixels)
    img.save(path)
    return path


def _clamp8(v: float) -> int:
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def nearest_index(
    r: float,
    g: float,
    b: float,
    palette: Sequence[Tuple[int, int, int]],
    start: int = 0,
) -> int:
    """Nearest palette entry by Euclidean distance in RGB8 space."""
    best_i = start
    best_d = float('inf')
    rr, gg, bb = float(r), float(g), float(b)
    for i in range(start, len(palette)):
        pr, pg, pb = palette[i]
        d = (rr - pr) ** 2 + (gg - pg) ** 2 + (bb - pb) ** 2
        if d < best_d:
            best_d = d
            best_i = i
            if d == 0:
                break
    return best_i


def _palette_tuples(flat_rgb: Sequence[int], num_colors: int) -> List[Tuple[int, int, int]]:
    out: List[Tuple[int, int, int]] = []
    for i in range(num_colors):
        base = i * 3
        if base + 2 < len(flat_rgb):
            out.append((int(flat_rgb[base]), int(flat_rgb[base + 1]), int(flat_rgb[base + 2])))
        else:
            out.append((0, 0, 0))
    return out


def _build_palette_median_cut(
    opaque_rgb: Sequence[Tuple[int, int, int]],
    num_colors: int,
) -> List[Tuple[int, int, int]]:
    """
    Derive up to num_colors colours in Amiga RGB4 space.

    Pixels are snapped to the 12-bit cube first. If that already fits in
    ``num_colors``, keep the most frequent unique colours. Otherwise run
    median-cut on the snapped image and back-fill unused frequent colours
    so snap-collisions do not waste palette slots as duplicate $000.
    """
    if Image is None:
        raise RuntimeError('Pillow is required (pip install pillow)')
    if num_colors < 1:
        num_colors = 1
    if not opaque_rgb:
        return [(0, 0, 0)] * num_colors

    snapped_pixels = [snap_rgb8_to_amiga(r, g, b) for (r, g, b) in opaque_rgb]
    freq = Counter(snapped_pixels)
    by_freq = [colour for colour, _ in freq.most_common()]

    if len(by_freq) <= num_colors:
        colours = list(by_freq)
        while len(colours) < num_colors:
            colours.append((0, 0, 0))
        return colours[:num_colors]

    temp = Image.new('RGB', (len(snapped_pixels), 1))
    temp.putdata(snapped_pixels)
    # Ask Pillow for a few extras so snap/merge still yields enough uniques.
    ask = min(256, max(num_colors * 2, num_colors + 8))
    quantized = temp.quantize(colors=ask, method=Image.MEDIANCUT, dither=Image.NONE)
    raw = quantized.getpalette() or []
    colours: List[Tuple[int, int, int]] = []
    seen = set()
    for i in range(ask):
        base = i * 3
        if base + 2 >= len(raw):
            break
        snapped = snap_rgb8_to_amiga(raw[base], raw[base + 1], raw[base + 2])
        if snapped in seen:
            continue
        seen.add(snapped)
        colours.append(snapped)
        if len(colours) >= num_colors:
            break

    for colour in by_freq:
        if len(colours) >= num_colors:
            break
        if colour not in seen:
            seen.add(colour)
            colours.append(colour)

    while len(colours) < num_colors:
        colours.append((0, 0, 0))
    return colours[:num_colors]


def _palette_from_mode_p(img, max_colors: int) -> Tuple[List[Tuple[int, int, int]], Optional[int]]:
    """Read an indexed PNG palette; return (colours, transparent_index_or_None)."""
    raw = img.getpalette() or []
    transparent_index = None
    info = getattr(img, 'info', {}) or {}
    if 'transparency' in info:
        t = info['transparency']
        if isinstance(t, int):
            transparent_index = t

    size = min(len(raw) // 3, max_colors)
    colours = []
    for i in range(size):
        colours.append(snap_rgb8_to_amiga(raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]))
    while len(colours) < max_colors:
        colours.append((0, 0, 0))
    return colours[:max_colors], transparent_index


def _bayer_bias(x: int, y: int, matrix_size: int) -> float:
    """Signed bias in roughly -0.5..+0.5 from a Bayer matrix cell."""
    if matrix_size >= 8:
        m = BAYER_8
        n = 8
    else:
        m = BAYER_4
        n = 4
    cell = m[y % n][x % n]
    return (cell / float(n * n) - 0.5)


def map_indices(
    rgba_rows: Sequence[Sequence[Tuple[int, int, int, int]]],
    palette: Sequence[Tuple[int, int, int]],
    *,
    dither: str = 'none',
    reserve_transparent: bool = False,
    matrix_size: int = 4,
) -> List[List[int]]:
    """Map RGBA rows onto palette indices with optional dithering."""
    h = len(rgba_rows)
    w = len(rgba_rows[0]) if h else 0
    start = 1 if reserve_transparent and len(palette) > 1 else 0
    dither = (dither or 'none').lower()

    if dither == 'fs':
        # Working buffer in float RGB
        buf = [[list(px[:3]) for px in row] for row in rgba_rows]
        out: List[List[int]] = []
        for y in range(h):
            row_out: List[int] = []
            for x in range(w):
                r, g, b, a = rgba_rows[y][x]
                if reserve_transparent and a < ALPHA_THRESHOLD:
                    row_out.append(0)
                    continue
                pr, pg, pb = buf[y][x]
                idx = nearest_index(pr, pg, pb, palette, start=start)
                row_out.append(idx)
                tr, tg, tb = palette[idx]
                er, eg, eb = pr - tr, pg - tg, pb - tb

                def _diffuse(nx: int, ny: int, factor: float) -> None:
                    if 0 <= nx < w and 0 <= ny < h:
                        # Do not push error into transparent destinations.
                        if reserve_transparent and rgba_rows[ny][nx][3] < ALPHA_THRESHOLD:
                            return
                        buf[ny][nx][0] += er * factor
                        buf[ny][nx][1] += eg * factor
                        buf[ny][nx][2] += eb * factor

                _diffuse(x + 1, y, 7 / 16)
                _diffuse(x - 1, y + 1, 3 / 16)
                _diffuse(x, y + 1, 5 / 16)
                _diffuse(x + 1, y + 1, 1 / 16)
            out.append(row_out)
        return out

    if dither == 'ordered':
        # ~one Amiga step of spread keeps ordered dither useful on OCS stills.
        spread = 17.0
        out = []
        for y in range(h):
            row_out = []
            for x in range(w):
                r, g, b, a = rgba_rows[y][x]
                if reserve_transparent and a < ALPHA_THRESHOLD:
                    row_out.append(0)
                    continue
                bias = _bayer_bias(x, y, matrix_size) * spread
                idx = nearest_index(_clamp8(r + bias), _clamp8(g + bias), _clamp8(b + bias),
                                    palette, start=start)
                row_out.append(idx)
            out.append(row_out)
        return out

    # none
    out = []
    for y in range(h):
        row_out = []
        for x in range(w):
            r, g, b, a = rgba_rows[y][x]
            if reserve_transparent and a < ALPHA_THRESHOLD:
                row_out.append(0)
            else:
                row_out.append(nearest_index(r, g, b, palette, start=start))
        out.append(row_out)
    return out


def convert_image(
    png_path_or_image,
    *,
    colors: int = 32,
    dither: str = 'none',
    index0: str = 'backdrop',
    match_palette_words: Optional[Sequence[int]] = None,
    requantize: bool = False,
    ordered_size: int = 4,
) -> dict:
    """
    Convert a PNG (path or PIL Image) to an Amiga-sized palette.

    Parameters
    ----------
    colors:
        Target colour count (typically 16 or 32).
    dither:
        'none' | 'fs' | 'ordered'
    index0:
        'backdrop'  – all colour slots usable; alpha ignored for indexing
                      (COLOR0 is a visible playfield colour).
        'transparent' – reserve index 0 for alpha < 128 (BOB/sprite style).
        'none' – same mapping as backdrop (alias for clarity in CLIs).
    match_palette_words:
        If set, force remapping onto this existing RGB4 palette (truncated/padded
        to `colors`) instead of deriving a new one.
    requantize:
        If True, ignore source mode-P palette and always rebuild colours.
    ordered_size:
        4 or 8 for Bayer matrix when dither='ordered'.

    Returns dict with width, height, indices_by_row, palette_rgb8, palette_words,
    has_transparent, max_colors, reserved_transparent, source_mode.
    """
    if Image is None:
        raise RuntimeError('Pillow is required (pip install pillow)')

    if colors not in (2, 4, 8, 16, 32) and not (2 <= colors <= 32):
        raise ValueError(f'colors must be between 2 and 32, got {colors}')
    colors = int(colors)
    if colors < 2 or colors > 32:
        raise ValueError(f'colors must be between 2 and 32, got {colors}')

    index0 = (index0 or 'backdrop').lower()
    if index0 not in ('backdrop', 'transparent', 'none'):
        raise ValueError("index0 must be 'backdrop', 'transparent', or 'none'")
    dither = (dither or 'none').lower()
    if dither not in ('none', 'fs', 'ordered'):
        raise ValueError("dither must be 'none', 'fs', or 'ordered'")

    if isinstance(png_path_or_image, (str, Path)):
        img = Image.open(str(png_path_or_image))
    else:
        img = png_path_or_image

    w, h = img.size
    source_mode = getattr(img, 'mode', None)
    rgba = img.convert('RGBA')
    rgba_data = flatten_image_pixels(rgba)
    rgba_rows = [
        [rgba_data[y * w + x] for x in range(w)]
        for y in range(h)
    ]
    has_alpha = any(px[3] < ALPHA_THRESHOLD for row in rgba_rows for px in row)
    reserve_transparent = index0 == 'transparent'
    # When reserving transparency, always keep slot 0 even if the PNG is opaque,
    # so masks / BOB conventions stay stable.
    opaque_slots = colors - 1 if reserve_transparent else colors
    if opaque_slots < 1:
        opaque_slots = 1

    palette: Optional[List[Tuple[int, int, int]]] = None

    if match_palette_words is not None:
        words = [int(x) & 0xFFF for x in match_palette_words[:colors]]
        while len(words) < colors:
            words.append(0)
        if reserve_transparent:
            words[0] = 0
        palette = [word_to_rgb8(word) for word in words]
    elif source_mode and source_mode.upper() == 'P' and not requantize:
        # Preserve indexed source when used colours already fit the target.
        # If the source uses more colours than allowed, rebuild via median-cut.
        used_idx = Counter(flatten_image_pixels(img))
        target_opaque = opaque_slots if reserve_transparent else colors
        if len(used_idx) > target_opaque:
            requantize = True
        else:
            mode_p_colours, t_idx = _palette_from_mode_p(img, max(len(used_idx), target_opaque))
            if reserve_transparent:
                opaque: List[Tuple[int, int, int]] = []
                for idx, _ in used_idx.most_common():
                    if t_idx is not None and idx == t_idx:
                        continue
                    if idx < len(mode_p_colours):
                        opaque.append(mode_p_colours[idx])
                    if len(opaque) >= opaque_slots:
                        break
                while len(opaque) < opaque_slots:
                    opaque.append((0, 0, 0))
                palette = [(0, 0, 0)] + opaque[:opaque_slots]
            else:
                ordered: List[Tuple[int, int, int]] = []
                seen = set()
                for idx, _ in used_idx.most_common():
                    if idx < len(mode_p_colours):
                        col = mode_p_colours[idx]
                        if col not in seen:
                            seen.add(col)
                            ordered.append(col)
                palette = ordered[:colors]

    if palette is None:
        opaque_pixels = [
            (r, g, b)
            for row in rgba_rows
            for (r, g, b, a) in row
            if (not reserve_transparent) or a >= ALPHA_THRESHOLD
        ]
        built = _build_palette_median_cut(opaque_pixels, opaque_slots)
        if reserve_transparent:
            palette = [(0, 0, 0)] + list(built[:opaque_slots])
        else:
            palette = list(built[:colors])

    # Truncate / pad to exact colour count.
    palette = list(palette[:colors])
    while len(palette) < colors:
        palette.append((0, 0, 0))

    indices_by_row = map_indices(
        rgba_rows,
        palette,
        dither=dither,
        reserve_transparent=reserve_transparent,
        matrix_size=ordered_size,
    )

    flat: List[int] = []
    for r, g, b in palette:
        flat.extend([r, g, b])
    words = [rgb8_to_word(r, g, b) for (r, g, b) in palette]

    return {
        'width': w,
        'height': h,
        'indices_by_row': indices_by_row,
        'palette_rgb8': flat,
        'palette_words': words,
        'palette_tuples': palette,
        'has_transparent': has_alpha,
        'reserved_transparent': reserve_transparent,
        'max_colors': colors,
        'source_mode': source_mode,
        'dither': dither,
        'index0': index0,
    }


def colors_from_planes(planes: int) -> int:
    if planes < 1 or planes > 5:
        raise ValueError(f'planes must be 1..5, got {planes}')
    return 2 ** planes
