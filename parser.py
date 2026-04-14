# =============================================================
# parser.py  —  AI-powered NL requirement parser
# Hardcoded fast-path for 50+ common circuits + Claude API fallback
# =============================================================

import json, re, os, requests
from dataclasses import dataclass
from typing import List, Optional


# ── Data Structures ───────────────────────────────────────────

@dataclass
class SignalSpec:
    name: str
    direction: str        # 'input' | 'output'
    width: int = 1
    is_clock: bool = False
    is_reset: bool = False
    active_low: bool = False

@dataclass
class ConditionSpec:
    trigger: str
    condition: str
    expected: str
    delay_cycles: int = 0

@dataclass
class AssertionSpec:
    label: str
    antecedent: str
    consequent: str
    delay: str = "##1"

@dataclass
class ParsedSpec:
    module_name: str
    signals: List[SignalSpec]
    conditions: List[ConditionSpec]
    assertions: List[AssertionSpec]
    clock_signal: Optional[str]
    reset_signal: Optional[str]
    reset_active_low: bool
    circuit_type: str
    num_test_vectors: int
    description: str


# ── Helpers ───────────────────────────────────────────────────

def _sig(name, direction, width=1, is_clock=False, is_reset=False, active_low=False):
    return SignalSpec(name, direction, width, is_clock, is_reset, active_low)

def _cond(expected, condition="1", trigger="*", delay=0):
    return ConditionSpec(trigger, condition, expected, delay)

def _scond(expected, condition="1", delay=0):
    return ConditionSpec("posedge clk", condition, expected, delay)

def _build_assertions(conditions):
    return [AssertionSpec(f"assert_chk_{i}", c.condition, c.expected,
                          f"##{c.delay_cycles}" if c.delay_cycles else "##1")
            for i, c in enumerate(conditions)]

def _combo(name, signals, conditions, text, nvec=None):
    if nvec is None:
        inp = sum(1 for s in signals if s.direction == "input")
        nvec = min(2**inp, 64)
    return ParsedSpec(name, signals, conditions, _build_assertions(conditions),
                      None, None, False, "combinational", nvec, text)

def _seq(name, signals, conditions, text, clk="clk", rst=None, alow=False, nvec=30):
    return ParsedSpec(name, signals, conditions, _build_assertions(conditions),
                      clk, rst, alow, "sequential", nvec, text)


# ── Claude API system prompt ──────────────────────────────────

_SYSTEM_PROMPT = """
You are a hardware verification expert. Parse the natural language circuit description
and return ONLY a valid JSON object — no markdown, no explanation.

Schema:
{
  "module_name": "<snake_case>",
  "circuit_type": "<combinational|sequential>",
  "clock_signal": "<name or null>",
  "reset_signal": "<name or null>",
  "reset_active_low": <bool>,
  "num_test_vectors": <int>,
  "signals": [{"name":"","direction":"input|output","width":<int>,"is_clock":<bool>,"is_reset":<bool>,"active_low":<bool>}],
  "conditions": [{"trigger":"*|posedge clk","condition":"1 or SV expr","expected":"SV expr","delay_cycles":<int>}]
}

Key rules:
- Combinational: trigger="*", clock_signal=null
- Sequential: trigger="posedge clk"
- Use SV operators: &(AND) |(OR) ^(XOR) ~(NOT) +(ADD) -(SUB) *(MUL)
- Ternary: sel ? a : b
- width is always an integer
- module_name uses underscores, no spaces
- No comments in JSON
"""


# ── Public API ────────────────────────────────────────────────

def parse(text: str) -> ParsedSpec:
    quick = _try_known_circuit(text)
    if quick:
        return quick
    try:
        raw = _call_claude_api(text)
        data = json.loads(raw)
        return _dict_to_spec(data, text)
    except Exception as e:
        print(f"[parser] AI error: {e}")
        return _rule_based_fallback(text)


# ══════════════════════════════════════════════════════════════
# KNOWN CIRCUIT LIBRARY  — 50+ circuits, all hardcoded
# ══════════════════════════════════════════════════════════════

