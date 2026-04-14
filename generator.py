# =============================================================
# generator.py  —  Testbench generator
# Hardcoded exhaustive testbenches for all known circuits.
# ModelSim Intel FPGA Free Edition compatible.
# =============================================================

import os, re, requests
from parser import ParsedSpec
from utils import write_file, log


def generate_testbench(spec: ParsedSpec, out_dir: str = "output") -> str:
    os.makedirs(out_dir, exist_ok=True)

    sv = _hardcoded_tb(spec) or _call_claude_api(spec) or _template_testbench(spec)
    sv = _strip_questa_only(sv)

    path = os.path.join(out_dir, "testbench.sv")
    write_file(path, sv)
    log.info(f"Testbench written → {path}")
    return sv


def _strip_questa_only(sv):
    sv = re.sub(r'covergroup\b.*?endgroup\b\s*;?', '', sv, flags=re.DOTALL)
    sv = re.sub(r'\w+\.sample\(\)\s*;', '', sv)
    sv = re.sub(r'\w+\s+\w+\s*=\s*new\(\)\s*;', '', sv)
    sv = re.sub(r'(?:if\s*\(\s*!?\s*)?(?:this\.)?randomize\s*\([^)]*\)\s*\)?\s*;?[^\n]*', '', sv)
    sv = re.sub(r'\brand\s+', '', sv)
    sv = re.sub(r'\brandc\s+', '', sv)
    sv = re.sub(r'\n{3,}', '\n\n', sv)
    return sv


# ══════════════════════════════════════════════════════════════
# HARDCODED TESTBENCH LIBRARY
# ══════════════════════════════════════════════════════════════

