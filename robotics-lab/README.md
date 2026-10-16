# Robotics Safety Test Lab

A **real-algorithm** autonomous-robot perception/safety pipeline with an attack / fault-injection
harness and **measured, seed-averaged** before/after metrics. It runs genuine tracking code
(Kalman filter + plot-to-track association) and measures how each class of cyber attack makes a
**warehouse autonomous mobile robot (AMR)** take an *unsafe action from a valid command*.

This is the **general-robotics sibling of the C-UAS lab** (`../cuas-lab/`): the **same method and
the same engine**, applied to a robot instead of a counter-drone system. It is the HIVE thesis —
*valid command, unsafe outcome when sensor data or state is manipulated across the mission chain* —
on a second embodiment. A drone is itself a robotic system; this shows the method generalises.

> **Scope (read before quoting any number).** Perception-sensor **specifications are real**
> (manufacturer-published; a source is cited with each entry). The **behaviour is modelled** from
> those specs — this is "real components, modelled physics," **not** a real fielded robot, **not**
> any customer's deployment, and **not** an exploit of a real robot's buses. Ranges are scaled down
> (÷3) for a fast, reproducible run. Effects are faithful **in kind**; exact magnitudes on a live
> robot come only from an actual assessment. See `NOTICE.md`.

## The scenario

A warehouse AMR must detect and safely handle **hazards** (people/obstacles moving into its path)
while not needlessly halting for **cleared** objects (safe to pass). The attacks corrupt what the
robot perceives, so it makes a dangerous decision:

| C-UAS lab term | Robotics lab term | Meaning |
|---|---|---|
| Neutralised | **Safely handled** | hazard stopped-for / avoided in time |
| Leaked | **Collisions** | hazard reached the robot un-handled |
| Fratricide | **False stops** | robot halted for a cleared object (availability failure) |
| Effectors | **Safety responses** | emergency stop, dynamic re-plan, speed-zone, RF-tag stop |

## Install & run

```bash
cd robotics-lab
pip install -r requirements.txt            # numpy, scipy (stdlib otherwise)
```

**Web UI** (design + run; recommended):
```bash
python -m robo_lab.serve                    # prints the URL (auto-picks a free port, e.g. http://localhost:8109)
```
The UI lets you:
1. **Design the robot's safety stack** — load a preset or pick real sensors (SICK microScan3,
   Ouster/Velodyne LiDAR, Intel RealSense / ZED cameras, TI mmWave, RF tag reader), safety
   responses, and a controller (hardened / standard ROS 2 / legacy). Hover any ⓘ for specs + source.
2. Set the **Hazards / Cleared** object counts.
3. **Run** baseline vs. every attack and read the measured impact (table + charts).
4. **Compare two presets** — which safety stack prevents more collisions under attack.
5. **Download results (CSV)** — a hand-off file with design, counts and scope caveat baked in.

**Terminal** (same engine, same numbers):
```bash
python -m robo_lab.run                       # baseline vs. every attack
python -m robo_lab.run gps suppress          # baseline vs. named attacks only
python -m robo_lab.run --hazards 12 --cleared 4 --seeds 5
```

Requires Python 3.10+. No GPU, no ROS install needed.

## Attacks (17)

Same harness as the C-UAS lab, framed for a robot: packet loss (DoS), high latency, sensor
flooding, phantom-obstacle injection, replay/duplicate, **localization spoof**, timestamp anomaly,
malformed message, **camera dropout**, sensor disagreement (fusion poisoning), **detection
suppression**, **misclassification** (person read as clear / cleared read as hazard), active-sensor
misdirection, safe-stop exhaustion, spoofed stop/override command, object-ID swap, coast
exploitation. Each carries a plain-language description, a **modelling-basis** note (direction is
the finding; magnitude is modelled) and a **standard mapping** (ROS 2/DDS, localization integrity,
ISO 3691-4 AMR safety, IEC 61508, etc.).

## Why results are averaged + capped

