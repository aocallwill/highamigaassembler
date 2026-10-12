import re

from .target import DEFAULT_TARGET, TargetSpec


def peephole_optimize(lines, target: TargetSpec = DEFAULT_TARGET):
    """Multi-pass peephole optimizer with explicit CPU target plumbing.

    Target-specific rewrites remain disabled until indexed-address lowering is
    centralized and independently validated.
    
    Args:
        lines: List of assembly instruction strings.
        target: TargetSpec with CPU capabilities (currently unused but preserved for Phase 4+).
    """
    # NOTE: target parameter is preserved for Phase 4+ when target-specific rewrites
    # (e.g., avoiding certain shifts for 68020 scaled-operand forms) are implemented.
    # Currently all optimizations are target-neutral.
    optimized = lines
    changed = True
    passes = 0
    max_passes = 5  # Prevent infinite loops

    while changed and passes < max_passes:
        changed = False
        prev_len = len(optimized)
        
        # Apply optimization passes in sequence
        optimized = _eliminate_move_self(optimized)
        optimized = _eliminate_redundant_moves(optimized)
        optimized = _eliminate_redundant_lea(optimized)
        optimized = _eliminate_dead_stores(optimized)
        optimized = _optimize_immediate_ops(optimized)
        optimized = _fold_immediate_to_memory(optimized)
        optimized = _fold_clr_to_memory(optimized)
        optimized = _eliminate_clr_move(optimized)
        optimized = _optimize_move_chains(optimized)
        optimized = _eliminate_redundant_compare(optimized)
        optimized = _optimize_branch_to_branch(optimized)
        optimized = _fold_constant_shifts(optimized)
        optimized = _optimize_indexed_addressing(optimized)
        optimized = _fold_neg_one(optimized)
        optimized = _eliminate_tst_after_andi_neg(optimized)
        optimized = _eliminate_redundant_flag_test(optimized)
        optimized = _optimize_cmp_zero_to_tst(optimized)
        
        if len(optimized) < prev_len:
            changed = True
        passes += 1
    
    return optimized


def _eliminate_move_self(lines):
    """Remove move.x reg,reg (no-op)."""
    optimized = []
    for line in lines:
        base = line.split(';', 1)[0].rstrip()
        m = re.match(r"\s*move(\.[bwl])?\s+([da]\d+),\2$", base)
        if not m:
            optimized.append(line)
    return optimized


def _eliminate_redundant_moves(lines):
    """Remove obvious store-then-reload of the same dest into d0."""
    optimized = []
    i = 0
    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(';', 1)[0].rstrip()
            base2 = lines[i + 1].split(';', 1)[0].rstrip()
            m1 = re.match(r"\s*move(\.[bwl])\s+d0,(\S+)$", base1)
            if m1:
                suffix, dest = m1.groups()
                pattern = rf"\s*move{suffix}\s+{re.escape(dest)},d0$"
                if re.match(pattern, base2):
                    optimized.append(lines[i])
                    i += 2
                    continue
        optimized.append(lines[i])
        i += 1
    return optimized


def _eliminate_redundant_lea(lines):
    """Conservatively drop back-to-back identical LEA instructions.

    The previous, more aggressive caching version could keep stale address
    registers alive across complex instructions and led to bad pointers in
    some routines (e.g., explosions). This variant only removes an LEA when
    the immediately preceding instruction was the same LEA to the same
    register, which is safe and still trims obvious duplication.
    """
    optimized = []
    prev_match = None  # (address, reg)

    for line in lines:
        base = line.split(';', 1)[0].rstrip()
        m = re.match(r"\s*lea\s+(\S+),(a\d+)$", base)

        if m and prev_match == m.groups():
            # Skip exact duplicate LEA
            continue

        optimized.append(line)
        prev_match = m.groups() if m else None

    return optimized


