# FixMate AI

Paste broken code, get fixed code back — with a plain-English reason why it broke.

Built for the **Developer Tools** track. Team **RedAnt** — Pugazhenthi, Alfiya.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`. **No API key required** — the local engine runs
fully offline. Add a free [Groq](https://console.groq.com) API key in the sidebar
only if you want to escalate to a cloud LLM for bugs outside the 3 built-in classes.

## What it catches (offline, no LLM needed)

| Error class | Example | How it's fixed |
|---|---|---|
| Missing import | `math.pi` used, no `import math` | Inserts the correct `import` line |
| Syntax error | missing `:` , stray tabs, unbalanced brackets | Targeted repair, then re-parses to confirm |
| Undefined variable | `item` used when the parameter is `items` | Matches against names actually in scope, renames the typo |

Try it instantly with the four example snippets in the sidebar — one of them
(**"Multiple bugs at once"**) has all three error classes stacked in one
function, and the pipeline fixes all of them in a single run.

## Architecture

```
app.py                        Streamlit UI — renders whatever core/engine.py returns
core/
  config.py                   Env-based settings (GROQ_API_KEY, model, retry count)
  models.py                   Typed contracts: Issue, Fix, PipelineStep, AnalysisResult
  engine.py                   Orchestrator: detect → fix → re-verify loop + optional
                               cloud escalation
  llm_client.py                Groq chat-completions wrapper (isolated — local
                               detectors never import it)
  detectors/
    base.py                    Detector interface (detect() + fix())
    missing_import.py          AST-based: walks Name nodes, cross-references a
                               known-module lookup table
    syntax_error.py            Catches SyntaxError, applies targeted repairs
                               (colon, tabs, brackets), loops until it parses
    undefined_variable.py      AST scope analysis + difflib fuzzy match against
                               names actually in scope
examples.py                   One-click demo snippets
test_engine.py                Offline smoke test — run with: python test_engine.py
```

**Why it's built this way:** each error class is owned end-to-end by one
detector (`detect()` finds it, `fix()` repairs it), so adding a fourth error
class later is a new file, not a rewrite. The engine loop treats every fix as
provisional — it always re-parses the result before declaring success, and
logs every step to a `trace` so the UI can show the pipeline's reasoning live
instead of just a final answer.

## Test suite

Four scripts, no pytest required — run any of them directly:

```bash
python test_engine.py                  # 4 example snippets fix correctly & re-parse
python test_stress.py                  # 10 adversarial cases: decorators, walrus
                                        # operator, lambdas, classes, global/nonlocal,
                                        # f-strings (false-positive check) + harder
                                        # syntax repairs + empty input
python test_ui.py                      # drives the real Streamlit UI end-to-end via
                                        # streamlit.testing.v1.AppTest — actually
                                        # clicks "Analyze & Fix", not just checks
                                        # the server boots
python test_settings_propagation.py    # regression test, see note below
```

All 20 cases pass as of the last full audit.

### A real bug found (and fixed) during that audit

`engine.py`, `llm_client.py`, and `detectors/syntax_error.py` originally did
`from core.config import settings` — a snapshot binding taken once, at
import time. Because Streamlit caches imported modules across reruns, typing
a Groq API key into the sidebar (`config.settings = config.load_settings()`)
never actually reached those three modules — they kept using the old,
keyless settings object for the life of the process, so cloud escalation
would silently never activate. Fixed by having them import the `config`
module itself and read `config.settings.xxx` at call time instead of at
import time. `test_settings_propagation.py` drives the real sidebar widget
and fails if this regresses.

## Roadmap (not in this build)

- Multi-file / cross-repo logic errors
- Full CI/CD auto-PR pipeline
- Docker-sandboxed test execution before proposing a fix
- Local/on-device LLM option (no cloud dependency at all)