def _try_known_circuit(text: str) -> Optional[ParsedSpec]:
    t = text.lower()

    # ── ADDERS ────────────────────────────────────────────────
    if re.search(r"full[\s_-]adder", t):
        bits = _get_bits(t)
        return _make_nbit_full_adder(bits, text) if bits > 1 else _make_full_adder(text)

    if re.search(r"half[\s_-]adder", t):
        return _make_half_adder(text)

    if re.search(r"ripple[\s_-]carry", t):
        bits = _get_bits(t) or 4
        return _make_ripple_carry_adder(bits, text)

    if re.search(r"carry[\s_-]look[\s_-]?ahead|cla\s+adder", t):
        bits = _get_bits(t) or 4
        return _make_cla_adder(bits, text)

    if re.search(r"\badder\b", t) and not re.search(r"full|half|ripple|cla|carry look", t):
        bits = _get_bits(t) or 8
        return _make_simple_adder(bits, text)

    # ── SUBTRACTORS ───────────────────────────────────────────
    if re.search(r"full[\s_-]subtractor", t):
        return _make_full_subtractor(text)

    if re.search(r"half[\s_-]subtractor", t):
        return _make_half_subtractor(text)

    if re.search(r"\bsubtractor\b", t):
        bits = _get_bits(t) or 8
        return _make_nbit_subtractor(bits, text)

    # ── MULTIPLIERS ───────────────────────────────────────────
    if re.search(r"\bmultiplier\b|\bmul\b", t):
        bits = _get_bits(t) or 4
        return _make_multiplier(bits, text)

    # ── COMPARATORS ───────────────────────────────────────────
    if re.search(r"\bcomparator\b|\bmagnitude comparator\b", t):
        bits = _get_bits(t) or 4
        return _make_comparator(bits, text)

    # ── GATES ─────────────────────────────────────────────────
    if re.search(r"\bnand\s+gate\b", t):         return _make_gate("nand_gate",  "~(a & b)", text)
    if re.search(r"\bnor\s+gate\b", t):          return _make_gate("nor_gate",   "~(a | b)", text)
    if re.search(r"\bxnor\s+gate\b", t):         return _make_gate("xnor_gate",  "~(a ^ b)", text)
    if re.search(r"\bxor\s+gate\b", t):          return _make_gate("xor_gate",   "a ^ b",    text)
    if re.search(r"\band\s+gate\b", t):          return _make_gate("and_gate",   "a & b",    text)
    if re.search(r"\bor\s+gate\b", t):           return _make_gate("or_gate",    "a | b",    text)
    if re.search(r"\bnot\s+gate\b|\binverter\b", t): return _make_not_gate(text)

    # Multi-input gates
    if re.search(r"3[\s-]?input\s+and", t):      return _make_gate3("and3_gate", "a & b & c", text)
    if re.search(r"3[\s-]?input\s+or", t):       return _make_gate3("or3_gate",  "a | b | c", text)
    if re.search(r"3[\s-]?input\s+nand", t):     return _make_gate3("nand3_gate","~(a & b & c)", text)
    if re.search(r"3[\s-]?input\s+nor", t):      return _make_gate3("nor3_gate", "~(a | b | c)", text)
    if re.search(r"3[\s-]?input\s+xor", t):      return _make_gate3("xor3_gate", "a ^ b ^ c", text)
    if re.search(r"4[\s-]?input\s+and", t):      return _make_gate4("and4_gate", "a & b & c & d", text)
    if re.search(r"4[\s-]?input\s+or", t):       return _make_gate4("or4_gate",  "a | b | c | d", text)
    if re.search(r"4[\s-]?input\s+nand", t):     return _make_gate4("nand4_gate","~(a & b & c & d)", text)

    # ── MULTIPLEXERS ──────────────────────────────────────────
    if re.search(r"8[\s:-]?to[\s:-]?1\s*mux|8x1\s*mux", t): return _make_mux8to1(text)
    if re.search(r"4[\s:-]?to[\s:-]?1\s*mux|4x1\s*mux", t): return _make_mux4to1(text)
    if re.search(r"2[\s:-]?to[\s:-]?1\s*mux|2x1\s*mux", t): return _make_mux2to1(text)
    if re.search(r"\bmux\b|\bmultiplexer\b", t):
        if "8" in t: return _make_mux8to1(text)
        if "4" in t: return _make_mux4to1(text)
        return _make_mux2to1(text)

    # ── DEMULTIPLEXERS ────────────────────────────────────────
    if re.search(r"1[\s:-]?to[\s:-]?4\s*demux|1x4\s*demux", t): return _make_demux1to4(text)
    if re.search(r"1[\s:-]?to[\s:-]?2\s*demux|1x2\s*demux", t): return _make_demux1to2(text)
    if re.search(r"\bdemux\b|\bdemultiplexer\b", t):
        if "4" in t: return _make_demux1to4(text)
        return _make_demux1to2(text)

    # ── ENCODERS ──────────────────────────────────────────────
    if re.search(r"priority\s+encoder", t):
        if "8" in t: return _make_priority_encoder8(text)
        return _make_priority_encoder4(text)
    if re.search(r"4[\s:-]?to[\s:-]?2\s*encoder", t): return _make_encoder4to2(text)
    if re.search(r"8[\s:-]?to[\s:-]?3\s*encoder", t): return _make_encoder8to3(text)
    if re.search(r"\bencoder\b", t):
        if "8" in t: return _make_encoder8to3(text)
        return _make_encoder4to2(text)

    # ── DECODERS ──────────────────────────────────────────────
    if re.search(r"2[\s:-]?to[\s:-]?4\s*decoder", t): return _make_decoder2to4(text)
    if re.search(r"3[\s:-]?to[\s:-]?8\s*decoder", t): return _make_decoder3to8(text)
    if re.search(r"\bdecoder\b", t):
        if "8" in t: return _make_decoder3to8(text)
        return _make_decoder2to4(text)

    # ── CODE CONVERTERS ───────────────────────────────────────
    if re.search(r"binary\s+to\s+gray|bin.*gray", t):  return _make_bin2gray(text)
    if re.search(r"gray\s+to\s+binary|gray.*bin", t):  return _make_gray2bin(text)
    if re.search(r"binary\s+to\s+bcd|bin.*bcd", t):    return _make_bin2bcd(text)
    if re.search(r"bcd\s+to\s+excess|bcd.*excess.3", t): return _make_bcd2xs3(text)
    if re.search(r"excess.3\s+to\s+bcd", t):           return _make_xs32bcd(text)

    # ── PARITY ────────────────────────────────────────────────
    if re.search(r"parity\s+generator|parity\s+checker", t):
        bits = _get_bits(t) or 4
        return _make_parity_gen(bits, text)

    # ── FLIP-FLOPS ────────────────────────────────────────────
    if re.search(r"\bsr\s+flip[\s-]?flop\b|\bsr\s+ff\b|\bsr\s+latch\b", t): return _make_sr_ff(text)
    if re.search(r"\bjk\s+flip[\s-]?flop\b|\bjk\s+ff\b", t):                return _make_jk_ff(text)
    if re.search(r"\bt\s+flip[\s-]?flop\b|\bt\s+ff\b", t):                   return _make_t_ff(text)
    if re.search(r"\bd\s+flip[\s-]?flop\b|\bdff\b|\bd\s+ff\b", t):           return _make_d_ff(text)
    if re.search(r"flip[\s-]?flop", t):                                        return _make_d_ff(text)

    # ── LATCHES ───────────────────────────────────────────────
    if re.search(r"\bd\s+latch\b", t):   return _make_d_latch(text)
    if re.search(r"\bsr\s+latch\b", t):  return _make_sr_latch(text)

    # ── REGISTERS ─────────────────────────────────────────────
    if re.search(r"shift\s+register|siso|sipo|piso|pipo", t):
        bits = _get_bits(t) or 8
        if re.search(r"siso|serial.in.*serial.out", t): return _make_siso(bits, text)
        if re.search(r"sipo|serial.in.*parallel", t):   return _make_sipo(bits, text)
        if re.search(r"piso|parallel.in.*serial", t):   return _make_piso(bits, text)
        return _make_sipo(bits, text)
    if re.search(r"\bregister\b|\bparallel.load\b", t):
        bits = _get_bits(t) or 8
        return _make_register(bits, text)

    # ── COUNTERS ──────────────────────────────────────────────
    if re.search(r"ring\s+counter", t):
        bits = _get_bits(t) or 4
        return _make_ring_counter(bits, text)
    if re.search(r"johnson\s+counter", t):
        bits = _get_bits(t) or 4
        return _make_johnson_counter(bits, text)
    if re.search(r"up[\s/]?down\s+counter|bidirectional\s+counter", t):
        bits = _get_bits(t) or 4
        return _make_updown_counter(bits, text)
    if re.search(r"down\s+counter", t):
        bits = _get_bits(t) or 4
        return _make_down_counter(bits, text)
    if re.search(r"bcd\s+counter|decade\s+counter", t):
        return _make_bcd_counter(text)
    if re.search(r"\bcounter\b", t):
        bits = _get_bits(t) or 4
        return _make_up_counter(bits, text)

    # ── ALU ───────────────────────────────────────────────────
    if re.search(r"\balu\b|\barithmetic\s+logic\s+unit\b", t):
        bits = _get_bits(t) or 8
        return _make_alu(bits, text)

    # ── BARREL SHIFTER ────────────────────────────────────────
    if re.search(r"barrel\s+shift", t):
        bits = _get_bits(t) or 8
        return _make_barrel_shifter(bits, text)

    # ── MAGNITUDE / COMPARATOR ────────────────────────────────
    if re.search(r"\bcomparator\b", t):
        bits = _get_bits(t) or 4
        return _make_comparator(bits, text)

    return None


