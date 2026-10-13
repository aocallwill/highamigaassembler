% Scroll Function Design - Summary and Index

# Scroll Function Design Package

This directory contains a complete design specification for implementing and using the **Scroll** function in the HAS compiler ecosystem.

## Overview

The Scroll function is an external library function that scrolls a rectangular region of the Amiga screen by a specified number of pixels in horizontal and/or vertical directions. It is optimized for performance using the Amiga Blitter hardware and uses a register-based calling convention to minimize function call overhead.

### Key Features

- **7 parameters**: All passed in dedicated data registers (d0–d6)
- **Zero stack overhead**: No parameter push/pop, no stack cleanup
- **Register-based ABI**: Caller specifies which registers receive which parameters
- **Return value**: 0 (success) or -1 (error) in d0
- **Mode restriction**: Works in Mode 0 (1-bitplane), Mode 1 (2-bitplane), and Mode 3 (dual
  playfield, active playfield only); not HAM6
- **Hardware accelerated**: Uses Amiga Blitter for high-performance scrolling

---

## Document Index

### 1. **SCROLL_FUNCTION_DESIGN.md**
   **Comprehensive Specification (7 sections, ~500 lines)**
   
   Contents:
   - Overview and extern declaration syntax
   - Detailed parameter passing convention (table with register assignments)
   - 5+ practical HAS examples (full-screen, windows, error handling, animation)
   - Generated assembly code examples for each case
   - Constraints, mode restrictions, Blitter behavior
   - ABI and stack frame notes
   - Library implementation template
   - Comparison with stack-based alternatives
   
   **Read this if you need**: Deep understanding of how Scroll works, detailed calling convention, assembly code generation patterns.

### 2. **SCROLL_FUNCTION_QUICK_REF.md**
   **Quick Reference Card (1 page, ~100 lines)**
   
   Contents:
   - Declaration syntax
   - Parameter table (register, purpose)
   - Return value semantics
   - 4 quick examples (up, right, left, sub-region)
   - Constraints at a glance
   - Common errors
   - Link to full documentation
   
   **Read this if you need**: Quick lookup during coding, parameter reference, common patterns.

### 3. **scroll_function_demo.has**
   **Practical Example File (HAS source, ~150 lines)**
   
   Contents:
   - Extern declaration (copy-paste ready)
   - 5 helper procedures (scroll_screen_up, down, left, right, window)
   - Safe scroll with validation
   - Animated scroll example
   - Complete main() demonstrating all patterns
   
   **Run this to**: Understand HAS calling patterns, test generated assembly, see error handling.

### 4. **scroll.s**
   **Reference VASM Implementation (commented template, ~200 lines)**
   
   Contents:
   - Function signature and calling convention comments
   - Input/output register specifications
   - Validation logic (region bounds, parameter ranges)
   - Blitter parameter calculation framework
   - Error handling paths
   - Implementation notes and edge cases
   
   **Use this if you need**: To implement the external Scroll function in VASM, understand hardware integration, extend with Blitter programming.

---

## Quick Start

### For HAS Programmers

1. Copy the extern declaration from **scroll_function_demo.has**:
   ```has
   extern func Scroll(__reg(d0) x0: int, __reg(d1) y0: int, __reg(d2) x1: int, 
                      __reg(d3) y1: int, __reg(d4) hor: int, __reg(d5) vert: int, 
                      __reg(d6) pixels: int) -> int;
   ```

2. Use the helper procedures from the demo file (or create your own):
   ```has
   var result: int = Scroll(0, 0, 319, 255, 0, -1, 16);  // Scroll up 16 pixels
   ```

3. Check the return value:
   ```has
   if (result == 0) {
       // Success
   } else {
       // Error: invalid region or unsupported mode
   }
   ```

### For VASM Library Developers

1. Review **SCROLL_FUNCTION_DESIGN.md** sections 2 and 6 for the calling convention and implementation template.
2. Examine **scroll.s** for the function skeleton and pseudocode.
3. Implement the Blitter setup and wait logic according to your Amiga graphics system.
4. Export the function as `XDEF Scroll` for linking with HAS code.

### For Compiler Developers

1. Reference the generated assembly examples in **SCROLL_FUNCTION_DESIGN.md** (Section 4).
2. Verify that your `extern func` code generation matches the register-based calling convention.
3. Test with **scroll_function_demo.has** to ensure correct parameter loading and cleanup.

---

## Calling Convention Summary

| Aspect | Value |
|--------|-------|
| **Parameters** | 7 × 32-bit integers in registers d0–d6 |
| **Return Value** | 32-bit integer in d0 (0 or -1) |
| **Stack Usage** | None (all parameters in registers) |
| **Preserved Registers** | d1–d7, a0–a5 (caller saves if needed) |
| **Calling Instruction** | `jsr Scroll` |
| **Return Instruction** | `rts` (standard 68000) |

---

## Parameter Table

| Register | Parameter | Type | Range | Meaning |
|----------|-----------|------|-------|---------|
| d0 | x0 | int | 0–319 | Left edge of scroll region |
| d1 | y0 | int | 0–255/511 | Top edge of scroll region |
| d2 | x1 | int | >x0 | Right edge of scroll region |
| d3 | y1 | int | >y0 | Bottom edge of scroll region |
| d4 | hor | int | -1/0/1 | Horizontal direction (left/none/right) |
| d5 | vert | int | -1/0/1 | Vertical direction (up/none/down) |
| d6 | pixels | int | >0 | Scroll distance in pixels |

---

## Supported Modes

