# HAS Developer's Guide

A practical guide to the High Assembler (HAS) language with examples for every feature.

## Table of Contents
1. [Getting Started](#getting-started)
2. [Basic Syntax](#basic-syntax)
3. [Data Types](#data-types)
4. [Procedures and Functions](#procedures-and-functions)
5. [Variables and Constants](#variables-and-constants)
6. [Arrays](#arrays)
7. [Pointers](#pointers)
8. [Control Flow](#control-flow)
9. [Operators](#operators)
10. [Code Execution Order](#code-execution-order)
11. [Amiga OS Takeover and Release](#amiga-os-takeover-and-release-system)
12. [Advanced Features](#advanced-features)
13. [Compilation](#compilation)

---

## Getting Started

### Setup
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Your First Program
```has
code main:
    call main();
    asm "rts";

    proc main() -> long {
        return 42;
    }
```

Compile and run:
```bash
python -m hasc.cli example.has -o out.s
./scripts/build.sh out.s out.o out.exe
```

---

## Basic Syntax

### Comments
```has
// This is a comment in HAS
// Comments use double forward slashes

code demo:
    proc test() -> long {
        // Inline comments are supported
        return 0;  // Comment at end of line
    }
```

**Note:** Semicolons terminate HAS statements. In generated 68000 assembly, `;` starts a comment (instructions are separated by newlines), and inline `asm { ... }` follows the same assembly commenting rules.

### Code Sections
HAS organizes code into three section types:

```has
// Data section - initialized global variables
data globals:
    counter = 42
    pi = 314159

// BSS section - uninitialized memory
bss buffers:
    output_buffer[1024]

// Code section - procedures
code main:
    proc main() -> long {
        return 0;
    }
```

---

## Data Types

### Basic Types
```has
code types_demo:
    proc demo() -> long {
        // 8-bit types
        var b1: byte = 255;           // 8-bit unsigned
        var b2: i8 = -128;            // 8-bit signed
        var ch: char = 'A';           // Character (8-bit)
        var flag: bool = TRUE;        // Boolean (0=false, 1=true)
        
        // 16-bit types
        var w1: word = 65535;         // 16-bit unsigned
        var w2: i16 = -32768;         // 16-bit signed
        
        // 32-bit types (most common)
        var n1: long = 1000000;       // 32-bit signed
        var n2: int = 42;             // Alias for long
        var u1: u32 = 4000000000;     // 32-bit unsigned
        
        // Pointer types
        var ptr1: ptr = 0;            // Generic pointer
        var ptr2: int* = 0;           // Pointer to int
        
        // Special type
        var nothing: void;            // No value
        
        return 0;
    }
```

### Boolean Type
The `bool` type is a 1-byte type optimized for boolean semantics. Values are:
- **0** = false
- **Non-zero** (typically 1) = true

Use `bool` for explicit boolean intent. For boolean constants, define them with `const`:

```has
const TRUE = 1;
const FALSE = 0;

code bool_example:
    proc check_flag(enabled: bool) -> long {
        if (enabled == TRUE) {
            return 1;
        }
        return 0;
    }
```

Alternatively, use `byte` when you need a raw 8-bit value without boolean semantics.

### Amiga-Specific Types
```has
code amiga_types:
    proc setup() -> long {
        var byte_val: UBYTE = 255;    // Unsigned byte
        var word_val: UWORD = 65535;  // Unsigned word
        var long_val: ULONG = 1000;   // Unsigned long
        var amiga_ptr: APTR = 0;      // Amiga pointer
        
        return 0;
    }
```

### Type Promotion
```has
code promotion_demo:
    proc calc() -> long {
        var b: byte = 10;
        var w: word = 20;
        var l: long = 30;
        
        // Implicit promotion: byte → word → long
        var result: long = b + w + l;  // All promoted to long
        
        return result;
    }
```

---

## Procedures and Functions

### Basic Procedure
```has
code procedures:
    proc add(a: long, b: long) -> long {
        return a + b;
    }
    
    proc main() -> long {
        var result: long = add(5, 3);
        return result;  ; Returns 8
    }
```

### Procedures with Multiple Parameters
```has
code multi_param:
    proc multiply(x: long, y: long, z: long) -> long {
        return x * y * z;
    }
    
    proc main() -> long {
        return multiply(2, 3, 4);  ; Returns 24
    }
```

### Forward Declarations
```has
code forward_decl:
    ; Declare function before defining it
    func helper(n: long) -> long;
    
    proc main() -> long {
        return helper(10);
    }
    
    ; Define it later in the code section
    proc helper(n: long) -> long {
        return n * 2;
    }
```

### External Functions
```has
code external:
    ; Import from external module
    extern func print_int(value: long) -> long;
    extern func get_time() -> long;
    
    proc main() -> long {
        var time: long = get_time();
        print_int(time);
        return 0;
    }
```

### External Variables

External variables can be declared with optional type annotation:

```has
code external_vars:
    extern var screen_buffer: byte*;        ; Pointer (no type annotation)
    extern var frame_counter: int;          ; Typed: 32-bit signed
    extern var velocity_x: i16;             ; Typed: 16-bit signed, sign-extends
    extern var palette: u8*;                ; Typed: unsigned byte pointer
    
    proc update_frame() -> long {
        frame_counter = frame_counter + 1;  ; Loads with sign-extension
        return frame_counter;
    }
```

**Typed vs. Untyped External Variables:**

- **Untyped** (`extern var name;`): Treated as generic pointers or 32-bit values; byte/word loads zero-extend
- **Typed** (`extern var name: i8;` / `i16` / `u8` / `u16`): Sign-extend on load (for signed types) or zero-extend (unsigned types)

Sign-extension is crucial for correct comparisons on signed extern globals:

```has
extern var dx: i8;     ; Signed displacement - sign-extends on load
extern var flags: u8;  ; Unsigned flags - zero-extends on load

proc check() -> int {
    if (dx < 0) {      ; Correctly detects negative displacement
        return -1;
    }
    if (flags < 0) {   ; Always false: zero-extended value is always >= 0
        return -1;
    }
    return 0;
}
```

See [examples/extern_signed_byte_test.has](../examples/extern_signed_byte_test.has) for complete example.

### Register Parameters (Performance)
```has
code register_params:
    ; Allocate parameters to specific registers for speed
    proc fast_add(__reg(d0) a: long, __reg(d1) b: long) -> long {
        return a + b;  ; Arguments already in d0 and d1
    }
    
    proc main() -> long {
        return fast_add(100, 200);
    }
```

**Important Optimization Note:**

Register parameters (`__reg(d0)`, `__reg(d1)`, etc.) provide **maximum performance benefit only when used with native assembly-body procedures**:

```has
native proc vector_mult(__reg(a0) vec: ptr, __reg(d0) scale: long) -> void {
    asm {
        ; Direct register access - optimal performance
        move.l (a0),d1
        muls.l d0,d1
        move.l d1,(a0)
    }
    return;
}
```

When used with HAS (high-level) code bodies, register parameters provide **minimal or no benefit** because:
- The compiler saves data register parameters to stack immediately (to prevent clobbering)
- HAS code then accesses parameters from stack locations
- Parameter passing overhead is equivalent to stack-based calling convention

```has
proc vec_add(__reg(d0) a: long, __reg(d1) b: long) -> long {
    ; d0 and d1 are saved to stack in prologue
    ; Compiler loads them from stack for each use
    ; No performance advantage over stack parameters
    return a + b;
}
```

**Best Practices:**
- Use `__reg()` for **external functions** (library calls) where calling convention is fixed
- Use `__reg()` with **native assembly-only procedures** where you directly access registers
- For **HAS-body procedures**: Register parameters provide no optimization, stick with stack parameters

---

### Calling Convention

HAS uses a simple, library-friendly calling convention:

- Default is **stack-based**: arguments are pushed in reverse order, then `jsr`.
- Each argument occupies **4 bytes (long)** on the stack, regardless of source type.
- Small types (`bool`, `byte`, `word`) are **widened to 32-bit** by the caller and pushed as longs.
    - Current widening behavior: **zero-extension** for small types.
- Callee accesses parameters from its frame at **`8(a6)`, `12(a6)`, `16(a6)`...**.
- After the call, the caller performs stack cleanup via **`add.l #4*n,a7`**.
- If a procedure declares register parameters via `__reg(...)`, the caller loads those registers before `jsr`. Data registers used for parameters are saved/restored around the call in HAS bodies.

Example (conceptual):

```
; Caller (push args as longs)
clr.l d0
move.b move_flag,d0   ; bool → zero-extended
move.l d0,-(a7)
jsr DrawPlayer
addq.l #4,a7          ; one argument → 4 bytes cleanup

; Callee
link a6,#-...
move.l 8(a6),d0       ; first parameter as long
cmp.l #1,d0
...
unlk a6
rts
```

This convention keeps HAS-compatible with the provided `lib/*.s` libraries and typical Amiga assembly interfaces while avoiding ambiguity with narrow types.

**Sign Extension for Signed Types:**

When loading 8-bit or 16-bit values (from global variables, local variables, or procedure parameters), the behavior depends on the variable's declared type:

- **Typed form** (`var name: i8` / `i16` / `byte` / `word` in typed syntax): Sign-extended (for negative values)
  - 68020: Single `extb.l` (for `i8`) or `ext.l` (for `i16`) instruction
  - 68000: Two-instruction sequence (`ext.w`+`ext.l`)
  
- **Legacy form** (`var name.b` / `.w`): Always zero-extended (unsigned)
  - Both targets: `andi.l #$FF` (byte) or `andi.l #$FFFF` (word)

This applies to:
- Global variables declared with `name: type = value;` (typed) vs. `name.b = value;` (legacy)
- External variables declared with `extern var name: type;` (typed)
- Local procedure parameters (always use declared type)

**Example: Sign vs. Zero Extension**

```has
data globals:
    signed_byte: i8 = 0xFB      ; -5 (sign-extended on load)
    legacy_byte.b = 0xFB        ; 251 (zero-extended on load)

code checks:
    proc test() -> int {
        if (signed_byte < 0) {   ; TRUE: signed_byte loads as -5
            return -1;
        }
        if (legacy_byte < 0) {   ; FALSE: legacy_byte loads as 251 (always >= 0)
            return 0;
        }
        return 0;
    }
```

---

## Variables and Constants

### Global Variables

HAS supports two forms of global variable declaration in `data` sections, each with distinct sign-extension behavior:

#### Legacy Form (Zero-Extends)
```has
data globals:
    counter = 100        ; Initialize with value (always zero-extends)
    name = "Game"        ; String data

code variables:
    proc increment() -> long {
        ; Access global from data section
        return counter;
    }
    
    proc main() -> long {
        return increment();
    }
```

The legacy form uses no type annotation. When loaded, byte/word values are always zero-extended (unsigned interpretation):

```has
data legacy_globals:
    myByte.b = 0xFB     ; 0xFB is loaded as 251 (unsigned)
    myWord.w = 0xFFFF   ; 0xFFFF is loaded as 65535 (unsigned)
```

#### Typed Form (Sign-Extends for Signed Types)

**New in 0.9.5**: Opt-in syntax for explicit type annotation:

```has
data typed_globals:
    signedByte: i8 = 0xFB    ; -5 (sign-extended)
    signedWord: i16 = 0xFFFF ; -1 (sign-extended)
    unsignedByte: u8 = 0xFB  ; 251 (zero-extended)
    counter: int = 100       ; 32-bit signed (no extension needed)
```

When loaded, signed-typed values use sign-extension:
- `i8`, `byte`: Load with `extb.l` (68020) or `ext.w`+`ext.l` (68000)
- `i16`, `word`: Load with `ext.l`
- `u8`, `u16`, `int`, `long`: Zero-extend (unchanged)

**When to Use:**
- Use **typed form** for signed arithmetic globals that must preserve sign (e.g., velocity, offset)
- Use **legacy form** for bit patterns and masks that need zero-extension
- Both forms compile correctly; the difference is semantic

**Example: Sign Difference**
```has
data values:
    signed: i8 = -5      ; 0xFB, loads as -5 → comparisons like "if (signed < 0)" work
    legacy: byte.b = -5  ; 0xFB, loads as 251 → comparisons like "if (legacy < 0)" fail

code checks:
    proc test() -> int {
        if (signed < 0) {
            return -1;   ; Executes: signed loads as -5
        }
        if (legacy < 0) {
            return -1;   ; Never executes: legacy loads as 251
        }
        return 0;
    }
```

See [examples/global_signed_byte_test.has](../examples/global_signed_byte_test.has) for complete demonstration.

### Local Variables
```has
code locals:
    proc process(input: long) -> long {
        var local1: long = input;
        var local2: long = 42;
        var local3: long = local1 + local2;
        
        return local3;
    }
    
    proc main() -> long {
        return process(8);  ; Returns 50
    }
```

### Compile-Time Constants
```has
const MAX_SIZE = 1024;
const BUFFER_SIZE = 256;
const TOTAL_SIZE = MAX_SIZE + BUFFER_SIZE;
const TRUE = 1;      ; Boolean constants for readability
const FALSE = 0;

code with_constants:
    proc allocate() -> long {
        ; Constants substituted at compile time
        return MAX_SIZE;
    }
```

Constant initializers support compile-time numeric expressions with `+`, `-`, `*`, `/`, `%`,
unary signs, and parentheses. References are resolved in declaration order, so a constant may
use an earlier constant but not a later one. Decimal values use the compiler's Q16 fixed-point
representation.

### Variable Initialization
```has
data initialized:
    x = 10              ; Initialize to value
    y[10]               ; Array uninitialized
    z = { 1, 2, 3 }    ; Array initialized

bss uninitialized:
    temp[100]           ; Uninitialized memory
```

---

## Arrays

### Single-Dimensional Arrays
```has
data arrays:
    numbers[10]                      ; Declare array of 10 longs
    scores = { 100, 200, 300 }      ; Initialize with values

code array_access:
    proc get_element(index: long) -> long {
        var my_array[5];
        my_array[0] = 10;
        my_array[1] = 20;
        my_array[index] = 99;
        
        return my_array[2];
    }
    
    proc main() -> long {
        return get_element(2);
    }
```

### Multi-Dimensional Arrays
```has
data matrices:
    grid[5][5]                              ; 5×5 matrix
    matrix2d = { {1, 2}, {3, 4} }          ; 2D with init

code multi_dim:
    proc access_2d() -> long {
        var board[8][8];
        board[0][0] = 1;
        board[7][7] = 99;
        
        return board[0][0];
    }
    
    proc main() -> long {
        return access_2d();
    }
```

### Array Dimensions from Constants
```has
const ROWS = 10;
const COLS = 20;

data grid:
    data_grid[ROWS][COLS]

code array_const_dims:
    proc init_grid() -> long {
        ; Array dimensions can reference constants
        return ROWS;
    }
```

---

## Pointers

### Pointer Declaration and Address-Of
```has
code pointer_basics:
    proc pointers() -> long {
        var value: long = 42;
        var ptr: long* = &value;    ; Get address of value
        
        return *ptr;                 ; Dereference: returns 42
    }
    
    proc main() -> long {
        return pointers();
    }
```

### Pointer Arithmetic
```has
code pointer_arithmetic:
    proc array_via_pointer() -> long {
        var arr[10];
        arr[0] = 100;
        arr[1] = 200;
        
        var ptr: long* = &arr[0];
        var next_elem: long = *(ptr + 1);  ; Next element via pointer
        
        return next_elem;  ; Returns 200
    }
```

### Pointer Dereferencing
```has
code dereferencing:
    proc modify_via_pointer(ptr: long*) -> long {
        *ptr = 999;      ; Modify value at pointer
        return *ptr;     ; Read modified value
    }
    
    proc main() -> long {
        var x: long = 1;
        modify_via_pointer(&x);
        return x;        ; Returns 999
    }
```

### Null Pointer Checks
```has
code null_checks:
    proc safe_deref(ptr: long*) -> long {
        if (ptr == 0) {
            return -1;      ; Null pointer
        }
        return *ptr;        ; Safe dereference
    }
```

### Struct Pointers with Arrow Operator

HAS supports C-style arrow operator (`->`) for accessing struct members through pointers:

```has
data types:
    struct Player {
        x: word;
        y: word;
        health: byte;
        active: byte;
    }

data game:
    player: Player[10];

code game_logic:
    proc update_player(index: int) -> void {
        var p: Player*;
        
        p = &player[index];     ; Get pointer to array element
        
        ; Arrow operator (recommended - clean and readable)
        p->x = p->x + 5;
        p->y = p->y + 10;
        p->health = p->health - 1;
        
        ; Equivalent explicit dereference (also works)
        (*p).x = (*p).x + 5;
        (*p).y = (*p).y + 10;
    }
```

**Performance Benefit:** Struct pointers cache the address calculation, reducing code size and execution time when accessing multiple fields:

```has
; Without pointer: 6 array index calculations
player[i].x = 10;
player[i].y = 20;
player[i].health = 100;

; With pointer: 1 address calculation + reuse
p = &player[i];
p->x = 10;
p->y = 20;
p->health = 100;
```

See [docs/STRUCT_POINTERS.md](STRUCT_POINTERS.md) for detailed documentation and performance analysis.

---

## Control Flow

### If-Else Statements

**Note:** IF conditions must be enclosed in parentheses.

Conditions accept any expression. A value of `0` is false; every nonzero
value is true. Use `!expr` to invert that test: `!expr` is true only when
`expr` is `0`.

```has
code conditionals:
    proc compare(a: long, b: long) -> long {
        if (a > b) {
            return a;
        } else {
            return b;
        }
    }
    
    proc test_if(x: long) -> long {
        if (x == 0) {
            return 1;
        } else if (x == 1) {
            return 2;
        } else {
            return 3;
        }
    }

    proc test_flag(flag: int) -> int {
        if (flag) {
            return 1;  // Runs when flag is nonzero
        }
        if (!flag) {
            return 2;  // Runs when flag is zero
        }
        return 0;
    }
```

### While Loops

**Note:** WHILE conditions must be enclosed in parentheses.

```has
code while_loops:
    proc count_down(n: long) -> long {
        while (n > 0) {
            n = n - 1;
        }
        return n;  ; Returns 0
    }
    
    proc sum_series(limit: long) -> long {
        var sum: long = 0;
        var i: long = 0;
        while (i < limit) {
            sum = sum + i;
            i = i + 1;
        }
        return sum;
    }
```

### Do-While Loops

```has
code do_while:
    proc run_once(n: long) -> long {
        do {
            n = n * 2;
        } while (n < 0);  ; Body always executes once
        
        return n;
    }
```
Do-while loops are supported and always execute the loop body at least once.

```has
code do_while:
    proc run_once(n: long) -> long {
        do {
            n = n * 2;
        } while (n < 0);  ; Body always executes once

        return n;
    }
```

### For Loops
```has
code for_loops:
    proc sum_array(arr: long*, len: long) -> long {
        var sum: long = 0;
        for i = 0 to len {
            sum = sum + arr[i];
        }
        return sum;
    }
    
    proc countdown(start: long) -> long {
        for i = start downto 0 {
            ; Process each i
        }
        return 0;
    }
```

### Break and Continue
```has
code loop_control:
    proc find_value(arr: long*, len: long, target: long) -> long {
        for i = 0 to len {
            if (arr[i] == target) {
                break;      ; Exit loop early
            }
        }
        return i;
    }
    
    proc skip_even(limit: long) -> long {
        var sum: long = 0;
        for i = 0 to limit {
            if (i % 2 == 0) {
                continue;   ; Skip to next iteration
            }
            sum = sum + i;
        }
        return sum;
    }
```

---

## Operators

### Arithmetic Operators
```has
code arithmetic:
    proc math_ops(a: long, b: long) -> long {
        var add: long = a + b;        ; Addition
        var sub: long = a - b;        ; Subtraction
        var mul: long = a * b;        ; Multiplication
        var div: long = a / b;        ; Division
        var mod: long = a % b;        ; Modulo
        var neg: long = -a;           ; Negation
        
        return add;
    }
```

### Comparison Operators
```has
code comparisons:
    proc compare(a: long, b: long) -> long {
        if (a == b) { return 1; }       ; Equal
        if (a != b) { return 1; }       ; Not equal
        if (a < b) { return 1; }        ; Less than
        if (a <= b) { return 1; }       ; Less or equal
        if (a > b) { return 1; }        ; Greater than
        if (a >= b) { return 1; }       ; Greater or equal
        
        return 0;
    }
```

### Logical Operators
```has
code logical:
    proc logic(a: long, b: long) -> long {
        if (a > 0 && b > 0) {           ; Logical AND
            return 1;
        }
        if (a < 0 || b < 0) {           ; Logical OR
            return 2;
        }
        if (!a) {                        ; Logical NOT
            return 3;
        }
        return 0;
    }
```

### Bitwise Operators
```has
code bitwise:
    proc bit_ops(a: long, b: long) -> long {
        var and: long = a & b;        ; Bitwise AND
        var or: long = a | b;         ; Bitwise OR
        var xor: long = a ^ b;        ; Bitwise XOR
        var not: long = ~a;           ; Bitwise NOT
        var lshift: long = a << 2;    ; Left shift
        var rshift: long = a >> 2;    ; Right shift
        
        return xor;
    }
```

### Assignment and Compound Assignment
```has
code assignments:
    proc assign_ops() -> long {
        var x: long = 10;
        x = x + 5;          ; x = 15
        x += 3;             ; x = 18
        x -= 2;             ; x = 16
        x *= 2;             ; x = 32
        x /= 4;             ; x = 8
        x %= 3;             ; x = 2
        x &= 255;           ; x = x & 255
        x |= 128;           ; x = x | 128
        x ^= 64;            ; x = x ^ 64
        
        return x;
    }
```

### Increment and Decrement
```has
code increment:
    proc counters() -> long {
        var x: long = 10;
        x++;                ; Postfix increment
        ++x;                ; Prefix increment
        x--;                ; Postfix decrement
        --x;                ; Prefix decrement
        
        return x;
    }
```

Codegen note: when `++`/`--` are used as standalone statements, HAS emits direct
updates to the underlying storage (local/stack/global/register-backed parameter)
without materializing an unused temporary result register. Expression contexts
such as `y = x++` still preserve post-increment old-value semantics.

---

## Advanced Features

### Macros

Macros provide compile-time code templates that expand their body at each call site. Macro parameters can be substituted into HAS statements (expressions, assignments, etc.), but **not into inline assembly strings**:

```has
// Macro without parameters - works with asm blocks
macro clear_registers() {
    asm "clr.l d0";
    asm "clr.l d1";
}

// Macro with parameters - parameters substitute in HAS code, not asm
macro add_values(x, y, result) {
    result = x + y;  // Parameters substituted in HAS expressions
}

code macro_demo:
    proc test() -> long {
        clear_registers();              // No parameters needed
        
        var a: int = 10;
        var b: int = 20;
        var sum: int = 0;
        add_values(a, b, sum);          // Expands to: sum = a + b;
        
        return sum;
    }
```

**Key Points:**
- Macro bodies are compile-time expansions (not runtime function calls)
- **Parameter substitution works in HAS statements only** (assignments, expressions, etc.)
- **Parameter substitution does NOT work in asm blocks** (asm blocks are plain strings)
- Macros can contain any valid HAS statement: variables, loops, conditionals, asm blocks
- Variables in asm blocks (local or parameters) use the `@varname` syntax (e.g., `move.l @temp,d0`)
- For register-parameter manipulation in asm, implement as a regular procedure instead (procedures support `@varname` substitution)

### Python Directives
```has
code python_demo:
    proc computed() -> long {
        @python {
            # Python code runs during compilation
            values = [i * 2 for i in range(10)]
            code = "var table: long = { " + ", ".join(str(v) for v in values) + " };"
            emit(code)
        }
        
        return table[5];  ; Accesses generated variable
    }
```

### External Code Generation
Create `generator.py`:
```python
#!/usr/bin/env python3

def main():
    code = """
data generated:
    lookup_table = { """
    
    values = [i * i for i in range(256)]
    code += ", ".join(str(v) for v in values)
    
    code += """ }

code main:
    proc main() -> long {
        return 0;
    }
"""
    print(code)

if __name__ == "__main__":
    main()
```

Compile with:
```bash
python -m hasc.cli program.has --generate generator.py -o out.s
```

### Inline Assembly
```has
code inline_asm:
    proc raw_code() -> long {
        asm {
            move.l #$12345678,d0    // Raw 68000 instructions
            add.l d0,d1
            rts
        }
        return 0;
    }
```

### Directives
```has
#warning "This feature is deprecated, use NEW_FEATURE instead";

#error "Platform not supported for this build";

#pragma lockreg(a5, a4);

#pragma strict16arith(on);
code math_safe:
    proc mul_small(a: byte, b: word) -> long {
        // In strict16arith mode, operands must be provably safe for 68000 word arithmetic.
        return a * b;
    }

#pragma strict16arith(off);
```

`#warning` emits a compile-time warning and compilation continues. `#error`
emits a compile-time error and stops compilation.

`strict16arith` defaults to `off`. On `--cpu 68000`, `*`, `/` and `%` use only
the low word of each operand, so wider values are silently truncated at
runtime; turning the pragma `on` makes that a compile-time error instead. The
prover accepts literals in range, byte- and signed-word-typed locals and
parameters, named constants, global and extern scalars, byte-sized struct
fields, and `x & C` masks with a constant `C` in range. It deliberately rejects
word-sized struct fields and global array elements, because those are read
without sign extension and so cannot be proven to fit a signed word. The pragma
has no effect under `--cpu 68020`, where `muls.l`/`divsl.l` handle full 32-bit
operands natively.

Conditional compilation directives are resolved at compile time:

```has
const USE_FAST_PATH = 1;

#ifdef USE_FAST_PATH
const MODE = 1;
#else
const MODE = 0;
#endif

#ifndef DEBUG_BUILD
#warning "DEBUG_BUILD is not set";
#endif
```

- `#ifdef NAME` is true whenever `const NAME` is defined, regardless of its
  value (so `const NAME = 0;` still counts as defined).
- `#ifndef NAME` is true when `NAME` is not defined.
- `#else` selects the opposite branch within the current conditional block.
- `#endif` closes the current conditional block.

`#if IDENT OP EXPR` compares a previously-defined `const` against a
constant expression, evaluated with the same evaluator used for `const`
declarations (arithmetic and parentheses are supported):

```has
const API_VERSION = 3;

#if API_VERSION >= 3
const USE_NEW_API = 1;
#else
const USE_NEW_API = 0;
#endif

const RETRY_LIMIT = 5;

#if RETRY_LIMIT > (2+2)
#warning "Retry limit is higher than the recommended default";
#endif
```

- Supported operators: `==` (or its alias `=`), `!=` (or its alias `<>`),
  `>`, `<`, `>=`, `<=`.
- `IDENT` must be a `const` defined earlier in the file; referencing an
  undefined identifier is a compile error, *unless* the `#if` itself is
  inside an already-inactive/dead branch, in which case the condition is
  not evaluated at all (matching `#ifdef`/`#ifndef`/`#include` behavior in
  dead code).
- `#if` frames nest freely with `#ifdef`/`#ifndef`, and support `#else`/`#endif`
  the same way.

---

## Code Execution Order

### ⚠️ Important: No "main()" Entry Point

**HAS executes from top to bottom, exactly like traditional assembly language. There is NO special "main()" entry point.**

When you load and run a compiled HAS program:
1. Execution starts at the **first instruction** in the first code section
2. Code executes sequentially from top to bottom
3. Procedures are only executed when explicitly called or when execution reaches them

```has
code example:
    ; This instruction executes FIRST when program starts
    asm "move.l #42,d0";
    
    ; This procedure will NOT run unless called
    proc helper() -> long {
        return 100;
    }
    
    ; If execution reaches here, this runs next
    asm "move.l #1,d1";
    
    ; A procedure named "main" has NO special meaning
    ; It only runs if called or if execution reaches it
    proc main() -> long {
        return 0;
    }
```

**To create a traditional program with a main function, you must explicitly call it:**

```has
code program:
    ; Program entry point - starts HERE
    call main();  ; Explicitly call main
    asm "rts";    ; Return to OS
    
    ; This only runs when called above
    proc main() -> long {
        var result: long = 42;
        return result;
    }
```

### Top-to-Down Execution (Like Assembler)
HAS code executes from top to bottom, similar to traditional assembly language:

```has
code execution_order:
    proc setup() -> long {
        return 100;
    }
    
    proc main() -> long {
        ; This does NOT run automatically!
        ; It only runs if execution reaches here or if explicitly called
        var val: long = setup();
        return val;
    }
    
    proc cleanup() -> long {
        ; This only executes if called explicitly
        return 0;
    }
```

**Key Points:**
- Code sections are processed in order from first to last
- Procedures don't execute unless called OR unless execution reaches them sequentially
- Forward declarations (`func`) allow calling procedures defined later
- Global data in `data` and `bss` sections is available to all procedures
- **There is no automatic entry point** - execution starts at the first instruction

### Example: Execution Flow
```has
const VERSION = 1;

data settings:
    counter = 0

code app:
    ; Execution starts HERE (first instruction)
    call main();  ; Explicitly call main
    asm "rts";    ; Return to OS
    
    ; Procedure definitions (only run when called)
    proc setup() -> long {
        return VERSION;
    }
    
    proc process(input: long) -> long {
        return input * 2;
    }
    
    ; This does NOT auto-execute - must be called
    proc main() -> long {
        var x: long = setup();     ; Call setup
        var y: long = process(x);  ; Call process
        return y;
    }
    
    proc helper() -> long {
        return counter;
    }
```

When compiled and run:
1. Execution starts at `call main();`
2. `main()` is called → calls `setup()` → returns 1
3. `main()` calls `process(1)` → returns 2
4. `main()` returns to the `call` site
5. Program executes `rts` → returns to OS

### Best Practice: Using main()

While `main()` has no special meaning in HAS, you can follow this pattern for clarity:

```has
code program:
    ; Entry point - execution starts here
    call main();
    asm "rts";
    
    ; Main application logic
    proc main() -> long {
        ; Your code here
        return 0;
    }
```

**Why this pattern is useful:**
- Makes the entry point explicit and easy to find
- Similar to C/C++ conventions (familiar to other programmers)
- Keeps setup/initialization separate from application logic
- Easy to add other top-level code (like cleanup) after main() returns

**Alternative patterns:**

```has
code startup:
    ; Direct execution - no procedure call
    var result: long = 42;
    asm "rts";
```

or

```has
code app:
    asm "jsr _init";  ; Call your initialization
    asm "jsr _run";   ; Call your main loop
    asm "jsr _quit";  ; Call cleanup
    asm "rts";        ; Return to OS
```

See [examples/execution_order_demo.has](../examples/execution_order_demo.has) for a complete demonstration.

---

## Amiga OS Takeover and Release System

### Overview
When running graphics-intensive applications on Amiga, you need to take exclusive control of hardware from the operating system, then properly release it. The `TakeSystem()` and `ReleaseSystem()` functions handle this critical handoff.

### TakeSystem() Function
Disables the OS and takes full control of hardware:

```has
extern func TakeSystem() -> long;

code game:
    proc initialize() -> long {
        TakeSystem();           // Disable OS, take hardware control
        setup_graphics();
        return 0;
    }
    
    proc setup_graphics() -> long {
        // Now you have exclusive access to:
        // - DMA channels
        // - Blitter
        // - Copper
        // - Interrupts
        return 0;
    }
```

### ReleaseSystem() Function
Restores hardware control to the OS:

```has
extern func TakeSystem() -> long;
extern func ReleaseSystem() -> long;

const TRUE = 1;
const FALSE = 0;

code game:
    ; Entry point - execution starts here
    call main();
    asm "rts";

    proc shutdown() -> long {
        // Restore all hardware state
        ReleaseSystem();        // Re-enable OS
        return 0;
    }
    
    proc main() -> long {
        TakeSystem();
        
        // Run game loop
        var running: long = TRUE;
        while (running) {
            // Game logic here
            running = FALSE;        // Exit when done
        }
        
        shutdown();             // Always restore!
        return 0;
    }
```

### Hardware Resources Controlled
When you call `TakeSystem()`, you gain control of:

| Resource | Purpose | Saved By |
|----------|---------|----------|
| **DMA Channels** | Bitplane, Blitter, Copper DMA | DMACON register |
| **Blitter** | Bitwise operations on memory | OwnBlitter() |
| **Copper** | Coprocessor for display lists | COP1LC register |
| **Interrupts** | Hardware and software interrupts | INTENA/INTREQ |
| **Timer** | CIA-A timer interrupt | CIAAICR |
| **Graphics Base** | graphics.library functions | OpenLibrary() |

### Complete Example: Game Template
```has
extern func TakeSystem() -> long;
extern func ReleaseSystem() -> long;

const TRUE = 1;
const FALSE = 0;

data game_state:
    is_running = 1
    frame_count = 0

code game:
    ; Entry point - execution starts here
    call main();
    asm "rts";

    proc update_frame() -> long {
        // Game logic per frame
        return 0;
    }
    
    proc render() -> long {
        // Render graphics
        return 0;
    }
    
    proc game_loop() -> long {
        while (is_running) {
            update_frame();
            render();
        }
        return 0;
    }
    
    proc main() -> long {
        // Take control from OS
        TakeSystem();
        
        // Run game
        game_loop();
        
        // Always restore, even if error
        ReleaseSystem();
        
        return 0;
    }
```

### Critical Rules

✓ **DO:**
- Always call `ReleaseSystem()` before exit
- Save system state before modification
- Use `Forbid()` to disable multitasking
- Use `Disable()` to disable interrupts

✗ **DON'T:**
- Forget to release system (hangs Amiga)
- Access OS functions after `TakeSystem()` without `Permit()` first
- Modify memory without checking bounds
- Leave interrupts disabled too long

### Library Integration
```has
// Link with takeover.o and graphics library
// vlink -belf game.o takeover.o graphics.o -o game.exe

extern func TakeSystem() -> long;   // From takeover.o
extern func ReleaseSystem() -> long; // From takeover.o

code app:
    proc main() -> long {
        TakeSystem();
        // Your game code
        ReleaseSystem();
        return 0;
    }
```

### Millisecond Delays with WaitMs()

For precise timing independent of VBlank or display state, use the `WaitMs()` function from `lib/timer.s`:

```has
extern func WaitMs(ms: int) -> void;

code timing:
    proc wait_one_second() -> void {
        WaitMs(1000);  ; Wait 1000 milliseconds
    }
    
    proc animation_loop() -> void {
        for frame = 0 to 60 {
            render_frame();
            WaitMs(16);   ; ~60 FPS at 16ms per frame
        }
    }
```

#### How WaitMs Works

`WaitMs(ms)` performs a busy-wait using CIA-A Timer A in one-shot mode, driven by the E-clock (709379 Hz on PAL). The delay is accurate regardless of DMA or display state:

- Accurate to within a few CIA clock cycles (~1.4 microseconds)
- Non-blocking: other interrupts (keyboard, music) continue to work
- Safe to use alongside `lib/ptplayer.s` music playback (uses CIA-B, not CIA-A)
- Handles delays up to 90ms per load; longer waits are chained internally

#### Timing Comparisons

| Method | Accuracy | Display-Dependent | Interrupt-Safe | Notes |
|--------|----------|------------------|-----------------|-------|
| **WaitMs()** | E-clock (~1.4µs) | No | Yes | Minimal CPU use |
| **WaitVBlank()** | ~20ms (PAL 50Hz) | Yes | Yes | Display-synchronized |
| **Spin loop** | CPU-dependent | No | Blocks interrupts | Inefficient |

Use **WaitMs()** for frame-rate timing or sub-second delays; use **WaitVBlank()** for synchronizing with display updates.

#### Example: Millisecond Pulse

```has
extern func WaitMs(ms: int) -> void;

code timing:
    proc pulse_led(count: int) -> void {
        for i = 0 to count {
            write_led(1);     ; Turn on
            WaitMs(500);      ; On for 500ms
            write_led(0);     ; Turn off
            WaitMs(500);      ; Off for 500ms
        }
    }
```

**Note:** `lib/timer.s` is automatically linked when the HAS compiler detects a `WaitMs` call. No manual library inclusion is required.

### Runtime CPU Detection with GetCPUType()

For games that support multiple Amiga models, detect the CPU at runtime and enable 68020-specific features dynamically:

```has
extern func GetCPUType() -> long;

const CPUTYPE_68000  = 0;
const CPUTYPE_68010  = 1;
const CPUTYPE_68020  = 2;
const CPUTYPE_68030  = 3;
const CPUTYPE_68040  = 4;
const CPUTYPE_68060  = 6;

code main:
    proc optimize_for_cpu() -> int {
        var cpu: long = GetCPUType();
        if (cpu >= CPUTYPE_68020) {
            return setup_fast_path();  ; 68020+ specific code
        } else {
            return setup_baseline();   ; Fallback for 68000
        }
    }
```

#### Function Signature

```
GetCPUType() -> long
```

- **Returns:** CPU type constant (CPUTYPE_68000 through CPUTYPE_68060)
- **Interrupts:** Safe to call at any time
- **Implementation:** Queries Exec library `AttnFlags` and translates to HAS constants

#### Supported CPU Types

- `CPUTYPE_68000`: Original 68000
- `CPUTYPE_68010`: 68010
- `CPUTYPE_68020`: 68020
- `CPUTYPE_68030`: 68030
- `CPUTYPE_68040`: 68040
- `CPUTYPE_68060`: 68060

Unknown CPUs are reported as their closest lower type.

#### Example: Feature Gating

```has
extern func GetCPUType() -> long;
extern func fast_multiply(a: long, b: long) -> long;
extern func slow_multiply(a: long, b: long) -> long;

const CPUTYPE_68000  = 0;
const CPUTYPE_68020  = 2;

code features:
    proc multiply(a: long, b: long) -> long {
        var cpu: long = GetCPUType();
        if (cpu >= CPUTYPE_68020) {
            return fast_multiply(a, b);   ; Native 32-bit muls.l
        } else {
            return slow_multiply(a, b);   ; 16-bit sequence
        }
    }
```

See [examples/cpu_detection.has](../examples/cpu_detection.has) for a complete example.

---

## Compilation

### Basic Compilation
```bash
# Compile .has to assembly
python -m hasc.cli example.has -o out.s

# With code generation
python -m hasc.cli example.has --generate generator.py -o out.s

# Skip validation
python -m hasc.cli example.has --no-validate -o out.s

# Emit debug annotations (source line comments)
python -m hasc.cli example.has --annotate -o out.s

# Explicitly enable build statistics comments (default)
python -m hasc.cli example.has --asm-stats -o out.s

# Disable build statistics comments
python -m hasc.cli example.has --no-asm-stats -o out.s
```

Generated assembly always starts with a HAS preamble comment (version/date).
By default, a `HAS Build Statistics` comment block is emitted immediately after
the preamble; use `--no-asm-stats` to disable that block.

### Debug Output: Annotated Assembly

The `--annotate` flag emits debug comments into generated assembly, helpful for understanding the compiler's output without affecting generated instructions:

```bash
python -m hasc.cli example.has --annotate -o out.s
```

**Output Example:**

Without `--annotate`:
```asm
    move.l d0,d1
    add.l #42,d1
```

With `--annotate`:
```asm
    ; L5: var result: long = input;
    move.l d0,d1
    ; L6: result = result + 42;
    add.l #42,d1
    ; end for
```

**Features:**
- Emits `; L{n}: <source line>` comments before most statements
- Adds `; end for`, `; end while`, `; end repeat` markers after loop ends
- Zero effect on generated instructions or program behavior
- Fully opt-in: off by default

**Known Limitation:** With `#include` directives, source line numbers may not align perfectly with quoted text (cosmetic only; compiled program behavior is unaffected).

**Use Cases:**
- Debugging unexpected codegen output
- Understanding compiler optimizations
- Teaching/learning HAS compilation
- Correlating assembly with HAS source during performance analysis

### CPU Targets and Assembler Flags

HAS defaults to Motorola 68000 output. The opt-in 68020 target enables advanced
instruction-selection optimizations for indexed addressing, arithmetic operations,
and sign extension. It does not change HAS syntax, data layout, ABI, calling
convention, alignment, or pointer size. All code compiles identically on both
targets; only the generated instructions differ.

```bash
# Default: 68000 baseline (100% compatible with original 68000/68010 hardware)
python -m hasc.cli example.has -o out-68000.s
vasmm68k_mot -m68000 -Fhunkexe -o out-68000.o out-68000.s

# Opt in: 68020 optimizations (requires 68020+ CPU)
python -m hasc.cli example.has --cpu 68020 -o out-68020.s
vasmm68k_mot -m68020 -Fhunkexe -o out-68020.o out-68020.s
```

#### 68020 Instruction Selection Optimizations

Only `68000` and `68020` are accepted by `--cpu`. When compiling for 68020, the following optimizations are applied:

##### Scaled Indexed Addressing (Phases 0–2)

Dynamic array, typed-pointer, struct-array, two-dimensional, and address-of paths
may use scaled `.l` indexes (`*2`, `*4`, or `*8`) where legal:

- **Phase 0 (Scaled `.l` indexes):** Basic scaled indexes (`a0,d1.l*2`)
- **Phase 1 (Full-extension displacements):** Out-of-range displacements up to ±32KB
  (e.g., `1000(a0,d1.l*4)` instead of separate `add.l` arithmetic)
- **Phase 2 (`.w` index sizing):** Compile-time-constant indexes in 16-bit range emit
  `.w`-sized indexes (e.g., `4(a0,d1.w*8)`) for smaller operands

Constant indexes remain direct offsets. Unsupported strides and byte indexing remain
unscaled. The default `--cpu 68000` output is completely unaffected.

##### Struct Field Displacement Folding

Struct-array member access folds field offsets directly into indexed-addressing operands
for 68020, eliminating separate arithmetic instructions. This applies to arbitrary struct
sizes (not just 2/4/8 bytes).

Example (`--cpu 68020` only):
```has
struct Enemy {
    x: word;
    y: word;
    health: byte;  ; offset +4
}

data enemies[100];

proc check() -> int {
    var i: int = 5;
    if (enemies[i].health < 10) {  ; Folds offset 4 into indexed operand
        return -1;
    }
    return 0;
}
```

Generates (68020):
```asm
move.b 4(a0,d1.l*sizeof(Enemy)),d0  ; Offset folded directly
```

##### 32-Bit Multiply/Divide/Modulo (Phase 4)

On `--cpu 68020`, `*`, `/`, `%` operators on `int`/`long` operands now natively
use `muls.l` (multiply) or `divsl.l` (divide/modulo):

```has
code math:
    proc calc() -> long {
        var a: long = 1000000;
        var b: long = 2000000;
        var result: long = a * b;      ; Uses muls.l (native 32-bit)
        var quotient: long = a / b;    ; Uses divsl.l
        var remainder: long = a % b;   ; Uses divsl.l + remainder extraction
        return result;
    }
```

**Behavior Change:** The 16-bit constant restriction is lifted on 68020 only:

- **68000 (default):** Multiply/divide constants must fit `-32768..32767` (16-bit range)
- **68020:** Full 32-bit constants and runtime operands supported natively

This is a genuine capability upgrade, not just a speed optimization.

##### Unsigned Multiply/Divide/Modulo (Phase 5.1)

The unsigned instruction forms are emitted when every non-literal operand is a
local or parameter declared `u8`/`u16`/`u32`/`UBYTE`/`UWORD`/`ULONG`, and at
least one operand is such a value. A non-negative integer literal is
signedness-neutral and does not block the unsigned path. Every other type -
including `q16` (a *signed* fixed-point format), `float`, `ptr`/`APTR`, `bool`,
pointer types like `int*`, struct types, and globals - stays on the signed
lowering.

```has
code math:
    proc scale(a: u32, b: u32) -> u32 {
        return a * b;      ; 68020: mulu.l   68000: mulu.w (no ext.l)
    }

    proc split(a: u32, b: u32) -> u32 {
        return a / b;      ; 68020: divul.l  68000: divu.w + andi.l #$FFFF
    }
```

What actually changes numerically differs per target:

- **`--cpu 68020`:** `divul.l` is a real fix - it removes the signed-32-bit
  ceiling, so `u32` dividends above `$7FFFFFFF` compute correctly. `mulu.l` is
  **not** a numeric fix: the 32x32 -> 32 single-destination forms
  `MULS.L <ea>,Dn` and `MULU.L <ea>,Dn` produce bit-identical products and
  differ only in the V flag, which HAS does not consume.
- **`--cpu 68000`:** both are real fixes at word width - `muls.w` sign-extends
  a word operand such as `50000` to `-15536`, whereas `mulu.w` treats it as
  `50000`. The constant operand-range check for that path becomes the unsigned
  `0..65535` range instead of the signed `-32768..32767` range.

> **68000 16-bit ceiling warning:** `divu.w` on the 68000 is a 32/16 -> 16:16
> divide, so the `split` example above is only correct while the quotient fits
> 16 bits (`a / b <= 65535`). On quotient overflow the 68000 does **not** trap:
> `DIVU.W`/`DIVS.W` raise an exception only on divide-by-zero. Overflow simply
> sets the V flag and leaves the destination register **unchanged**, so the
> following `andi.l #$FFFF` masks the untouched dividend and the procedure
> silently returns a wrong value. Use `--cpu 68020` (`divul.l`, full 32-bit
> quotient) when the quotient can exceed 65535.

Mixed signed/unsigned operands deliberately keep the signed lowering, so a
negative value is never reinterpreted as a large unsigned number. See
`examples/cpu68020_unsigned_muldiv.has` and
[OPERATORS.md](OPERATORS.md#unsigned-multiplydividemodulo).

##### Sign Extension Optimization (Phase 4)

On `--cpu 68020`, signed byte-to-long sign extension uses the single-instruction
`extb.l` instead of the 68000 two-instruction `ext.w`+`ext.l` sequence:

```has
code signed_ops:
    proc load_byte() -> long {
        var b: i8 = -5;
        return b;  ; Uses single "extb.l" on 68020, two instructions on 68000
    }
```

The same signed-byte code compiles successfully on both targets; only the
instruction count differs.

#### Important Notes

- Do **not** assemble 68020 output with `-m68000`; scaled instructions are not valid
  for 68000/68010 hardware
- Memory-indirect addressing and additional 68020 optimizations remain deferred
- All 68020 optimizations are strictly transparent: the generated program produces
  identical results on both targets

### Output
The compiler generates Motorola assembly compatible with `vasm`. Select the
assembler CPU flag to match the compiler target:

```asm
; Generated assembly excerpt
    section .data
counter:
    dc.l 100

    section .code
    proc add:
        link a6,#0
        move.l 8(a6),d0      ; param a
        add.l 12(a6),d0      ; param b
        unlk a6
        rts
```

### Building with vasm/vlink
```bash
# One-liner using provided build script
./scripts/build.sh out.s out.o out.exe

# Manual assembly and linking
vasm -Felf -m68000 out.s -o out.o
vlink -belf out.o -o out.exe
```

---

## Best Practices

### 1. Use Meaningful Names
```has
; Good
proc calculate_factorial(n: long) -> long {
    var result: long = 1;
    for i = 2 to n {
        result = result * i;
    }
    return result;
}

; Avoid
proc calc(a: long) -> long {
    var r: long = 1;
    for i = 2 to a {
        r = r * i;
    }
    return r;
}
```

### 2. Organize Code Logically
```has
// Group related procedures together
code math_lib:
    proc add(a: long, b: long) -> long { return a + b; }
    proc sub(a: long, b: long) -> long { return a - b; }
    proc mul(a: long, b: long) -> long { return a * b; }

// Separate data from code
data constants:
    PI_APPROX = 314159
    TAU_APPROX = 628318
```

### 3. Use Forward Declarations for Complex Logic
```has
code structured:
    func process_data(input: long*) -> long;
    func validate_input(data: long) -> long;
    func handle_error(code: long) -> long;
    
    proc main() -> long {
        var input[100];
        if (validate_input(input[0])) {
            return process_data(&input[0]);
        } else {
            return handle_error(1);
        }
    }
    
    proc process_data(input: long*) -> long {
        // Implementation
        return 0;
    }
    
    // ... more implementations
```

### 4. Leverage Register Allocation
```has
code optimized:
    // For frequently-called functions, hint register parameters
    proc critical_path(__reg(d0) a: long, __reg(d1) b: long) -> long {
        return a + b;
    }
```

### 5. Test with Examples
```bash
# Create simple test file
cat > test_add.has << 'EOF'
code test:
    proc add(a: long, b: long) -> long {
        return a + b;
    }
    proc main() -> long {
        return add(5, 3);
    }
EOF

# Compile and verify
python -m hasc.cli test_add.has -o test.s
./scripts/build.sh test.s test.o test.exe
```

---

## Quick Reference: Feature Checklist

- [x] **Basic Types** - byte, word, long, ptr
- [x] **Variables** - local, global, constants
- [x] **Arrays** - 1D, 2D, with initialization
- [x] **Pointers** - address-of, dereference, arithmetic
- [x] **Procedures** - definition, parameters, return values
- [x] **Control Flow** - if/else, loops, break/continue
- [x] **Operators** - arithmetic, logical, bitwise
- [x] **Advanced** - macros, @python, inline asm
- [x] **Directives** - #warning, #error, #pragma
- [x] **External Integration** - extern func, code generation

---

## Troubleshooting

### Compilation Errors
```bash
# Check syntax
python -m hasc.cli program.has --no-validate -o test.s

# Enable parser debugging (modify parser.py)
# Lark(..., debug=True)

# Check generated assembly
cat out.s | head -50
```

### Common Issues

**"Unknown variable"** - Declare with `var` keyword in procedure
**"Type mismatch"** - Use explicit casts or correct types
**"Register overflow"** - Use fewer temporaries or split expressions
**"Undefined function"** - Use `func` forward declaration before use

---

## Additional Resources

- [README.md](../README.md) - Feature overview and project entry points
- [examples/](../examples/) - 80+ working examples
- [hasc/ast.py](../hasc/ast.py) - Complete type system
- [hasc/codegen.py](../hasc/codegen.py) - Code generation patterns
- [.github/copilot-instructions.md](../.github/copilot-instructions.md) - Architecture guide
