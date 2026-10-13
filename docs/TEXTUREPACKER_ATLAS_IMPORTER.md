# TexturePacker Atlas Importer

`tools/texturepacker_atlas_importer.py` converts a TexturePacker XML atlas and PNG into Amiga BOB
assembly files. All frames use one shared quantized palette, so they can be used as an animation.

For in-language compile-time import (preferred for single-module games), use:

```has
#import atlas "assets/walk.xml" as walk planes=5 add_word shared_palette;
// Registers walk_palette + walk_<frame>…; INCLUDEs build/gen/walk_atlas.s
```

See README / [SPRITE_TOOLS_QUICK_REFERENCE.md](SPRITE_TOOLS_QUICK_REFERENCE.md). The CLI below
remains useful for Makefile batch pipelines and when you need finer control over output layout.

## Basic Usage

```bash
python tools/texturepacker_atlas_importer.py walk.xml \
    --outdir build/gen \
    --shared-palette-file build/gen/walk_palette.s \
    --shared-palette \
    --master-include build/gen/walk_atlas.s
```

Each XML sprite produces a sanitized, prefixed descriptor label. For example, `walk_0.png` in
`walk.xml` produces `walk_walk_0` by default. Pass its address to `CreateBobAnimation` or `CreateBob`.

`--shared-palette` eliminates the repeated palette words from each BOB file. The generated
descriptor retains its normal `data, mask, palette, width, height, color_count` layout, but its
palette pointer refers to the one `<prefix>_palette` block written by `--shared-palette-file`.
Include that palette before the BOB files; the generated master include does this automatically.

## Rendering A Shared-Palette Atlas

The generated master include is assembly input, not a HAS `#include`. Assemble it once as an asset
object and link that object with the compiled HAS program. A small wrapper keeps the generated files
together:

```asm
; assets/walk_assets.s
    INCLUDE "walk_atlas.s"
```

`walk_atlas.s` includes `walk_palette.s` before all frame descriptors. Do not also assemble the
individual files included by `walk_atlas.s`, because that would define their exported labels twice.

Declare the descriptor and palette labels in HAS, select a compatible display mode, load the palette
once, then create and draw BOB handles. This example uses the default five planes, so it loads 32
colours into the lores display palette:

```has
extern func SetGraphicsMode(mode: int) -> int;
extern func LoadPalette(palette_ptr: int, num_colors: int) -> int;
extern func CreateBob(descriptor_ptr: int, save_background: int) -> int;
extern func PasteBob(handle: int, x: int, y: int, mode: int) -> void;

extern var walk_palette: int;
extern var walk_walk_0: int;
extern var walk_walk_1: int;

var walk_frame_0: int;
var walk_frame_1: int;

proc InitWalkBobs() -> int
{
    if (SetGraphicsMode(0) == -1) { return -1; }

    // Load once: every frame uses the same index-to-colour mapping.
    if (LoadPalette(&walk_palette, 32) == -1) { return -2; }

    walk_frame_0 = CreateBob(&walk_walk_0, 0);
    walk_frame_1 = CreateBob(&walk_walk_1, 0);
    if (walk_frame_0 == -1 || walk_frame_1 == -1) {
        return -3;
    }

    return 0;
}

proc DrawWalk() -> void
{
    call PasteBob(walk_frame_0, 100, 80, 1);  // mode 1 uses the generated mask
    call PasteBob(walk_frame_1, 132, 80, 1);
}
```

For animation, keep one handle per frame and pass the current handle to `PasteBob`. `PasteBob` does
not switch palettes; it only blits the selected frame's data and mask. With a 5-plane atlas, use
`SetGraphicsMode(0)` and `LoadPalette(..., 32)`. Hires and HAM6 modes accept at most 16 palette
entries, so generate a four-plane atlas for those modes. Destroy the handles only when the atlas is
no longer needed and no blit is using its data.

## Repeated Frames

TexturePacker may list the same frame more than once. By default, the importer writes a complete BOB
file for every XML entry, preserving the existing one-file-per-frame behavior.

Use `--deduplicate-frames` to store identical converted frames only once:

```bash
python tools/texturepacker_atlas_importer.py walk.xml \
    --outdir build/gen \
    --master-include build/gen/walk_atlas.s \
    --deduplicate-frames
```

The first matching frame is the canonical file. Later frames export alias labels at the same
descriptor, data, mask, and palette addresses. Every logical frame name remains usable in an
animation, but the master include references the physical file only once.

Frames are compared after extraction, optional size restoration, and shared-palette quantization.
Consequently, source pixels that become identical at the selected bitplane depth can be deduplicated.
Changing from normal output to deduplicated output also removes stale duplicate frame files.

## Common Options

| Option | Purpose |
|---|---|
| `--planes 1..5` | Select 2 to 32 colours; default is 5 bitplanes. |
| `--label-prefix NAME` | Override the XML filename prefix used for assembly labels. |
| `--restore-original-size` | Pad trimmed sprites back to their original dimensions. |
| `--dither` | Enable Floyd-Steinberg dithering during shared-palette quantization. |
| `--add-word` | Add a 16-pixel blitter safety word. |
| `--sprites a,b` | Import only the listed TexturePacker names or stems. |
| `--shared-palette-file PATH` | Write the shared palette as a standalone assembly file. |
| `--shared-palette` | Point all descriptors at the standalone palette; requires `--shared-palette-file`. |
| `--force` | Regenerate output even when existing files are current. |

See [LIBRARY_REFERENCE.md](LIBRARY_REFERENCE.md) for the runtime animation API.