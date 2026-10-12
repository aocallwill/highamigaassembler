"""Basic unit tests for HAS compiler codegen functionality.

Tests cover:
- Stack frame management (link/unlk offsets)
- Calling conventions (parameter passing, return values)
- Basic arithmetic and variable operations
- Array access
- Pointer operations
- Function calls

Run with:
    python -m pytest tests/test_codegen_basic.py -v
"""

from collections import Counter
import re
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hasc import ast
from hasc import parser as has_parser
from hasc import codegen as has_codegen
from hasc import validator as has_validator
from hasc.target import CpuTarget, TargetSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compile_src(src: str, target=None) -> str:
    """Parse, validate, generate assembly for a HAS source string.
    Returns the full, peephole-optimized assembly text."""
    mod = has_parser.parse(src)
    validator = has_validator.Validator(mod)
    validator.validate()
    validator.apply_resolutions()
    cg = has_codegen.CodeGen(mod, target) if target else has_codegen.CodeGen(mod)
    return cg.gen()


def proc_body(asm: str, proc_name: str) -> str:
    """Extract just one procedure's assembly lines (from label to next proc)."""
    lines = asm.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip() == f"{proc_name}:"), None)
    if start is None:
        raise ValueError(f"Procedure '{proc_name}' not found in assembly")
    
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        # Next procedure is marked by blank line + label
        if re.match(r'^\w+:$', stripped) and i > 0 and lines[i - 1].strip() == "":
            end = i - 1
            break
    return "\n".join(lines[start:end])


def assert_contains(asm: str, pattern: str):
    """Assert that assembly text contains a regex pattern."""
    if not re.search(pattern, asm, re.MULTILINE):
        raise AssertionError(f"Assembly does not contain pattern:\n{pattern}\n\nGot:\n{asm}")


def assert_internal_branch_targets_defined(asm: str):
    """Assert that each branch target emitted in a generated procedure is defined."""
    label_definitions = re.findall(r'^\s*([.\w]+):', asm, re.MULTILINE)
    defined_labels = set(label_definitions)
    branch_targets = set(re.findall(r'^\s*b(?:ra|[a-z]{2})(?:\.[bwls])?\s+([.\w]+)', asm, re.MULTILINE))
    undefined_targets = branch_targets - defined_labels
    assert not undefined_targets, f"Undefined internal branch labels: {sorted(undefined_targets)}"
    duplicate_labels = sorted(label for label, count in Counter(label_definitions).items() if count > 1)
    assert not duplicate_labels, f"Duplicate internal labels: {duplicate_labels}"


# ---------------------------------------------------------------------------
# Tests: Stack Frames
# ---------------------------------------------------------------------------

class TestStackFrames:
    """Tests for link/unlk and local variable offset calculations."""
    
    def test_simple_return(self):
        """Simple procedure with return should compile."""
        src = """
code main:
    proc foo() -> int {
        return 42;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "foo")
        # Should have link/unlk
        assert_contains(body, r"link\s+a6")
        assert_contains(body, r"unlk\s+a6")
    
    def test_one_local_allocates_space(self):
        """One local variable should allocate space (including a4 save)."""
        src = """
code main:
    proc foo() -> int {
        var x: int = 0;
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "foo")
        # link allocates space for locals (actual amount depends on a4 frame opt)
        assert_contains(body, r"link")
    
    def test_multiple_locals_stack_growth(self):
        """Multiple locals should allocate space for all."""
        src = """
code main:
    proc foo() -> int {
        var x: int = 0;
        var y: int = 0;
        var z: byte = 0;
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "foo")
        # Multiple locals should use link with bigger negative offset
        assert_contains(body, r"link.*#-")


# ---------------------------------------------------------------------------
# Tests: Calling Conventions
# ---------------------------------------------------------------------------

class TestCallingConventions:
    """Tests for parameter passing and return values."""
    
    def test_return_immediate_value(self):
        """Return value should be placed in d0."""
        src = """
