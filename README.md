# Natural Language–Driven SystemVerilog Generation and Verification Framework

## 📌 Overview

This project presents a **Natural Language–Driven Framework for Automated SystemVerilog Generation and Hardware Verification**.
It enables users to describe digital circuits in plain English and automatically generates synthesizable RTL, self-checking testbenches, and verification reports.

The framework integrates parsing, code generation, reference modeling, and simulation into a unified pipeline, reducing manual effort in hardware design and verification.

---

## 🚀 Key Features

* 🧠 Natural Language → Hardware Specification Parsing
* ⚙️ Automated DUT (RTL) Generation (SystemVerilog)
* 🧪 Self-checking Testbench Generation
* 📊 Python-Based Reference Model for Golden Validation
* 🖥️ ModelSim Integration for End-to-End Simulation
* 🌐 Web Interface using Flask
* 🔁 Modular and Extensible Architecture

---

## 🏗️ System Architecture

```
User Input (Natural Language)
            ↓
        Parser (NL → Spec)
            ↓
   ┌───────────────┬───────────────┐
   ↓               ↓               ↓
DUT Generator   Testbench Gen   Reference Model
   ↓               ↓               ↓
         SystemVerilog Files + Expected Outputs
                        ↓
                ModelSim Simulation
                        ↓
               Verification Report
```

---

## ⚙️ Tech Stack

* **Backend:** Python (Flask)
* **Frontend:** HTML/CSS/JS
* **Hardware Description:** SystemVerilog
* **Simulation Tool:** ModelSim / QuestaSim
* **APIs:** LLM-based parsing (optional fallback)

---

## 📂 Project Structure

```
.
├── app.py                # Flask backend
├── main.py               # CLI pipeline runner
├── parser.py             # NL → specification parser
├── circuit_generator.py  # RTL (DUT) generator
├── generator.py          # Testbench generator
├── reference_model.py    # Golden reference model
├── modelsim_runner.py    # Simulation automation
├── utils.py              # Utility functions
├── index.html            # Frontend UI
├── requirements.txt      # Dependencies
└── output/               # Generated files (ignored)
```

---

## ▶️ Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/agarwalarpit2006/natural-language-driven-systemverilog-generation-and-verification-framework.git
cd natural-language-driven-systemverilog-generation-and-verification-framework
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the Web App

```bash
python app.py
```

Open in browser:

```
http://localhost:5000
```

---

## 🧪 Example

### Input:

```
Design a full adder with inputs a, b, cin
```

### Output:

* `dut.sv` → RTL implementation
* `testbench.sv` → Automated verification
* Simulation report with PASS/FAIL results

---

## 📊 Key Contributions

* Natural language–driven hardware specification extraction
* Automated RTL and testbench generation pipeline
* Integration of golden reference model for validation
* End-to-end verification using industry-standard simulation tools
* Hybrid AI + deterministic approach for reliability

---

## 🔬 Future Work

* Support for complex sequential circuits and FSMs
* Coverage-driven verification integration
* FPGA synthesis support
* Enhanced LLM-based parsing accuracy
* Cloud-based simulation deployment

---

