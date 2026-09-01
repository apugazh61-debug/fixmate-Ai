# 🛠️ FixMate AI — Autonomous Code Repair, Safety Gate & CI/IDE Pipeline

> **Paste broken code, get verified repairs back — with a plain-English explanation, security validation, and automated GitHub PR creation.**  
> Built for the **Developer Tools** track · Team **RedAnt** — Pugazhenthi, Alfiya.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Node.js 18+](https://img.shields.io/badge/node.js-18+-green.svg)](https://nodejs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests: 16/16 Passed](https://img.shields.io/badge/tests-16%2F16%20passed-brightgreen.svg)]()
[![Offline First](https://img.shields.io/badge/offline-100%25%20functional-success.svg)]()

---

## ⚡ Quick Start

```bash
# 1. Clone and install dependencies
git clone https://github.com/apugazh61-debug/fixmate-Ai.git
cd fixmate-Ai
pip install -r requirements.txt

# 2. Launch the Streamlit Web Application
streamlit run app.py

# 3. (Optional) Launch the FastAPI Webhook & VS Code backend service
uvicorn webhook_app:app --port 8000
```

- **Streamlit Web UI:** `http://localhost:8501` — **No API key required!** The local deterministic engine runs 100% offline.
- **FastAPI CI / IDE Service:** `http://localhost:8000` (Health check at `/health`, IDE diagnostics at `POST /analyze/inline`).

---

## 🌟 Core Architecture & Capabilities

```text
                               ┌──────────────────────────────────────────────┐
                               │             FixMate AI Pipeline              │
                               └──────────────────────┬───────────────────────┘
                                                      │
                       ┌──────────────────────────────┴──────────────────────────────┐
                       ▼                                                             ▼
         ┌───────────────────────────┐                                 ┌───────────────────────────┐
         │     Python Detectors      │                                 │   JavaScript Detectors    │
         ├───────────────────────────┤                                 ├───────────────────────────┤
         │ • Missing Imports (AST)   │                                 │ • Missing CommonJS Module │
         │ • Syntax Errors (Colons)  │                                 │ • JS Syntax & Parentheses │
         │ • Scope Typos (Difflib)   │                                 │ • Lexical Scope Typos     │
         └─────────────┬─────────────┘                                 └─────────────┬─────────────┘
                       └──────────────────────────────┬──────────────────────────────┘
                                                      │
                                                      ▼
                                       ┌─────────────────────────────┐
                                       │   Re-Verify & Ast Check     │
                                       └──────────────┬──────────────┘
                                                      │ (If out of scope / escalates)
                                                      ▼
                                       ┌─────────────────────────────┐
                                       │ Groq LLM + Sibling Context  │
                                       │ (context_gatherer.py walk)  │
                                       └──────────────┬──────────────┘
                                                      │
                       ┌──────────────────────────────┴──────────────────────────────┐
                       ▼                                                             ▼
         ┌───────────────────────────┐                                 ┌───────────────────────────┐
         │   Docker Sandbox Runner   │                                 │   Pre-Merge Safety Gate   │
         ├───────────────────────────┤                                 ├───────────────────────────┤
         │ Ephemeral python:3.12     │                                 │ • Bandit Security Scan    │
         │ Automated Pytest Suite    │                                 │ • Blast Radius Score (%)  │
         │ Verification Runs         │                                 │ • Signature Breaking AST  │
         └───────────────────────────┘                                 └─────────────┬─────────────┘
                                                                                     │
                                                                                     ▼
                                                                       ┌───────────────────────────┐
                                                                       │     GitHub Auto-PR Bot    │
                                                                       │ (Direct PR or CI Webhook) │
                                                                       └───────────────────────────┘
```

### 1. 📴 100% Offline Deterministic Engine (Python & JavaScript)
- **Zero API Key Required:** Sub-50 millisecond deterministic AST and lexical scope repairs for syntax errors, missing imports, and variable typos.
- **Multi-Language Generality:** Extends the exact same `Detector` contract to JavaScript (`core/detectors/javascript/`) with CommonJS/ES module resolution and `node --check` syntax validation.

### 2. 🐳 Docker Sandbox Verification & Automated Pytest Suite
- **Ephemeral Sandbox Execution:** Runs candidate fixes in isolated `python:3.12-slim` containers (`--network none`, 5s timeout) to confirm runtime validity.
- **Test Generation:** Automatically generates unit tests using Groq and executes them against the repaired code.

### 3. 🛡️ Pre-Merge Safety Gate (`core/safety_gate.py`)
- **Bandit Security Diff Scanning:** Runs Bandit in a subprocess to isolate only **NEW** security vulnerabilities introduced by candidate fixes.
- **Blast Radius & Signature Check:** Detects function signature alterations and high blast radius ($>50\%$ file change), blocking unsafe automated PRs.

### 4. 📈 Empirical Confidence Calibration (`core/calibration.py`)
- **Bayesian Prior + Empirical Blending:** Records developer acceptance telemetry in SQLite (`analytics.db`). When $\ge 10$ samples exist for an error class, dynamically calibrates confidence scores based on empirical acceptance rates.

### 5. 🤖 Autonomous GitHub Actions CI Bot (`webhook_app.py`)
- **HMAC SHA-256 Webhook Listener:** Captures CI workflow run failures, extracts Python stack traces, runs FixMate repairs, verifies the fix, and automatically opens a Pull Request or posts a explanatory commit comment.

### 6. 💻 Real-Time VS Code Extension (`vscode-extension/`)
- **Sub-Second Native Diagnostics:** On file save, highlights syntax errors and typos with squiggly underlines.
- **1-Click Quick Fix:** Press `Ctrl + .` / `Cmd + .` and click **"🛠️ FixMate: Apply automated fix"** to instantly repair code via `WorkspaceEdit`.

---

## 📊 Empirical Benchmark Results

Evaluated across a curated **70-snippet evaluation corpus** (60 Python + 10 JavaScript):

| Metric | Condition (i): FixMate Local | Condition (ii): FixMate Hybrid | Condition (iii): Naive Baseline |
|:---|:---:|:---:|:---:|
| **Verified Syntax Clean Rate** | **98.6%** | **98.6%** | 0.0% |
| **Exact Match Ground Truth Rate** | **68.6%** | **68.6%** | 0.0% |
| **Mean Latency (sec)** | **0.0473s** | 0.9853s | 0.0010s |
| **Cost per 1,000 Fixes** | **$0.000 (Free)** | $0.0000 | $0.1500 |
| **Offline Operable** | ✅ 100% Offline | 🔄 Hybrid (Offline First) | ❌ Cloud Required |

Detailed benchmark documentation and charts are available in [benchmark/results.md](benchmark/results.md).

---

## 🧪 Comprehensive Test Matrix (16/16 Test Suites)

Run all test suites locally:

```bash
python test_engine.py                  # Core detector & repair loop
python test_stress.py                  # 10 adversarial edge cases (walrus, lambdas, closures)
python test_ui.py                      # Full Streamlit AppTest browser automation
python test_settings_propagation.py    # Live env setting propagation
python test_sandbox.py                 # Docker availability & output parsing
python test_test_generator.py          # Pytest test generator & sandbox execution
python test_github_integration.py      # GitHub REST API PR creation
python test_webhook_listener.py        # HMAC SHA-256 webhook & CI traceback parsing
python test_context_gatherer.py        # Multi-file AST context crawler
python test_analytics_store.py         # SQLite analytics database migrations & queries
python test_safety_gate.py             # Bandit security diff & blast radius gate
python test_calibration.py             # Empirical Bayes confidence calibration
python test_js_detectors.py            # JavaScript CommonJS & syntax detectors
python test_benchmark_corpus.py        # 70-snippet benchmark corpus integrity check
python test_vscode_smoke.py            # VS Code inline analysis endpoint contract
python test_cross_phase_integration.py # Full cross-phase end-to-end integration
```

---

## 📂 Repository File Map

```text
fixmate_ai/
├── app.py                          # Streamlit interactive UI
├── webhook_app.py                  # FastAPI server (CI Webhook + VS Code backend)
├── core/
│   ├── config.py                   # Live env settings
│   ├── models.py                   # Dataclasses (Issue, Fix, AnalysisResult)
│   ├── engine.py                   # Multi-language pipeline orchestrator
│   ├── llm_client.py               # Isolated Groq client wrapper
│   ├── sandbox.py                  # Docker sandbox execution
│   ├── test_generator.py           # Automated test generation
│   ├── github_integration.py       # GitHub PR creation
│   ├── context_gatherer.py         # AST sibling file crawler
│   ├── analytics_store.py          # SQLite analytics store
│   ├── safety_gate.py              # Bandit security scanner & risk gate
│   ├── calibration.py              # Empirical confidence calibration
│   └── detectors/
│       ├── base.py                 # Detector abstract base class
│       ├── missing_import.py       # Python missing import detector
│       ├── syntax_error.py         # Python syntax error detector
│       ├── undefined_variable.py   # Python typo & scope detector
│       └── javascript/
│           ├── base.py             # JavaScript detector base class
│           ├── missing_import.py   # CommonJS / Node require detector
│           ├── syntax_error.py     # JS syntax & parenthesis repair
│           └── undefined_variable.py # JS lexical scope typo detector
├── pages/
│   └── 1_Analytics.py              # Multipage team analytics dashboard
├── vscode-extension/               # Real-time VS Code extension
│   ├── package.json, tsconfig.json # TypeScript build config
│   ├── src/extension.ts            # Extension diagnostics & Quick Fix provider
│   └── README.md                   # Extension launch guide (F5 debugging)
├── benchmark/
│   ├── corpus.py                   # Curated 70-snippet evaluation corpus
│   ├── run_benchmark.py            # Automated benchmark evaluation runner
│   ├── results.md                  # Detailed benchmark report
│   └── results/                    # Generated charts (accuracy, latency, verified rate)
└── test_*.py                       # 16 comprehensive test suites (100% passing)
```

---

## 👥 Authors & Acknowledgments

- **Team RedAnt** — Pugazhenthi (`apugazh61@gmail.com`), Alfiya
- Built for the **IQOO Hackathon — Developer Tools Track**
- GitHub: [https://github.com/apugazh61-debug/fixmate-Ai](https://github.com/apugazh61-debug/fixmate-Ai)