def _eliminate_dead_stores(lines):
    """Remove stores that are overwritten before being read.

    Safety: Only consider register destinations (dN/aN). Memory destinations
    can have side effects (e.g., -(a7) stack pushes, (aN)+ autoincrement,
    hardware registers). Restricting to registers avoids corrupting the stack
    or I/O state.
    """
    optimized = []
    i = 0
    
    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(';', 1)[0].rstrip()
            base2 = lines[i + 1].split(';', 1)[0].rstrip()
            
            # Match: move.x src,dest followed by move.x src2,dest (same dest)
            # Safety: restrict dest to registers only
            m1 = re.match(r"\s*move(\.[bwl])\s+\S+,([da]\d+)$", base1)
            m2 = re.match(r"\s*move(\.[bwl])\s+\S+,([da]\d+)$", base2)
            
            if m1 and m2:
                suffix1, dest1 = m1.groups()
                suffix2, dest2 = m2.groups()
                source2 = base2.rsplit(',', 1)[0]
                
                # Same destination and size - first write is dead
                # The next MOVE may read the previous destination while forming
                # an effective address, e.g. move.l (a0,d1.l*4),d1.
                if (dest1 == dest2 and suffix1 == suffix2
                        and dest1 not in _extract_used_regs(source2)):
                    # Skip first move
                    i += 1
                    continue
        
        optimized.append(lines[i])
        i += 1
    
    return optimized


def _optimize_immediate_ops(lines):
    """Use ADDQ/SUBQ for small immediates (1-8), MOVEQ for small values."""
    optimized = []
    
    for line in lines:
        base = line.split(';', 1)[0].rstrip()
        comment = ';' + line.split(';', 1)[1] if ';' in line else ''
        
        # ADD.L #n,reg -> ADDQ.L #n,reg (n = 1-8)
        # Safety: restrict to data registers only to preserve CCR semantics
        m = re.match(r"(\s*)add\.l\s+#(\d+),(d\d+)$", base)
        if m:
            indent, val, reg = m.groups()
            n = int(val)
            if 1 <= n <= 8:
                optimized.append(f"{indent}addq.l #{n},{reg}{comment}")
                continue
        
        # SUB.L #n,reg -> SUBQ.L #n,reg (n = 1-8)
        # Safety: restrict to data registers only to preserve CCR semantics
        m = re.match(r"(\s*)sub\.l\s+#(\d+),(d\d+)$", base)
        if m:
            indent, val, reg = m.groups()
            n = int(val)
            if 1 <= n <= 8:
                optimized.append(f"{indent}subq.l #{n},{reg}{comment}")
                continue
        
        # MOVE.L #n,dN -> MOVEQ #n,dN (n = -128 to 127)
        m = re.match(r"(\s*)move\.l\s+#(-?\d+),(d\d+)$", base)
        if m:
            indent, val, reg = m.groups()
            n = int(val)
            if -128 <= n <= 127:
                optimized.append(f"{indent}moveq #{n},{reg}{comment}")
                continue
        
        optimized.append(line)
    
    return optimized


def _eliminate_clr_move(lines):
    """Remove CLR.L only when the next instruction fully overwrites the register.

    On 68000, MOVE.B and MOVE.W to a data register do not clear the upper bytes,
    so the CLR.L must be preserved for zero-extension patterns.
    """
    optimized = []
    i = 0
    
    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(';', 1)[0].rstrip()
            base2 = lines[i + 1].split(';', 1)[0].rstrip()
            
            # CLR.L dN followed by a full-width write to the same register.
            m1 = re.match(r"\s*clr\.l\s+(d\d+)$", base1)
            target_reg = m1.group(1) if m1 else None
            move_long = re.match(rf"\s*move\.l\s+\S+,{re.escape(target_reg)}$", base2) if target_reg else None
            moveq = re.match(rf"\s*moveq\s+#-?\d+,{re.escape(target_reg)}$", base2) if target_reg else None
            
            if m1 and (move_long or moveq):
                # The move will overwrite the CLR, so skip CLR
                i += 1
                continue
        
        optimized.append(lines[i])
        i += 1
    
    return optimized


