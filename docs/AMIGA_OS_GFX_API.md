# Amiga OS Graphics API (custom screens)

**Audience:** HAS and pythonami authors targeting AmigaOS 2.x+ Intuition custom screens.
**Purpose:** OS-cooperative Deluxe Paint–style drawing: own screen, palette, RastPort
primitives, blits, and SimpleSprites — **not** bare-metal `TakeSystem` / `$DFF0xx`.

**Companions**

- Bare-metal (unchanged): [GRAPHICS_LIBRARY_INTERFACE.md](GRAPHICS_LIBRARY_INTERFACE.md) (`lib/graphics.s`)
- Workbench dialogs (unchanged): [GUI_INTUITION_RUNTIME_SPEC.md](GUI_INTUITION_RUNTIME_SPEC.md)
- pythonami mirror: sibling repo `docs/amiga-os-gfx.md`

**Target:** AmigaOS 2.0+ (`intuition.library` / `graphics.library` V37), 68000.
No `TakeSystem()`, no copper list ownership.

---

## Screen modes and palette

| Concept | Behaviour |
|---------|-----------|
| Custom screen | `OpenScreen` / tags: you own width, height, depth, and ColorMap |
| Depth | `1`→2 pens … `3`→8 … `4`→16 … `5`→32 (OCS) |
| Workbench pens | Irrelevant once you open a custom screen |
| Palette | `GfxColor(index, r, g, b)` → `SetRGB4` (components 0..15) |
| Drawing pen | `GfxInk(pen)` → `SetAPen` on the screen RastPort |

**Mode flags** (`GfxOpenScreen` last argument; OR together):

| Name | Value | Meaning |
|------|------:|---------|
| `GFX_MODE_LORES` | 0 | 320-wide pixels (default) |
| `GFX_MODE_HIRES` | 0x8000 | HIRES |
| `GFX_MODE_LACE` | 0x0004 | Interlace |
| `GFX_MODE_SPRITES` | 0x4000 | Enable SimpleSprites + pointer colors |

HAM / dual-playfield / AGA are out of scope for v1.

---

## Mandatory call order

```text
GfxInit()
  GfxOpenScreen(x, y, w, h, depth, mode)   → Screen* or 0
    GfxColor / GfxInk / drawing / blit / sprites …
  GfxCloseScreen()
GfxShutdown()
```

Single active screen. `GfxWaitTOF()` may be called while a screen is open.

---

## HAS API (`lib/amiga_gfx.s`)

```has
extern func GfxInit() -> int;
extern func GfxShutdown() -> void;
extern func GfxOpenScreen(x: int, y: int, w: int, h: int, depth: int, mode: int) -> int;
extern func GfxCloseScreen() -> void;
extern func GfxWaitTOF() -> void;

extern func GfxInk(pen: int) -> void;
extern func GfxColor(index: int, r: int, g: int, b: int) -> void;

extern func GfxPlot(x: int, y: int) -> void;
extern func GfxLine(x0: int, y0: int, x1: int, y1: int) -> void;
extern func GfxRect(x: int, y: int, w: int, h: int, filled: int) -> void;
extern func GfxCircle(cx: int, cy: int, r: int, filled: int) -> void;
extern func GfxFill(x: int, y: int) -> void;  // Flood mode 1; needs TmpRas (set by GfxOpenScreen)
extern func GfxText(x: int, y: int, text: int) -> void;

extern func GfxAllocBitMap(w: int, h: int, depth: int) -> int;
extern func GfxFreeBitMap(handle: int) -> void;
extern func GfxBitMapClear(handle: int) -> void;
extern func GfxBitMapPlot(handle: int, x: int, y: int, pen: int) -> void;
extern func GfxBlit(src: int, sx: int, sy: int, w: int, h: int, dx: int, dy: int) -> void;

extern func GfxSpriteGet(prefer: int) -> int;
extern func GfxSpriteData(slot: int, data: int, height: int) -> int;
extern func GfxSpriteMove(slot: int, x: int, y: int) -> void;
extern func GfxSpriteFree(slot: int) -> void;

extern func GfxWaitEvent() -> int;   // 0=none, 1=close (borderless quit window)
```

Returns: `0` / `-1` for status; `GfxOpenScreen` / `GfxAllocBitMap` / `GfxSpriteGet` return
pointers or handles as ints (`0` = fail).

Quit path: a thin borderless `CUSTOMSCREEN` window with `IDCMP_CLOSEWINDOW` /
`IDCMP_VANILLAKEY` (ESC); `GfxWaitEvent` returns `1` on close/ESC.

---

## pythonami Layer 1 (`ext/amiga_gfx/amiga_gfx.py68k`)

Same drawing surface as HAS, snake_case. Additional OS-only display/input
(shipped in pythonami first; HAS may mirror later):

```python
gfx.open_window(title, x, y, w, h)   # Workbench window; draw+blit on RPort
gfx.poll()                           # non-blocking IDCMP
gfx.key() / gfx.rawkey()
gfx.mouse_x() / gfx.mouse_y() / gfx.mouse_buttons()
gfx.joy(port) / gfx.joy_x(port) / gfx.joy_y(port) / gfx.joy_fire(port)
gfx.sprite_box(slot, height, pattern)  # chip SimpleSprite fill (1..3)
gfx.bob_create(bitmap, save_bg)        # save_bg=1: restore bg on move
gfx.bob_draw(bob, x, y) / bob_undraw / bob_free
```

Workbench windows support plot/line/rect/circle/text/blit. Custom screens own
the palette and are preferred for SimpleSprites (`MODE_SPRITES`).

Keep the library module reachable until after `shutdown`.
Layer 2: `lib/amiga_gfx.py`.

---

## Validation

| Gate | Evidence |
|------|----------|
| HAS assemble | `hasc` + `vasmm68k_mot` on demo |
| Plugin link | `make amiga-ext` |
| Host syntax | `pythonami --check` on smoke scripts |
| Intuition execution | Owner AROS / WinUAE / hardware — not Musashi |
