# =============================================================
# reference_model.py  —  Python golden reference model
# Evaluates expected outputs in Python for cross-validation.
# =============================================================

import random
import re
from parser import ParsedSpec, SignalSpec, ConditionSpec
from utils import log
from typing import Dict, List, Tuple

InputVector  = Dict[str, int]
OutputVector = Dict[str, int]


# ── Public API ────────────────────────────────────────────────

def generate_vectors(spec: ParsedSpec, seed: int = 42) -> List[InputVector]:
    """Generate input vectors. Exhaustive for small circuits, random for large."""
    rng = random.Random(seed)
    inputs = _get_inputs(spec)
    total_bits = sum(s.width for s in inputs)

    vectors = []

    if total_bits <= 4 and spec.circuit_type == "combinational":
        # Exhaustive
        for combo in range(2 ** total_bits):
            vec: InputVector = {}
            bit_off = total_bits
            for s in inputs:
                bit_off -= s.width
                mask = (1 << s.width) - 1
                vec[s.name] = (combo >> bit_off) & mask
            vectors.append(vec)
    else:
        # Random
        for _ in range(spec.num_test_vectors):
            vec: InputVector = {}
            for s in inputs:
                vec[s.name] = rng.randint(0, (1 << s.width) - 1)
            vectors.append(vec)

    return vectors


def compute_expected(spec: ParsedSpec, input_vec: InputVector) -> OutputVector:
    """
    Compute expected outputs using the spec conditions.
    Evaluates SV-like expressions in Python.
    """
    result: OutputVector = {}
    outputs = _get_outputs(spec)

    for cond in spec.conditions:
        # Check if condition applies
        if not _eval_condition(cond.condition, input_vec, result):
            continue
        # Parse "lhs == rhs" from expected
        m = re.match(r"(.+?)\s*==\s*(.+)", cond.expected.strip())
        if not m:
            continue
        lhs = m.group(1).strip()
        rhs = m.group(2).strip()

        # Handle {cout, sum} = ... style
        concat_m = re.match(r"\{(\w+),\s*(\w+)\}", lhs)
        if concat_m:
            hi_name = concat_m.group(1)
            lo_name = concat_m.group(2)
            hi_sig = next((s for s in outputs if s.name == hi_name), None)
            lo_sig = next((s for s in outputs if s.name == lo_name), None)
            if lo_sig:
                val = _eval_expr(rhs, input_vec, result)
                if val is not None:
                    lo_mask = (1 << lo_sig.width) - 1
                    result[lo_name] = val & lo_mask
                    if hi_sig:
                        result[hi_name] = (val >> lo_sig.width) & ((1 << hi_sig.width) - 1)
        else:
            # Find the output signal to get its width
            out_sig = next((s for s in outputs if s.name == lhs), None)
            width = out_sig.width if out_sig else 1
            val = _eval_expr(rhs, input_vec, result)
            if val is not None:
                mask = (1 << width) - 1
                result[lhs] = val & mask

    # Fill missing outputs with 0
    for s in outputs:
        if s.name not in result:
            result[s.name] = 0

    return result


