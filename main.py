# =============================================================
# main.py  —  End-to-end pipeline orchestrator
# Usage: python main.py "generate a full adder with inputs a b cin"
#        python main.py --gui
# =============================================================

import argparse, sys, os
import parser as nl_parser
import generator as tb_gen
import circuit_generator as dut_gen
import reference_model as ref_model
import modelsim_runner as sim
from utils import log, ensure_output_dir, write_file


def run_pipeline(nl_text, out_dir="output", seed=42, run_sim=False, run_ref=True):
    ensure_output_dir(out_dir)

    log.info("Step 1/4 — Parsing natural language …")
    spec = nl_parser.parse(nl_text)
    log.info(f"  → {spec.module_name} | {spec.circuit_type} | "
             f"{len(spec.signals)} signals | {len(spec.conditions)} conditions")

    log.info("Step 2/4 — Generating DUT (dut.sv) …")
    dut_sv = dut_gen.generate_dut(spec, out_dir)

    log.info("Step 3/4 — Generating Testbench (testbench.sv) …")
    tb_sv = tb_gen.generate_testbench(spec, out_dir)

    ref_report = ""
    if run_ref:
        log.info("Step 4/4 — Running Python reference model …")
        ref_report = ref_model.run_reference_sim(spec, seed=seed)
        write_file(os.path.join(out_dir, "reference_report.txt"), ref_report)

    sim_report = None
    if run_sim:
        log.info("Invoking ModelSim …")
        sim_report = sim.run_modelsim(seed=seed)

    return {
        "spec": spec, "dut_sv": dut_sv, "testbench_sv": tb_sv,
        "ref_report": ref_report, "sim_report": sim_report,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("nl_input", nargs="?")
    ap.add_argument("--out",    default="output")
    ap.add_argument("--seed",   default=42, type=int)
    ap.add_argument("--no-sim", action="store_true")
    ap.add_argument("--no-ref", action="store_true")
    ap.add_argument("--gui",    action="store_true")
    args = ap.parse_args()

    if args.gui:
        import gui; gui.launch(); sys.exit()

    if not args.nl_input:
        print('Usage: python main.py "describe your circuit"')
        sys.exit(1)

    nl = args.nl_input
    if os.path.isfile(nl):
        with open(nl) as f: nl = f.read()

    r = run_pipeline(nl, args.out, args.seed, not args.no_sim, not args.no_ref)
    if r["ref_report"]: print(r["ref_report"])
    if r["sim_report"]: print(r["sim_report"])
    print(f"\nFiles saved to: {args.out}/")
