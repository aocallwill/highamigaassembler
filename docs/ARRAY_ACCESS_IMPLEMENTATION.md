# Array Access Code Generation

## Compiler Pipeline

`hasc.ast.ArrayAccess` represents one- and two-dimensional indexing with a
list of index expressions. The parser accepts chained subscripts, the validator
checks the base and each index expression, and `hasc/codegen.py` records global
array dimensions before emission.

Indexed reads, writes, address-of operations, typed-pointer access, and struct
array member access use helpers in `hasc/codegen_indexed_address.py`. Those
helpers delegate stride lowering to `hasc/indexed_address.py`, which returns a
prelude and a final indexed operand. Keep both parts together when adding a new
call site.

## One-Dimensional Access
```m68k
lea arrayname,a0           ; Load base address
move.l index_expr,d1       ; Evaluate index
lsl.l #2,d1                ; Multiply by 4 (element size)
move.l (a0,d1.l),d0        ; Load element
```

The 68000 sequence above is the compatibility baseline. With `--cpu 68020`,
dynamic accesses use the 68020 scaled form for supported strides:

```m68k
lea arrayname,a0
move.l index_expr,d1
move.l (a0,d1.l*4),d0      ; long/int element
```

The same lowering is used for primitive 1D reads and stores, typed-pointer
reads and stores, struct-array member access, two-dimensional reads and stores,
and address-of operations. The shared `hasc/indexed_address.py` helper returns
both any required prelude instructions and the final indexed operand; wrappers
in `hasc/codegen_indexed_address.py` keep each code-generation path on that
contract.

## CPU-Dependent Lowering

The CLI accepts `--cpu 68000` and `--cpu 68020`, defaulting to `68000`. Index
registers are long-sized (`dN.l`) by default. Scale factors `2`, `4`, and `8` are
emitted only for 68020-capable paths; scale `1` is represented by the ordinary
unscaled indexed operand. Constant indexes continue to use direct constant
offsets.

Under `--cpu 68020`, `index_fits_word_range()` in `hasc/indexed_address.py`
checks whether an index expression is a compile-time constant fitting the
signed 16-bit range (-32768..32767). When true, `lower_indexed_address()` uses
a `.w`-sized index register (e.g. `4(a0,d1.w*8)`) instead of `.l` (e.g.
`4(a0,d1.l*8)`), a smaller/faster operand. This is applied at four call sites
in `hasc/codegen_indexed_address.py`: struct-array member read and store,
array store, and typed-pointer store. Typed-pointer reads and address-of are
not covered by this analysis, as those paths already constant-fold
differently. `--cpu 68000` output is unaffected, since the `.w` gate requires
`supports_scaled_index`.

For struct-array members, a field displacement is folded directly into the
indexed operand's displacement (e.g. `8(a0,d1.l)`) whenever `--cpu 68020` is
selected and the offset fits the signed 8-bit brief-displacement range
(-128..127), or the target supports full-extension addressing for larger
offsets. This folding applies regardless of struct size, so real-world
structs outside the `{2, 4, 8}`-byte scaled-addressing set, such as the 10-,
11-, and 29-byte `explosions`, `Enemy`, and `bullet` structs in
`examples/games/launchers/launchers.has`, save one `add.l`-style instruction
per field access. Scale-factor addressing itself (using `*2`, `*4`, or `*8`
in the operand) remains a separate optimization that still only applies when
the struct stride is exactly `2`, `4`, or `8` bytes; larger or non-power-of-two
strides are never forced into a scaled operand, but still benefit from
displacement folding. `--cpu 68000` output is unaffected either way and
keeps the displacement as explicit `add.l` arithmetic.

Fallback lowering is target-independent: strides `16` and `32` use long shifts,
other strides through `32767` use `mulu.w`, and larger strides use full-width
shift/add multiplication rather than a truncating word multiply. These paths
preserve the existing 68000-compatible address calculation.

Assemble generated output with the matching vasm CPU flag:

```bash
python -m hasc.cli input.has --cpu 68000 -o /tmp/output-68000.s
vasmm68k_mot -m68000 -Fhunkexe -o /tmp/output-68000.o /tmp/output-68000.s

python -m hasc.cli input.has --cpu 68020 -o /tmp/output-68020.s
vasmm68k_mot -m68020 -Fhunkexe -o /tmp/output-68020.o /tmp/output-68020.s
```

## Two-Dimensional Access
```m68k
; Calculate: base + (row * col_count + col) * element_size
move.l row_expr,d1         ; Evaluate row
move.l d1,d2               ; Save row
move.l col_expr,d1         ; Evaluate col
; Full-width shift/add sequence computes d2 = row * col_count using d3 scratch.
move.l d2,d3
clr.l d2
add.l d1,d2                ; + col
lsl.l #2,d2                ; * 4 (element size)
lea arrayname,a0           ; Load base address
move.l (a0,d2.l),d0        ; Load element
```