def _optimize_move_chains(lines):
    """Optimize chains like move.l d0,d1; move.l d1,d2 -> move.l d0,d1; move.l d0,d2."""
    optimized = []
    i = 0
    
    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(';', 1)[0].rstrip()
            base2 = lines[i + 1].split(';', 1)[0].rstrip()
            
            m1 = re.match(r"(\s*)move(\.[bwl])\s+([da]\d+),([da]\d+)$", base1)
            m2 = re.match(r"(\s*)move(\.[bwl])\s+([da]\d+),([da]\d+)$", base2)
            
            if m1 and m2:
                indent1, size1, src1, dest1 = m1.groups()
                indent2, size2, src2, dest2 = m2.groups()
                
                # move.l d0,d1 followed by move.l d1,d2 (src2 == dest1)
                if src2 == dest1 and size1 == size2:
                    # Replace second move to use original source
                    optimized.append(lines[i])
                    optimized.append(f"{indent2}move{size2} {src1},{dest2}")
                    i += 2
                    continue
        
        optimized.append(lines[i])
        i += 1
    
    return optimized


def _eliminate_redundant_compare(lines):
    """Remove redundant comparisons in same basic block."""
    optimized = []
    last_cmp = None
    i = 0
    
    while i < len(lines):
        line = lines[i]
        base = line.split(';', 1)[0].rstrip()
        
        # Reset on control flow
        if _is_label(base) or _is_branch(base):
            last_cmp = None
            optimized.append(line)
            i += 1
            continue
        
        # Match CMP instruction
        m = re.match(r"\s*cmp(\.[bwl])?\s+(.+)$", base)
        if m:
            cmp_sig = m.group(2)
            if cmp_sig == last_cmp:
                # Skip redundant compare
                i += 1
                continue
            last_cmp = cmp_sig
            optimized.append(line)
            i += 1
            continue
        
        # Reset if operands are modified
        if last_cmp:
            modified = _extract_modified_regs(base)
            # Check if any register in comparison is modified
            for reg in modified:
                if reg in last_cmp:
                    last_cmp = None
                    break
        
        optimized.append(line)
        i += 1
    
    return optimized


def _is_label(line):
    """Check if line is a label."""
    return line and not line.startswith(' ') and ':' in line


def _is_branch(line):
    """Check if line is a branch, or any other control transfer (jsr/bsr) whose
    target can arbitrarily modify registers/flags - callers rely on this to
    reject such lines as a safe no-op "gap" instruction."""
    branch_ops = ['bra', 'beq', 'bne', 'blt', 'ble', 'bgt', 'bge', 
                  'blo', 'bls', 'bhi', 'bhs', 'bcc', 'bcs', 'bpl', 'bmi',
                  'jsr', 'bsr']
    for op in branch_ops:
        if f' {op} ' in line or f' {op}.' in line or line.strip().startswith(op):
            return True
    return 'rts' in line or 'rte' in line


def _extract_modified_regs(instruction):
    """Extract registers that are modified (written to) by instruction."""
    modified = set()
    
    # Match destination operand patterns
    # Format: op src,dest or op dest
    
    # Two-operand instructions: destination is after the LAST comma.
    # This must handle indexed addressing forms like "(a0,d1.l),d0" where
    # a naive first-comma split would incorrectly treat d1 as destination.
    m = re.match(r"\s*\w+(?:\.\w+)?\s+(.+)$", instruction)
    if m:
        operands = m.group(1).strip()
        if ',' in operands:
            dest = operands.rsplit(',', 1)[1].strip()
            if re.fullmatch(r"[da]\d+", dest):
                modified.add(dest)
                return modified
    
    # Single-operand instructions that modify
    single_ops = ['clr', 'neg', 'not', 'addq', 'subq', 'asl', 'asr', 'lsl', 'lsr', 'rol', 'ror']
    for op in single_ops:
        m = re.match(rf"\s*{op}(\.\w)?\s+([da]\d+)", instruction)
        if m:
            modified.add(m.group(2))
            break
    
    return modified

def _extract_used_regs(operand):
    """Extract registers that are used (read) in an operand.
    Examples:
        "5(a0)" -> {'a0'}
        "(a0)" -> {'a0'}
        "(a0,d1.w)" -> {'a0', 'd1'}
        "d0" -> set() (direct register, not part of addressing)
    """
    used = set()
    
    # Match indirect addressing modes: offset(reg), (reg), (reg,index)
    # Pattern: anything(reg) or (reg) or (reg,index)
    matches = re.findall(r'([da]\d+)', operand)
    for match in matches:
        used.add(match)
    
    return used

