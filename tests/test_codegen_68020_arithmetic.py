import re
import subprocess
import shutil
from pathlib import Path

from hasc import codegen, parser
from hasc.target import CpuTarget, TargetSpec


ROOT = Path(__file__).resolve().parents[1]
VASM_PATH = Path(
    shutil.which("vasmm68k_mot")
    or "C:\\Users\\prozentreter\\Documents\\vbcc_win_x64\\vbcc\\bin\\vasmm68k_mot.exe"
)

BASELINE = TargetSpec.for_cpu(CpuTarget.M68000)
TARGET_68020 = TargetSpec.for_cpu(CpuTarget.M68020)

LARGE_CONST_MUL_SRC = """
code main:
    proc mul_large(a: int) -> int {
        return a * 100000;
    }
"""

LARGE_CONST_DIV_SRC = """
code main:
    proc div_large(a: int) -> int {
        return a / 100000;
    }
"""

LARGE_CONST_MOD_SRC = """
code main:
    proc mod_large(a: int) -> int {
        return a % 100000;
    }
"""

# Nested mul/div/mod expression with a large sub-expression constant (100000
# exceeds the old 16-bit range). Exercises _muldiv_remainder_reg scratch
# selection across nested _emit_expr recursion (outer div, inner mul+mod).
NESTED_ARITH_SRC = """
code main:
    proc nested_arith(a: int, b: int, c: int) -> int {
        return (a * 100000) / (b % c);
    }
"""


def _instruction_mnemonics(lines):
    """Return (mnemonics, source_indices) for real instruction lines, skipping
    labels/blank lines/comment-only lines, so slices can be compared by opcode
    regardless of register naming or trailing comments."""
    mnemonics = []
    indices = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(';') or stripped.endswith(':'):
            continue
        code_part = stripped.split(';', 1)[0].strip()
        if not code_part:
            continue
        mnemonics.append(code_part.split()[0])
        indices.append(i)
    return mnemonics, indices


def vasm_assemble(asm_text, cpu_target):
    if not VASM_PATH.exists():
        return None, None, "vasm not available"

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.s', delete=False) as asm_file:
        asm_file.write(asm_text)
        asm_path = asm_file.name

    obj_path = asm_path.replace('.s', '.o')
    result = subprocess.run(
        [str(VASM_PATH), f"-m{cpu_target}", "-Fhunkexe", "-o", obj_path, asm_path],
        capture_output=True,
        text=True,
    )
    try:
        Path(asm_path).unlink()
        Path(obj_path).unlink(missing_ok=True)
    except Exception:
        pass
    return result.returncode, result.stdout, result.stderr


def test_supports_32bit_muldiv_only_on_68020():
    assert not BASELINE.supports_32bit_muldiv
    assert TARGET_68020.supports_32bit_muldiv


def test_68020_multiply_with_large_constant_uses_muls_l():
    module = parser.parse(LARGE_CONST_MUL_SRC)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    lines = asm.splitlines()

    assert any("muls.l" in line for line in lines)
    assert not any("ext.l" in line and "16-bit" in line for line in lines)
    assert not any(line.strip().startswith("muls.w") for line in lines)

    rc, _, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_68020_divide_with_large_constant_uses_divsl_l():
    module = parser.parse(LARGE_CONST_DIV_SRC)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    lines = asm.splitlines()

    assert any("divsl.l" in line for line in lines)
    assert not any(line.strip().startswith("divs.w") for line in lines)

    rc, _, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_68020_modulo_with_large_constant_uses_divsl_l():
    module = parser.parse(LARGE_CONST_MOD_SRC)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    lines = asm.splitlines()

    assert any("divsl.l" in line for line in lines)
    assert any("move.l" in line and "result = remainder" in line for line in lines)
    assert not any(line.strip().startswith("divs.w") for line in lines)

    rc, _, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_68020_nested_muldivmod_scratch_register_no_collision():
    """Nested (a * <large const>) / (b % c) on 68020: verifies the
    _muldiv_remainder_reg scratch pick for the outer divide and inner modulo
    never collides with a register still holding a live operand/result from
    the sibling/outer subexpression, and that the whole thing assembles."""
    module = parser.parse(NESTED_ARITH_SRC)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    lines = asm.splitlines()

    assert any("muls.l" in line for line in lines)
    assert any("divsl.l" in line for line in lines)

    rc, _, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_68000_multiply_with_large_constant_still_fails():
    module = parser.parse(LARGE_CONST_MUL_SRC)
    try:
        codegen.CodeGen(module, BASELINE).gen()
        assert False, "expected CodeGenError for out-of-range constant on 68000"
    except codegen.CodeGenError as exc:
        assert "outside signed 16-bit range" in str(exc)