code main:
    proc foo() -> int {
        return 42;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "foo")
        # Should have d0 with return value
        assert_contains(body, r"d0")
    
    def test_one_parameter_on_stack(self):
        """Single parameter should be at +8(a6)."""
        src = """
code main:
    proc add_one(x: int) -> int {
        return x + 1;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "add_one")
        # Parameter x should be loaded from +8(a6)
        assert_contains(body, r"move\.l\s+8\(a6\)")
    
    def test_multiple_parameters(self):
        """Multiple parameters at +8, +12, +16, etc."""
        src = """
code main:
    proc add_three(x: int, y: int, z: int) -> int {
        return x + y + z;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "add_three")
        # x at +8(a6), y at +12(a6), z at +16(a6)
        assert_contains(body, r"8\(a6\)")
        assert_contains(body, r"12\(a6\)")
        assert_contains(body, r"16\(a6\)")


# ---------------------------------------------------------------------------
# Tests: Arithmetic Operations
# ---------------------------------------------------------------------------

class TestArithmetic:
    """Tests for basic arithmetic operations."""
    
    def test_addition(self):
        """Addition should emit add instruction."""
        src = """
code main:
    proc add_nums(a: int, b: int) -> int {
        return a + b;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "add_nums")
        assert_contains(body, r"add\.l")
    
    def test_subtraction(self):
        """Subtraction should emit sub instruction."""
        src = """
code main:
    proc sub_nums(a: int, b: int) -> int {
        return a - b;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "sub_nums")
        assert_contains(body, r"sub\.l")


# ---------------------------------------------------------------------------
# Tests: Variable Operations
# ---------------------------------------------------------------------------

class TestVariableOps:
    """Tests for storing and loading variables."""
    
    def test_assign_local_variable(self):
        """Assignment to local should use move to frame offset."""
        src = """
code main:
    proc assign_test() -> int {
        var x: int = 0;
        x = 42;
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "assign_test")
        # Should move 42 to x's frame offset
        assert_contains(body, r"move\.l\s+#42")
    
    def test_read_local_variable(self):
        """Reading a local should load from frame offset."""
        src = """
code main:
    proc read_test() -> int {
        var x: int = 42;
        var y: int = x;
        return y;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "read_test")
        # Should load from frame
        assert_contains(body, r"move\.l.*\(a6\)")


class TestIncDecOps:
    """Tests for increment/decrement code generation."""

    def test_statement_inc_dec_avoids_unused_result_loads(self):
        """Standalone ++/-- statements should not load into d0."""
        src = """
code main:
    proc incdec_stmt() -> int {
        var x: int = 1;
        x++;
        ++x;
        x--;
        --x;
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "incdec_stmt")

        # No value from x should be loaded to d0 for statement-only ++/--.
        assert not re.search(r"move\.l\s+-\d+\(a[46]\),d0", body)

        # Side effects still happen: two increments and two decrements.
        assert len(re.findall(r"add\.l\s+#1,-\d+\(a[46]\)", body)) == 2
        assert len(re.findall(r"sub\.l\s+#1,-\d+\(a[46]\)", body)) == 2

    def test_post_increment_expression_still_returns_old_value(self):
        """post-increment in expression context must still preserve old value."""
        src = """
code main:
    proc post_expr() -> int {
        var x: int = 7;
        var y: int = x++;
        return y;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "post_expr")
        # In expression context, post-increment still needs the old value.
        assert re.search(r"move\.l\s+-\d+\(a[46]\),d0", body)


# ---------------------------------------------------------------------------
# Tests: Array Access
# ---------------------------------------------------------------------------

