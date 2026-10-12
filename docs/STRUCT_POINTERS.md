# Struct Pointers

## Overview

HAS supports typed struct pointers, addresses of struct-array elements, field
access through pointers, and indexed pointer access. These forms are available
for both `--cpu 68000` and `--cpu 68020`; instruction selection differs where
the 68020 target can use scaled indexed addressing.

## Syntax

### Declaration
```has
var p:bullet*;          // Pointer to bullet struct
var enemy_ptr:Enemy*;   // Pointer to Enemy struct
```

### Getting Address
```has
p = &bullet[2];         // Get address of bullet[2]
p = &enemies[i];        // Get address of enemies[i] in loop
```

### Accessing Through Pointer
```has
// Two syntaxes supported:
p->x = 100;             // Arrow operator (recommended)
var frame = p->frame;   // Cleaner and more readable

(*p).x = 100;           // Explicit dereference (also works)
var frame = (*p).frame; // Equivalent to arrow operator
```

### Indexing Through a Pointer

A struct pointer can be indexed directly, and it strides by the **struct size** -
identical to indexing the struct array itself:

```has
proc get_x(p: Ent*, i: int) -> int { return p[i].x; }   // strides by sizeof(Ent)
proc arr_x(i: int) -> int { return Ent[i].x; }          // same stride
```

For `struct Ent { x: i16, y: i16, z: i16 }` (6 bytes) both emit `mulu.w #6`.
Scalar pointees stride by their element size: `i8*` needs no scaling, `i16*`
uses `lsl.l #1`, `i32*` uses `lsl.l #2`. Reads and writes always use the same
stride.

Indexing a `void*` is rejected at validation, because the element size is
undefined and any stride would be a guess:

```
Cannot index through 'void*' variable 'p': the element size is undefined.
Declare it with a concrete element type (e.g. 'byte*', 'int*').
```

### Field Declaration: Size Suffix vs Type

Struct fields can be declared two ways, and the choice determines how a narrow
field is **read back**:

```has
struct entity[16] {
    x: i16,        // typed  -> sign-extended on read
    y: i16,
    vx: i8,        // typed  -> sign-extended on read
    flags: u8,     // typed  -> zero-extended on read
    frame.b,       // suffix -> zero-extended on read (legacy)
    sprite.l
}
```

A size-suffix field (`frame.b`) carries no signedness, so it is always read
zero-extended: a `.w` field holding `-1` reads back as `65535`, and a guard
like `if (e.frame_delta <= 0)` can never fire for a negative value. Use the
typed form for any field that must hold negative values - coordinates that go
off-screen left/top, velocities, deltas.

Emission per field type, at all three access sites (`s.field`, `p->field`,
`arr[i].field`):

| Field type | Read emission (68000) | Read emission (68020) |
| --- | --- | --- |
| `i8`, `byte`, `char`, `BYTE` | `move.b` + `ext.w` + `ext.l` | `move.b` + `extb.l` |
| `u8`, `bool`, `UBYTE` | `clr.l` + `move.b` | same |
| `i16`, `word`, `short`, `WORD` | `move.w` + `ext.l` | same |
| `u16`, `UWORD` | `clr.l` + `move.w` | same |
| `int`, `long`, `i32`, pointers | `move.l` | same |
| `.b` / `.w` suffix (legacy) | zero-extended | zero-extended |

The suffix form remains correct and is not deprecated - it is the right choice
for flags, frame indices, tile IDs, and other non-negative data, and it stays
byte-for-byte compatible with existing code.

## Reusing an Element Address

Repeated `array[i].field` expressions recalculate the element address. In a hot
loop that accesses several fields, take the address once and reuse a typed
pointer.

### Repeated Array Access

```has
proc UpdateBullets() -> void {
    var i:int;
    
    for i = 0 to MAX_BULLETS {
        if (bullet[i].active == 1) {
            // Each access recalculates bullet[i] address
            bullet[i].x = bullet[i].x + bullet[i].dir_x;
            bullet[i].y = bullet[i].y + bullet[i].dir_y;
            bullet[i].frame = (bullet[i].frame + 1) & 3;
        }
    }
}
```

The generated code recalculates the element offset for each access:
```asm
lea bullet,a0
move.l d7,d1
mulu.w #10,d1           ; Calculate offset
; Access first field
lea bullet,a0           ; RECALCULATE AGAIN
move.l d7,d1
mulu.w #10,d1           ; RECALCULATE AGAIN
; Access second field
lea bullet,a0           ; RECALCULATE AGAIN
move.l d7,d1
mulu.w #10,d1           ; RECALCULATE AGAIN
; ... and so on for each field
```