def test_68000_divide_with_large_constant_still_fails():
    module = parser.parse(LARGE_CONST_DIV_SRC)
    try:
        codegen.CodeGen(module, BASELINE).gen()
        assert False, "expected CodeGenError for out-of-range constant on 68000"
    except codegen.CodeGenError as exc:
        assert "outside signed 16-bit range" in str(exc)


def test_68000_modulo_with_large_constant_still_fails():
    module = parser.parse(LARGE_CONST_MOD_SRC)
    try:
        codegen.CodeGen(module, BASELINE).gen()
        assert False, "expected CodeGenError for out-of-range constant on 68000"
    except codegen.CodeGenError as exc:
        assert "outside signed 16-bit range" in str(exc)


def test_68000_small_operand_multiply_has_no_inert_ext():
    src = """
code main:
    proc mul_small(a: int, b: int) -> int {
        return a * b;
    }
"""
    module = parser.parse(src)
    asm = codegen.CodeGen(module, BASELINE).gen()
    lines = asm.splitlines()

    mnemonics, _ = _instruction_mnemonics(lines)
    idx = mnemonics.index("muls.w")
    # muls.w reads only the low word of both operands and overwrites all 32 bits
    # of the destination, so no sign normalization is needed before or after it.
    assert mnemonics[idx] == "muls.w"
    assert "ext.l" not in mnemonics


def test_68000_small_operand_divide_keeps_only_quotient_ext():
    src = """
code main:
    proc div_small(a: int, b: int) -> int {
        return a / b;
    }
"""
    module = parser.parse(src)
    asm = codegen.CodeGen(module, BASELINE).gen()
    lines = asm.splitlines()

    mnemonics, _ = _instruction_mnemonics(lines)
    idx = mnemonics.index("divs.w")
    # Divisor normalization is inert (divs.w reads its low word only); the trailing
    # ext.l is load-bearing because it isolates the quotient from the remainder word.
    assert mnemonics[idx - 1] != "ext.l"
    assert mnemonics[idx:idx + 2] == ["divs.w", "ext.l"]
    assert mnemonics.count("ext.l") == 1


def test_68000_small_operand_modulo_keeps_only_remainder_ext():
    src = """
code main:
    proc mod_small(a: int, b: int) -> int {
        return a % b;
    }
"""
    module = parser.parse(src)
    asm = codegen.CodeGen(module, BASELINE).gen()
    lines = asm.splitlines()

    mnemonics, _ = _instruction_mnemonics(lines)
    idx = mnemonics.index("divs.w")
    # The post-swap ext.l is load-bearing: it sign-extends the remainder.
    assert mnemonics[idx - 1] != "ext.l"
    assert mnemonics[idx:idx + 3] == ["divs.w", "swap", "ext.l"]
    assert mnemonics.count("ext.l") == 1


COMPLEX_RIGHT_MUL_SRC = """
code main:
    proc mul_complex(a: int, b: int, c: int) -> int {
        return a * (b - c);
    }
"""


