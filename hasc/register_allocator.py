"""Register allocation helpers for 68000 assembly code generation.

``CodeGen`` owns one ``RegisterAllocator`` per module (constructed with
``#pragma lockreg`` locks) and ``reset()``s it at each procedure entry.
Expression lowering consults ``allocate_data`` / ``free`` for nested BinOp
temps so free ``d3``–``d6`` are preferred over ad-hoc ``-(a7)`` spills.

``d7`` remains reserved compiler-wide for ``dbra`` loop counters and is
managed exclusively by ``CodeGen._dbra_loop_enter`` / ``_dbra_loop_exit``
(and call-site save/restore when ``dbra_depth > 0``).
"""


class RegisterAllocator:
    """Tracks data/address register in-use sets with optional stack spilling.

    Intended 68000 conventions:

    Data Registers (d0-d7):
    - d0: Primary expression result, function return value
    - d1: Secondary operand, right-hand side of binary ops
    - d2: Tertiary temp (nested expressions)
    - d3-d6: Available for complex expressions
    - d7: Reserved for loop counters (dbra); never allocate as a general scratch

    Address Registers (a0-a6):
    - a0: Primary address register (array base, pointer operations)
    - a1-a2: Secondary address registers
    - a3-a5: Available for user code / future allocation
    - a6: Frame pointer (reserved by link/unlk)
    - a7: Stack pointer (reserved)

    Calling convention notes:
    - Caller-save in practice for HAS codegen scratches: d0-d2, a0-a1
    - d7 must be preserved across calls while a dbra loop is active (CodeGen)
    - AmigaOS callee-save expectations for handwritten asm still apply at the
      ABI boundary; this allocator does not emit prologue/epilogue saves.
    """

    def __init__(self, locked_regs=None):
        # Manage d0-d6; d7 reserved for loop counters
        self.data_regs = ['d0', 'd1', 'd2', 'd3', 'd4', 'd5', 'd6']
        self.addr_regs = ['a0', 'a1', 'a2']

        self.locked_regs = set(locked_regs) if locked_regs else set()
        self.data_regs = [r for r in self.data_regs if r not in self.locked_regs]
        self.addr_regs = [r for r in self.addr_regs if r not in self.locked_regs]

        self.data_in_use = set()
        self.addr_in_use = set()
        self.spilled_stack = []

    def mark_in_use(self, register):
        """Reserve a register already holding a live value (exclusion only)."""
        if register in self.data_regs:
            self.data_in_use.add(register)
        elif register in self.addr_regs:
            self.addr_in_use.add(register)

    def unmark(self, register):
        """Release a mark_in_use reservation without emitting restore code."""
        self.data_in_use.discard(register)
        self.addr_in_use.discard(register)

    def try_allocate_preserve(self):
        """Allocate a data register safe across nested hardcoded d0-d2 temps.

        Nested ``_emit_expr`` paths still default to d0/d1/d2, so a live value
        that must survive a nested evaluation can only live in d3-d6 (or on the
        stack). Returns ``(reg, [])`` or ``(None, [])`` when no high reg is free.
        """
        for reg in ('d6', 'd5', 'd4', 'd3'):
            if reg in self.data_regs and reg not in self.data_in_use:
                self.data_in_use.add(reg)
                return (reg, [])
        return (None, [])

    def allocate_data(self, preferred=None):
        """Allocate a data register. Returns (register, spilled_code)."""
        if preferred in self.data_regs and preferred not in self.data_in_use:
            self.data_in_use.add(preferred)
            return (preferred, [])

        for reg in self.data_regs:
            if reg not in self.data_in_use:
                self.data_in_use.add(reg)
                return (reg, [])

        to_spill = next((r for r in self.data_regs[1:] if r in self.data_in_use), self.data_regs[0])
        code = [f"    move.l {to_spill},-(a7)  ; spill {to_spill}"]
        self.spilled_stack.append(to_spill)
        self.data_in_use.remove(to_spill)
        return (to_spill, code)

    def allocate_addr(self, preferred=None):
        """Allocate an address register. Returns (register, spilled_code)."""
        if preferred in self.addr_regs and preferred not in self.addr_in_use:
            self.addr_in_use.add(preferred)
            return (preferred, [])

        for reg in self.addr_regs:
            if reg not in self.addr_in_use:
                self.addr_in_use.add(reg)
                return (reg, [])

        to_spill = self.addr_regs[0]
        code = [f"    move.l {to_spill},-(a7)  ; spill {to_spill}"]
        self.spilled_stack.append(to_spill)
        self.addr_in_use.remove(to_spill)
        return (to_spill, code)

    def free(self, register):
        """Free a register, making it available for reuse."""
        if register in self.data_in_use:
            self.data_in_use.remove(register)
        elif register in self.addr_in_use:
            self.addr_in_use.remove(register)

    def restore_spilled(self):
        """Generate code to restore most recently spilled register.
        Returns (register, restore_code)."""
        if not self.spilled_stack:
            return (None, [])

        reg = self.spilled_stack.pop()
        if reg.startswith('d'):
            self.data_in_use.add(reg)
        elif reg.startswith('a'):
            self.addr_in_use.add(reg)
        code = [f"    move.l (a7)+,{reg}  ; restore {reg}"]
        return (reg, code)

    def restore_spills_since(self, depth):
        """Restore spills pushed after ``depth`` (len of spilled_stack snapshot)."""
        code = []
        while len(self.spilled_stack) > depth:
            _, restore = self.restore_spilled()
            code.extend(restore)
        return code

    def save_context(self):
        """Save current allocation state (for nested contexts like function calls)."""
        return (set(self.data_in_use), set(self.addr_in_use), list(self.spilled_stack))

    def restore_context(self, state):
        """Restore allocation state."""
        self.data_in_use, self.addr_in_use, self.spilled_stack = state

    def reset(self):
        """Reset all allocations (for new procedure)."""
        self.data_in_use.clear()
        self.addr_in_use.clear()
        self.spilled_stack.clear()

    def assert_all_free(self, context=""):
        """Fail if any register remains allocated or spilled (end-of-proc check)."""
        if self.data_in_use or self.addr_in_use or self.spilled_stack:
            summary = self.get_allocation_summary()
            where = f" ({context})" if context else ""
            raise RuntimeError(f"Register allocator leak{where}: {summary}")

    def validate_usage(self, code_line, used_regs):
        """Validate that code doesn't use unallocated or conflicting registers."""
        warnings = []
        for reg in used_regs:
            if reg.startswith('d') and reg in self.data_regs:
                if reg not in self.data_in_use:
                    warnings.append(f"Warning: Using unallocated register {reg} in: {code_line}")
            elif reg.startswith('a') and reg in self.addr_regs:
                if reg not in self.addr_in_use:
                    warnings.append(f"Warning: Using unallocated register {reg} in: {code_line}")
        return warnings

    def get_allocation_summary(self):
        """Get human-readable summary of current allocations (for debugging)."""
        return {
            'data_in_use': sorted(self.data_in_use),
            'addr_in_use': sorted(self.addr_in_use),
            'spilled': self.spilled_stack.copy(),
            'data_available': [r for r in self.data_regs if r not in self.data_in_use],
            'addr_available': [r for r in self.addr_regs if r not in self.addr_in_use]
        }
