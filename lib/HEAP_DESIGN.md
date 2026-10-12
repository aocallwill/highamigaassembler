# Heap Memory Manager - Design Document

## Executive Summary

The heap memory allocator for Amiga 68000 targets is a compact first-fit scanner
over a fixed internal buffer with 8-byte headers and no operating-system
dependency. This design supports bare-metal use and keeps allocation behavior
visible to HAS programs.

The buffer defaults to `10*1024` bytes and is allocated in the `bss_c` section, so it uses CHIP
RAM. Projects may override the size when assembling `lib/heap.s` with
`-D HEAP_MEMORY=<bytes>`; `scripts/build_game.sh` also accepts `HEAP_MEMORY` and passes it only
to that library. Block lengths use a 32-bit word count, so the allocator does not impose a
16-bit length ceiling. Practical limits are available CHIP RAM and the assembly/link format.

## Design Decision: Custom vs. Kickstart

### Kickstart `AllocMem`/`FreeMem` Tradeoffs

1. Requires proper Exec library initialization
2. Complex calling conventions and ABI compliance
3. Exception handling needed for memory exhaustion
4. Dependencies on DOS/Workbench for real systems
5. Makes project less portable (not bare-metal friendly)
6. Overkill for simple allocation patterns

### Custom Allocator Tradeoffs

1. **Portability**: Works bare-metal, emulators, any 68000 environment
2. **Educational**: Clear algorithm visible to users
3. **Control**: Optimization for specific patterns
4. **Minimal dependencies**: Pure assembly, no OS calls
5. **Transparency**: Users can understand every operation
6. **Customizable**: Easy to modify for specific needs

## Algorithm: First-Fit Scan with Coalescing

### Allocation Strategy

```
Walk heap from start:
  - Skip occupied blocks
  - Take first free block with enough words
  - Split if the remainder can still hold an 8-byte header and payload
  - Return payload pointer (header + 8)
```

**Why First-Fit?**
- Simple, small, predictable
- Works well for the project’s allocation patterns

### Deallocation Strategy

```
Mark block free:
  - Coalesce forward with following free blocks
  - Find predecessor by scanning from heap_start, then coalesce backward
```

**Coalescing Benefits:**
- Reduces fragmentation
- Restores larger blocks when neighbors free

## Data Structure: Linear Blocks

### Block Metadata (8 bytes per block)

```
Offset +0.l: length in words (payload only)
Offset +4.l: status (0 = free, 1 = occupied)

Payload follows immediately
End marker: 8-byte header with length=0 marks heap end
```

### Why So Small?

1. Uses full-width lengths without pointers in headers
2. Works with fixed internal buffer and sequential scan
3. Simplifies splitting/coalescing logic

### Memory Overhead

| Component | Bytes | Notes |
|-----------|-------|-------|
| Per block header | 8 | Fixed overhead |
| Min allocation | 2 payload bytes (1 word) |
| Overhead % | ~3% for 256-byte allocation |

## Fragmentation Management

### Block Splitting Example

```
Before: [Free: 512 words]
Request: 200 words (400 bytes)

After split:
[Alloc: 200w + 8-byte header] [Free: 308w]
(split only if the tail can hold a 4-word header and payload)
```

### Coalescing Example

```
State: [Alloc 128w][Free 64w][Free 32w]

Free(alloc block) → mark free, then merge both following blocks. The result is
232 words: 128 + 64 + 32 payload words plus two reclaimed 4-word headers.
```

## API Design

### Minimal Core (3 functions)

1. **HeapInit() → void**
  - One-time setup; uses internal heap buffer

2. **HeapAlloc(size_words: long) → d0: address**
  - The longword argument is passed on the stack and specifies 16-bit words
  - Returns 0 on failure

3. **HeapFree(address: ptr) → void**
  - The pointer argument is passed on the stack
  - Safe with NULL/0
  - Address must come from HeapAlloc