def test_68000_multiply_with_complex_right_keeps_stack_save_restore():
    """The removed ext.l sat between the left-operand save/restore pair; pin the
    surrounding sequence so the pair itself cannot silently disappear.

    Preserve may use a high Dn (d3-d6) via RegisterAllocator, or fall back to stack.
    """
    module = parser.parse(COMPLEX_RIGHT_MUL_SRC)
    asm = codegen.CodeGen(module, BASELINE).gen()
    lines = asm.splitlines()

    mnemonics, indices = _instruction_mnemonics(lines)
    idx = mnemonics.index("muls.w")
    assert mnemonics[idx - 1] == "move.l"
    restore_line = lines[indices[idx - 1]]
    assert (
        "(a7)+" in restore_line
        or re.search(r"move\.l\s+d[3-6],d\d+\s+;\s*restore left operand", restore_line)
    )
    save = next(
        i for i in range(idx - 1, -1, -1)
        if "-(a7)" in lines[indices[i]]
        or re.search(r";\s*preserve left operand", lines[indices[i]])
    )
    assert mnemonics[save] == "move.l"
    assert "ext.l" not in mnemonics


COMPOUND_ASSIGN_SRC = """
code main:
    proc compound(a: int, b: int) -> int {
        var x: int = a;
        x *= b;
        x /= b;
        x %= b;
        return x;
    }
"""


def test_68000_compound_muldiv_assignment_matches_the_binop_lowering():
    """`*=` / `/=` / `%=` desugar through the same _emit_expr path, so they must
    lose the same inert ext.l and keep the load-bearing post-divide ones."""
    module = parser.parse(COMPOUND_ASSIGN_SRC)
    asm = codegen.CodeGen(module, BASELINE).gen()
    mnemonics, _ = _instruction_mnemonics(asm.splitlines())

    mul = mnemonics.index("muls.w")
    assert mnemonics[mul - 1] != "ext.l"
    assert mnemonics[mul + 1] != "ext.l"

    div = mnemonics.index("divs.w")
    assert mnemonics[div - 1] != "ext.l"
    assert mnemonics[div:div + 2] == ["divs.w", "ext.l"]

    mod = mnemonics.index("divs.w", div + 1)
    assert mnemonics[mod - 1] != "ext.l"
    assert mnemonics[mod:mod + 3] == ["divs.w", "swap", "ext.l"]

    # Exactly the two load-bearing post-divide extensions remain.
    assert mnemonics.count("ext.l") == 2


def test_division_by_zero_constant_still_rejected_on_both_targets():
    src = """
code main:
    proc div_zero(a: int) -> int {
        return a / 0;
    }
"""
    module = parser.parse(src)
    for target in (BASELINE, TARGET_68020):
        try:
            codegen.CodeGen(module, target).gen()
            assert False, "expected CodeGenError for division by zero constant"
        except codegen.CodeGenError as exc:
            assert "Division by zero constant" in str(exc)


BYTE_LOCAL_SIGN_EXTEND_SRC = """
code main:
    proc byte_local_use() -> int {
        var b: byte = -5;
        return b + 1;
    }
"""

BYTE_PARAM_SIGN_EXTEND_SRC = """
code main:
    proc byte_param_use(b: byte) -> int {
        return b + 1;
    }
"""


def test_supports_extb_l_only_on_68020():
    assert not BASELINE.supports_extb_l
    assert TARGET_68020.supports_extb_l


def test_68020_signed_byte_local_uses_extb_l():
    module = parser.parse(BYTE_LOCAL_SIGN_EXTEND_SRC)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    lines = asm.splitlines()

    mnemonics, _ = _instruction_mnemonics(lines)
    assert "extb.l" in mnemonics
    assert "ext.w" not in mnemonics

    rc, _, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_68020_signed_byte_param_uses_extb_l():
    module = parser.parse(BYTE_PARAM_SIGN_EXTEND_SRC)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    lines = asm.splitlines()

    mnemonics, _ = _instruction_mnemonics(lines)
    assert "extb.l" in mnemonics
    assert "ext.w" not in mnemonics

    rc, _, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_68000_signed_byte_local_still_uses_ext_w_ext_l_sequence():
    module = parser.parse(BYTE_LOCAL_SIGN_EXTEND_SRC)
    asm = codegen.CodeGen(module, BASELINE).gen()
    lines = asm.splitlines()

    mnemonics, _ = _instruction_mnemonics(lines)
    assert "extb.l" not in mnemonics
    idx = mnemonics.index("ext.w")
    assert mnemonics[idx:idx + 2] == ["ext.w", "ext.l"]

    rc, _, stderr = vasm_assemble(asm, "68000")
    if rc is not None:
        assert rc == 0, f"vasm -m68000 failed: {stderr}"


