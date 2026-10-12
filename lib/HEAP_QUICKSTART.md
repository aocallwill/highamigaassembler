# Heap Memory Manager - Quick Start Guide (current heap.s)

## Files

- **lib/heap.s** - Core heap allocator implementation (68000 assembly)
- **lib/HEAP_README.md** - Complete API reference and usage documentation
- **lib/HEAP_DESIGN.md** - Design decisions and architecture details

## Quick Usage

### 1. Initialize Heap

The current heap uses an internal buffer defined in heap.s. No arguments are required.
It reserves 10 KiB by default in CHIP RAM. To change the size for a direct vasm build, pass
`-D HEAP_MEMORY=<bytes>` while assembling `lib/heap.s`:

```bash
vasmm68k_mot -Fhunk -devpac -I lib -D HEAP_MEMORY=65536 -o heap.o lib/heap.s
```

For game builds, set the environment variable instead:

```bash
HEAP_MEMORY=65536 ./scripts/build_game.sh examples/games/robots/robots.has
```

The build helper passes this define only to `heap.s`; the generated HAS source and other
libraries are unchanged. Because the heap lives in `bss_c`, its size comes from CHIP RAM.
Block lengths are stored as 32-bit word counts, so there is no 128 KiB metadata ceiling.
Available CHIP RAM, runtime demand, and fragmentation determine the practical heap size.

```asm
; In your startup code:
jsr HeapInit
```

### 2. Allocate Memory (size in words)

```asm
move.l #128,-(sp)           ; stack argument: 128 words = 256 bytes
jsr HeapAlloc
addq.l #4,sp
; d0 now contains address (or 0 if failed)
```

### 3. Use Memory

```asm
move.l d0,a0                ; a0 = allocated address
move.l #0x12345678,(a0)     ; Write to memory
```

### 4. Free Memory

```asm
move.l d0,-(sp)             ; stack argument: address to free
jsr HeapFree
addq.l #4,sp                ; safe when the argument is 0
```

## Integration Steps

### Step 1: Compile and Assemble

```bash
python -m hasc.cli myprogram.has -o myprogram.s
vasmm68k_mot -Fhunk -devpac -opt-allbra -I lib myprogram.s -o myprogram.o
vasmm68k_mot -Fhunk -devpac -opt-allbra -I lib lib/heap.s -o heap.o
vlink -bamigahunk myprogram.o heap.o -o myprogram.exe
```

### Step 2: Declare Functions in HAS

In your `.has` code, declare the external functions and call them normally. HAS
emits the stack-based argument sequence:

```has
extern func HeapInit();
extern func HeapAlloc(size_words: long) -> ptr;
extern func HeapFree(ptr: ptr);

code myapp:
    proc test_malloc() -> int {
        HeapInit();
        var buffer: ptr = HeapAlloc(128);
        if (buffer != 0) {
            HeapFree(buffer);
        }
        return 0;
    }
```

## Common Patterns

### Array Allocation

```asm
; Allocate array of 100 integers (400 bytes => 200 words)
move.l #200,-(sp)
jsr HeapAlloc
addq.l #4,sp
move.l d0,array_base

; Access element at index i:
move.l i,d0
asl.l #2,d0                 ; Multiply by 4
add.l array_base,d0         ; d0 = &array[i]
```

### Linked List Node

```asm
; Allocate node (8 bytes data + 8 bytes pointers = 16 bytes => 8 words)
move.l #8,-(sp)
jsr HeapAlloc
addq.l #4,sp
move.l d0,node_ptr

; Write data
move.l #0xCAFE,(node_ptr)
move.l #0xBEEF,4(node_ptr)

; Initialize links
move.l #0,8(node_ptr)       ; next = NULL
move.l #0,12(node_ptr)      ; prev = NULL
```

### Safe Free

```asm
; Always check before freeing
cmp.l #0,ptr                ; Check if ptr is not NULL
beq skip_free
move.l ptr,-(sp)
jsr HeapFree
addq.l #4,sp
skip_free:
```

## Allocation Sizes

| Requested (words) | Allocated (words) | Overhead (bytes) |
|-------------------|-------------------|------------------|
| 1                 | 1                 | 8                |
| 128 (256B)        | 128               | 8                |
| 512 (1KB)         | 512               | 8                |
| 2048 (4KB)        | 2048              | 8                |

**Note:** Each header is 8 bytes; requests are measured in 16-bit words.

## Performance Tips

1. **Batch allocations**: Allocate once, use multiple times (reduces fragmentation)
2. **Free in reverse-ish order**: Helps keep larger blocks contiguous
3. **Use fixed-size pools**: For frequent allocations of same size
4. **Check for NULL**: Always check HeapAlloc return value

## Debugging

### Validate Allocations

```asm
; Write known pattern
move.l #0xDEADBEEF,(ptr)

; Later, verify
cmp.l #0xDEADBEEF,(ptr)
bne memory_corrupted
```

## Known Limitations

- No realloc() - can't resize existing blocks
- No alignment control beyond word alignment
- Single heap - fixed internal buffer
- First-fit scan only

## Next Steps

1. Review **HEAP_README.md** for complete API documentation
2. Read **HEAP_DESIGN.md** for architecture and design decisions
3. Link **lib/heap.s** with your project using the separate-object workflow above

## Support

For issues or questions:
- Check API documentation in HEAP_README.md
- See architecture details in HEAP_DESIGN.md