# ══════════════════════════════════════════════════════════════
# ADDERS
# ══════════════════════════════════════════════════════════════

def _make_full_adder(text):
    s = [_sig("a","input"),_sig("b","input"),_sig("cin","input"),
         _sig("sum","output"),_sig("cout","output")]
    c = [_cond("sum == (a ^ b ^ cin)"),
         _cond("cout == ((a & b) | (b & cin) | (a & cin))")]
    return _combo("full_adder", s, c, text, 8)

def _make_half_adder(text):
    s = [_sig("a","input"),_sig("b","input"),
         _sig("sum","output"),_sig("cout","output")]
    c = [_cond("sum == (a ^ b)"), _cond("cout == (a & b)")]
    return _combo("half_adder", s, c, text, 4)

def _make_nbit_full_adder(bits, text):
    s = [_sig("a","input",bits),_sig("b","input",bits),_sig("cin","input"),
         _sig("sum","output",bits),_sig("cout","output")]
    c = [_cond("{cout,sum} == a + b + cin")]
    return _combo(f"adder_{bits}bit", s, c, text, 20)

def _make_simple_adder(bits, text):
    s = [_sig("a","input",bits),_sig("b","input",bits),
         _sig("sum","output",bits+1)]
    c = [_cond("sum == a + b")]
    return _combo(f"adder_{bits}bit", s, c, text, 20)

def _make_ripple_carry_adder(bits, text):
    s = [_sig("a","input",bits),_sig("b","input",bits),_sig("cin","input"),
         _sig("sum","output",bits),_sig("cout","output")]
    c = [_cond("{cout,sum} == a + b + cin")]
    return _combo(f"rca_{bits}bit", s, c, text, 20)