def _fold_constant_shifts(lines):
    """Fold constant shift operations: moveq #N,dX; lsl.l #M,dX -> moveq #(N<<M),dX"""
    optimized = []
    i = 0
    
    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(';', 1)[0].rstrip()
            base2 = lines[i + 1].split(';', 1)[0].rstrip()
            comment2 = ';' + lines[i + 1].split(';', 1)[1] if ';' in lines[i + 1] else ''
            
            # Match: moveq #N,dX followed by lsl.l #M,dX
            m1 = re.match(r"(\s*)moveq\s+#(-?\d+),(d\d+)$", base1)
            if m1:
                indent, value, reg = m1.groups()
                # Build pattern to match shift on same register
                m2 = re.match(rf"\s*lsl\.l\s+#(\d+),{re.escape(reg)}$", base2)
                
                if m2:
                    shift = int(m2.group(1))
                    result = int(value) << shift
                    
                    # If result fits in moveq range (-128 to 127), use moveq
                    if -128 <= result <= 127:
                        optimized.append(f"{indent}moveq #{result},{reg}{comment2}")
                    else:
                        # Use move.l for larger values
                        optimized.append(f"{indent}move.l #{result},{reg}{comment2}")
                    
                    i += 2
                    continue
        
        optimized.append(lines[i])
        i += 1
    
    return optimized


def _optimize_indexed_addressing(lines):
    """Optimize indexed addressing with zero offset.
    
    Patterns optimized:
    - move.x (aX,0.l),dY -> move.x (aX),dY
    - move.x dY,(aX,0.l) -> move.x dY,(aX)
    """
    optimized = []
    
    for line in lines:
        base = line.split(';', 1)[0].rstrip()
        comment = ';' + line.split(';', 1)[1] if ';' in line else ''
        
        # Match: move.x (aX,0.l),dY
        m = re.match(r"(\s*move(\.[bwl])?)\s+\((a\d+),0\.l\),(d\d+)$", base)
        if m:
            move_instr, suffix, areg, dreg = m.groups()
            optimized.append(f"{move_instr} ({areg}),{dreg}{comment}")
            continue
        
        # Match: move.x dY,(aX,0.l)
        m = re.match(r"(\s*move(\.[bwl])?)\s+(d\d+),\((a\d+),0\.l\)$", base)
        if m:
            move_instr, suffix, dreg, areg = m.groups()
            optimized.append(f"{move_instr} {dreg},({areg}){comment}")
            continue
        
        optimized.append(line)
    
    return optimized

def _optimize_branch_to_branch(lines):
    """
    Optimize pattern:
        cmp.l #0,d0
        bCC labelA       ; conditional branch
        bra labelB       ; unconditional branch
    labelA:
    
    Into:
        cmp.l #0,d0
        bINV_CC labelB   ; inverted conditional branch directly
    labelA:
    
    Where INV_CC is the inverted condition (e.g., bge->blt, blt->bge, etc.)
    while preserving any explicit branch size suffix such as .s.
    """
    optimized = []
    i = 0
    
    # Condition inversion map
    invert_map = {
        'beq': 'bne', 'bne': 'beq',
        'blt': 'bge', 'bge': 'blt',
        'bgt': 'ble', 'ble': 'bgt',
        'bcs': 'bcc', 'bcc': 'bcs',
        'bmi': 'bpl', 'bpl': 'bmi',
        'bvs': 'bvc', 'bvc': 'bvs'
    }
    
    while i < len(lines):
        # Look for pattern: conditional branch followed by unconditional branch followed by label
        if i + 2 < len(lines):
            line1 = lines[i].split(';', 1)[0].rstrip()
            line2 = lines[i + 1].split(';', 1)[0].rstrip()
            line3 = lines[i + 2].split(';', 1)[0].rstrip()
            
            # Match: b<cond>[.size] label1
            m1 = re.match(r"\s*(b[a-z]+)(\.[a-z]+)?\s+([._$A-Za-z]\w*)$", line1)
            # Match: bra[.size] label2
            m2 = re.match(r"\s*bra(\.[a-z]+)?\s+([._$A-Za-z]\w*)$", line2)
            # Match: label1:
            m3 = re.match(r"^([._$A-Za-z]\w*):$", line3)
            
            if m1 and m2 and m3:
                cond_branch = m1.group(1)
                cond_suffix = m1.group(2) or ""
                label1 = m1.group(3)
                label2 = m2.group(2)
                actual_label = m3.group(1)
                
                # Verify that label1 matches the actual label on line3
                if label1 == actual_label and cond_branch in invert_map:
                    # Keep explicit loop-continue branches intact. Rewriting
                    #   bCC <endif>; bra <forcont/while/...>; <endif>:
                    # into an inverted conditional removes the explicit
                    # continue jump, which makes continue-path control flow
                    # harder to reason about and has caused regressions.
                    if re.match(r"^(forcont|repeatcont|dowhilecont|while)\d+$", label2):
                        optimized.append(lines[i])
                        i += 1
                        continue

                    # Found the pattern! Replace with inverted conditional branch
                    inverted = invert_map[cond_branch]
                    
                    # Preserve comment from original line if present
                    comment = ""
                    if ';' in lines[i]:
                        comment = " ; " + lines[i].split(';', 1)[1].strip()
                    
                    optimized.append(f"    {inverted}{cond_suffix} {label2}{comment}")
                    # Skip the bra instruction
                    i += 1
                    # Keep the label
                    optimized.append(lines[i + 1])
                    i += 2
                    continue
        
        optimized.append(lines[i])
        i += 1
    
    return optimized