class TestArrayOps:
    """Tests for array operations."""

    def test_struct_array_member_store_evaluates_rhs_before_address(self):
        """RHS calls and indexed reads must not clobber the pending store address."""
        src = """
code main:
    proc get_bonus() -> int {
        return 5;
    }

    proc update(index: int) -> int {
        destination[index].value = source[index].value + get_bonus();
        return destination[index].value;
    }

bss test_bss:
    struct source[4] { value.l }
    struct destination[4] { value.l }
        """
        asm = compile_src(src)
        body = proc_body(asm, "update")

        rhs_base = body.find("lea source,a0")
        rhs_call = body.find("jsr get_bonus")
        destination_base = body.find("lea destination,a0")
        final_store = body.find("move.l d0,(a0,d1.l)", destination_base)

        assert rhs_base != -1
        assert rhs_call != -1
        assert destination_base != -1
        assert final_store != -1
        assert rhs_base < destination_base
        assert rhs_call < destination_base
        assert destination_base < final_store
    
    def test_complex_index_store_preserves_left_index_operand(self):
        """Complex index stores should preserve partial index values across nested rhs eval."""
        src = """
code main:
    proc index_bug_regression() -> int {
        var pos: int = 20;
        var digit_idx: int = 1;
        var rem: int = 7;

        test_buf[pos + (3 - digit_idx)] = 48 + rem;
        return test_buf[pos + (3 - digit_idx)];
    }

bss test_bss:
    test_buf.b[64]
        """
        asm = compile_src(src)
        body = proc_body(asm, "index_bug_regression")

        # The top-level index expression must preserve d1 while evaluating (3 - digit_idx).
        # Prefer high Dn (d3-d6) via RegisterAllocator; fall back to stack when busy.
        assert (
            re.search(r"move\.l\s+d1,d[3-6]\s+;\s*preserve left operand", body)
            or re.search(r"move\.l\s+d1,-\(a7\)\s+;\s*preserve left operand", body)
        )
        assert (
            re.search(r"move\.l\s+d[3-6],d1\s+;\s*restore left operand", body)
            or re.search(r"move\.l\s+\(a7\)\+,d1\s+;\s*restore left operand", body)
        )
        assert_contains(body, r"move\.b\s+d0,\(a0,d1\.l\)")
        assert_contains(body, r"move\.b\s+\(a0,d1\.l\),d0")

        # Ensure preserve/restore brackets nested index evaluation before final add/store.
        store_anchor = body.find("lea test_buf,a0")
        preserve_m = re.search(
            r"move\.l\s+d1,(?:d[3-6]|-\(a7\))\s+;\s*preserve left operand",
            body[store_anchor:],
        )
        assert preserve_m is not None
        preserve_idx = store_anchor + preserve_m.start()
        sub_idx = body.find("sub.l d0,d2", preserve_idx)
        if sub_idx < 0:
            sub_idx = body.find("sub.l d1,d2", preserve_idx)
        restore_m = re.search(
            r"move\.l\s+(?:d[3-6]|\(a7\)\+),d1\s+;\s*restore left operand",
            body[sub_idx:],
        )
        assert restore_m is not None
        restore_idx = sub_idx + restore_m.start()
        add_idx = body.find("add.l d2,d1", restore_idx)
        store_idx = body.find("move.b d0,(a0,d1.l)", add_idx)

        assert store_anchor != -1
        assert preserve_idx != -1
        assert sub_idx != -1
        assert restore_idx != -1
        assert add_idx != -1
        assert store_idx != -1


# ---------------------------------------------------------------------------
# Tests: Pointers
# ---------------------------------------------------------------------------

class TestPointers:
    """Tests for pointer operations."""
    
    def test_address_of_local(self):
        """Address-of local should use lea."""
        src = """
code main:
    proc test_address() -> int {
        var x: int = 0;
        var p: int* = &x;
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "test_address")
        # lea for loading address
        assert_contains(body, r"lea")
    
    def test_pointer_dereference(self):
        """Pointer dereference should load through address register."""
        src = """
code main:
    proc test_deref(p: int*) -> int {
        return *p;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "test_deref")
        # move through address register
        assert_contains(body, r"move\.l.*\(\w+\)")


# ---------------------------------------------------------------------------
# Tests: Function Calls
# ---------------------------------------------------------------------------

class TestFunctionCalls:
    """Tests for function call code generation."""
    
    def test_call_no_args(self):
        """Call without arguments should emit jsr."""
        src = """
code main:
    proc foo() -> int { return 0; }
    proc bar() -> int { foo(); return 0; }
        """
        asm = compile_src(src)
        body = proc_body(asm, "bar")
        assert_contains(body, r"jsr\s+foo")
    
    def test_call_with_args(self):
        """Call with arguments should push them."""
        src = """
code main:
    proc add(a: int, b: int) -> int { return a + b; }
    proc caller() -> int { return add(1, 2); }
        """
        asm = compile_src(src)
        body = proc_body(asm, "caller")
        # Should push arguments and call
        assert_contains(body, r"jsr\s+add")