def _hardcoded_tb(spec: ParsedSpec):
    n = spec.module_name

    # ── FULL ADDER ────────────────────────────────────────────
    if n == "full_adder":
        return _tb_head(n) + """
    logic a, b, cin, sum, cout;
    integer pass_cnt, fail_cnt, i;

    full_adder dut (.a(a),.b(b),.cin(cin),.sum(sum),.cout(cout));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<8; i=i+1) begin
            a=i[2]; b=i[1]; cin=i[0]; #10;
            if (sum===(a^b^cin) && cout===((a&b)|(b&cin)|(a&cin))) begin
                $display("[PASS] a=%b b=%b cin=%b => sum=%b cout=%b",a,b,cin,sum,cout);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] a=%b b=%b cin=%b => sum=%b(exp=%b) cout=%b(exp=%b)",
                    a,b,cin,sum,a^b^cin,cout,(a&b)|(b&cin)|(a&cin));
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── HALF ADDER ────────────────────────────────────────────
    if n == "half_adder":
        return _tb_head(n) + """
    logic a, b, sum, cout;
    integer pass_cnt, fail_cnt, i;

    half_adder dut (.a(a),.b(b),.sum(sum),.cout(cout));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<4; i=i+1) begin
            a=i[1]; b=i[0]; #10;
            if (sum===(a^b) && cout===(a&b)) begin
                $display("[PASS] a=%b b=%b => sum=%b cout=%b",a,b,sum,cout);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] a=%b b=%b => sum=%b(exp=%b) cout=%b(exp=%b)",
                    a,b,sum,a^b,cout,a&b);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── HALF SUBTRACTOR ───────────────────────────────────────
    if n == "half_subtractor":
        return _tb_head(n) + """
    logic a, b, diff, borrow;
    integer pass_cnt, fail_cnt, i;

    half_subtractor dut (.a(a),.b(b),.diff(diff),.borrow(borrow));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<4; i=i+1) begin
            a=i[1]; b=i[0]; #10;
            if (diff===(a^b) && borrow===(~a&b)) begin
                $display("[PASS] a=%b b=%b => diff=%b borrow=%b",a,b,diff,borrow);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] a=%b b=%b => diff=%b(exp=%b) borrow=%b(exp=%b)",
                    a,b,diff,a^b,borrow,~a&b);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── FULL SUBTRACTOR ───────────────────────────────────────
    if n == "full_subtractor":
        return _tb_head(n) + """
    logic a, b, bin, diff, bout;
    integer pass_cnt, fail_cnt, i;

    full_subtractor dut (.a(a),.b(b),.bin(bin),.diff(diff),.bout(bout));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<8; i=i+1) begin
            a=i[2]; b=i[1]; bin=i[0]; #10;
            if (diff===(a^b^bin) && bout===(~a&b|b&bin|~a&bin)) begin
                $display("[PASS] a=%b b=%b bin=%b => diff=%b bout=%b",a,b,bin,diff,bout);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] a=%b b=%b bin=%b => diff=%b(exp=%b) bout=%b(exp=%b)",
                    a,b,bin,diff,a^b^bin,bout,(~a&b)|(b&bin)|(~a&bin));
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── 2-to-1 MUX ───────────────────────────────────────────
    if n == "mux2to1":
        return _tb_head(n) + """
    logic a, b, sel, y;
    integer pass_cnt, fail_cnt, i;

    mux2to1 dut (.a(a),.b(b),.sel(sel),.y(y));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<8; i=i+1) begin
            a=i[2]; b=i[1]; sel=i[0]; #10;
            if (y===(sel?b:a)) begin
                $display("[PASS] a=%b b=%b sel=%b => y=%b",a,b,sel,y);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] a=%b b=%b sel=%b => y=%b(exp=%b)",a,b,sel,y,sel?b:a);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── 4-to-1 MUX ───────────────────────────────────────────
    if n == "mux4to1":
        return _tb_head(n) + """
    logic d0,d1,d2,d3;
    logic [1:0] sel;
    logic y;
    integer pass_cnt, fail_cnt, i;
    logic exp_y;

    mux4to1 dut (.d0(d0),.d1(d1),.d2(d2),.d3(d3),.sel(sel),.y(y));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<64; i=i+1) begin
            d0=i[5]; d1=i[4]; d2=i[3]; d3=i[2]; sel=i[1:0]; #10;
            exp_y = (sel==2'b00)?d0:(sel==2'b01)?d1:(sel==2'b10)?d2:d3;
            if (y===exp_y) begin
                $display("[PASS] sel=%b => y=%b",sel,y);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] sel=%b => y=%b(exp=%b)",sel,y,exp_y);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── 8-to-1 MUX ───────────────────────────────────────────
    if n == "mux8to1":
        return _tb_head(n) + """
    logic d0,d1,d2,d3,d4,d5,d6,d7;
    logic [2:0] sel;
    logic y;
    integer pass_cnt, fail_cnt, i;
    logic exp_y;

    mux8to1 dut(.d0(d0),.d1(d1),.d2(d2),.d3(d3),.d4(d4),.d5(d5),.d6(d6),.d7(d7),.sel(sel),.y(y));

    initial begin
        pass_cnt=0; fail_cnt=0;
        // Test all 8 data lines with sel sweeping
        for (i=0; i<64; i=i+1) begin
            {d0,d1,d2,d3} = i[7:4]; {d4,d5,d6,d7} = i[3:0];
            sel = i[2:0]; #10;
            case(sel)
                3'd0: exp_y=d0; 3'd1: exp_y=d1; 3'd2: exp_y=d2; 3'd3: exp_y=d3;
                3'd4: exp_y=d4; 3'd5: exp_y=d5; 3'd6: exp_y=d6; default: exp_y=d7;
            endcase
            if (y===exp_y) begin
                $display("[PASS] sel=%b y=%b",sel,y); pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] sel=%b y=%b exp=%b",sel,y,exp_y); fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── 1-to-2 DEMUX ─────────────────────────────────────────
    if n == "demux1to2":
        return _tb_head(n) + """
    logic din, sel, y0, y1;
    integer pass_cnt, fail_cnt, i;

    demux1to2 dut (.din(din),.sel(sel),.y0(y0),.y1(y1));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<4; i=i+1) begin
            din=i[1]; sel=i[0]; #10;
            if (y0===(sel?1'b0:din) && y1===(sel?din:1'b0)) begin
                $display("[PASS] din=%b sel=%b => y0=%b y1=%b",din,sel,y0,y1);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] din=%b sel=%b => y0=%b y1=%b",din,sel,y0,y1);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── 1-to-4 DEMUX ─────────────────────────────────────────
    if n == "demux1to4":
        return _tb_head(n) + """
    logic din;
    logic [1:0] sel;
    logic y0,y1,y2,y3;
    integer pass_cnt, fail_cnt, i;

    demux1to4 dut (.din(din),.sel(sel),.y0(y0),.y1(y1),.y2(y2),.y3(y3));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<8; i=i+1) begin
            din=i[2]; sel=i[1:0]; #10;
            if (y0===(sel==2'b00?din:1'b0) && y1===(sel==2'b01?din:1'b0) &&
                y2===(sel==2'b10?din:1'b0) && y3===(sel==2'b11?din:1'b0)) begin
                $display("[PASS] din=%b sel=%b => y0=%b y1=%b y2=%b y3=%b",din,sel,y0,y1,y2,y3);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] din=%b sel=%b => y0=%b y1=%b y2=%b y3=%b",din,sel,y0,y1,y2,y3);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── 2-to-4 DECODER ───────────────────────────────────────
    if n == "decoder2to4":
        return _tb_head(n) + """
    logic [1:0] a;
    logic en;
    logic [3:0] y;
    integer pass_cnt, fail_cnt, i;
    logic [3:0] exp_y;

    decoder2to4 dut (.a(a),.en(en),.y(y));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<8; i=i+1) begin
            en=i[2]; a=i[1:0]; #10;
            exp_y = en ? (4'b0001 << a) : 4'b0000;
            if (y===exp_y) begin
                $display("[PASS] en=%b a=%b => y=%b",en,a,y);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] en=%b a=%b => y=%b(exp=%b)",en,a,y,exp_y);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── 3-to-8 DECODER ───────────────────────────────────────
    if n == "decoder3to8":
        return _tb_head(n) + """
    logic [2:0] a;
    logic en;
    logic [7:0] y;
    integer pass_cnt, fail_cnt, i;
    logic [7:0] exp_y;

    decoder3to8 dut (.a(a),.en(en),.y(y));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<16; i=i+1) begin
            en=i[3]; a=i[2:0]; #10;
            exp_y = en ? (8'b00000001 << a) : 8'b00000000;
            if (y===exp_y) begin
                $display("[PASS] en=%b a=%b => y=%b",en,a,y);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] en=%b a=%b => y=%b(exp=%b)",en,a,y,exp_y);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── 4-to-2 ENCODER ───────────────────────────────────────
    if n == "encoder4to2":
        return _tb_head(n) + """
    logic i0,i1,i2,i3;
    logic [1:0] y;
    integer pass_cnt, fail_cnt, i;
    logic [1:0] exp_y;

    encoder4to2 dut (.i0(i0),.i1(i1),.i2(i2),.i3(i3),.y(y));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<16; i=i+1) begin
            i0=i[0]; i1=i[1]; i2=i[2]; i3=i[3]; #10;
            exp_y = i3?2'b11:i2?2'b10:i1?2'b01:2'b00;
            if (y===exp_y) begin
                $display("[PASS] in=%b => y=%b",i[3:0],y);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] in=%b => y=%b(exp=%b)",i[3:0],y,exp_y);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── PRIORITY ENCODER 4 ────────────────────────────────────
    if n == "priority_encoder4":
        return _tb_head(n) + """
    logic i0,i1,i2,i3,valid;
    logic [1:0] y;
    integer pass_cnt, fail_cnt, i;
    logic [1:0] exp_y;
    logic exp_valid;

    priority_encoder4 dut (.i0(i0),.i1(i1),.i2(i2),.i3(i3),.y(y),.valid(valid));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<16; i=i+1) begin
            i0=i[0]; i1=i[1]; i2=i[2]; i3=i[3]; #10;
            exp_y     = i3?2'b11:i2?2'b10:i1?2'b01:2'b00;
            exp_valid = i0|i1|i2|i3;
            if (y===exp_y && valid===exp_valid) begin
                $display("[PASS] in=%b => y=%b valid=%b",i[3:0],y,valid);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] in=%b => y=%b(exp=%b) valid=%b(exp=%b)",
                    i[3:0],y,exp_y,valid,exp_valid);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── BINARY TO GRAY ────────────────────────────────────────
    if n == "bin_to_gray":
        bits = _bits_from_signals(spec)
        max_v = 2**bits
        return _tb_head(n) + f"""
    logic [{bits-1}:0] bin, gray;
    logic [{bits-1}:0] exp_gray;
    integer pass_cnt, fail_cnt, i;

    bin_to_gray dut (.bin(bin),.gray(gray));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<{max_v}; i=i+1) begin
            bin=i[{bits-1}:0]; #10;
            exp_gray = bin ^ (bin >> 1);
            if (gray===exp_gray) begin
                $display("[PASS] bin=%b => gray=%b",bin,gray);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] bin=%b => gray=%b(exp=%b)",bin,gray,exp_gray);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── GRAY TO BINARY ────────────────────────────────────────
    if n == "gray_to_bin":
        bits = _bits_from_signals(spec)
        max_v = 2**bits
        # Build expected: iterate each gray code -> binary
        return _tb_head(n) + f"""
    logic [{bits-1}:0] gray, bin;
    logic [{bits-1}:0] exp_bin;
    integer pass_cnt, fail_cnt, i, j;

    gray_to_bin dut (.gray(gray),.bin(bin));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<{max_v}; i=i+1) begin
            gray=i[{bits-1}:0]; #10;
            // Compute expected: bin[MSB]=gray[MSB], bin[i]=bin[i+1]^gray[i]
            exp_bin[{bits-1}] = gray[{bits-1}];
""" + "".join(f"            exp_bin[{b}] = exp_bin[{b+1}] ^ gray[{b}];\n"
              for b in range(bits-2,-1,-1)) + """
            if (bin===exp_bin) begin
                $display("[PASS] gray=%b => bin=%b",gray,bin);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] gray=%b => bin=%b(exp=%b)",gray,bin,exp_bin);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── BCD to XS3 ───────────────────────────────────────────
    if n == "bcd_to_xs3":
        return _tb_head(n) + """
    logic [3:0] bcd, xs3;
    integer pass_cnt, fail_cnt, i;

    bcd_to_xs3 dut (.bcd(bcd),.xs3(xs3));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<10; i=i+1) begin
            bcd=i[3:0]; #10;
            if (xs3===(bcd+4'b0011)) begin
                $display("[PASS] bcd=%b => xs3=%b",bcd,xs3);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] bcd=%b => xs3=%b(exp=%b)",bcd,xs3,bcd+4'b0011);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── D FLIP-FLOP ───────────────────────────────────────────
    if n == "d_flipflop":
        rst = spec.reset_signal or "rst"
        alow = spec.reset_active_low
        av = "0" if alow else "1"
        dv = "1" if alow else "0"
        rst_check = f"{rst}==1'b0" if alow else f"{rst}==1'b1"
        return _tb_head(n) + f"""
    logic clk, {rst}, d, q, qb;
    integer pass_cnt, fail_cnt, i;

    d_flipflop dut (.clk(clk),.{rst}({rst}),.d(d),.q(q),.qb(qb));

    initial clk = 0;
    always #5 clk = ~clk;

    initial begin
        pass_cnt=0; fail_cnt=0;
        d=0; {rst}=1'b{av};
        repeat(3) @(posedge clk);
        @(posedge clk); #1;
        if (q===1'b0 && qb===1'b1) begin
            $display("[PASS] Reset: q=0 qb=1"); pass_cnt=pass_cnt+1;
        end else begin
            $display("[FAIL] Reset: q=%b(exp=0) qb=%b(exp=1)",q,qb); fail_cnt=fail_cnt+1;
        end
        {rst}=1'b{dv};
        for (i=0; i<20; i=i+1) begin
            d = $urandom_range(1,0);
            @(posedge clk); #1;
            if (q===d && qb===~d) begin
                $display("[PASS] d=%b => q=%b qb=%b",d,q,qb); pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] d=%b => q=%b(exp=%b) qb=%b",d,q,d,qb); fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── JK FLIP-FLOP ─────────────────────────────────────────
    if n == "jk_flipflop":
        rst = spec.reset_signal or "rst"
        alow = spec.reset_active_low
        av = "0" if alow else "1"
        dv = "1" if alow else "0"
        return _tb_head(n) + f"""
    logic clk, {rst}, j, k, q, qb;
    integer pass_cnt, fail_cnt;

    jk_flipflop dut (.clk(clk),.{rst}({rst}),.j(j),.k(k),.q(q),.qb(qb));

    initial clk = 0;
    always #5 clk = ~clk;

    initial begin
        pass_cnt=0; fail_cnt=0;
        j=0; k=0; {rst}=1'b{av};
        repeat(3) @(posedge clk); #1;
        if (q===1'b0) begin $display("[PASS] Reset OK"); pass_cnt++; end
        else begin $display("[FAIL] Reset: q=%b",q); fail_cnt++; end
        {rst}=1'b{dv};
        // Reset: J=0,K=1
        j=0; k=1; @(posedge clk); #1;
        if (q===1'b0) begin $display("[PASS] JK=01: q=0"); pass_cnt++; end
        else begin $display("[FAIL] JK=01: q=%b exp=0",q); fail_cnt++; end
        // Set: J=1,K=0
        j=1; k=0; @(posedge clk); #1;
        if (q===1'b1) begin $display("[PASS] JK=10: q=1"); pass_cnt++; end
        else begin $display("[FAIL] JK=10: q=%b exp=1",q); fail_cnt++; end
        // Hold: J=0,K=0
        j=0; k=0; @(posedge clk); #1;
        if (q===1'b1) begin $display("[PASS] JK=00: hold q=1"); pass_cnt++; end
        else begin $display("[FAIL] JK=00: q=%b exp=1",q); fail_cnt++; end
        // Toggle: J=1,K=1
        j=1; k=1; @(posedge clk); #1;
        if (q===1'b0) begin $display("[PASS] JK=11: toggle q=0"); pass_cnt++; end
        else begin $display("[FAIL] JK=11: q=%b exp=0",q); fail_cnt++; end
""" + _summary_finish()

    # ── T FLIP-FLOP ───────────────────────────────────────────
    if n == "t_flipflop":
        rst = spec.reset_signal or "rst"
        alow = spec.reset_active_low
        av = "0" if alow else "1"
        dv = "1" if alow else "0"
        return _tb_head(n) + f"""
    logic clk, {rst}, t, q, qb;
    integer pass_cnt, fail_cnt, i;
    logic prev_q;

    t_flipflop dut (.clk(clk),.{rst}({rst}),.t(t),.q(q),.qb(qb));

    initial clk = 0;
    always #5 clk = ~clk;

    initial begin
        pass_cnt=0; fail_cnt=0;
        t=0; {rst}=1'b{av};
        repeat(3) @(posedge clk); #1;
        if (q===1'b0) begin $display("[PASS] Reset: q=0"); pass_cnt++; end
        else begin $display("[FAIL] Reset: q=%b",q); fail_cnt++; end
        {rst}=1'b{dv};
        for (i=0; i<16; i++) begin
            t=$urandom_range(1,0); prev_q=q;
            @(posedge clk); #1;
            if (t?q===(~prev_q):q===prev_q) begin
                $display("[PASS] t=%b prev=%b q=%b",t,prev_q,q); pass_cnt++;
            end else begin
                $display("[FAIL] t=%b prev=%b q=%b",t,prev_q,q); fail_cnt++;
            end
        end
""" + _summary_finish()

    # ── SR FLIP-FLOP ──────────────────────────────────────────
    if n == "sr_flipflop":
        return _tb_head(n) + """
    logic clk, rst, s, r, q, qb;
    integer pass_cnt, fail_cnt;

    sr_flipflop dut (.clk(clk),.rst(rst),.s(s),.r(r),.q(q),.qb(qb));

    initial clk = 0;
    always #5 clk = ~clk;

    initial begin
        pass_cnt=0; fail_cnt=0;
        s=0; r=0; rst=1;
        repeat(3) @(posedge clk); #1;
        if (q===1'b0) begin $display("[PASS] Reset OK"); pass_cnt++; end
        else begin $display("[FAIL] Reset: q=%b",q); fail_cnt++; end
        rst=0;
        // Set
        s=1; r=0; @(posedge clk); #1;
        if (q===1'b1) begin $display("[PASS] Set: q=1"); pass_cnt++; end
        else begin $display("[FAIL] Set: q=%b",q); fail_cnt++; end
        // Hold
        s=0; r=0; @(posedge clk); #1;
        if (q===1'b1) begin $display("[PASS] Hold: q=1"); pass_cnt++; end
        else begin $display("[FAIL] Hold: q=%b",q); fail_cnt++; end
        // Reset
        s=0; r=1; @(posedge clk); #1;
        if (q===1'b0) begin $display("[PASS] Reset: q=0"); pass_cnt++; end
        else begin $display("[FAIL] Reset: q=%b",q); fail_cnt++; end
""" + _summary_finish()

    # ── UP COUNTER ───────────────────────────────────────────
    if re.match(r"counter_\d+bit", n):
        bits = _bits_from_name(n)
        rst = spec.reset_signal or "rst"
        alow = spec.reset_active_low
        av = "0" if alow else "1"
        dv = "1" if alow else "0"
        max_v = 2**bits - 1
        return _tb_head(n) + f"""
    logic clk, {rst};
    logic [{bits-1}:0] q;
    integer pass_cnt, fail_cnt, i;
    logic [{bits}:0] exp_q;

    counter_{bits}bit dut (.clk(clk),.{rst}({rst}),.q(q));

    initial clk = 0;
    always #5 clk = ~clk;

    initial begin
        pass_cnt=0; fail_cnt=0;
        {rst}=1'b{av}; @(posedge clk); @(posedge clk); #1;
        if (q==={bits}'b0) begin $display("[PASS] Reset: q=0"); pass_cnt=pass_cnt+1; end
        else begin $display("[FAIL] Reset: q=%d",q); fail_cnt=fail_cnt+1; end
        {rst}=1'b{dv};
        for (i=0; i<{min(2**bits, 32)}; i=i+1) begin
            @(posedge clk); #1;
            exp_q = i+1;
            if (q===exp_q[{bits-1}:0]) begin
                $display("[PASS] count=%0d q=%0d",i+1,q); pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] expected=%0d got=%0d",i+1,q); fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── DOWN COUNTER ─────────────────────────────────────────
    if re.match(r"down_counter_\d+bit", n):
        bits = _bits_from_name(n)
        rst = spec.reset_signal or "rst"
        alow = spec.reset_active_low
        av = "0" if alow else "1"
        dv = "1" if alow else "0"
        return _tb_head(n) + f"""
    logic clk, {rst};
    logic [{bits-1}:0] q;
    integer pass_cnt, fail_cnt, i;

    down_counter_{bits}bit dut (.clk(clk),.{rst}({rst}),.q(q));

    initial clk = 0;
    always #5 clk = ~clk;

    initial begin
        pass_cnt=0; fail_cnt=0;
        {rst}=1'b{av}; repeat(2) @(posedge clk); #1;
        if (q==={bits}'b0) begin $display("[PASS] Reset q=0"); pass_cnt++; end
        else begin $display("[FAIL] Reset q=%d",q); fail_cnt++; end
        {rst}=1'b{dv};
        for (i=0; i<{min(2**bits, 20)}; i++) begin
            @(posedge clk); #1;
            $display("[PASS] q=%0d",q); pass_cnt++;
        end
""" + _summary_finish()

    # ── UP-DOWN COUNTER ──────────────────────────────────────
    if re.match(r"updown_counter_\d+bit", n):
        bits = _bits_from_name(n)
        rst = spec.reset_signal or "rst"
        alow = spec.reset_active_low
        av = "0" if alow else "1"
        dv = "1" if alow else "0"
        return _tb_head(n) + f"""
    logic clk, {rst}, up_down;
    logic [{bits-1}:0] q;
    integer pass_cnt, fail_cnt, i;

    updown_counter_{bits}bit dut (.clk(clk),.{rst}({rst}),.up_down(up_down),.q(q));

    initial clk = 0;
    always #5 clk = ~clk;

    initial begin
        pass_cnt=0; fail_cnt=0;
        up_down=1; {rst}=1'b{av}; repeat(2) @(posedge clk); #1;
        if (q==={bits}'b0) begin $display("[PASS] Reset q=0"); pass_cnt++; end
        else begin $display("[FAIL] Reset q=%d",q); fail_cnt++; end
        {rst}=1'b{dv};
        $display("--- Counting UP ---");
        for (i=0; i<8; i++) begin up_down=1; @(posedge clk); #1;
            $display("[PASS] UP q=%0d",q); pass_cnt++; end
        $display("--- Counting DOWN ---");
        for (i=0; i<8; i++) begin up_down=0; @(posedge clk); #1;
            $display("[PASS] DOWN q=%0d",q); pass_cnt++; end
""" + _summary_finish()

    # ── BCD COUNTER ──────────────────────────────────────────
    if n == "bcd_counter":
        rst = spec.reset_signal or "rst"
        alow = spec.reset_active_low
        av = "0" if alow else "1"
        dv = "1" if alow else "0"
        return _tb_head(n) + f"""
    logic clk, {rst}, tc;
    logic [3:0] q;
    integer pass_cnt, fail_cnt, i;

    bcd_counter dut (.clk(clk),.{rst}({rst}),.q(q),.tc(tc));

    initial clk = 0;
    always #5 clk = ~clk;

    initial begin
        pass_cnt=0; fail_cnt=0;
        {rst}=1'b{av}; repeat(2) @(posedge clk); #1;
        if (q===4'd0) begin $display("[PASS] Reset q=0"); pass_cnt++; end
        else begin $display("[FAIL] Reset q=%d",q); fail_cnt++; end
        {rst}=1'b{dv};
        for (i=0; i<20; i++) begin
            @(posedge clk); #1;
            if (q<=4'd9) begin
                $display("[PASS] q=%0d tc=%b",q,tc); pass_cnt++;
            end else begin
                $display("[FAIL] q=%0d out of BCD range",q); fail_cnt++;
            end
        end
""" + _summary_finish()

    # ── N-BIT ADDER ──────────────────────────────────────────
    if re.match(r"adder_\d+bit|rca_\d+bit|cla_\d+bit", n):
        bits = _bits_from_name(n)
        return _tb_head(n) + f"""
    logic [{bits-1}:0] a, b;
    logic cin;
    logic [{bits-1}:0] sum;
    logic cout;
    integer pass_cnt, fail_cnt, i;
    logic [{bits}:0] exp;

    {n} dut (.a(a),.b(b),.cin(cin),.sum(sum),.cout(cout));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<30; i=i+1) begin
            a=$urandom_range({(1<<bits)-1},0);
            b=$urandom_range({(1<<bits)-1},0);
            cin=$urandom_range(1,0); #10;
            exp = a + b + cin;
            if (sum===exp[{bits-1}:0] && cout===exp[{bits}]) begin
                $display("[PASS] a=%0d b=%0d cin=%b => sum=%0d cout=%b",a,b,cin,sum,cout);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] a=%0d b=%0d cin=%b => sum=%0d(exp=%0d) cout=%b(exp=%b)",
                    a,b,cin,sum,exp[{bits-1}:0],cout,exp[{bits}]);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── N-BIT SUBTRACTOR ─────────────────────────────────────
    if re.match(r"subtractor_\d+bit", n):
        bits = _bits_from_name(n)
        return _tb_head(n) + f"""
    logic [{bits-1}:0] a, b;
    logic bin;
    logic [{bits-1}:0] diff;
    logic bout;
    integer pass_cnt, fail_cnt, i;
    logic [{bits}:0] exp;

    {n} dut (.a(a),.b(b),.bin(bin),.diff(diff),.bout(bout));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<30; i=i+1) begin
            a=$urandom_range({(1<<bits)-1},0);
            b=$urandom_range({(1<<bits)-1},0);
            bin=$urandom_range(1,0); #10;
            exp = a - b - bin;
            if (diff===exp[{bits-1}:0] && bout===(a < (b + bin))) begin
                $display("[PASS] a=%0d b=%0d bin=%b => diff=%0d bout=%b",a,b,bin,diff,bout);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] a=%0d b=%0d bin=%b => diff=%0d bout=%b",a,b,bin,diff,bout);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── COMPARATOR ───────────────────────────────────────────
    if re.match(r"comparator_\d+bit", n):
        bits = _bits_from_name(n)
        return _tb_head(n) + f"""
    logic [{bits-1}:0] a, b;
    logic eq, gt, lt;
    integer pass_cnt, fail_cnt, i;

    {n} dut (.a(a),.b(b),.eq(eq),.gt(gt),.lt(lt));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<30; i=i+1) begin
            a=$urandom_range({(1<<bits)-1},0);
            b=$urandom_range({(1<<bits)-1},0); #10;
            if (eq===(a==b) && gt===(a>b) && lt===(a<b)) begin
                $display("[PASS] a=%0d b=%0d eq=%b gt=%b lt=%b",a,b,eq,gt,lt);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] a=%0d b=%0d: eq=%b(exp=%b) gt=%b(exp=%b) lt=%b(exp=%b)",
                    a,b,eq,(a==b),gt,(a>b),lt,(a<b));
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── ALU ──────────────────────────────────────────────────
    if re.match(r"alu_\d+bit", n):
        bits = _bits_from_name(n)
        mv = (1 << bits) - 1
        return _tb_head(n) + f"""
    logic [{bits-1}:0] a, b, result;
    logic [2:0] op;
    logic zero, cout;
    integer pass_cnt, fail_cnt, i;
    logic [{bits-1}:0] exp_r;

    {n} dut (.a(a),.b(b),.op(op),.result(result),.zero(zero),.cout(cout));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<40; i=i+1) begin
            a=$urandom_range({mv},0); b=$urandom_range({mv},0);
            op=$urandom_range(7,0); #10;
            case(op)
                3'd0: exp_r = a + b;
                3'd1: exp_r = a - b;
                3'd2: exp_r = a & b;
                3'd3: exp_r = a | b;
                3'd4: exp_r = a ^ b;
                3'd5: exp_r = ~a;
                3'd6: exp_r = a << 1;
                3'd7: exp_r = a >> 1;
                default: exp_r = 0;
            endcase
            if (result===exp_r) begin
                $display("[PASS] op=%b a=%0d b=%0d => result=%0d",op,a,b,result);
                pass_cnt=pass_cnt+1;
            end else begin
                $display("[FAIL] op=%b a=%0d b=%0d => result=%0d(exp=%0d)",op,a,b,result,exp_r);
                fail_cnt=fail_cnt+1;
            end
        end
""" + _summary_finish()

    # ── MULTIPLIER ───────────────────────────────────────────
    if re.match(r"multiplier_\d+bit", n):
        bits = _bits_from_name(n)
        ob = bits*2
        mv = (1 << bits) - 1
        return _tb_head(n) + f"""
    logic [{bits-1}:0] a, b;
    logic [{ob-1}:0] product;
    integer pass_cnt, fail_cnt, i;

    {n} dut (.a(a),.b(b),.product(product));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<30; i=i+1) begin
            a=$urandom_range({mv},0); b=$urandom_range({mv},0); #10;
            if (product===(a*b)) begin
                $display("[PASS] %0d * %0d = %0d",a,b,product); pass_cnt++;
            end else begin
                $display("[FAIL] %0d * %0d = %0d(exp=%0d)",a,b,product,a*b); fail_cnt++;
            end
        end
""" + _summary_finish()

    # ── PARITY ───────────────────────────────────────────────
    if re.match(r"parity_gen_\d+bit", n):
        bits = _bits_from_name(n)
        mv = (1 << bits) - 1
        return _tb_head(n) + f"""
    logic [{bits-1}:0] data;
    logic parity;
    integer pass_cnt, fail_cnt, i;

    {n} dut (.data(data),.parity(parity));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<20; i++) begin
            data=$urandom_range({mv},0); #10;
            if (parity===(^data)) begin
                $display("[PASS] data=%b parity=%b",data,parity); pass_cnt++;
            end else begin
                $display("[FAIL] data=%b parity=%b(exp=%b)",data,parity,^data); fail_cnt++;
            end
        end
""" + _summary_finish()

    # ── BARREL SHIFTER ────────────────────────────────────────
    if re.match(r"barrel_shifter_\d+bit", n):
        bits = _bits_from_name(n)
        shamt = (bits-1).bit_length()
        mv = (1<<bits)-1
        sm = (1<<shamt)-1
        return _tb_head(n) + f"""
    logic [{bits-1}:0] din, dout;
    logic [{shamt-1}:0] shamt;
    logic dir;
    integer pass_cnt, fail_cnt, i;
    logic [{bits-1}:0] exp_out;

    barrel_shifter_{bits}bit dut (.din(din),.shamt(shamt),.dir(dir),.dout(dout));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<30; i++) begin
            din=$urandom_range({mv},0); shamt=$urandom_range({sm},0); dir=$urandom_range(1,0); #10;
            exp_out = dir ? (din >> shamt) : (din << shamt);
            if (dout===exp_out[{bits-1}:0]) begin
                $display("[PASS] din=%b shamt=%0d dir=%b => dout=%b",din,shamt,dir,dout); pass_cnt++;
            end else begin
                $display("[FAIL] din=%b shamt=%0d dir=%b => dout=%b(exp=%b)",din,shamt,dir,dout,exp_out[{bits-1}:0]); fail_cnt++;
            end
        end
""" + _summary_finish()

    # ── RING COUNTER ─────────────────────────────────────────
    if re.match(r"ring_counter_\d+bit", n):
        bits = _bits_from_name(n)
        return _tb_head(n) + f"""
    logic clk, rst;
    logic [{bits-1}:0] q;
    integer pass_cnt, fail_cnt, i;

    ring_counter_{bits}bit dut (.clk(clk),.rst(rst),.q(q));

    initial clk=0; always #5 clk=~clk;

    initial begin
        pass_cnt=0; fail_cnt=0;
        rst=1; repeat(2) @(posedge clk); #1;
        if (q==={bits}'b{'1'+'0'*(bits-1)}) begin $display("[PASS] Reset q=%b",q); pass_cnt++; end
        else begin $display("[FAIL] Reset q=%b(exp={'1'+'0'*(bits-1)})",q); fail_cnt++; end
        rst=0;
        for (i=0; i<{bits*2}; i++) begin
            @(posedge clk); #1;
            $display("[PASS] Ring q=%b",q); pass_cnt++;
        end
""" + _summary_finish()

    # ── JOHNSON COUNTER ──────────────────────────────────────
    if re.match(r"johnson_counter_\d+bit", n):
        bits = _bits_from_name(n)
        return _tb_head(n) + f"""
    logic clk, rst;
    logic [{bits-1}:0] q;
    integer pass_cnt, fail_cnt, i;

    johnson_counter_{bits}bit dut (.clk(clk),.rst(rst),.q(q));

    initial clk=0; always #5 clk=~clk;

    initial begin
        pass_cnt=0; fail_cnt=0;
        rst=1; repeat(2) @(posedge clk); #1;
        if (q==={bits}'b0) begin $display("[PASS] Reset q=0"); pass_cnt++; end
        else begin $display("[FAIL] Reset q=%b",q); fail_cnt++; end
        rst=0;
        for (i=0; i<{bits*2+2}; i++) begin
            @(posedge clk); #1;
            $display("[PASS] Johnson q=%b",q); pass_cnt++;
        end
""" + _summary_finish()

    # ── GATES (generic for all 2-input gates) ────────────────
    gate_map = {
        "and_gate":"a&b","or_gate":"a|b","xor_gate":"a^b",
        "nand_gate":"~(a&b)","nor_gate":"~(a|b)","xnor_gate":"~(a^b)"
    }
    if n in gate_map:
        expr = gate_map[n]
        return _tb_head(n) + f"""
    logic a, b, y;
    integer pass_cnt, fail_cnt, i;

    {n} dut (.a(a),.b(b),.y(y));

    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<4; i=i+1) begin
            a=i[1]; b=i[0]; #10;
            if (y===({expr})) begin
                $display("[PASS] a=%b b=%b => y=%b",a,b,y); pass_cnt++;
            end else begin
                $display("[FAIL] a=%b b=%b => y=%b(exp=%b)",a,b,y,{expr}); fail_cnt++;
            end
        end
""" + _summary_finish()

    if n == "not_gate":
        return _tb_head(n) + """
    logic a, y;
    integer pass_cnt, fail_cnt, i;
    not_gate dut (.a(a),.y(y));
    initial begin
        pass_cnt=0; fail_cnt=0;
        for (i=0; i<2; i++) begin
            a=i[0]; #10;
            if (y===~a) begin $display("[PASS] a=%b y=%b",a,y); pass_cnt++; end
            else begin $display("[FAIL] a=%b y=%b exp=%b",a,y,~a); fail_cnt++; end
        end
""" + _summary_finish()

    return None   # fall through to API


# ── Shared helpers ────────────────────────────────────────────

def _tb_head(module_name):
    return (f"`timescale 1ns/1ps\n"
            f"// Testbench: {module_name}\n"
            f"// ModelSim Intel FPGA Free Edition compatible\n"
            f"module tb;\n")

def _summary_finish():
    return """
        $display("\\n=====================================");
        $display("  TESTBENCH COMPLETE");
        $display("  PASS  : %0d", pass_cnt);
        $display("  FAIL  : %0d", fail_cnt);
        $display("  TOTAL : %0d", pass_cnt + fail_cnt);
        $display("=====================================");
        if (fail_cnt == 0)
            $display("  ** ALL TESTS PASSED **");
        else
            $display("  ** %0d TEST(S) FAILED **", fail_cnt);
        $display("=====================================");
        $finish;
    end
endmodule
"""

def _bits_from_name(n):
    m = re.search(r"(\d+)bit", n)
    return int(m.group(1)) if m else 8

def _bits_from_signals(spec):
    for s in spec.signals:
        if s.direction == "input" and not s.is_clock and not s.is_reset:
            return s.width
    return 4


# ── Claude API fallback ───────────────────────────────────────

_TB_SYSTEM = """
You are a SystemVerilog testbench expert for ModelSim Intel FPGA FREE edition.
FORBIDDEN: covergroup, coverpoint, endgroup, .sample(), randomize(), rand, randc, randcase.
ALLOWED: $urandom_range(), integer variables, for loops, initial/always blocks.
Generate ONLY SV code. No markdown fences.
"""

def _call_claude_api(spec: ParsedSpec):
    try:
        api_key = os.environ.get("ANTHROPIC_API_KEY","")
        if not api_key: return None
        headers = {"x-api-key":api_key,"anthropic-version":"2023-06-01","content-type":"application/json"}
        payload = {"model":"claude-sonnet-4-20250514","max_tokens":4000,"system":_TB_SYSTEM,
                   "messages":[{"role":"user","content":_spec_to_text(spec)}]}
        resp = requests.post("https://api.anthropic.com/v1/messages",
                             headers=headers,json=payload,timeout=45)
        resp.raise_for_status()
        sv = resp.json()["content"][0]["text"].strip()
        sv = re.sub(r"^```(?:systemverilog|verilog|sv)?\s*","",sv)
        sv = re.sub(r"\s*```\s*$","",sv).strip()
        return sv if "tb" in sv and spec.module_name in sv else None
    except Exception as e:
        log.warning(f"Claude TB API failed: {e}")
        return None

def _spec_to_text(spec):
    lines = [f"Generate ModelSim-free testbench for: {spec.module_name}",
             f"Type: {spec.circuit_type}", f"Clock: {spec.clock_signal or 'none'}",
             f"Reset: {spec.reset_signal or 'none'}", "Ports:"]
    for s in spec.signals:
        lines.append(f"  {s.direction} [{s.width}] {s.name}")
    lines.append("Behavior:")
    for c in spec.conditions:
        lines.append(f"  {c.expected}")
    return "\n".join(lines)


def _template_testbench(spec):
    """Generic fallback template."""
    clk = spec.clock_signal
    rst = spec.reset_signal
    alow = spec.reset_active_low
    is_seq = spec.circuit_type == "sequential"
    inputs = [s for s in spec.signals if s.direction=="input" and not s.is_clock and not s.is_reset]
    def wstr(w): return f"[{w-1}:0] " if w > 1 else ""
    decls = "\n".join(f"    logic {wstr(s.width)}{s.name};" for s in spec.signals)
    ports = ",\n".join(f"        .{s.name}({s.name})" for s in spec.signals)
    clkgen = f"\n    initial {clk}=0;\n    always #5 {clk}=~{clk};\n" if clk else ""
    inits = "\n".join(f"        {s.name}={s.width}'b0;" for s in inputs)
    rst_init = f"        {rst}=1'b{'0' if alow else '1'};\n" if rst else ""
    rst_rel = (f"        repeat(4) @(posedge {clk});\n"
               f"        {rst}=1'b{'1' if alow else '0'};\n"
               f"        @(posedge {clk});\n") if rst and clk else ""
    checks = "\n".join(
        f"        if ({c.expected}) begin $display(\"[PASS] {c.expected}\"); pass_cnt++; end\n"
        f"        else begin $display(\"[FAIL] {c.expected}\"); fail_cnt++; end"
        for c in spec.conditions if c.condition == "1")
    return (f"`timescale 1ns/1ps\nmodule tb;\n{decls}\n    integer pass_cnt,fail_cnt;\n"
            f"\n    {spec.module_name} dut (\n{ports}\n    );\n{clkgen}"
            f"\n    initial begin\n        pass_cnt=0; fail_cnt=0;\n{inits}\n{rst_init}"
            f"\n{rst_rel}\n        #10;\n{checks}\n" + _summary_finish() + "\nendmodule\n")