The final element-size scaling is target-aware: 68000 uses an explicit long
shift or arithmetic fallback, while 68020 may use a legal scaled operand such
as `(a0,d2.l*4)`. Row multiplication remains full-width and does not use
`mulu.w`.

## Narrow Element Extension Rules

A `move.b`/`move.w` writes only the low 8 or 16 bits of the destination, so a
byte- or word-sized element read must always be paired with an extension;
otherwise the upper bits keep whatever the previous computation left there.
`emit_narrow_element_load()` in `hasc/codegen_indexed_address.py` is the single
place that decides this, and it is used by `emit_1d_array_read()`,
`emit_2d_array_read()`, and `emit_typed_pointer_read()` (both the constant- and
variable-index branches).

| Element / pointee type | `--cpu 68000` | `--cpu 68020` |
| --- | --- | --- |
| signed 8-bit (`i8`, `byte`, `char`, `BYTE`) | `move.b` + `ext.w` + `ext.l` | `move.b` + `extb.l` |
| unsigned 8-bit (`u8`, `bool`, `UBYTE`) | `clr.l` + `move.b` | `clr.l` + `move.b` |
| signed 16-bit (`i16`, `word`, `short`, `WORD`) | `move.w` + `ext.l` | `move.w` + `ext.l` |
| unsigned 16-bit (`u16`, `UWORD`) | `clr.l` + `move.w` | `clr.l` + `move.w` |
| 32-bit and pointer types | `move.l` | `move.l` |

Zero-extension is hoisted to a `clr.l` *before* the load (6 cycles / 2 bytes)
rather than a trailing `andi.l #$FF`/`#$FFFF` (14 cycles / 6 bytes). The
`clr.l` must be emitted after the address prelude, because the prelude computes
the scaled index into the index register. When the destination register aliases
that still-live index register, hoisting is illegal and the trailing `andi.l`
form is used instead.

Signedness for global arrays is recorded by `_build_array_dimensions()` in
`hasc/codegen.py` from `ast.GlobalVarDecl.signed`, which is only set by the
opt-in typed declaration form (`grid: i8[4] = {...}`). The legacy suffix form
(`grid.b[4]`) carries no type information and is treated as unsigned, matching
the existing behavior for scalar globals. Typed pointer reads classify the
pointee type directly with `ast.is_signed()`.

Regression coverage lives in `tests/test_narrow_element_reads.py` and
`examples/tests/compiler/narrow_element_read_test.has`.

## Register and Evaluation-Order Contract

- `d0`: Primary result register (reg_left)
- `d1`: Secondary operand register (reg_right)
- `d2`: Temp for 2D array calculations
- `d3`: Scratch for full-width 2D row multiplication
- `a0`: Address register for array base
- Stack: Preserve left operand in complex binary operations

Index expressions may contain calls. Emitters must evaluate a call-bearing
index before loading a base address that the call could clobber. Stores must
evaluate the right-hand side before forming the final destination address.
Tests in `tests/test_codegen_basic.py` and
`tests/test_codegen_68020_indexing.py` pin these ordering rules.

## Current Limits

- Local arrays are not stack-allocated; array declarations are global.
- Primitive arrays support up to two dimensions. Struct-array member access is
  one-dimensional.
- Array bounds are not checked at runtime.
- 68020 memory-indirect indexed forms are not emitted.
- On 68020, `.w` index selection is limited to compile-time constants in the
  signed 16-bit range at the four call sites described above. Dynamic indexes,
  typed-pointer reads, and address-of paths retain `.l` indexes.

## Examples

### 1D Array Access:
```has
var value: int = numbers[index];
```

### 2D Array Access:
```has
var element: int = matrix[row][col];
```

### Complex Expression:
```has
result = arr1[i] + matrix[i][j] * 2 - arr2[j];
```

### In Loops:
```has
for i = 0 to 9 {
    sum = sum + arr[i];
}
```

## Verification

Compile the language examples for both targets:

```bash
python -m hasc.cli examples/tests/compiler/array_access_test.has --cpu 68000 -o build/array_access_68000.s
python -m hasc.cli examples/tests/compiler/array_access_test.has --cpu 68020 -o build/array_access_68020.s
```

Run the focused code-generation tests:

```bash
python -m pytest tests/test_codegen_basic.py tests/test_codegen_68020_indexing.py tests/test_narrow_element_reads.py
```

See [CPU 68020 Implementation Plan](CPU_68020_IMPLEMENTATION_PLAN.md) for the
remaining target roadmap.
