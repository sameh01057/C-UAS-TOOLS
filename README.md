# C-UAS Tools

A monorepo of **counter-UAS (C-UAS)** and **robotics security-testing tools** — one visual
simulator and two real-algorithm measurement labs for adversarial security testing.

Each tool demonstrates the same core idea: a cyber adversary can manipulate the data a
detection/safety system relies on, causing it to make a **valid decision on corrupted input** —
blindness, false tracks, fratricide, or collisions — without ever touching the hardware.

---

## Repository contents

| Directory | Stack | What it is |
|-----------|-------|------------|
| [`cuas-sim/`](cuas-sim/) | React + Vite (JavaScript) | **AEGIS** — a browser-based C-UAS detection, tracking, defeat & adversarial-attack simulator. A polished *visual* demo for presentations. |
| [`cuas-lab/`](cuas-lab/) | Python 3.10+ | **C-UAS Security Test Lab** — a *real-algorithm* counter-UAS pipeline (Kalman tracker + plot-to-track association) with an attack/fault-injection harness and **measured, seed-averaged** metrics. |
| [`robotics-lab/`](robotics-lab/) | Python 3.10+ | **Robotics Safety Test Lab** — the general-robotics sibling of the C-UAS lab; the *same engine* applied to a warehouse autonomous mobile robot (AMR). |

> **One persuades, one proves.** `cuas-sim` shows an audience *how* attacks defeat a C-UAS
> system. `cuas-lab` and `robotics-lab` *measure* that the attacks degrade real tracking code.

---

## Quick start

### AEGIS simulator — `cuas-sim/`

A SENTINEL-class C-UAS simulator with an adversarial attack layer (false-track injection,
track suppression, fusion poisoning, saturation, replay, sensor dropout).

```bash
cd cuas-sim
npm install
npm run dev        # opens on http://localhost:5173
```

Build for deployment:

```bash
npm run build      # outputs to dist/
npm run preview    # preview the production build
```

### C-UAS Security Test Lab — `cuas-lab/`

A real-algorithm counter-UAS pipeline with 33 real-product components, a genuine Kalman
tracker, and a full attack catalogue — all with measured, seed-averaged before/after metrics.

```bash
cd cuas-lab
pip install -r requirements.txt            # numpy, scipy

# Web UI (recommended) — design a C-UAS system, run attacks, compare presets, export CSV
python -m cuas_lab.serve                    # prints the URL (e.g. http://localhost:8099)

# Terminal
python -m cuas_lab.run                       # baseline vs. every attack
python -m cuas_lab.run gps flood             # baseline vs. named attacks only
```

### Robotics Safety Test Lab — `robotics-lab/`

The same engine as the C-UAS lab, applied to a warehouse autonomous mobile robot. Includes a
**profile system** — add any robot type (AMR, autonomous boat, cobot…) via a small JSON profile
without changing code.

```bash
cd robotics-lab
pip install -r requirements.txt            # numpy, scipy

# Web UI (recommended)
python -m robo_lab.serve                    # prints the URL (e.g. http://localhost:8109)

# Terminal
python -m robo_lab.run                       # baseline vs. every attack
python -m robo_lab.run gps suppress          # baseline vs. named attacks only
```

---

## Testing

```bash
# C-UAS lab
cd cuas-lab
python check.py                             # fast pre-demo check
python check.py --full                      # whole invariant suite

# Robotics lab
cd robotics-lab
python check.py                             # fast pre-demo check
python check.py --full                      # whole invariant suite
```

Both Python labs require **Python 3.10+**. No GPU, no ROS install needed.

---

## How the tools relate

- **`cuas-sim/`** (AEGIS) — the polished, visual browser demo for presentations. Modeled
  JavaScript logic; numbers are illustrative.
- **`cuas-lab/`** — real algorithms + measured attack impact; the credibility and tooling layer.
  The proposal's test catalogue implemented as runnable, measurable experiments.
- **`robotics-lab/`** — the general-robotics instance of the same method (warehouse AMR, plus a
  profile system for any robot). Shows the method generalises beyond counter-drones.

A drone is itself a robotic system; the robotics lab demonstrates that the attack/fault-injection
method is domain-agnostic.

---

## Scope & honesty

Component **specifications are real** (manufacturer-published; a source is cited with each entry).
The **behaviour is modelled** from those specs — "real components, modelled physics," **not** a
real fielded system, **not** any customer's deployment, and **not** an exploit of real RF/C2 links.
Effects are faithful **in kind**; exact magnitudes on a live system come only from an actual
assessment. See the `NOTICE.md` in each lab.

## License

See each project's directory for details.
