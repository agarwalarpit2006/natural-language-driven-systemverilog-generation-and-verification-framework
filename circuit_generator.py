# =============================================================
# circuit_generator.py  —  DUT generator (AI + hardcoded fallback)
# =============================================================

import os, re, requests
from parser import ParsedSpec
from utils import write_file, log


def generate_dut(spec: ParsedSpec, out_dir: str = "output") -> str:
    os.makedirs(out_dir, exist_ok=True)
    sv = _hardcoded_dut(spec) or _call_claude_api(spec) or _template_dut(spec)
    path = os.path.join(out_dir, "dut.sv")
    write_file(path, sv)
    log.info(f"DUT written → {path}")
    return sv


# ══════════════════════════════════════════════════════════════
# HARDCODED DUT LIBRARY — guaranteed correct RTL
# ══════════════════════════════════════════════════════════════

def _hardcoded_dut(spec: ParsedSpec):
    n = spec.module_name

    # ── Adders ──────────────────────────────────────────────
    if n == "full_adder":
        return _wrap(n, "input a, input b, input cin, output sum, output cout",
            "    assign sum  = a ^ b ^ cin;\n"
            "    assign cout = (a & b) | (b & cin) | (a & cin);", spec)

    if n == "half_adder":
        return _wrap(n, "input a, input b, output sum, output cout",
            "    assign sum  = a ^ b;\n"
            "    assign cout = a & b;", spec)

    if re.match(r"adder_\d+bit|rca_\d+bit|cla_\d+bit", n):
        bits = _bits_from_name(n)
        return _wrap(n, f"input [{bits-1}:0] a, input [{bits-1}:0] b, input cin, "
                        f"output [{bits-1}:0] sum, output cout",
            f"    assign {{cout, sum}} = a + b + cin;", spec)

    # ── Subtractors ──────────────────────────────────────────
    if n == "half_subtractor":
        return _wrap(n, "input a, input b, output diff, output borrow",
            "    assign diff   = a ^ b;\n"
            "    assign borrow = ~a & b;", spec)

    if n == "full_subtractor":
        return _wrap(n, "input a, input b, input bin, output diff, output bout",
            "    assign diff = a ^ b ^ bin;\n"
            "    assign bout = (~a & b) | (b & bin) | (~a & bin);", spec)

    if re.match(r"subtractor_\d+bit", n):
        bits = _bits_from_name(n)
        return _wrap(n, f"input [{bits-1}:0] a, input [{bits-1}:0] b, input bin, "
                        f"output [{bits-1}:0] diff, output bout",
            f"    assign {{bout, diff}} = a - b - bin;", spec)

    # ── Multiplier ───────────────────────────────────────────
    if re.match(r"multiplier_\d+bit", n):
        bits = _bits_from_name(n)
        ob = bits * 2
        return _wrap(n, f"input [{bits-1}:0] a, input [{bits-1}:0] b, output [{ob-1}:0] product",
            "    assign product = a * b;", spec)

    # ── Gates ─────────────────────────────────────────────────
    if n == "and_gate":   return _wrap(n,"input a, input b, output y","    assign y = a & b;",spec)
    if n == "or_gate":    return _wrap(n,"input a, input b, output y","    assign y = a | b;",spec)
    if n == "xor_gate":   return _wrap(n,"input a, input b, output y","    assign y = a ^ b;",spec)
    if n == "nand_gate":  return _wrap(n,"input a, input b, output y","    assign y = ~(a & b);",spec)
    if n == "nor_gate":   return _wrap(n,"input a, input b, output y","    assign y = ~(a | b);",spec)
    if n == "xnor_gate":  return _wrap(n,"input a, input b, output y","    assign y = ~(a ^ b);",spec)
    if n == "not_gate":   return _wrap(n,"input a, output y","    assign y = ~a;",spec)
    if n == "and3_gate":  return _wrap(n,"input a,input b,input c,output y","    assign y = a & b & c;",spec)
    if n == "or3_gate":   return _wrap(n,"input a,input b,input c,output y","    assign y = a | b | c;",spec)
    if n == "nand3_gate": return _wrap(n,"input a,input b,input c,output y","    assign y = ~(a&b&c);",spec)
    if n == "nor3_gate":  return _wrap(n,"input a,input b,input c,output y","    assign y = ~(a|b|c);",spec)
    if n == "xor3_gate":  return _wrap(n,"input a,input b,input c,output y","    assign y = a^b^c;",spec)
    if n == "and4_gate":  return _wrap(n,"input a,input b,input c,input d,output y","    assign y = a&b&c&d;",spec)
    if n == "or4_gate":   return _wrap(n,"input a,input b,input c,input d,output y","    assign y = a|b|c|d;",spec)
    if n == "nand4_gate": return _wrap(n,"input a,input b,input c,input d,output y","    assign y = ~(a&b&c&d);",spec)

    # ── MUX ─────────────────────────────────────────────────
    if n == "mux2to1":
        return _wrap(n,"input a, input b, input sel, output y",
            "    assign y = sel ? b : a;", spec)

    if n == "mux4to1":
        return _wrap(n,"input d0,input d1,input d2,input d3,input [1:0] sel,output y",
            "    assign y = (sel==2'b00)?d0:(sel==2'b01)?d1:(sel==2'b10)?d2:d3;",spec)

    if n == "mux8to1":
        ports = ",".join(f"input d{i}" for i in range(8))+",input [2:0] sel,output y"
        body  = ("    assign y = (sel==3'd0)?d0:(sel==3'd1)?d1:(sel==3'd2)?d2:(sel==3'd3)?d3:\n"
                 "               (sel==3'd4)?d4:(sel==3'd5)?d5:(sel==3'd6)?d6:d7;")
        return _wrap(n, ports, body, spec)

    # ── DEMUX ────────────────────────────────────────────────
    if n == "demux1to2":
        return _wrap(n,"input din,input sel,output y0,output y1",
            "    assign y0 = (sel==1'b0) ? din : 1'b0;\n"
            "    assign y1 = (sel==1'b1) ? din : 1'b0;", spec)

    if n == "demux1to4":
        return _wrap(n,"input din,input [1:0] sel,output y0,output y1,output y2,output y3",
            "    assign y0 = (sel==2'b00)?din:1'b0;\n"
            "    assign y1 = (sel==2'b01)?din:1'b0;\n"
            "    assign y2 = (sel==2'b10)?din:1'b0;\n"
            "    assign y3 = (sel==2'b11)?din:1'b0;", spec)

    # ── ENCODER ─────────────────────────────────────────────
    if n == "encoder4to2":
        return _wrap(n,"input i0,input i1,input i2,input i3,output [1:0] y",
            "    assign y = i3?2'b11:i2?2'b10:i1?2'b01:2'b00;", spec)

    if n == "encoder8to3":
        ports = ",".join(f"input i{i}" for i in range(8))+",output [2:0] y"
        body  = ("    assign y = i7?3'b111:i6?3'b110:i5?3'b101:i4?3'b100:\n"
                 "               i3?3'b011:i2?3'b010:i1?3'b001:3'b000;")
        return _wrap(n, ports, body, spec)

    if n == "priority_encoder4":
        return _wrap(n,"input i0,input i1,input i2,input i3,output [1:0] y,output valid",
            "    assign y     = i3?2'b11:i2?2'b10:i1?2'b01:2'b00;\n"
            "    assign valid = i0|i1|i2|i3;", spec)

    if n == "priority_encoder8":
        ports = ",".join(f"input i{i}" for i in range(8))+",output [2:0] y,output valid"
        body  = ("    assign y     = i7?3'b111:i6?3'b110:i5?3'b101:i4?3'b100:\n"
                 "                   i3?3'b011:i2?3'b010:i1?3'b001:3'b000;\n"
                 "    assign valid = |{i7,i6,i5,i4,i3,i2,i1,i0};")
        return _wrap(n, ports, body, spec)

    # ── DECODER ─────────────────────────────────────────────
    if n == "decoder2to4":
        return _wrap(n,"input [1:0] a, input en, output [3:0] y",
            "    assign y = en ? (4'b0001 << a) : 4'b0000;", spec)

    if n == "decoder3to8":
        return _wrap(n,"input [2:0] a, input en, output [7:0] y",
            "    assign y = en ? (8'b00000001 << a) : 8'b00000000;", spec)

    # ── CODE CONVERTERS ──────────────────────────────────────
    if n == "bin_to_gray":
        bits = _bits_from_signals(spec)
        return _wrap(n,f"input [{bits-1}:0] bin, output [{bits-1}:0] gray",
            "    assign gray = bin ^ (bin >> 1);", spec)

    if n == "gray_to_bin":
        bits = _bits_from_signals(spec)
        # Standard iterative expression for 4-bit
        body = (f"    assign bin[{bits-1}] = gray[{bits-1}];\n" +
                "\n".join(f"    assign bin[{i}] = bin[{i+1}] ^ gray[{i}];"
                          for i in range(bits-2, -1, -1)))
        return _wrap(n, f"input [{bits-1}:0] gray, output [{bits-1}:0] bin", body, spec)

    if n == "bin_to_bcd":
        return _wrap(n,"input [3:0] bin, output [3:0] bcd_tens, output [3:0] bcd_units",
            "    assign bcd_tens  = bin / 10;\n"
            "    assign bcd_units = bin % 10;", spec)

    if n == "bcd_to_xs3":
        return _wrap(n,"input [3:0] bcd, output [3:0] xs3",
            "    assign xs3 = bcd + 4'b0011;", spec)

    if n == "xs3_to_bcd":
        return _wrap(n,"input [3:0] xs3, output [3:0] bcd",
            "    assign bcd = xs3 - 4'b0011;", spec)

    # ── PARITY ───────────────────────────────────────────────
    if re.match(r"parity_gen_\d+bit", n):
        bits = _bits_from_name(n)
        return _wrap(n,f"input [{bits-1}:0] data, output parity",
            "    assign parity = ^data;", spec)

    # ── COMPARATOR ───────────────────────────────────────────
    if re.match(r"comparator_\d+bit", n):
        bits = _bits_from_name(n)
        return _wrap(n,
            f"input [{bits-1}:0] a, input [{bits-1}:0] b, "
            f"output eq, output gt, output lt",
            "    assign eq = (a == b);\n"
            "    assign gt = (a >  b);\n"
            "    assign lt = (a <  b);", spec)

    # ── ALU ──────────────────────────────────────────────────
    if re.match(r"alu_\d+bit", n):
        bits = _bits_from_name(n)
        b1 = bits - 1
        return _wrap(n,
            f"input [{b1}:0] a, input [{b1}:0] b, input [2:0] op, "
            f"output [{b1}:0] result, output zero, output cout",
            f"    reg [{b1}:0] res;\n"
            f"    reg co;\n"
            f"    always @(*) begin\n"
            f"        co = 1'b0;\n"
            f"        case (op)\n"
            f"            3'b000: {{co,res}} = a + b;\n"
            f"            3'b001: begin res = a - b; co = (a < b); end\n"
            f"            3'b010: res = a & b;\n"
            f"            3'b011: res = a | b;\n"
            f"            3'b100: res = a ^ b;\n"
            f"            3'b101: res = ~a;\n"
            f"            3'b110: res = a << 1;\n"
            f"            3'b111: res = a >> 1;\n"
            f"            default: res = {bits}'b0;\n"
            f"        endcase\n"
            f"    end\n"
            f"    assign result = res;\n"
            f"    assign zero   = (res == {bits}'b0);\n"
            f"    assign cout   = co;", spec)

    # ── BARREL SHIFTER ───────────────────────────────────────
    if re.match(r"barrel_shifter_\d+bit", n):
        bits = _bits_from_name(n)
        shamt = (bits-1).bit_length()
        return _wrap(n,
            f"input [{bits-1}:0] din, input [{shamt-1}:0] shamt, input dir, output [{bits-1}:0] dout",
            "    assign dout = dir ? din >> shamt : din << shamt;", spec)

    # ── D FLIP-FLOP ──────────────────────────────────────────
    if n == "d_flipflop":
        rst  = spec.reset_signal or "rst"
        alow = spec.reset_active_low
        rst_cond = f"!{rst}" if alow else rst
        return _wrap(n,
            f"input clk, input {rst}, input d, output reg q, output reg qb",
            f"    always @(posedge clk) begin\n"
            f"        if ({rst_cond}) begin q <= 1'b0; qb <= 1'b1; end\n"
            f"        else begin q <= d; qb <= ~d; end\n"
            f"    end", spec, use_timescale=True)

    # ── JK FLIP-FLOP ─────────────────────────────────────────
    if n == "jk_flipflop":
        rst  = spec.reset_signal or "rst"
        alow = spec.reset_active_low
        rst_cond = f"!{rst}" if alow else rst
        return _wrap(n,
            f"input clk, input {rst}, input j, input k, output reg q, output reg qb",
            f"    always @(posedge clk) begin\n"
            f"        if ({rst_cond}) begin q <= 1'b0; qb <= 1'b1; end\n"
            f"        else begin\n"
            f"            case ({{j,k}})\n"
            f"                2'b00: q <= q;\n"
            f"                2'b01: q <= 1'b0;\n"
            f"                2'b10: q <= 1'b1;\n"
            f"                2'b11: q <= ~q;\n"
            f"            endcase\n"
            f"            qb <= ~q;\n"
            f"        end\n"
            f"    end", spec, use_timescale=True)

    # ── SR FLIP-FLOP ─────────────────────────────────────────
    if n == "sr_flipflop":
        return _wrap(n,
            "input clk, input rst, input s, input r, output reg q, output reg qb",
            "    always @(posedge clk) begin\n"
            "        if (rst) begin q <= 1'b0; qb <= 1'b1; end\n"
            "        else begin\n"
            "            case ({s,r})\n"
            "                2'b00: q <= q;\n"
            "                2'b01: q <= 1'b0;\n"
            "                2'b10: q <= 1'b1;\n"
            "                2'b11: q <= 1'bx;\n"
            "            endcase\n"
            "            qb <= ~q;\n"
            "        end\n"
            "    end", spec, use_timescale=True)

    # ── T FLIP-FLOP ──────────────────────────────────────────
    if n == "t_flipflop":
        rst  = spec.reset_signal or "rst"
        alow = spec.reset_active_low
        rst_cond = f"!{rst}" if alow else rst
        return _wrap(n,
            f"input clk, input {rst}, input t, output reg q, output reg qb",
            f"    always @(posedge clk) begin\n"
            f"        if ({rst_cond}) begin q <= 1'b0; qb <= 1'b1; end\n"
            f"        else begin q <= q ^ t; qb <= ~(q ^ t); end\n"
            f"    end", spec, use_timescale=True)

    # ── D LATCH ──────────────────────────────────────────────
    if n == "d_latch":
        return _wrap(n, "input en, input d, output reg q, output reg qb",
            "    always @(*) begin\n"
            "        if (en) begin q = d; qb = ~d; end\n"
            "    end", spec)

    # ── SR LATCH ─────────────────────────────────────────────
    if n == "sr_latch":
        return _wrap(n, "input s, input r, output reg q, output reg qb",
            "    always @(*) begin\n"
            "        if (s & ~r) begin q = 1'b1; qb = 1'b0; end\n"
            "        else if (~s & r) begin q = 1'b0; qb = 1'b1; end\n"
            "    end", spec)

    # ── REGISTERS ────────────────────────────────────────────
    if re.match(r"register_\d+bit", n):
        bits = _bits_from_name(n)
        rst  = spec.reset_signal or "rst"
        alow = spec.reset_active_low
        rst_cond = f"!{rst}" if alow else rst
        return _wrap(n,
            f"input clk, input {rst}, input load, input [{bits-1}:0] d, output reg [{bits-1}:0] q",
            f"    always @(posedge clk) begin\n"
            f"        if ({rst_cond}) q <= {bits}'b0;\n"
            f"        else if (load) q <= d;\n"
            f"    end", spec, use_timescale=True)

    if re.match(r"sipo_\d+bit", n):
        bits = _bits_from_name(n)
        return _wrap(n,
            f"input clk, input rst, input sin, output reg [{bits-1}:0] pout",
            f"    always @(posedge clk) begin\n"
            f"        if (rst) pout <= {bits}'b0;\n"
            f"        else pout <= {{pout[{bits-2}:0], sin}};\n"
            f"    end", spec, use_timescale=True)

    if re.match(r"siso_\d+bit", n):
        bits = _bits_from_name(n)
        return _wrap(n,
            f"input clk, input rst, input sin, output sout",
            f"    reg [{bits-1}:0] sr;\n"
            f"    always @(posedge clk) begin\n"
            f"        if (rst) sr <= {bits}'b0;\n"
            f"        else sr <= {{sr[{bits-2}:0], sin}};\n"
            f"    end\n"
            f"    assign sout = sr[{bits-1}];", spec, use_timescale=True)

    if re.match(r"piso_\d+bit", n):
        bits = _bits_from_name(n)
        return _wrap(n,
            f"input clk, input rst, input load, input [{bits-1}:0] pin, output sout",
            f"    reg [{bits-1}:0] sr;\n"
            f"    always @(posedge clk) begin\n"
            f"        if (rst) sr <= {bits}'b0;\n"
            f"        else if (load) sr <= pin;\n"
            f"        else sr <= {{1'b0, sr[{bits-1}:1]}};\n"
            f"    end\n"
            f"    assign sout = sr[0];", spec, use_timescale=True)

    # ── COUNTERS ─────────────────────────────────────────────
    if re.match(r"counter_\d+bit", n):
        bits = _bits_from_name(n)
        rst  = spec.reset_signal or "rst"
        alow = spec.reset_active_low
        rst_cond = f"!{rst}" if alow else rst
        return _wrap(n,
            f"input clk, input {rst}, output reg [{bits-1}:0] q",
            f"    always @(posedge clk) begin\n"
            f"        if ({rst_cond}) q <= {bits}'b0;\n"
            f"        else q <= q + 1;\n"
            f"    end", spec, use_timescale=True)

    if re.match(r"down_counter_\d+bit", n):
        bits = _bits_from_name(n)
        rst  = spec.reset_signal or "rst"
        alow = spec.reset_active_low
        rst_cond = f"!{rst}" if alow else rst
        return _wrap(n,
            f"input clk, input {rst}, output reg [{bits-1}:0] q",
            f"    always @(posedge clk) begin\n"
            f"        if ({rst_cond}) q <= {bits}'b0;\n"
            f"        else q <= q - 1;\n"
            f"    end", spec, use_timescale=True)

    if re.match(r"updown_counter_\d+bit", n):
        bits = _bits_from_name(n)
        rst  = spec.reset_signal or "rst"
        alow = spec.reset_active_low
        rst_cond = f"!{rst}" if alow else rst
        return _wrap(n,
            f"input clk, input {rst}, input up_down, output reg [{bits-1}:0] q",
            f"    always @(posedge clk) begin\n"
            f"        if ({rst_cond}) q <= {bits}'b0;\n"
            f"        else if (up_down) q <= q + 1;\n"
            f"        else q <= q - 1;\n"
            f"    end", spec, use_timescale=True)

    if n == "bcd_counter":
        rst  = spec.reset_signal or "rst"
        alow = spec.reset_active_low
        rst_cond = f"!{rst}" if alow else rst
        return _wrap(n,
            f"input clk, input {rst}, output reg [3:0] q, output tc",
            f"    always @(posedge clk) begin\n"
            f"        if ({rst_cond}) q <= 4'b0;\n"
            f"        else if (q == 4'd9) q <= 4'b0;\n"
            f"        else q <= q + 1;\n"
            f"    end\n"
            f"    assign tc = (q == 4'd9);", spec, use_timescale=True)

    if re.match(r"ring_counter_\d+bit", n):
        bits = _bits_from_name(n)
        msb = bits - 1
        return _wrap(n,
            f"input clk, input rst, output reg [{msb}:0] q",
            f"    always @(posedge clk) begin\n"
            f"        if (rst) q <= {bits}'b{'1'+'0'*(bits-1)};\n"
            f"        else q <= {{q[{msb-1}:0], q[{msb}]}};\n"
            f"    end", spec, use_timescale=True)

    if re.match(r"johnson_counter_\d+bit", n):
        bits = _bits_from_name(n)
        msb = bits - 1
        return _wrap(n,
            f"input clk, input rst, output reg [{msb}:0] q",
            f"    always @(posedge clk) begin\n"
            f"        if (rst) q <= {bits}'b0;\n"
            f"        else q <= {{q[{msb-1}:0], ~q[{msb}]}};\n"
            f"    end", spec, use_timescale=True)

    return None   # Fall through to AI