def _is_pure_reg_kill(instruction, reg):
    """True when ``instruction`` overwrites ``reg`` without reading it."""
    base = instruction.split(';', 1)[0].rstrip().strip()
    m = re.match(rf"(?:move(?:\.[bwl])?|moveq)\s+(\S+),\s*{re.escape(reg)}$", base)
    if m and not re.search(rf"\b{re.escape(reg)}\b", m.group(1)):
        return True
    if re.match(rf"(?:clr|ext|extb)(?:\.[bwl])?\s+{re.escape(reg)}$", base):
        return True
    return False


def _register_live_after(lines, start_idx, reg):
    """Conservative liveness: True if ``reg`` may be read after ``start_idx``.

    Labels and branches are treated as live (loop back-edges / unknown CFG).
    A pure kill of ``reg`` ends the scan as dead.
    """
    for j in range(start_idx, len(lines)):
        base = lines[j].split(';', 1)[0].rstrip()
        stripped = base.strip()
        if not stripped:
            continue
        if _is_label(base):
            return True
        if _is_branch(base):
            return True
        if re.search(rf"\b{re.escape(reg)}\b", stripped):
            if _is_pure_reg_kill(stripped, reg):
                return False
            return True
    return False


def _fold_immediate_to_memory(lines):
    """Fold patterns loading an immediate into a register followed by a store to memory.

    Patterns:
    - moveq #N,dX ; move.s dX,<ea>  -> move.s #N,<ea>
    - move.l #N,dX ; move.s dX,<ea> -> move.s #N,<ea>
    - One-gap variant: allow one intervening instruction that does not modify dX

    Safety:
    - Only folds when the store destination is not a register (i.e., memory EA).
    - Ensure gap instruction does not modify the source register.
    - Do **not** fold when dX remains live after the store (e.g. for-loop induction
      register init ``move #0,d6`` + ``move d6,frame`` then ``cmp d1,d6``).
    """
    optimized = []
    i = 0

    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(';', 1)[0].rstrip()
            base2 = lines[i + 1].split(';', 1)[0].rstrip()
            comment2 = ';' + lines[i + 1].split(';', 1)[1] if ';' in lines[i + 1] else ''

            m1 = re.match(r"(\s*)(moveq\s+#(-?\d+)|(move\.l\s+#(-?\d+))),\s*(d\d+)$", base1)
            if m1:
                indent = m1.group(1)
                val = m1.group(3) if m1.group(3) is not None else m1.group(5)
                reg = m1.group(6)

                # Adjacent case
                m2 = re.match(rf"\s*move(\.[bwl])\s+{re.escape(reg)},\s*(\S+)$", base2)
                if m2:
                    size = m2.group(1)
                    dest = m2.group(2)
                    if not re.match(r"[da]\d+$", dest):
                        # Keep Dn load when the register is still live after the store.
                        if not _register_live_after(lines, i + 2, reg):
                            optimized.append(f"{indent}move{size} #{val},{dest}{comment2}")
                            i += 2
                            continue

                # One-gap variant
                if i + 2 < len(lines):
                    base_mid = lines[i + 1].split(';', 1)[0].rstrip()
                    base3 = lines[i + 2].split(';', 1)[0].rstrip()
                    comment3 = ';' + lines[i + 2].split(';', 1)[1] if ';' in lines[i + 2] else ''

                    if not _is_label(base_mid) and not _is_branch(base_mid):
                        modified = _extract_modified_regs(base_mid)
                        if reg not in modified:
                            m3 = re.match(rf"\s*move(\.[bwl])\s+{re.escape(reg)},\s*(\S+)$", base3)
                            if m3:
                                size = m3.group(1)
                                dest = m3.group(2)
                                if not re.match(r"[da]\d+$", dest):
                                    # CRITICAL FIX: Check if middle instruction modifies registers used by dest
                                    dest_regs = _extract_used_regs(dest)
                                    if not any(dreg in modified for dreg in dest_regs):
                                        if not _register_live_after(lines, i + 3, reg):
                                            optimized.append(f"{indent}move{size} #{val},{dest}{comment3}")
                                            i += 3
                                            continue

        optimized.append(lines[i])
        i += 1

    return optimized