def _make_cla_adder(bits, text):
    s = [_sig("a","input",bits),_sig("b","input",bits),_sig("cin","input"),
         _sig("sum","output",bits),_sig("cout","output")]
    c = [_cond("{cout,sum} == a + b + cin")]
    return _combo(f"cla_{bits}bit", s, c, text, 20)


# ══════════════════════════════════════════════════════════════
# SUBTRACTORS
# ══════════════════════════════════════════════════════════════

def _make_half_subtractor(text):
    s = [_sig("a","input"),_sig("b","input"),
         _sig("diff","output"),_sig("borrow","output")]
    c = [_cond("diff == (a ^ b)"), _cond("borrow == (~a & b)")]
    return _combo("half_subtractor", s, c, text, 4)

def _make_full_subtractor(text):
    s = [_sig("a","input"),_sig("b","input"),_sig("bin","input"),
         _sig("diff","output"),_sig("bout","output")]
    c = [_cond("diff == (a ^ b ^ bin)"),
         _cond("bout == ((~a & b) | (b & bin) | (~a & bin))")]
    return _combo("full_subtractor", s, c, text, 8)

def _make_nbit_subtractor(bits, text):
    s = [_sig("a","input",bits),_sig("b","input",bits),_sig("bin","input"),
         _sig("diff","output",bits),_sig("bout","output")]
    c = [_cond("{bout,diff} == a - b - bin")]
    return _combo(f"subtractor_{bits}bit", s, c, text, 20)


# ══════════════════════════════════════════════════════════════
# MULTIPLIER
# ══════════════════════════════════════════════════════════════

def _make_multiplier(bits, text):
    out_bits = bits * 2
    s = [_sig("a","input",bits),_sig("b","input",bits),
         _sig("product","output",out_bits)]
    c = [_cond("product == a * b")]
    return _combo(f"multiplier_{bits}bit", s, c, text, 20)


# ══════════════════════════════════════════════════════════════
# GATES
# ══════════════════════════════════════════════════════════════

def _make_gate(name, expr, text):
    s = [_sig("a","input"),_sig("b","input"),_sig("y","output")]
    return _combo(name, s, [_cond(f"y == ({expr})")], text, 4)

def _make_gate3(name, expr, text):
    s = [_sig("a","input"),_sig("b","input"),_sig("c","input"),_sig("y","output")]
    return _combo(name, s, [_cond(f"y == ({expr})")], text, 8)

def _make_gate4(name, expr, text):
    s = [_sig("a","input"),_sig("b","input"),_sig("c","input"),_sig("d","input"),_sig("y","output")]
    return _combo(name, s, [_cond(f"y == ({expr})")], text, 16)

def _make_not_gate(text):
    s = [_sig("a","input"),_sig("y","output")]
    return _combo("not_gate", s, [_cond("y == (~a & 1'b1)")], text, 2)


# ══════════════════════════════════════════════════════════════
# MULTIPLEXERS
# ══════════════════════════════════════════════════════════════

def _make_mux2to1(text):
    s = [_sig("a","input"),_sig("b","input"),_sig("sel","input"),_sig("y","output")]
    c = [_cond("y == (sel ? b : a)")]
    return _combo("mux2to1", s, c, text, 8)

def _make_mux4to1(text):
    s = [_sig("d0","input"),_sig("d1","input"),_sig("d2","input"),_sig("d3","input"),
         _sig("sel","input",2),_sig("y","output")]
    c = [_cond("y == (sel==2'b00 ? d0 : sel==2'b01 ? d1 : sel==2'b10 ? d2 : d3)")]
    return _combo("mux4to1", s, c, text, 16)

def _make_mux8to1(text):
    sigs = [_sig(f"d{i}","input") for i in range(8)]
    sigs += [_sig("sel","input",3),_sig("y","output")]
    expr = ("(sel==3'b000 ? d0 : sel==3'b001 ? d1 : sel==3'b010 ? d2 : "
            "sel==3'b011 ? d3 : sel==3'b100 ? d4 : sel==3'b101 ? d5 : "
            "sel==3'b110 ? d6 : d7)")
    return _combo("mux8to1", sigs, [_cond(f"y == {expr}")], text, 32)


# ══════════════════════════════════════════════════════════════
# DEMULTIPLEXERS
# ══════════════════════════════════════════════════════════════

def _make_demux1to2(text):
    s = [_sig("din","input"),_sig("sel","input"),
         _sig("y0","output"),_sig("y1","output")]
    c = [_cond("y0 == (sel==1'b0 ? din : 1'b0)"),
         _cond("y1 == (sel==1'b1 ? din : 1'b0)")]
    return _combo("demux1to2", s, c, text, 4)

def _make_demux1to4(text):
    s = [_sig("din","input"),_sig("sel","input",2),
         _sig("y0","output"),_sig("y1","output"),
         _sig("y2","output"),_sig("y3","output")]
    c = [_cond("y0 == (sel==2'b00 ? din : 1'b0)"),
         _cond("y1 == (sel==2'b01 ? din : 1'b0)"),
         _cond("y2 == (sel==2'b10 ? din : 1'b0)"),
         _cond("y3 == (sel==2'b11 ? din : 1'b0)")]
    return _combo("demux1to4", s, c, text, 8)