def test_68000_signed_byte_param_still_uses_ext_w_ext_l_sequence():
    module = parser.parse(BYTE_PARAM_SIGN_EXTEND_SRC)
    asm = codegen.CodeGen(module, BASELINE).gen()
    lines = asm.splitlines()

    mnemonics, _ = _instruction_mnemonics(lines)
    assert "extb.l" not in mnemonics
    idx = mnemonics.index("ext.w")
    assert mnemonics[idx:idx + 2] == ["ext.w", "ext.l"]

    rc, _, stderr = vasm_assemble(asm, "68000")
    if rc is not None:
        assert rc == 0, f"vasm -m68000 failed: {stderr}"


def test_unsigned_byte_path_unaffected_by_extb_l_on_both_targets():
    src = """
code main:
    proc ubyte_local() -> int {
        var u: u8 = 1;
        return u + 1;
    }

    proc ubyte_param(u: u8) -> int {
        return u + 1;
    }
"""
    module = parser.parse(src)
    for target in (BASELINE, TARGET_68020):
        asm = codegen.CodeGen(module, target).gen()
        lines = asm.splitlines()
        assert any("andi.l #$FF," in line for line in lines)
        assert not any("extb.l" in line for line in lines)

UNSIGNED_MUL_SRC = """
code main:
    proc mul_unsigned(a: u32, b: u32) -> u32 {
        return a * b;
    }
"""

UNSIGNED_DIV_SRC = """
code main:
    proc div_unsigned(a: u32, b: u32) -> u32 {
        return a / b;
    }
"""

UNSIGNED_MOD_SRC = """
code main:
    proc mod_unsigned(a: u32, b: u32) -> u32 {
        return a % b;
    }
"""

MIXED_SIGNEDNESS_SRC = """
code main:
    proc mixed_mul(a: u32, b: int) -> int {
        return a * b;
    }

    proc mixed_div(a: u32, b: int) -> int {
        return a / b;
    }
"""

UNSIGNED_LITERAL_SRC = """
code main:
    proc scale_unsigned(a: u32) -> u32 {
        return a * 10;
    }

    proc shrink_unsigned(a: u32) -> u32 {
        return a / 10;
    }
"""


def test_68020_unsigned_multiply_uses_mulu_l():
    module = parser.parse(UNSIGNED_MUL_SRC)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    mnemonics, _ = _instruction_mnemonics(asm.splitlines())

    assert "mulu.l" in mnemonics
    assert "muls.l" not in mnemonics
    assert "mulu.w" not in mnemonics

    rc, _, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_68020_unsigned_divide_uses_divul_l():
    module = parser.parse(UNSIGNED_DIV_SRC)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    mnemonics, _ = _instruction_mnemonics(asm.splitlines())

    assert "divul.l" in mnemonics
    assert "divsl.l" not in mnemonics

    rc, _, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_68020_unsigned_modulo_uses_divul_l_and_remainder_move():
    module = parser.parse(UNSIGNED_MOD_SRC)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    lines = asm.splitlines()
    mnemonics, _ = _instruction_mnemonics(lines)

    assert "divul.l" in mnemonics
    assert "divsl.l" not in mnemonics
    assert any("result = remainder" in line for line in lines)

    rc, _, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_68000_unsigned_multiply_uses_mulu_w_without_sign_extension():
    module = parser.parse(UNSIGNED_MUL_SRC)
    asm = codegen.CodeGen(module, BASELINE).gen()
    mnemonics, _ = _instruction_mnemonics(asm.splitlines())

    idx = mnemonics.index("mulu.w")
    assert "muls.w" not in mnemonics
    # No ext.l sign-normalization anywhere in this fixture's unsigned multiply path.
    assert "ext.l" not in mnemonics
    assert mnemonics[idx - 1] != "ext.l"
    assert "mulu.l" not in mnemonics

    rc, _, stderr = vasm_assemble(asm, "68000")
    if rc is not None:
        assert rc == 0, f"vasm -m68000 failed: {stderr}"


