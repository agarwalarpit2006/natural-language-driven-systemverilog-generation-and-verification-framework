# =============================================================
# modelsim_runner.py  —  Compile & simulate with ModelSim
# =============================================================

import subprocess, re, os, datetime


def run_modelsim(seed: int = 42, extra_flags: list = None) -> str:
    extra_flags = extra_flags or []
    do_cmd = (
        "vlib work; "
        "vlog output/dut.sv output/testbench.sv; "
        f"vsim -sv_seed {seed} work.tb {' '.join(extra_flags)}; "
        "run -all; quit -f;"
    )
    try:
        result = subprocess.run(
            ["vsim", "-c", "-do", do_cmd],
            capture_output=True, text=True, timeout=60
        )
        raw = result.stdout + result.stderr
    except FileNotFoundError:
        return (
            "⚠  ModelSim (vsim) not found on PATH.\n"
            "   Install Questa/ModelSim and ensure vsim is in your PATH.\n"
            "   Generated .sv files are in the output/ folder."
        )
    except subprocess.TimeoutExpired:
        return "⚠  Simulation timed out after 60 seconds."
    except Exception as e:
        return f"⚠  Unexpected error: {e}"

    return _parse_output(raw, seed)


def _parse_output(raw: str, seed: int) -> str:
    lines = raw.splitlines()
    pass_lines = [l for l in lines if "[PASS]" in l]
    fail_lines = [l for l in lines if "[FAIL]" in l]
    sva_errors = [l for l in lines if re.search(r'\[SVA', l)]
    errors     = [l for l in lines if re.search(r'^\s*#\s*\*\*\s*(Error|Fatal)', l)]
    warnings   = [l for l in lines if re.search(r'^\s*#\s*\*\*\s*Warning', l)]
    cov_match  = re.search(r'Coverage:\s*([\d.]+)%', raw)
    coverage   = cov_match.group(1) + "%" if cov_match else "N/A"
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    banner = "=" * 52
    report_lines = [
        banner, f"  SIMULATION REPORT  —  {ts}", f"  Seed: {seed}", banner,
        f"  PASS : {len(pass_lines)}", f"  FAIL : {len(fail_lines)}", f"  Coverage : {coverage}", banner,
    ]
    if fail_lines:
        report_lines.append("\n[FAILURES]")
        report_lines.extend(f"  {l.strip()}" for l in fail_lines[:20])
    if sva_errors:
        report_lines.append("\n[SVA VIOLATIONS]")
        report_lines.extend(f"  {l.strip()}" for l in sva_errors[:10])
    if errors:
        report_lines.append("\n[COMPILE / SIM ERRORS]")
        report_lines.extend(f"  {l.strip()}" for l in errors[:10])
    if warnings:
        report_lines.append("\n[WARNINGS]")
        report_lines.extend(f"  {l.strip()}" for l in warnings[:5])
    report_lines.append("\n[FULL LOG]")
    report_lines.extend(lines[-60:])
    report = "\n".join(report_lines)
    os.makedirs("output", exist_ok=True)
    ts_file = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        with open(f"output/report_{ts_file}.txt", "w") as f:
            f.write(report)
    except Exception:
        pass
    return report