# ---------------------------------------------------------------------------
# Tests: Control Flow
# ---------------------------------------------------------------------------

class TestControlFlow:
    """Tests for loops and conditionals."""
    
    def test_while_loop(self):
        """While loop should emit branches."""
        src = """
code main:
    proc loop_test() -> int {
        var i: int = 0;
        while (i < 10) {
            i = i + 1;
        }
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "loop_test")
        # Should have branches for loop
        assert_contains(body, r"bra|beq|bne|blt|bgt|ble|bge")
    
    def test_if_statement(self):
        """If statement should have branches."""
        src = """
code main:
    proc if_test(x: int) -> int {
        if (x > 0) {
            return 1;
        } else {
            return 0;
        }
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "if_test")
        # Should have conditional branches
        assert_contains(body, r"ble|bgt|beq|bne")

    def test_if_with_value_and_logical_not(self):
        """Bare conditions test nonzero, and ! produces a logical boolean."""
        src = """
code main:
    proc condition_forms(cond: int) -> int {
        var result: int = 0;
        if (cond) {
            result = 1;
        }
        if (!cond) {
            result = 2;
        }
        return result;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "condition_forms")

        assert_contains(body, r"move\.l 8\(a6\),d0\s+beq endif")
        assert_contains(body, r"move\.l 8\(a6\),d0\s+seq d0\s+andi\.l #\$FF,d0\s+neg\.b d0")
        assert "not.l d0" not in body

    def test_else_if_and_defines_all_branch_targets(self):
        src = """
code main:
    proc test(a: byte, b: byte) -> void {
        if (a != 0) {
        } else if (a == 0 && b == 0) {
        }
    }
        """
        assert_internal_branch_targets_defined(proc_body(compile_src(src), "test"))

    def test_else_if_or_with_nested_and_defines_all_branch_targets(self):
        src = """
code main:
    proc test(a: byte, b: byte, c: byte) -> void {
        if (a != 0) {
        } else if (a == 0 || (b == 0 && c == 0)) {
        }
    }
        """
        body = proc_body(compile_src(src), "test")
        assert_internal_branch_targets_defined(body)
        assert len(re.findall(r'^\s*\.or_skip_\d+:', body, re.MULTILINE)) == 1

    def test_else_if_and_after_or_defines_all_branch_targets(self):
        src = """
code main:
    proc test(a: byte, b: byte, c: byte) -> void {
        if (a != 0 || b != 0) {
        } else if (b == 0 && c == 0) {
        }
    }
        """
        assert_internal_branch_targets_defined(proc_body(compile_src(src), "test"))

    def test_nested_boolean_value_expression_defines_all_branch_targets(self):
        src = """
code main:
    proc test(a: byte, b: byte, c: byte, d: byte) -> int {
        return a != 0 && (b != 0 || (c != 0 && d != 0));
    }
        """
        for cpu in CpuTarget:
            body = proc_body(compile_src(src, TargetSpec.for_cpu(cpu)), "test")
            assert_internal_branch_targets_defined(body)
            assert_contains(body, r"beq\.w \.and_false_\d+")
            assert_contains(body, r"bne\.w \.or_true_\d+")

    def test_do_while_nested_boolean_defines_all_branch_targets(self):
        src = """
code main:
    proc test(a: byte, b: byte, c: byte) -> void {
        do {
        } while (a != 0 && (b != 0 || c != 0));
    }
        """
        for cpu in CpuTarget:
            body = proc_body(compile_src(src, TargetSpec.for_cpu(cpu)), "test")
            assert_internal_branch_targets_defined(body)

    def test_while_nested_boolean_defines_all_branch_targets(self):
        src = """
code main:
    proc test(a: byte, b: byte, c: byte, d: byte) -> void {
        while (a != 0 || (b != 0 && (c != 0 || d != 0))) {
        }
    }
        """
        for cpu in CpuTarget:
            body = proc_body(compile_src(src, TargetSpec.for_cpu(cpu)), "test")
            assert_internal_branch_targets_defined(body)


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