Every scenario is run over several random worlds (default 5 seeds) and averaged, so run-to-run
noise cancels (a result within noise shows as "~"). **Safely-handled hazards are capped at the
clean baseline** for each seed — an attack can only ever *harm* safety, never improve it, so the
tool can never show an attack "helping."

## Tests

```bash
python check.py                             # fast pre-demo check
python check.py --full                      # whole invariant suite
python -m unittest tests.test_lab
```
Locks in: accounting balances, a strong stack holds / a weak one collides, localization spoof
causes collisions, misclassification causes false stops, **every attack moves a metric**, and **no
attack can improve safety**.

## Any robot: the profile system

The engine (tracker + 17 attacks + metrics) is **domain-agnostic**. What makes it "a warehouse AMR"
is a **profile** — plain data describing the robot's objects, outcome vocabulary, available
components and world parameters. **Adding a new robot type = adding a profile, not changing code.**

- In the UI: section **"0 · Choose the robot"** has a dropdown of robot types and an **"Add your
  robot"** panel. Paste a small JSON profile, click *Load this robot*, and it runs immediately with
  its own vocabulary (e.g. a fishing boat shows "Collisions at sea", a cobot "cell intrusion").
- Built-in profiles: **Warehouse AMR** (default; identical to the original lab) and **Autonomous
  fishing boat** (worked marine example: marine radar, AIS, sonar, GNSS; GPS spoof → collision at sea).
- A profile (all keys optional except name) looks like:

```json
{
  "id": "fishing_boat",
  "name": "Autonomous fishing boat",
  "robot_class": "Marine autonomous surface vessel",
  "standard": "IMO COLREGs / MASS guidelines",
  "terms": { "handled": "Safely avoided", "leaked": "Collisions at sea", "false": "Needless stops" },
  "world": { "hazard_speed": [8,26], "object_classes": [ {"name":"vessel","reflectivity":1.0,"rf":true}, {"name":"rock","reflectivity":0.8,"rf":false} ] },
  "components": { "sensors": ["marine_radar","ais_receiver","sonar","gnss_marine"], "responses": ["engine_cut","course_replan"], "controllers": ["ctrl_hardened","ctrl_standard","ctrl_legacy"] },
  "default_design": { "sensors": {"marine_radar":1,"ais_receiver":1,"sonar":1}, "responses": {"engine_cut":1,"course_replan":1}, "c2": {"ctrl_hardened":1} }
}
```

**Import your actual system (not just a type).** A profile can carry its **own hardware specs
inline** via `custom_components` — the customer's real sensors, responses and controller, with
their published ranges / FoV / min-RCS / C2 resilience — so the lab runs *their* parts, not the
stock library. Two ways in the UI:
- **"Import your system (form)"** — a no-JSON wizard: add each sensor (name/type/range/FoV/count),
  each safety response, and a controller resilience slider; it builds the profile, loads it, and
  runs the full assessment on the imported system automatically.
- **"Add your robot (JSON)"** — paste a full profile (with `custom_components`) for the technical user.

This is the honest first step of the §8.3 service ("we model *your* system"): a customer hands you
one self-contained profile and the real attacks run against their actual design.

Profiles live in `robo_lab/profiles.py` (built-ins) or are registered at runtime via the UI /
`POST /api/profile`. **The default (no profile / "amr") reproduces the original lab exactly** —
generalisation is purely additive. What a profile does *not* change: the tracker, the attacks, the
metrics math, the seed-averaging, or the baseline cap. It only changes the objects, the labels and
the component menu. (Honest limit: still 2D point-tracking, not vehicle dynamics or real firmware.)

## Relationship to the other assets

- **C-UAS lab** (`../cuas-lab/`) — the counter-drone instance; same engine.
- **This lab** (`robotics-lab/`) — the general-robotics instance (warehouse AMR).
- Both demonstrate HIVE's method — valid command, unsafe outcome under manipulated state — across
  two verticals, which is the platform story.