# ══════════════════════════════════════════════════════════════
# ENCODERS
# ══════════════════════════════════════════════════════════════

def _make_encoder4to2(text):
    s = [_sig("i0","input"),_sig("i1","input"),_sig("i2","input"),_sig("i3","input"),
         _sig("y","output",2)]
    c = [_cond("y == (i3 ? 2'b11 : i2 ? 2'b10 : i1 ? 2'b01 : 2'b00)")]
    return _combo("encoder4to2", s, c, text, 16)

def _make_encoder8to3(text):
    sigs = [_sig(f"i{i}","input") for i in range(8)] + [_sig("y","output",3)]
    expr = ("(i7 ? 3'b111 : i6 ? 3'b110 : i5 ? 3'b101 : i4 ? 3'b100 : "
            "i3 ? 3'b011 : i2 ? 3'b010 : i1 ? 3'b001 : 3'b000)")
    return _combo("encoder8to3", sigs, [_cond(f"y == {expr}")], text, 32)

def _make_priority_encoder4(text):
    s = [_sig("i0","input"),_sig("i1","input"),_sig("i2","input"),_sig("i3","input"),
         _sig("y","output",2),_sig("valid","output")]
    c = [_cond("y == (i3 ? 2'b11 : i2 ? 2'b10 : i1 ? 2'b01 : 2'b00)"),
         _cond("valid == (i0 | i1 | i2 | i3)")]
    return _combo("priority_encoder4", s, c, text, 16)

def _make_priority_encoder8(text):
    sigs = [_sig(f"i{i}","input") for i in range(8)]
    sigs += [_sig("y","output",3),_sig("valid","output")]
    expr = ("(i7?3'b111:i6?3'b110:i5?3'b101:i4?3'b100:"
            "i3?3'b011:i2?3'b010:i1?3'b001:3'b000)")
    vld  = "(i0|i1|i2|i3|i4|i5|i6|i7)"
    c = [_cond(f"y == {expr}"), _cond(f"valid == {vld}")]
    return _combo("priority_encoder8", sigs, c, text, 32)


# ══════════════════════════════════════════════════════════════
# DECODERS
# ══════════════════════════════════════════════════════════════

def _make_decoder2to4(text):
    s = [_sig("a","input",2),_sig("en","input"),
         _sig("y","output",4)]
    c = [_cond("y == (en ? (4'b0001 << a) : 4'b0000)")]
    return _combo("decoder2to4", s, c, text, 16)

def _make_decoder3to8(text):
    s = [_sig("a","input",3),_sig("en","input"),
         _sig("y","output",8)]
    c = [_cond("y == (en ? (8'b00000001 << a) : 8'b00000000)")]
    return _combo("decoder3to8", s, c, text, 16)


# ══════════════════════════════════════════════════════════════
# CODE CONVERTERS
# ══════════════════════════════════════════════════════════════

def _make_bin2gray(text):
    bits = _get_bits(text.lower()) or 4
    s = [_sig("bin","input",bits),_sig("gray","output",bits)]
    c = [_cond("gray == (bin ^ (bin >> 1))")]
    return _combo("bin_to_gray", s, c, text, 20)

def _make_gray2bin(text):
    bits = _get_bits(text.lower()) or 4
    # For 4-bit gray to binary (manual unrolling is clearest)
    s = [_sig("gray","input",bits),_sig("bin","output",bits)]
    # Use XOR cascade: b[n-1]=g[n-1], b[i]=b[i+1]^g[i]
    # Express as: bin[3]=gray[3], bin[2]=gray[3]^gray[2],
    #             bin[1]=gray[3]^gray[2]^gray[1], bin[0]=all XOR
    # Simplest single-condition: use the known formula
    c = [_cond("bin == (gray ^ (gray>>1) ^ (gray>>2) ^ (gray>>3))")]
    return _combo("gray_to_bin", s, c, text, 20)

def _make_bin2bcd(text):
    # 4-bit binary to BCD (0-9)
    s = [_sig("bin","input",4),
         _sig("bcd_tens","output",4),_sig("bcd_units","output",4)]
    c = [_cond("bcd_tens == (bin / 10)"),
         _cond("bcd_units == (bin % 10)")]
    return _combo("bin_to_bcd", s, c, text, 16)

def _make_bcd2xs3(text):
    s = [_sig("bcd","input",4),_sig("xs3","output",4)]
    c = [_cond("xs3 == (bcd + 4'b0011)")]
    return _combo("bcd_to_xs3", s, c, text, 10)

def _make_xs32bcd(text):
    s = [_sig("xs3","input",4),_sig("bcd","output",4)]
    c = [_cond("bcd == (xs3 - 4'b0011)")]
    return _combo("xs3_to_bcd", s, c, text, 10)


# ══════════════════════════════════════════════════════════════
# PARITY
# ══════════════════════════════════════════════════════════════

def _make_parity_gen(bits, text):
    s = [_sig("data","input",bits),_sig("parity","output")]
    c = [_cond("parity == ^data")]  # reduction XOR
    return _combo(f"parity_gen_{bits}bit", s, c, text, 20)


# ══════════════════════════════════════════════════════════════
# COMPARATOR
# ══════════════════════════════════════════════════════════════

