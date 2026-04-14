# =============================================================
# app.py  —  Flask REST backend for the web interface
# Run:  python app.py
# URL:  http://localhost:5000
# =============================================================

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os, sys, traceback

sys.path.insert(0, os.path.dirname(__file__))

import parser          as nl_parser
import generator       as tb_gen
import circuit_generator as dut_gen
import reference_model as ref_model
import modelsim_runner as sim_runner
from utils import ensure_output_dir

app = Flask(__name__, static_folder=".")
CORS(app)


@app.route("/health")
def health():
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY", ""))
    return jsonify({"status": "ok", "has_api_key": has_key})


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/generate", methods=["POST"])
def generate():
    body     = request.get_json(force=True)
    nl_text  = body.get("nl_text", "").strip()
    if not nl_text:
        return jsonify({"error": "nl_text is required"}), 400

    out_dir  = body.get("out_dir",  "output")
    seed     = int(body.get("seed",    42))
    run_ref  = bool(body.get("run_ref", True))
    run_sim  = bool(body.get("run_sim", False))

    # Allow the frontend to pass an API key directly
    api_key = body.get("api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key

    ensure_output_dir(out_dir)

    try:
        spec   = nl_parser.parse(nl_text)
        dut_sv = dut_gen.generate_dut(spec, out_dir)
        tb_sv  = tb_gen.generate_testbench(spec, out_dir)

        ref_report  = None
        ref_vectors = []
        if run_ref:
            ref_report = ref_model.run_reference_sim(spec, seed=seed)
            for i, vec in enumerate(ref_model.generate_vectors(spec, seed)[:50]):
                exp = ref_model.compute_expected(spec, vec)
                ref_vectors.append({
                    "idx":      i,
                    "inputs":   {k: hex(v) for k,v in vec.items()},
                    "expected": {k: hex(v) for k,v in exp.items()},
                })

        sim_report = None
        if run_sim:
            sim_report = sim_runner.run_modelsim(seed=seed)

        return jsonify({
            "spec":         _spec_to_dict(spec),
            "dut_sv":       dut_sv,
            "testbench_sv": tb_sv,
            "ref_report":   ref_report,
            "ref_vectors":  ref_vectors,
            "sim_report":   sim_report,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/simulate", methods=["POST"])
def simulate():
    body = request.get_json(force=True)
    seed = int(body.get("seed", 42))
    api_key = body.get("api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key

    if not os.path.exists("output/dut.sv"):
        return jsonify({"error": "Generate a testbench first."}), 400
    try:
        report = sim_runner.run_modelsim(seed=seed)
        return jsonify({"report": report})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _spec_to_dict(spec) -> dict:
    return {
        "module_name":      spec.module_name,
        "circuit_type":     spec.circuit_type,
        "clock_signal":     spec.clock_signal,
        "reset_signal":     spec.reset_signal,
        "reset_active_low": spec.reset_active_low,
        "num_test_vectors": spec.num_test_vectors,
        "description":      spec.description[:200],
        "signals": [
            {"name": s.name, "direction": s.direction, "width": s.width,
             "is_clock": s.is_clock, "is_reset": s.is_reset}
            for s in spec.signals
        ],
        "conditions": [
            {"trigger": c.trigger, "condition": c.condition,
             "expected": c.expected, "delay_cycles": c.delay_cycles}
            for c in spec.conditions
        ],
    }


if __name__ == "__main__":
    print("=" * 52)
    print("  NL → SV Generator  —  Web Backend")
    print("  http://localhost:5000")
    print("  Set ANTHROPIC_API_KEY env var for AI parsing")
    print("=" * 52)
    app.run(debug=True, host="0.0.0.0", port=5000)