### Reused Pointer
```has
proc UpdateBullets() -> void {
    var i:int;
    var b:bullet*;
    
    for i = 0 to MAX_BULLETS {
        b = &bullet[i];                      // Calculate once
        if (b->active == 1) {
            // Reuse cached address with arrow operator
            b->x = b->x + b->dir_x;
            b->y = b->y + b->dir_y;
            b->frame = (b->frame + 1) & 3;
        }
    }
}
```

The pointer form calculates the element address once, then uses field offsets:
```asm
lea bullet,a0
move.l d7,d1
mulu.w #10,d1           ; Calculate offset ONCE
add.l d1,a0
move.l a0,-8(a4)        ; Store pointer

; All subsequent accesses just load pointer and use offsets
move.l -8(a4),a0        ; Load pointer
move.w (a0),d0          ; Access x field at offset 0
move.l -8(a4),a0        ; Load pointer
move.b 4(a0),d2         ; Access dir_x at offset 4
; ... additional field accesses reuse the pointer
```

Whether this improves a particular loop depends on field count, register
pressure, and surrounding expressions. Compare the generated `.s` files for
the target CPU instead of relying on a fixed percentage estimate.

## Passing Pointers to Functions

You can pass struct pointers to functions for cleaner code:

```has
proc InitBullet(__reg(a0) b_ptr:bullet*, __reg(d0) x:word, __reg(d1) y:word) -> void {
    (*b_ptr).x = x;
    (*b_ptr).y = y;
    (*b_ptr).frame = 0;
    (*b_ptr).active = 1;
}

proc main() -> long {
    var p:bullet*;
    p = &bullet[5];
    InitBullet(p, 100, 200);  // Pass pointer in a0 register
    return 0;
}
```

## Compiler Model

- The parser represents `p->field` and `(*p).field` as member access through a
    typed pointer.
- `hasc/codegen.py` resolves the pointee layout and derives element stride,
    load width, and signedness from that layout.
- `hasc/codegen_indexed_address.py` applies the same indexed-address lowering
    to matching pointer and array reads and writes.
- `hasc/validator.py` rejects indexing when the pointee has no defined size,
    including `void*`.

## Examples and Verification

- `examples/tests/compiler/struct_pointer_test.has` covers field reads, writes,
    address-of, and loop usage.
- `examples/struct_pointer_advanced.has` demonstrates address reuse and pointer
    parameters.
- `tests/test_pointer_element_stride.py` verifies read/write symmetry and
    pointer/array stride equivalence on 68000 and 68020.
- `tests/test_typed_struct_fields.py` verifies signed and unsigned narrow-field
    loads on both CPU targets.

Compile the compiler example for both targets:

```bash
python -m hasc.cli examples/tests/compiler/struct_pointer_test.has --cpu 68000 -o build/struct_pointer_68000.s
python -m hasc.cli examples/tests/compiler/struct_pointer_test.has --cpu 68020 -o build/struct_pointer_68020.s
```

## Migration Guide

### Finding Opportunities

Look for code patterns like:
```has
if (entity[i].active) {
    entity[i].x = entity[i].x + 1;
    entity[i].y = entity[i].y + 1;
    entity[i].frame = entity[i].frame + 1;
}
```

### Address-Reuse Pattern

Replace with:
```has
var e:entity*;
e = &entity[i];
if ((*e).active) {
    (*e).x = (*e).x + 1;
    (*e).y = (*e).y + 1;
    (*e).frame = (*e).frame + 1;
}
```

### When to Use

Use struct pointers when:
- Accessing **3+ fields** of the same struct element
- In **hot loops** (called many times per frame)
- With **large structs** (10+ bytes)

Don't bother for:
- Single field access: `bullet[i].x = 100;` (overhead not worth it)
- Outside hot paths (initialization, one-time setup)

## Limitations

### Syntax Options

#### Arrow Operator (Recommended)

C-style arrow operator for cleaner syntax:
```has
p->field      // Recommended
p->x = 100;
var y = p->y;
```

#### Explicit Dereference

Direct dereference syntax (requires parentheses):
```has
(*p).field    // Equivalent explicit form
(*p).x = 100;
var y = (*p).y;

*p.field      // Invalid: ambiguous parsing
```

**Note:** The arrow operator `p->field` is syntactic sugar that the compiler translates to `(*p).field` internally. Both produce identical assembly code.

### Pointer Arithmetic

Basic pointer arithmetic works:
```has
var p:bullet*;
p = &bullet[0];
p = p + 1;        // Advance to next element
```

But be careful - pointer math uses **byte offsets**, not element indices. For proper element stepping, use array indexing:
```has
p = &bullet[i];
p = &bullet[i+1];  // Better than pointer arithmetic
```

## Related Material

- [Struct pointer compiler example](../examples/tests/compiler/struct_pointer_test.has)
- [Advanced struct pointer example](../examples/struct_pointer_advanced.has)
- [Array access code generation](ARRAY_ACCESS_IMPLEMENTATION.md)