def _make_comparator(bits, text):
    s = [_sig("a","input",bits),_sig("b","input",bits),
         _sig("eq","output"),_sig("gt","output"),_sig("lt","output")]
    c = [_cond("eq == (a == b)"),
         _cond("gt == (a > b)"),
         _cond("lt == (a < b)")]
    return _combo(f"comparator_{bits}bit", s, c, text, 20)


# ══════════════════════════════════════════════════════════════
# FLIP-FLOPS  (all sequential)
# ══════════════════════════════════════════════════════════════

def _make_d_ff(text):
    rst_alow = re.search(r"rst_n|active.low|active low", text.lower()) is not None
    rst_name = "rst_n" if rst_alow else "rst"
    s = [_sig("clk","input",1,is_clock=True),
         _sig(rst_name,"input",1,is_reset=True,active_low=rst_alow),
         _sig("d","input"),_sig("q","output"),_sig("qb","output")]
    rst_cond = f"{rst_name} == 1'b0" if rst_alow else f"{rst_name} == 1'b1"
    run_cond = f"{rst_name} == 1'b1" if rst_alow else f"{rst_name} == 1'b0"
    c = [_scond("q == 1'b0",  rst_cond),
         _scond("qb == 1'b1", rst_cond),
         _scond("q == d",     run_cond),
         _scond("qb == ~d",   run_cond)]
    return _seq("d_flipflop", s, c, text, rst=rst_name, alow=rst_alow, nvec=20)

def _make_jk_ff(text):
    rst_alow = re.search(r"rst_n|active.low", text.lower()) is not None
    rst_name = "rst_n" if rst_alow else "rst"
    s = [_sig("clk","input",1,is_clock=True),
         _sig(rst_name,"input",1,is_reset=True,active_low=rst_alow),
         _sig("j","input"),_sig("k","input"),
         _sig("q","output"),_sig("qb","output")]
    rst_cond = f"{rst_name} == 1'b0" if rst_alow else f"{rst_name} == 1'b1"
    # JK: 00=hold, 01=reset, 10=set, 11=toggle
    c = [_scond("q == 1'b0",  rst_cond),
         _scond("q == 1'b0",  f"({('!' if not rst_alow else '')}{rst_name}) && j==0 && k==1"),
         _scond("q == 1'b1",  f"({('!' if not rst_alow else '')}{rst_name}) && j==1 && k==0"),
         _scond("qb == ~q",   "1")]
    return _seq("jk_flipflop", s, c, text, rst=rst_name, alow=rst_alow, nvec=20)

def _make_sr_ff(text):
    s = [_sig("clk","input",1,is_clock=True),
         _sig("rst","input",1,is_reset=True),
         _sig("s","input"),_sig("r","input"),
         _sig("q","output"),_sig("qb","output")]
    c = [_scond("q == 1'b0",  "rst == 1'b1"),
         _scond("q == 1'b0",  "rst == 1'b0 && s==0 && r==1"),
         _scond("q == 1'b1",  "rst == 1'b0 && s==1 && r==0"),
         _scond("qb == ~q",   "1")]
    return _seq("sr_flipflop", s, c, text, rst="rst", alow=False, nvec=20)

def _make_t_ff(text):
    rst_alow = re.search(r"rst_n|active.low", text.lower()) is not None
    rst_name = "rst_n" if rst_alow else "rst"
    s = [_sig("clk","input",1,is_clock=True),
         _sig(rst_name,"input",1,is_reset=True,active_low=rst_alow),
         _sig("t","input"),_sig("q","output"),_sig("qb","output")]
    rst_cond = f"{rst_name} == 1'b0" if rst_alow else f"{rst_name} == 1'b1"
    run_cond = f"{rst_name} == 1'b1" if rst_alow else f"{rst_name} == 1'b0"
    c = [_scond("q == 1'b0", rst_cond),
         # toggle: q <= q ^ t
         _scond("qb == ~q",  "1")]
    return _seq("t_flipflop", s, c, text, rst=rst_name, alow=rst_alow, nvec=20)


# ══════════════════════════════════════════════════════════════
# LATCHES
# ══════════════════════════════════════════════════════════════

def _make_d_latch(text):
    s = [_sig("en","input"),_sig("d","input"),_sig("q","output"),_sig("qb","output")]
    c = [_cond("q == d",    "en == 1'b1", trigger="*"),
         _cond("qb == ~d",  "en == 1'b1", trigger="*")]
    return _combo("d_latch", s, c, text, 4)

def _make_sr_latch(text):
    s = [_sig("s","input"),_sig("r","input"),_sig("q","output"),_sig("qb","output")]
    c = [_cond("q == 1'b1",  "s==1 && r==0", trigger="*"),
         _cond("q == 1'b0",  "s==0 && r==1", trigger="*")]
    return _combo("sr_latch", s, c, text, 4)


# ══════════════════════════════════════════════════════════════
# REGISTERS
# ══════════════════════════════════════════════════════════════

