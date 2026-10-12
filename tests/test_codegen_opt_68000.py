"""Regression tests for 68000 codegen optimization plan (allocator, RMW, strength-reduce, induction)."""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hasc import codegen as has_codegen
from hasc import parser as has_parser
from hasc import validator as has_validator
from hasc.target import CpuTarget, TargetSpec

TARGET_68000 = TargetSpec.for_cpu(CpuTarget.M68000)
TARGET_68020 = TargetSpec.for_cpu(CpuTarget.M68020)


def compile_src(src: str, target=None) -> str:
    mod = has_parser.parse(src)
    val = has_validator.Validator(mod)
    val.validate()
    val.apply_resolutions()
    cg = has_codegen.CodeGen(mod, target) if target else has_codegen.CodeGen(mod)
    return cg.gen()


def proc_body(asm: str, proc_name: str) -> str:
    lines = asm.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip() == f"{proc_name}:"), None)
    if start is None:
        raise ValueError(f"Procedure '{proc_name}' not found in assembly")
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if re.match(r'^\w+:$', stripped) and i > 0 and lines[i - 1].strip() == "":
            end = i - 1
            break
    return "\n".join(lines[start:end])


NESTED_SRC = """
code main:
    proc nest() -> int {
        var a: int = 1;
        var b: int = 2;
        var c: int = 3;
        var d: int = 4;
        var e: int = 5;
        a = (b + c) * (d + e);
        return a;
    }
"""


class TestAllocatorPreserve:
    def test_nested_binop_preserves_in_high_reg(self):
        body = proc_body(compile_src(NESTED_SRC), "nest")
        assert re.search(r"move\.l\s+d0,d[3-6]\s+;\s*preserve left operand", body)
        assert "preserve left operand" in body
        # Prefer register preserve over stack when d3-d6 are free
        assert not re.search(r"move\.l\s+d0,-\(a7\)\s+;\s*preserve left operand", body)

    def test_nested_binop_both_cpus(self):
        for target in (TARGET_68000, TARGET_68020):
            body = proc_body(compile_src(NESTED_SRC, target=target), "nest")
            assert re.search(r"preserve left operand", body)

    def test_lockreg_excludes_scratch(self):
        src = """
#pragma lockreg(d3);
code main:
    proc nest() -> int {
        var a: int = 1;
        var b: int = 2;
        var c: int = 3;
        var d: int = 4;
        var e: int = 5;
        a = (b + c) * (d + e);
        return a;
    }
"""
        body = proc_body(compile_src(src), "nest")
        assert not re.search(r"\bd3\b", body)


class TestCompoundRmw:
    def test_local_addq(self):
        src = """
code main:
    proc rmw() -> int {
        var x: int = 1;
        x += 3;
        return x;
    }
"""
        body = proc_body(compile_src(src), "rmw")
        assert re.search(r"addq\.l\s+#3,-\d+\(a[46]\)", body)
        # RMW must not load/op/store for the += itself (return may still load x).
        assert not re.search(
            r"move\.l\s+-\d+\(a[46]\),d0\s*\n\s*add(?:q)?\.l\s+",
            body,
        )

    def test_local_andi(self):
        src = """
code main:
    proc rmw() -> int {
        var x: int = 15;
        x &= 7;
        return x;
    }
"""
        body = proc_body(compile_src(src), "rmw")
        assert re.search(r"andi\.l\s+#7,-\d+\(a[46]\)", body)

    def test_global_addq(self):
        src = """
data globals:
    g.l = 0

code main:
    proc rmw() -> int {
        g += 2;
        return g;
    }
"""
        body = proc_body(compile_src(src), "rmw")
        assert re.search(r"addq\.l\s+#2,g", body)


class TestStrengthReduceMul:
    def test_mul_by_four(self):
        src = """
code main:
    proc mul4(x: int) -> int {
        return x * 4;
    }
"""
        body = proc_body(compile_src(src), "mul4")
        assert re.search(r"lsl\.l\s+#2,", body)
        assert "muls" not in body
        assert "mulu" not in body

    def test_mul_by_neg_two(self):
        src = """
code main:
    proc mulneg(x: int) -> int {
        return x * -2;
    }
"""
        body = proc_body(compile_src(src), "mulneg")
        assert re.search(r"lsl\.l\s+#1,", body)
        assert re.search(r"neg\.l\s+", body)
        assert "muls" not in body

    def test_const_times_var(self):
        src = """
code main:
    proc mul8(x: int) -> int {
        return 8 * x;
    }
"""
        body = proc_body(compile_src(src), "mul8")
        assert re.search(r"lsl\.l\s+#3,", body)
        assert "muls" not in body


class TestInductionReg:
    def test_for_keeps_induction_in_reg(self):
        src = """
code main:
    proc sumto(n: int) -> int {
        var sum: int = 0;
        var i: int;
        for i = 0 to n by 1 {
            sum += i;
        }
        return sum;
    }
"""
        body = proc_body(compile_src(src), "sumto")
        assert re.search(r"; for i kept in d[3-6]", body)
        assert re.search(r"addq\.l\s+#1,d[3-6]", body)
        # Per-iteration compare must use the induction register, not a frame reload of i.
        assert re.search(r"cmp\.l\s+d1,d[3-6]", body)
        assert not re.search(r"move\.l\s+-\d+\(a[46]\),d0\s*\n\s*cmp\.l", body)
        # Peephole must NOT delete the live induction init (jetpac laser/meteor bug).
        assert re.search(r"move(?:q|\.l)\s+#0,d[3-6]", body)

    def test_for_body_incr_blocks_induction(self):
        src = """
code main:
    proc weird(n: int) -> int {
        var i: int;
        for i = 0 to n by 1 {
            i++;
        }
        return i;
    }
"""
        body = proc_body(compile_src(src), "weird")
        assert "kept in d" not in body

    def test_for_with_call_stays_memory_backed(self):
        src = """
code main:
    proc helper() -> int {
        return 1;
    }
    proc withcall(n: int) -> int {
        var i: int;
        var sum: int = 0;
        for i = 0 to n by 1 {
            sum += helper();
        }
        return sum;
    }
"""
        body = proc_body(compile_src(src), "withcall")
        assert "kept in d" not in body