def _fold_clr_to_memory(lines):
    """Fold CLR followed by store from the cleared register into a single immediate #0 store.

    Patterns:
    - clr.s dX ; move.s dX,<ea> -> move.s #0,<ea>
    - One-gap variant: allow one intervening instruction that does not modify dX

    Safety:
    - Only folds when the store destination is not a register (i.e., memory EA).
    - Ensure gap instruction does not modify the source register.
    """
    optimized = []
    i = 0

    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(';', 1)[0].rstrip()
            base2 = lines[i + 1].split(';', 1)[0].rstrip()
            comment2 = ';' + lines[i + 1].split(';', 1)[1] if ';' in lines[i + 1] else ''

            m1 = re.match(r"(\s*)clr(\.[bwl])\s+(d\d+)$", base1)
            if m1:
                indent, _, reg = m1.groups()

                # Adjacent case
                m2 = re.match(rf"\s*move(\.[bwl])\s+{re.escape(reg)},\s*(\S+)$", base2)
                if m2:
                    size = m2.group(1)
                    dest = m2.group(2)
                    if not re.match(r"[da]\d+$", dest):
                        if not _register_live_after(lines, i + 2, reg):
                            optimized.append(f"{indent}move{size} #0,{dest}{comment2}")
                            i += 2
                            continue

                # One-gap variant
                if i + 2 < len(lines):
                    base_mid = lines[i + 1].split(';', 1)[0].rstrip()
                    base3 = lines[i + 2].split(';', 1)[0].rstrip()
                    comment3 = ';' + lines[i + 2].split(';', 1)[1] if ';' in lines[i + 2] else ''

                    if not _is_label(base_mid) and not _is_branch(base_mid):
                        modified = _extract_modified_regs(base_mid)
                        # CRITICAL FIX: Don't optimize if the middle instruction modifies source register
                        if reg not in modified:
                            m3 = re.match(rf"\s*move(\.[bwl])\s+{re.escape(reg)},\s*(\S+)$", base3)
                            if m3:
                                size = m3.group(1)
                                dest = m3.group(2)
                                if not re.match(r"[da]\d+$", dest):
                                    # CRITICAL FIX: Extract registers used in destination operand
                                    # If destination uses addressing like "5(a0)" or "(a0)", we must check
                                    # if the middle instruction modifies that address register
                                    dest_regs = _extract_used_regs(dest)
                                    # Check if any register used by dest is modified by middle instruction
                                    if not any(dreg in modified for dreg in dest_regs):
                                        if not _register_live_after(lines, i + 3, reg):
                                            optimized.append(f"{indent}move{size} #0,{dest}{comment3}")
                                            i += 3
                                            continue

        optimized.append(lines[i])
        i += 1

    return optimized