def _make_register(bits, text):
    rst_alow = re.search(r"rst_n|active.low", text.lower()) is not None
    rst_name = "rst_n" if rst_alow else "rst"
    s = [_sig("clk","input",1,is_clock=True),
         _sig(rst_name,"input",1,is_reset=True,active_low=rst_alow),
         _sig("load","input"),_sig("d","input",bits),_sig("q","output",bits)]
    rst_cond = f"{rst_name} == 1'b0" if rst_alow else f"{rst_name} == 1'b1"
    c = [_scond(f"q == {bits}'b0", rst_cond),
         _scond("q == d",   f"load == 1'b1")]
    return _seq(f"register_{bits}bit", s, c, text, rst=rst_name, alow=rst_alow, nvec=20)

def _make_siso(bits, text):
    s = [_sig("clk","input",1,is_clock=True),_sig("rst","input",1,is_reset=True),
         _sig("sin","input"),_sig("sout","output")]
    c = [_scond("sout == 1'b0", "rst == 1'b1")]
    return _seq(f"siso_{bits}bit", s, c, text, rst="rst", nvec=20)

def _make_sipo(bits, text):
    s = [_sig("clk","input",1,is_clock=True),_sig("rst","input",1,is_reset=True),
         _sig("sin","input"),_sig("pout","output",bits)]
    c = [_scond(f"pout == {bits}'b0", "rst == 1'b1")]
    return _seq(f"sipo_{bits}bit", s, c, text, rst="rst", nvec=20)

def _make_piso(bits, text):
    s = [_sig("clk","input",1,is_clock=True),_sig("rst","input",1,is_reset=True),
         _sig("load","input"),_sig("pin","input",bits),_sig("sout","output")]
    c = [_scond("sout == 1'b0", "rst == 1'b1")]
    return _seq(f"piso_{bits}bit", s, c, text, rst="rst", nvec=20)


# ══════════════════════════════════════════════════════════════
# COUNTERS
# ══════════════════════════════════════════════════════════════

def _make_up_counter(bits, text):
    rst_alow = re.search(r"rst_n|active.low|active low", text.lower()) is not None
    rst_name = "rst_n" if rst_alow else "rst"
    s = [_sig("clk","input",1,is_clock=True),
         _sig(rst_name,"input",1,is_reset=True,active_low=rst_alow),
         _sig("q","output",bits)]
    rst_cond = f"{rst_name} == 1'b0" if rst_alow else f"{rst_name} == 1'b1"
    run_cond = f"{rst_name} == 1'b1" if rst_alow else f"{rst_name} == 1'b0"
    c = [_scond(f"q == {bits}'b0", rst_cond),
         _scond(f"q == q + 1",     run_cond)]
    return _seq(f"counter_{bits}bit", s, c, text, rst=rst_name, alow=rst_alow, nvec=30)

def _make_down_counter(bits, text):
    rst_alow = re.search(r"rst_n|active.low", text.lower()) is not None
    rst_name = "rst_n" if rst_alow else "rst"
    s = [_sig("clk","input",1,is_clock=True),
         _sig(rst_name,"input",1,is_reset=True,active_low=rst_alow),
         _sig("q","output",bits)]
    rst_cond = f"{rst_name} == 1'b0" if rst_alow else f"{rst_name} == 1'b1"
    run_cond = f"{rst_name} == 1'b1" if rst_alow else f"{rst_name} == 1'b0"
    c = [_scond(f"q == {bits}'b0",              rst_cond),
         _scond(f"q == q - 1", run_cond)]
    return _seq(f"down_counter_{bits}bit", s, c, text, rst=rst_name, alow=rst_alow, nvec=30)

def _make_updown_counter(bits, text):
    rst_alow = re.search(r"rst_n|active.low", text.lower()) is not None
    rst_name = "rst_n" if rst_alow else "rst"
    s = [_sig("clk","input",1,is_clock=True),
         _sig(rst_name,"input",1,is_reset=True,active_low=rst_alow),
         _sig("up_down","input"),_sig("q","output",bits)]
    rst_cond = f"{rst_name} == 1'b0" if rst_alow else f"{rst_name} == 1'b1"
    run_cond = f"{rst_name} == 1'b1" if rst_alow else f"{rst_name} == 1'b0"
    c = [_scond(f"q == {bits}'b0",              rst_cond),
         _scond(f"q == q + 1",   f"({run_cond}) && up_down==1"),
         _scond(f"q == q - 1",   f"({run_cond}) && up_down==0")]
    return _seq(f"updown_counter_{bits}bit", s, c, text, rst=rst_name, alow=rst_alow, nvec=30)

def _make_bcd_counter(text):
    rst_alow = re.search(r"rst_n|active.low", text.lower()) is not None
    rst_name = "rst_n" if rst_alow else "rst"
    s = [_sig("clk","input",1,is_clock=True),
         _sig(rst_name,"input",1,is_reset=True,active_low=rst_alow),
         _sig("q","output",4),_sig("tc","output")]
    rst_cond = f"{rst_name} == 1'b0" if rst_alow else f"{rst_name} == 1'b1"
    run_cond = f"{rst_name} == 1'b1" if rst_alow else f"{rst_name} == 1'b0"
    c = [_scond("q == 4'b0000",  rst_cond),
         _scond("q == 4'b0000",  f"({run_cond}) && q==4'd9"),
         _scond("q == q + 1",    f"({run_cond}) && q!=4'd9"),
         _scond("tc == (q==4'd9)","1")]
    return _seq("bcd_counter", s, c, text, rst=rst_name, alow=rst_alow, nvec=30)