def run_reference_sim(spec: ParsedSpec, seed: int = 42) -> str:
    """Run full reference simulation. Returns a formatted report."""
    vectors = generate_vectors(spec, seed)
    lines = [
        "=" * 52,
        "  REFERENCE MODEL REPORT",
        f"  Module  : {spec.module_name}",
        f"  Vectors : {len(vectors)}",
        "=" * 52,
    ]

    pass_cnt = 0
    fail_cnt = 0

    for i, vec in enumerate(vectors):
        expected = compute_expected(spec, vec)
        passed = True
        fail_reasons = []

        # Verify conditions
        for cond in spec.conditions:
            if not _eval_condition(cond.condition, vec, {}):
                continue
            m = re.match(r"(.+?)\s*==\s*(.+)", cond.expected.strip())
            if not m:
                continue
            lhs = m.group(1).strip()
            # Handle concat LHS
            concat_m = re.match(r"\{(\w+),\s*(\w+)\}", lhs)
            if concat_m:
                lhs = concat_m.group(2)
            if lhs in expected:
                rhs_val = _eval_expr(m.group(2).strip(), vec, {})
                if rhs_val is not None:
                    out_sig = next((s for s in spec.signals if s.name == lhs), None)
                    width = out_sig.width if out_sig else 1
                    mask = (1 << width) - 1
                    exp_masked = rhs_val & mask
                    if expected.get(lhs, 0) != exp_masked:
                        passed = False
                        fail_reasons.append(
                            f"{lhs}: got {expected.get(lhs,0):#x}, "
                            f"expected {exp_masked:#x}"
                        )

        in_str  = "  ".join(f"{k}={v:#x}" for k,v in vec.items())
        out_str = "  ".join(f"{k}={v:#x}" for k,v in expected.items())

        if passed:
            pass_cnt += 1
            lines.append(f"  [PASS] Vec {i:03d}: IN=[{in_str}]  OUT=[{out_str}]")
        else:
            fail_cnt += 1
            lines.append(f"  [FAIL] Vec {i:03d}: IN=[{in_str}]  " +
                          " | ".join(fail_reasons))

    lines += [
        "=" * 52,
        f"  TOTAL  : {len(vectors)}",
        f"  PASS   : {pass_cnt}",
        f"  FAIL   : {fail_cnt}",
        "=" * 52,
    ]

    log.info(f"Reference model: {pass_cnt} PASS, {fail_cnt} FAIL")
    return "\n".join(lines)


# ── Internal helpers ──────────────────────────────────────────

def _get_inputs(spec: ParsedSpec) -> List[SignalSpec]:
    return [s for s in spec.signals
            if s.direction == "input" and not s.is_clock and not s.is_reset]


def _get_outputs(spec: ParsedSpec) -> List[SignalSpec]:
    return [s for s in spec.signals if s.direction == "output"]


def _eval_condition(cond_sv: str, inputs: InputVector,
                    outputs: OutputVector) -> bool:
    """Evaluate a simple SV condition against known values."""
    if cond_sv.strip() in ("1", ""):
        return True
    ctx = {**inputs, **outputs}
    expr = _sv_to_python(cond_sv, ctx)
    try:
        return bool(eval(expr, {"__builtins__": {}}, ctx))
    except Exception:
        return True   # conservative


def _eval_expr(sv_expr: str, inputs: InputVector,
               partial_outputs: OutputVector) -> int | None:
    """Evaluate an SV RHS expression. Returns int or None on failure."""
    ctx = {**inputs, **partial_outputs}

    # Handle SV literals: 4'b0, 8'hFF, 1'b1
    def replace_literal(m):
        width = int(m.group(1))
        base  = m.group(2).lower()
        value = m.group(3).replace("_","")
        try:
            if base == 'h': return str(int(value, 16))
            if base == 'b': return str(int(value, 2))
            if base == 'd': return str(int(value, 10))
            return str(int(value, 10))
        except:
            return "0"

    expr = re.sub(r"(\d+)'([hbdHBD])([0-9a-fA-F_]+)", replace_literal, sv_expr)
    expr = re.sub(r"\b(\d+)'b0\b", "0", expr)

    # q + 1 style — replace q with its current value
    expr = _sv_to_python(expr, ctx)

    try:
        result = eval(expr, {"__builtins__": {}}, ctx)
        return int(result)
    except Exception:
        return None


def _sv_to_python(expr: str, ctx: dict) -> str:
    """Convert SV operators to Python operators."""
    # Replace SV literals first
    def replace_literal(m):
        base  = m.group(2).lower()
        value = m.group(3).replace("_","")
        try:
            if base == 'h': return str(int(value, 16))
            if base == 'b': return str(int(value, 2))
            return str(int(value, 10))
        except:
            return "0"
    expr = re.sub(r"\d+'([hbdHBD])([0-9a-fA-F_]+)", replace_literal, expr)

    # SV → Python operators
    expr = expr.replace("&&", " and ").replace("||", " or ")
    expr = re.sub(r"(?<![=!<>])!(?!=)", " not ", expr)

    # ^ is XOR in SV — use ^ in Python too (same)
    # ~ is bitwise NOT — use ~ in Python (same)
    # & | are same

    return expr