✅ **Mode 0** (1-bitplane, 16 colors)
✅ **Mode 1** (2-bitplane, 4 colors)
✅ **Mode 3** (dual playfield) — scrolls only the active playfield (`SetActivePlayfield`)
❌ **HAM6** (24-bit hold-and-modify) — **NOT SUPPORTED** → returns -1
❌ **Other modes** → **NOT SUPPORTED** → returns -1

---

## Usage Examples

### Example 1: Full-Screen Scroll Up
```has
extern func Scroll(...) -> int;

proc main() -> int {
    return Scroll(0, 0, 319, 255, 0, -1, 16);  // Scroll up 16 pixels
}
```

### Example 2: Window Sub-Region Scroll
```has
proc main() -> int {
    // Scroll window from (100, 50) to (200, 150) left by 8 pixels
    return Scroll(100, 50, 200, 150, -1, 0, 8);
}
```

### Example 3: With Error Checking
```has
proc main() -> int {
    var result: int;
    
    result = Scroll(0, 0, 319, 255, 0, -1, 32);
    
    if (result == 0) {
        return 0;  // Success
    } else {
        return -1; // Error
    }
}
```

### Example 4: Animated Scroll
```has
proc main() -> int {
    var frame: int = 0;
    
    while (frame < 10) {
        if (Scroll(0, 0, 319, 255, -1, 0, 4) != 0) {
            return -1;  // Error
        }
        frame = frame + 1;
    }
    
    return 0;
}
```

---

## Generated Assembly

### Basic Call
**HAS:**
```has
Scroll(100, 50, 200, 150, -1, 0, 8);
```

**Generated Assembly:**
```asm
    move.l #100,d0
    move.l #50,d1
    move.l #200,d2
    move.l #150,d3
    move.l #-1,d4
    move.l #0,d5
    move.l #8,d6
    jsr Scroll
```

**Overhead**: 8 instructions (7 moves + 1 jsr) ≈ 20 bytes

**Comparison with stack-based (7 stack parameters)**: 15 instructions (7 moves + 1 jsr + 1 add) ≈ 32 bytes — **37% more code**

---

## Performance Notes

- **Register parameters**: No stack memory access, no cleanup instruction needed
- **Single call**: One `jsr` instruction (no nested setup)
- **Blitter acceleration**: Hardware-accelerated scrolling (may have variable latency if Blitter is busy)
- **No ABI overhead**: Parameters directly in registers matching library calling convention

---

## Constraints and Limitations

1. **Region Validation**: x0 < x1 and y0 < y1 (returns -1 if invalid)
2. **Boundary Checking**: All coordinates must be within screen bounds
3. **Mode Restriction**: Works in Mode 0/1/3 (returns -1 for HAM6; Mode 3/dual playfield scrolls only the active playfield)
4. **Blitter Dependency**: Requires Amiga Blitter (may busy-wait if in use)
5. **No Wildcards**: Cannot scroll beyond region boundaries
6. **Signed Parameters**: Direction flags (hor, vert) are signed (-1, 0, 1)

---

## File Organization

```
docs/
  SCROLL_FUNCTION_DESIGN.md          [Full specification]
  SCROLL_FUNCTION_QUICK_REF.md       [Quick reference]
  SCROLL_FUNCTION_DESIGN_INDEX.md    [This file]

examples/
  scroll_function_demo.has           [HAS usage examples]

lib/
  scroll.s                           [VASM implementation template]
```

---

## Validation Checklist

When implementing or using the Scroll function:

- [ ] Extern declaration matches calling convention (d0–d6 for parameters, d0 for return)
- [ ] All 7 parameters loaded into correct registers before `jsr`
- [ ] Region coordinates satisfy x0 < x1, y0 < y1
- [ ] Graphics mode is Mode 0, Mode 1, or Mode 3/dual playfield (not HAM6)
- [ ] Return value checked (0 = success, -1 = error)
- [ ] Non-volatile registers preserved if used after call
- [ ] No stack cleanup required (register-based convention)
- [ ] Test with vasmm68k_mot to validate generated assembly

---

## Related Documentation

- [EXTERNAL_MODULES.md](EXTERNAL_MODULES.md) — How extern declarations work in HAS
- [TERMINOLOGY.md](TERMINOLOGY.md) — Calling convention overview
- [DEVELOPERS_GUIDE.md](DEVELOPERS_GUIDE.md) — HAS procedure/function guide
- [GRAPHICS_LIBRARY_INTERFACE.md](GRAPHICS_LIBRARY_INTERFACE.md) — Graphics library integration

---

## Questions and Troubleshooting

### Q: What if I need to scroll with stack-based parameters?
**A:** Define an alternative extern as `Scroll_Stack(...)` with unadorned parameters. Compiler will generate stack-based calling code. Not recommended for performance reasons.

### Q: Can I use Scroll in HAM6 mode?
**A:** No. The function will return -1 (error). Use alternative graphics routines or convert to Mode 0/1 for scrolling.

### Q: What happens if the Blitter is busy?
**A:** Scroll may busy-wait until the Blitter is available. In performance-critical code, use TakeSystem before calling Scroll repeatedly.

### Q: Can I scroll diagonally?
**A:** Yes, set both hor and vert to non-zero values (e.g., -1, 1) and Scroll will handle both directions.

### Q: Do I need to preserve d0–d6 before calling Scroll?
**A:** Only if you need the values after the call. Since you're loading new values into these registers to call Scroll, previous values are lost anyway.

---

**Last Updated**: 2026-09-06  
**HAS Version**: 0.9.9
**Status**: Design Phase (Reference Implementation)