# ---------------------------------------------------------------------------
# New optimizations – condition evaluation & constant folding (2025 plan)
# ---------------------------------------------------------------------------

def _is_v_zero_long_flag_setter(base, reg):
    """Return True if *base* sets Z/N flags for *reg* with V=0, C=0 via a long-word operation.

    On 68000, the following long-word instructions always set V=0 and C=0, with
    Z and N reflecting the result held in *reg* after the instruction:
      - move.l  src, reg   (register load)
      - moveq   #n, reg
      - and.l / andi.l     src, reg
      - or.l  / ori.l      src, reg
      - eor.l / eori.l     src, reg
      - not.l  reg
      - ext.l  reg
      - clr.l  reg
      - move.l reg, <dest> (register store - reg itself unchanged, CCR set based on reg)

    Instructions that may set V!=0 (add, sub, neg, mul ...) are deliberately
    excluded to keep every case safe for bge / blt / bgt / ble as well.
    """
    # Two-operand long-word V=0 setters writing to reg as destination
    m = re.match(
        r"\s*(move\.l|and\.l|andi\.l|or\.l|ori\.l|eor\.l|eori\.l)\s+[^,]+,\s*"
        + re.escape(reg) + r"$",
        base,
    )
    if m:
        return True

    # moveq (always long, always V=0)
    m = re.match(r"\s*moveq\s+#-?\d+,\s*" + re.escape(reg) + r"$", base)
    if m:
        return True

    # Single-operand long-word V=0 setters
    m = re.match(r"\s*(not\.l|ext\.l|clr\.l)\s+" + re.escape(reg) + r"$", base)
    if m:
        return True

    # move.l reg, <dest>  - reg is the SOURCE; reg is unchanged; CCR reflects reg; V=0
    m = re.match(r"\s*move\.l\s+" + re.escape(reg) + r",\s*(\S+)$", base)
    if m and m.group(1) != reg:          # guard against move.l d0,d0 (no-op)
        return True

    return False


def _eliminate_redundant_flag_test(lines):
    """Remove ``tst.l dN`` or ``cmp.l #0,dN`` when the immediately preceding
    instruction already sets the same Z/N/V=0/C=0 flags for *dN*.

    This handles the common codegen pattern::

        move.l -4(a4),d0   ; sets V=0, N, Z for d0
        tst.l d0            ; <-- redundant, removed
        beq endif1

    and the store-then-compare pattern::

        move.l d0,-4(a4)   ; CCR based on d0, V=0
        cmp.l #0,d0         ; <-- redundant, removed
        bge endif21

    Only long-word V=0 setters are considered so that the optimisation is safe
    for all conditional-branch types (beq, bne, bmi, bpl, bge, ble, bgt, blt).
    """
    optimized = []
    i = 0

    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(";", 1)[0].rstrip()
            base2 = lines[i + 1].split(";", 1)[0].rstrip()

            # Detect tst.l dN or cmp.l #0,dN on the *next* line
            m_tst = re.match(r"\s*tst\.l\s+(d\d+)$", base2)
            m_cmp = re.match(r"\s*cmp\.l\s+#0,\s*(d\d+)$", base2)

            target_reg = None
            if m_tst:
                target_reg = m_tst.group(1)
            elif m_cmp:
                target_reg = m_cmp.group(1)

            if target_reg and _is_v_zero_long_flag_setter(base1, target_reg):
                # Preceding instruction already set the required flags.
                # Emit the flag-setter line and skip the tst/cmp line.
                optimized.append(lines[i])
                i += 2
                continue

        optimized.append(lines[i])
        i += 1

    return optimized