def _make_ring_counter(bits, text):
    s = [_sig("clk","input",1,is_clock=True),_sig("rst","input",1,is_reset=True),
         _sig("q","output",bits)]
    c = [_scond(f"q == {bits}'b{'1'+'0'*(bits-1)}", "rst == 1'b1"),
         _scond(f"q == {{q[{bits-2}:0], q[{bits-1}]}}", "rst == 1'b0")]
    return _seq(f"ring_counter_{bits}bit", s, c, text, rst="rst", nvec=30)

def _make_johnson_counter(bits, text):
    s = [_sig("clk","input",1,is_clock=True),_sig("rst","input",1,is_reset=True),
         _sig("q","output",bits)]
    c = [_scond(f"q == {bits}'b0", "rst == 1'b1"),
         _scond(f"q == {{q[{bits-2}:0], ~q[{bits-1}]}}", "rst == 1'b0")]
    return _seq(f"johnson_counter_{bits}bit", s, c, text, rst="rst", nvec=30)


# ══════════════════════════════════════════════════════════════
# ALU
# ══════════════════════════════════════════════════════════════

def _make_alu(bits, text):
    s = [_sig("a","input",bits),_sig("b","input",bits),_sig("op","input",3),
         _sig("result","output",bits),_sig("zero","output"),_sig("cout","output")]
    # op: 000=add, 001=sub, 010=and, 011=or, 100=xor, 101=not_a, 110=shl, 111=shr
    c = [_cond(f"result == (op==3'b000 ? a+b : op==3'b001 ? a-b : op==3'b010 ? a&b : "
               f"op==3'b011 ? a|b : op==3'b100 ? a^b : op==3'b101 ? ~a : "
               f"op==3'b110 ? a<<1 : a>>1)"),
         _cond("zero == (result == 0)"),
         _cond(f"cout == (op==3'b000 ? (a+b > {(1<<bits)-1}) : op==3'b001 ? (a<b) : 1'b0)")]
    return _combo(f"alu_{bits}bit", s, c, text, 30)


# ══════════════════════════════════════════════════════════════
# BARREL SHIFTER
# ══════════════════════════════════════════════════════════════

def _make_barrel_shifter(bits, text):
    shamt_bits = (bits - 1).bit_length()
    s = [_sig("din","input",bits),_sig("shamt","input",shamt_bits),
         _sig("dir","input"),_sig("dout","output",bits)]
    c = [_cond("dout == (dir ? din >> shamt : din << shamt)")]
    return _combo(f"barrel_shifter_{bits}bit", s, c, text, 20)


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _get_bits(t: str) -> Optional[int]:
    m = re.search(r"(\d+)\s*[-\s]?bit", t)
    return int(m.group(1)) if m else None


# ── Claude API call ───────────────────────────────────────────

def _call_claude_api(text: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    payload = {"model": "claude-sonnet-4-20250514", "max_tokens": 2000,
               "system": _SYSTEM_PROMPT,
               "messages": [{"role": "user",
                              "content": f"Parse this hardware requirement:\n\n{text}"}]}
    resp = requests.post("https://api.anthropic.com/v1/messages",
                         headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    content = resp.json()["content"][0]["text"].strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```\s*$", "", content).strip()
    return content


def _dict_to_spec(data: dict, original_text: str) -> ParsedSpec:
    signals = [SignalSpec(s["name"], s["direction"], int(s.get("width",1)),
                          bool(s.get("is_clock",False)), bool(s.get("is_reset",False)),
                          bool(s.get("active_low",False)))
               for s in data.get("signals", [])]
    conditions = [ConditionSpec(c.get("trigger","*"), c.get("condition","1"),
                                c.get("expected","1"), int(c.get("delay_cycles",0)))
                  for c in data.get("conditions", [])]
    return ParsedSpec(data.get("module_name","dut"), signals, conditions,
                      _build_assertions(conditions),
                      data.get("clock_signal"), data.get("reset_signal"),
                      bool(data.get("reset_active_low",False)),
                      data.get("circuit_type","combinational"),
                      int(data.get("num_test_vectors",20)), original_text)


def _rule_based_fallback(text: str) -> ParsedSpec:
    t = text.lower()
    is_seq = any(k in t for k in ["clk","clock","flip","register","sequential","counter","dff"])
    clk = "clk" if is_seq else None
    rst, rst_alow = None, False
    for rname in ["rst_n","reset_n","rst","reset"]:
        if rname in t:
            rst = rname; rst_alow = rname.endswith("_n"); break
    if is_seq:
        signals = [_sig("clk","input",1,is_clock=True)]
        if rst: signals.append(_sig(rst,"input",1,is_reset=True,active_low=rst_alow))
        signals += [_sig("d","input"),_sig("q","output")]
        conds = [_scond("q == d")]
    else:
        signals = [_sig("a","input"),_sig("b","input"),_sig("y","output")]
        conds = [_cond("y == (a & b)")]
    return ParsedSpec("dut", signals, conds, _build_assertions(conds),
                      clk, rst, rst_alow, "sequential" if is_seq else "combinational",
                      20, text)