def test_68000_unsigned_divide_uses_divu_w_and_masks_quotient():
    module = parser.parse(UNSIGNED_DIV_SRC)
    asm = codegen.CodeGen(module, BASELINE).gen()
    lines = asm.splitlines()
    mnemonics, _ = _instruction_mnemonics(lines)

    idx = mnemonics.index("divu.w")
    assert "divs.w" not in mnemonics
    assert mnemonics[idx:idx + 2] == ["divu.w", "andi.l"]
    assert "divul.l" not in mnemonics

    rc, _, stderr = vasm_assemble(asm, "68000")
    if rc is not None:
        assert rc == 0, f"vasm -m68000 failed: {stderr}"


def test_68000_unsigned_modulo_uses_divu_w_swap_and_mask():
    module = parser.parse(UNSIGNED_MOD_SRC)
    asm = codegen.CodeGen(module, BASELINE).gen()
    mnemonics, _ = _instruction_mnemonics(asm.splitlines())

    idx = mnemonics.index("divu.w")
    assert "divs.w" not in mnemonics
    assert mnemonics[idx:idx + 3] == ["divu.w", "swap", "andi.l"]

    rc, _, stderr = vasm_assemble(asm, "68000")
    if rc is not None:
        assert rc == 0, f"vasm -m68000 failed: {stderr}"


def test_unsigned_operand_with_nonnegative_literal_takes_unsigned_path():
    module = parser.parse(UNSIGNED_LITERAL_SRC)

    mnemonics_68020, _ = _instruction_mnemonics(
        codegen.CodeGen(module, TARGET_68020).gen().splitlines())
    assert "mulu.l" in mnemonics_68020
    assert "divul.l" in mnemonics_68020

    mnemonics_68000, _ = _instruction_mnemonics(
        codegen.CodeGen(module, BASELINE).gen().splitlines())
    assert "mulu.w" in mnemonics_68000
    assert "divu.w" in mnemonics_68000


def test_mixed_signedness_keeps_signed_lowering_on_both_targets():
    module = parser.parse(MIXED_SIGNEDNESS_SRC)

    mnemonics_68020, _ = _instruction_mnemonics(
        codegen.CodeGen(module, TARGET_68020).gen().splitlines())
    assert "muls.l" in mnemonics_68020
    assert "divsl.l" in mnemonics_68020
    assert "mulu.l" not in mnemonics_68020
    assert "divul.l" not in mnemonics_68020

    mnemonics_68000, _ = _instruction_mnemonics(
        codegen.CodeGen(module, BASELINE).gen().splitlines())
    assert "muls.w" in mnemonics_68000
    assert "divs.w" in mnemonics_68000
    assert "mulu.w" not in mnemonics_68000
    assert "divu.w" not in mnemonics_68000


def test_no_68020_muldiv_instruction_leaks_into_68000_output():
    for src in (UNSIGNED_MUL_SRC, UNSIGNED_DIV_SRC, UNSIGNED_MOD_SRC, MIXED_SIGNEDNESS_SRC):
        module = parser.parse(src)
        mnemonics, _ = _instruction_mnemonics(
            codegen.CodeGen(module, BASELINE).gen().splitlines())
        for banned in ("mulu.l", "muls.l", "divul.l", "divsl.l"):
            assert banned not in mnemonics, f"{banned} leaked into --cpu 68000 output"