def _optimize_cmp_zero_to_tst(lines):
    """Replace sized CMP-zero tests on data registers with TST."""
    optimized = []

    for line in lines:
        line_ending = ""
        body = line
        if body.endswith("\r\n"):
            body, line_ending = body[:-2], "\r\n"
        elif body.endswith("\n"):
            body, line_ending = body[:-1], "\n"

        instruction, separator, comment = body.partition(";")
        match = re.fullmatch(
            r"(?P<indent>[ \t]*)cmp\.(?P<size>[bwl])[ \t]+#0,[ \t]*"
            r"(?P<reg>d[0-7])(?P<trailing>[ \t]*)",
            instruction,
        )
        if not match:
            optimized.append(line)
            continue

        rewritten = (
            f"{match.group('indent')}tst.{match.group('size')} {match.group('reg')}"
            f"{match.group('trailing')}"
        )
        if separator:
            rewritten += separator + comment
        optimized.append(rewritten + line_ending)

    return optimized


def _fold_neg_one(lines):
    """Fold ``moveq #N,dX ; neg.l dX``  ->  ``moveq #-N,dX``.

    On 68000, the code generator sometimes emits a constant load followed by
    ``neg.l`` to produce negative literals (e.g. ``moveq #1,d1; neg.l d1``
    for the value -1).  Folding eliminates the ``neg.l`` instruction.

    If the negated value falls outside the moveq range (-128...127) the result
    is emitted as ``move.l #value,dX`` instead.
    """
    optimized = []
    i = 0

    while i < len(lines):
        if i + 1 < len(lines):
            base1 = lines[i].split(";", 1)[0].rstrip()
            base2 = lines[i + 1].split(";", 1)[0].rstrip()
            comment1 = (";" + lines[i].split(";", 1)[1]) if ";" in lines[i] else ""

            m1 = re.match(r"(\s*)moveq\s+#(-?\d+),\s*(d\d+)$", base1)
            if m1:
                indent, val_str, reg = m1.groups()
                m2 = re.match(r"\s*neg\.l\s+" + re.escape(reg) + r"$", base2)
                if m2:
                    result = -int(val_str)
                    if -128 <= result <= 127:
                        optimized.append(f"{indent}moveq #{result},{reg}{comment1}")
                    else:
                        optimized.append(f"{indent}move.l #{result},{reg}{comment1}")
                    i += 2  # skip the neg.l
                    continue

        optimized.append(lines[i])
        i += 1

    return optimized


def _eliminate_tst_after_andi_neg(lines):
    """Remove ``tst.l dN`` following ``andi.l #$FF,dN; neg.b dN`` (or the
    word-width equivalent ``andi.l #$FFFF,dN; neg.w dN``).

    After ``andi.l #$FF,dN`` the upper 24 bits of *dN* are guaranteed zero.
    ``neg.b dN`` then toggles the byte between $00 and $01 while leaving the
    upper bytes at zero.  Because the long-word value is either $00000000 or
    $00000001, the Z flag set by ``neg.b`` already reflects the full 32-bit
    result, making the subsequent ``tst.l dN`` redundant.

    The same reasoning applies to ``andi.l #$FFFF,dN; neg.w dN``.
    """
    optimized = []
    i = 0

    while i < len(lines):
        if i + 2 < len(lines):
            base1 = lines[i].split(";", 1)[0].rstrip()
            base2 = lines[i + 1].split(";", 1)[0].rstrip()
            base3 = lines[i + 2].split(";", 1)[0].rstrip()

            # Match: andi.l #$FF,dN  or  andi.l #$FFFF,dN
            m1 = re.match(r"\s*andi\.l\s+#\$FF(FF)?,\s*(d\d+)$", base1)
            if m1:
                word_mode = m1.group(1) is not None   # True -> #$FFFF / neg.w
                reg = m1.group(2)
                expected_neg = "neg.w" if word_mode else "neg.b"

                # Match: neg.b dN  (byte) or neg.w dN  (word)
                m2 = re.match(
                    r"\s*" + re.escape(expected_neg) + r"\s+" + re.escape(reg) + r"$",
                    base2,
                )
                if m2:
                    # Match: tst.l dN
                    m3 = re.match(r"\s*tst\.l\s+" + re.escape(reg) + r"$", base3)
                    if m3:
                        # Emit andi and neg, skip the redundant tst.l
                        optimized.append(lines[i])
                        optimized.append(lines[i + 1])
                        i += 3
                        continue

        optimized.append(lines[i])
        i += 1

    return optimized