# ── Helpers ───────────────────────────────────────────────────

def _wrap(module_name, ports_str, body, spec, use_timescale=False):
    ts = "`timescale 1ns/1ps\n" if use_timescale else ""
    return (f"// Auto-generated DUT: {module_name}\n"
            f"{ts}"
            f"module {module_name} ({ports_str});\n"
            f"{body}\n"
            f"endmodule  // {module_name}\n")

def _bits_from_name(n):
    m = re.search(r"(\d+)bit", n)
    return int(m.group(1)) if m else 8

def _bits_from_signals(spec):
    for s in spec.signals:
        if s.direction == "input" and not s.is_clock and not s.is_reset:
            return s.width
    return 4


# ── Claude API fallback ───────────────────────────────────────

_DUT_SYSTEM = """
You are a SystemVerilog RTL expert. Generate a complete, synthesizable DUT module.
Rules:
- Use the exact module name and ports specified
- Correct logic implementation (full adder, counter, mux, etc.)
- Use assign for combinational, always_ff/@(posedge clk) for sequential
- Return ONLY SystemVerilog code. No markdown, no explanation.
"""

def _call_claude_api(spec: ParsedSpec):
    try:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key: return None
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        def wstr(w): return f"[{w-1}:0] " if w > 1 else ""
        ports = "\n".join(f"  {s.direction} logic {wstr(s.width)}{s.name}" for s in spec.signals)
        behavior = "\n".join(f"  When ({c.condition}): {c.expected}" for c in spec.conditions)
        prompt = (f"Module: {spec.module_name}\nType: {spec.circuit_type}\n"
                  f"Ports:\n{ports}\nBehavior:\n{behavior}\n"
                  f"Description: {spec.description}")
        payload = {"model":"claude-sonnet-4-20250514","max_tokens":2000,
                   "system":_DUT_SYSTEM,"messages":[{"role":"user","content":prompt}]}
        resp = requests.post("https://api.anthropic.com/v1/messages",
                             headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        sv = resp.json()["content"][0]["text"].strip()
        sv = re.sub(r"^```(?:systemverilog|verilog|sv)?\s*","",sv)
        sv = re.sub(r"\s*```\s*$","",sv).strip()
        return sv if spec.module_name in sv else None
    except Exception as e:
        log.warning(f"Claude DUT API failed: {e}")
        return None


def _template_dut(spec: ParsedSpec) -> str:
    """Last-resort template fallback."""
    def wstr(w): return f"[{w-1}:0] " if w > 1 else ""
    ports = ",\n".join(f"    {s.direction} logic {wstr(s.width)}{s.name}" for s in spec.signals)
    body_lines = []
    for c in spec.conditions:
        m = re.match(r"(.+?)\s*==\s*(.+)", c.expected.strip())
        if m:
            body_lines.append(f"    assign {m.group(1).strip()} = {m.group(2).strip()};")
    body = "\n".join(body_lines) or "    // TODO: implement logic"
    return (f"`timescale 1ns/1ps\nmodule {spec.module_name} (\n{ports}\n);\n"
            f"{body}\nendmodule\n")