### Convention Choices

- **Parameters on stack**: HAS external-call convention
- **Return in d0**: Primary results in d0
- **No exceptions**: Return 0 on failure (simple error handling)

## Performance Characteristics

### Time Complexity

| Operation  | Best | Average | Worst |
|------------|------|---------|-------|
| HeapAlloc  | O(1) | O(n)    | O(n)  |
| HeapFree   | O(1) | O(n)    | O(n)  |
| Coalesce   | O(1) | O(n)    | O(n)  |

Where n = number of blocks scanned (free + used)

### Typical Behavior

- **Few allocations**: ~O(1) - hits first block quickly
- **After many frees**: Degrades with fragmentation
- **With coalescing**: Keeps free list manageable

### Space Complexity

- **Allocated blocks**: O(n) + 8 bytes header per block
- **Free/used blocks**: Same header format; no extra pointers
- **Total overhead**: 8n bytes (where n = number of blocks)

## Implementation Highlights

### Key Features

1. **In-band metadata**: Headers stored in heap, not separate
2. **Full-width fields**: Longword length and longword status
3. **Sequential scan**: No explicit free list
4. **End marker**: Zero-length header terminates heap walk

### Edge Cases Handled

- NULL pointer to `HeapFree` is silently ignored.
- `HeapAlloc` rejects requests of zero words or less. Callers convert byte
  counts to words with `(bytes + 1) / 2`.
- Allocation larger than available memory returns `0`.
- Multiple adjacent free blocks are coalesced forward and backward.
- An empty heap is initialized as one free block plus an end marker.

## Testing Strategy

### Verification Cases

1. **Single allocation**: Allocate and free one block
2. **Multiple allocations**: Several blocks of different sizes
3. **Fragmentation**: Allocate/free pattern creating holes
4. **Coalescing**: Verify free blocks merge correctly
5. **Edge cases**: One-word request, NULL pointer, allocation failure

## Integration with High Assembler

### Linking

```bash
# Compile High Assembler source
python3 -m hasc.cli myprogram.has -o myprogram.s

# Assemble the program and heap as separate objects
vasmm68k_mot -Fhunk -devpac -opt-allbra -I lib myprogram.s -o myprogram.o
vasmm68k_mot -Fhunk -devpac -opt-allbra -I lib lib/heap.s -o heap.o

# Link
vlink -bamigahunk myprogram.o heap.o -o myprogram.exe
```

### Usage in .has Files

```has
extern func HeapInit();
extern func HeapAlloc(size_words: long) -> ptr;
extern func HeapFree(ptr: ptr);

code myapp:
  proc main() -> int {
    HeapInit();
    var buffer: ptr = HeapAlloc(128);   ; 256 bytes
    if (buffer != 0) {
      HeapFree(buffer);
    }
    return 0;
  }
```

## Future Enhancements

### Short Term

1. **realloc()**: Resize existing allocations
2. **calloc()**: Allocate and zero-fill
3. **Alignment options**: Wider-than-word alignment if needed

### Medium Term

1. **Power-of-2 buckets**: Fast path for common sizes
2. **Bitmap allocator**: O(1) allocation for small blocks
3. **Debug mode**: Track allocations for leak detection

### Long Term

1. **Virtual memory**: Demand paging on memory-tight systems
2. **Garbage collection**: Automatic memory management
3. **Pool allocator**: Fixed-size object pools for performance

## References & Sources

- Motorola 68000 Reference Manual
- "The C Programming Language" - malloc implementation (Kernighan & Ritchie)
- "Memory Allocators 101" - standard allocation algorithms
- Amiga Developer CDN - calling conventions and ABI

## Design Properties

- **Simplicity**: First-fit allocation with adjacent-block coalescing.
- **Portability**: No external runtime dependencies.
- **Transparency**: In-band metadata and linear scans are directly inspectable.
- **Performance**: Linear behavior is intended for heaps with a modest block count.