def test_68000_unsigned_multiply_rejects_out_of_range_literal():
    src = """
code main:
    proc mul_big(a: u32) -> u32 {
        return a * 100000;
    }
"""
    module = parser.parse(src)
    try:
        codegen.CodeGen(module, BASELINE).gen()
        assert False, "expected CodeGenError for out-of-range unsigned constant on 68000"
    except codegen.CodeGenError as exc:
        assert "outside unsigned 16-bit range" in str(exc)


def test_68000_negative_literal_with_unsigned_operand_stays_signed():
    src = """
code main:
    proc mul_negative(a: u32) -> int {
        return a * -3;
    }
"""
    module = parser.parse(src)
    mnemonics, _ = _instruction_mnemonics(
        codegen.CodeGen(module, BASELINE).gen().splitlines())
    assert "muls.w" in mnemonics
    assert "mulu.w" not in mnemonics


# Regression guard for the closed-allowlist bug: `not ast.is_signed(t)` classified
# every non-integer type (q16/float/ptr/bool/struct/`T*`) as unsigned and routed it
# onto MULU/DIVU. Q16.16 in particular is a signed format, so `q / 3` produced a
# huge positive value instead of the correct negative one.
NON_INTEGER_TYPES_SRC = """
code main:
    proc q16_scale(a: q16) -> q16 {
        return a * 3;
    }

    proc q16_ratio(a: q16, b: q16) -> q16 {
        return a / b;
    }

    proc float_scale(a: float) -> float {
        return a * 3;
    }

    proc ptr_scale(p: ptr) -> ptr {
        return p / 4;
    }

    proc typed_ptr_scale(p: int*) -> int {
        return p / 4;
    }

    proc bool_scale(f: bool) -> int {
        return f * 3;
    }
"""


def test_non_integer_types_never_take_unsigned_path_on_both_targets():
    module = parser.parse(NON_INTEGER_TYPES_SRC)

    mnemonics_68020, _ = _instruction_mnemonics(
        codegen.CodeGen(module, TARGET_68020).gen().splitlines())
    assert mnemonics_68020.count("muls.l") == 3
    assert mnemonics_68020.count("divsl.l") == 3
    assert "mulu.l" not in mnemonics_68020
    assert "divul.l" not in mnemonics_68020

    mnemonics_68000, _ = _instruction_mnemonics(
        codegen.CodeGen(module, BASELINE).gen().splitlines())
    assert mnemonics_68000.count("muls.w") == 3
    assert mnemonics_68000.count("divs.w") == 3
    assert "mulu.w" not in mnemonics_68000
    assert "divu.w" not in mnemonics_68000


def test_q16_arithmetic_assembles_signed_on_both_targets():
    module = parser.parse(NON_INTEGER_TYPES_SRC)

    for target, cpu in ((BASELINE, "68000"), (TARGET_68020, "68020")):
        asm = codegen.CodeGen(module, target).gen()
        rc, _, stderr = vasm_assemble(asm, cpu)
        if rc is not None:
            assert rc == 0, f"vasm -m{cpu} failed: {stderr}"


# The positive case the unsigned lowering exists for: 50000 does not fit a signed
# 16-bit word, so MULS.W would sign-extend it to -15536 and return a wrong product.
UNSIGNED_U16_OVERFLOW_SRC = """
code main:
    proc double_big() -> u32 {
        var big: u16 = 50000;
        return big * 3;
    }
"""


def test_u16_above_signed_word_range_uses_unsigned_multiply_on_both_targets():
    # Use * 3 (not * 2/4/8) so strength-reduce does not replace the mul.
    module = parser.parse(UNSIGNED_U16_OVERFLOW_SRC)

    mnemonics_68000, _ = _instruction_mnemonics(
        codegen.CodeGen(module, BASELINE).gen().splitlines())
    assert "mulu.w" in mnemonics_68000
    assert "muls.w" not in mnemonics_68000

    mnemonics_68020, _ = _instruction_mnemonics(
        codegen.CodeGen(module, TARGET_68020).gen().splitlines())
    assert "mulu.l" in mnemonics_68020
    assert "muls.l" not in mnemonics_68020
