# C-UAS Security Test Lab

A **real-algorithm** counter-UAS pipeline with an attack / fault-injection harness and
**measured, seed-averaged** before/after metrics. Unlike a visual demo, this runs genuine
tracking code (Kalman filter + plot-to-track association) and measures how each class of
cyber attack degrades the system's real performance.

It is the working counterpart to the C-UAS proposal: the proposal's test
catalogue implemented as runnable, measurable experiments.

> **Scope (read before quoting any number).** Component **specifications are real**
> (manufacturer-published; a source is cited with each entry). The **behaviour is modelled**
> from those specs — this is "real components, modelled physics," **not** a real fielded
> C-UAS, **not** any customer's deployment, and **not** an exploit of real RF/C2 links.
> Real ranges are in kilometres; the lab world is scaled down (÷3) for a fast, reproducible
> run. Effects are faithful **in kind**; exact magnitudes on a live system come only from an
> actual assessment. See `NOTICE.md`.

## Install & run

```bash
cd cuas-lab
pip install -r requirements.txt            # numpy, scipy (stdlib otherwise)
```

**Web UI** (design + run; recommended):
```bash
python -m cuas_lab.serve                    # prints the URL (auto-picks a free port, e.g. http://localhost:8099)
```
The UI lets you:
1. **Design your C-UAS system** — load a **preset** or pick from a library of **33 real
   products** across radar, RF/ESM, EO-IR/acoustic, effectors and C2 — each with its
   **published specs** and source (hover the ⓘ). `*` = range not publicly disclosed (sim
   assumption); `SG` = Singapore; `legacy` = older generation.
2. Set the **Hostile / Benign** drone counts (hover the ⓘ — benign = friendly drones that
   test whether the system wrongly fires on them = **fratricide**).
3. **Run** baseline vs. every attack and read the measured impact (table + impact charts).
4. **Compare two presets** side-by-side — which design best protects the asset under attack.
5. **Download results (CSV)** — a hand-off file with the design, counts and scope caveat baked in.

**Terminal** (same engine, same numbers):
```bash
python -m cuas_lab.run                       # baseline vs. every attack
python -m cuas_lab.run gps flood             # baseline vs. named attacks only
python -m cuas_lab.run --hostile 12 --benign 4   # raid size
python -m cuas_lab.run --seeds 1             # single raw run (no averaging) for quick checks
```

Requires Python 3.10+. No GPU, no Unreal, no web framework.
If the server seems stuck, a leftover instance is holding a port — kill it
(`taskkill /F /IM python.exe` on Windows) and start fresh.

## Why results are averaged

A single run is noisy — one marginal drone can flip a kill, making an attack look like it
"helped" (e.g. 20 kills vs a baseline of 19). Every scenario is therefore run over several
random worlds (default **5 seeds**) and the metrics are averaged, so only real, repeatable
effects remain. Values can be fractional; a result **within run-to-run noise shows as "~"**
in the charts rather than a misleading ±1.

## What it contains

- **`world.py`** — ground-truth drones (hostile + benign) and sensor models (radar/RF/EO/
  acoustic) producing noisy detections ("plots"), including field-of-view blind arcs and
  per-radar minimum RCS.
- **`tracker.py`** — a **real** multi-target tracker: constant-velocity Kalman filter per
  track, nearest-neighbour association with a gate, M-of-N confirmation. The component an
  adversary attacks.
- **`attacks.py`** — the attack / fault-injection harness: **18 attacks**, each a real
  transformation of the data entering the tracker — packet loss (DoS), latency, sensor
  flooding, false-track injection, replay/duplicate, GPS/position offset, timestamp anomaly,
  malformed telemetry, **protocol fuzzing (SAPIENT/CoT)**, sensor dropout (EO blind), sensor
  disagreement, track suppression, classification spoof (fratricide), slew-to-cue abuse,
  effector exhaustion, spoofed fire command, track-ID swap, coast exploitation. Protocol
  fuzzing emits the real malformed-message classes (out-of-range, NaN/infinity, oversized,
  stale/out-of-order) a protocol-aware fuzzer produces; a validating C2 rejects them, a
  non-validating one lets them corrupt the track picture.
- **`components.py`** — the real-product library (33 entries) with published specs + sources
  and honesty flags (`range_disclosed: False`, `legacy`, `spec_note`, `origin`). This is what
  turns the lab into a **design-exploration** tool: real range, FoV, min-RCS, effector defeat
  method and C2 resilience genuinely drive the outcome.
- **`run.py`** — the engine: `run_once` (one simulation), `run_api` (seed-averaged, for both
  the UI and CLI), `presets`, `attack_catalog`, `component_catalog`.
- **`serve.py`** — stdlib HTTP server exposing `/api/components`, `/api/presets`,
  `/api/catalog`, `/api/run` and the UI.
- **`ui.html`** — the single-page UI (design grid, presets, compare, charts, CSV export).

## Metrics (measured, not scripted; seed-averaged)

- **Neutralised** — hostiles stopped before reaching the asset (higher is better)
- **Leaked** — hostiles that reached the asset (the failures; higher is worse)
- **In flight** — unresolved at sim end (accounting only; N + Leaked + In flight = total hostiles)
- **Fratricide** — friendly/benign drones engaged by mistake (should be 0)
- **False tracks** — confirmed tracks with no real target behind them
- **Wasted shots** — effector engagements spent on phantoms
- **Track gap %** — share of time a live hostile had no good confirmed track (100% = blind)
- **RMSE (m)** — position error of real tracks

Example (seed-averaged, sound design): **GPS offset** drives Neutralised → 0, Leaked → all,
Track gap → 100%, RMSE → ~167 m — a full, measured break of the detect-to-defeat chain.
**Effector exhaustion** drains the magazine; **flooding/replay** generate false tracks and
wasted engagements. Not every attack causes a leak — mild degradation realistically does not —
but every attack moves a real metric (enforced by the test suite).

## Tests

```bash
python check.py                             # fast pre-demo check (run this before any demo)
python check.py --full                      # whole invariant suite (same as below)
python -m unittest tests.test_lab           # or: python -m pytest
```
The suite locks in the invariants that make the lab credible and the bugs we actually hit:
accounting balances, a sound design holds / a weak design leaks, GPS spoof breaks the chain,
flooding makes false tracks, **every attack moves at least one metric**, and seed-averaging is
deterministic.

## How this differs from the AEGIS simulator (`cuas-sim/`)

- **AEGIS (`cuas-sim/`)** = a polished **browser visual demo**. Modeled JavaScript logic; the
  numbers are illustrative. Its job is to *show* an audience how attacks defeat a C-UAS system.
- **This lab (`cuas-lab/`)** = a **real-algorithm measurement engine**. A genuine Kalman
  tracker fed genuinely corrupted data; the numbers are **measured**. Its job is to *prove* the
  attacks degrade real tracking.

One persuades, one proves.

## Relationship to the other C-UAS assets

- **Proposal** (`proposal/CUAS_PROPOSAL.md`) — the services pitch and test catalogue.
- **AEGIS** (`cuas-sim/`) — the polished, visual browser demo for presentations.
- **This lab** (`cuas-lab/`) — real algorithms + measured attack impact; the credibility and
  tooling layer behind the service.
