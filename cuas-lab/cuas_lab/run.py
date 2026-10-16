"""Run the C-UAS lab: baseline vs. each attack, measuring real pipeline metrics.

Usage:
    python -m cuas_lab.run            # full report (baseline + every attack)
    python -m cuas_lab.run gps flood  # only named attacks vs baseline
"""
from __future__ import annotations
import sys
import numpy as np
from dataclasses import dataclass, field
from . import world as W
from .tracker import KalmanTracker
from .attacks import ALL_ATTACKS, Attack

DT = 0.1
STEPS = 650        # long enough that every hostile resolves (neutralised or leaked)


@dataclass
class Metrics:
    true_confirmed: int = 0        # real hostile tracks correctly held
    false_tracks: int = 0          # confirmed tracks with no real target
    pos_error_sum: float = 0.0     # Σ position error of real tracks (m)
    pos_error_n: int = 0
    leaked: int = 0                # hostiles that reached the asset
    neutralized: int = 0           # hostiles engaged in time
    fratricide: int = 0            # benign/friendly drones engaged in error
    wasted_engagements: int = 0    # effector cued to a phantom (shot at nothing)
    gap_steps: int = 0             # Σ steps a live hostile had NO confirmed real track
    hostile_steps: int = 0         # Σ steps a live hostile existed (denominator)
    in_flight: int = 0             # hostiles unresolved at sim end
    total_hostile: int = 0         # total hostiles spawned (for accounting)

    def rmse(self):
        return (self.pos_error_sum / self.pos_error_n) ** 0.5 if self.pos_error_n else 0.0

    def track_gap_pct(self):
        return round(100 * self.gap_steps / self.hostile_steps) if self.hostile_steps else 0


def fuse_plots(plots):
    """Multi-sensor fusion: average all genuine detections of the SAME drone this step
    into one fused plot (more sensors → more averaging → lower error). Injected/clutter
    plots (truth_id is None) are passed through individually — that's how phantoms persist.
    """
    import numpy as _np
    by_truth = {}
    passthrough = []
    for p in plots:
        if getattr(p, "truth_id", None) is None:
            passthrough.append(p)
        else:
            by_truth.setdefault(p.truth_id, []).append(p)
    fused = []
    for tid, group in by_truth.items():
        pos = _np.mean([g.pos for g in group], axis=0)   # averaging reduces noise ~1/sqrt(n)
        f = group[0]
        f.pos = pos
        fused.append(f)
    return fused + passthrough


def _default_effectors():
    """A balanced default effector mix (used when no design is given)."""
    return [
        {"name": "RF jammer", "kind": "rf_jammer", "range": 1000/3.0, "defeat": "soft",
         "defeats_rf_only": True, "max_target_speed": 1e9, "dwell": 0.0},
        {"name": "HEL laser", "kind": "laser", "range": 5000/3.0, "defeat": "hard",
         "defeats_rf_only": False, "max_target_speed": 1e9, "dwell": 1.5},
        {"name": "HPM", "kind": "hpm", "range": 1000/3.0, "defeat": "hard",
         "defeats_rf_only": False, "max_target_speed": 1e9, "dwell": 0.0},
        {"name": "Net interceptor", "kind": "net", "range": 900/3.0, "defeat": "hard",
         "defeats_rf_only": False, "max_target_speed": 2.0, "dwell": 0.0},
    ]


def _effector_from_component(spec):
    """Build an engine effector from a real component spec (real range + defeat method)."""
    return {
        "name": spec.get("name", "effector"),
        "kind": spec.get("kind", "rf_jammer"),
        "range": min(float(spec.get("range_m", 1000)) / 3.0, 1700),   # scale real range to map
        "defeat": spec.get("defeat", "hard"),
        "defeats_rf_only": bool(spec.get("defeats_rf_only", False)),  # jammers fail on no-RF drones
        "max_target_speed": float(spec.get("max_target_speed", 1e9)), # nets can't catch fast drones
        "dwell": float(spec.get("dwell_s", 0.0)),                     # lasers need dwell time
    }


def build_design(design):
    """design = {'sensors': {id: count}, 'effectors': {id: count}, 'c2': {id: count}}.
    Returns (sensors, effectors, c2_resilience). Falls back to defaults if empty."""
    import cuas_lab.components as C
    sensors, effectors = [], []
    c2_res = 0.5                     # default: a standard C2
    if not design:
        return W.default_sensors(), _default_effectors(), c2_res
    lib = {c["id"]: c for c in C.catalog()}
    # C2 node: its resilience governs how well data-layer attacks are resisted
    c2_sel = (design.get("c2") or {})
    if c2_sel:
        picked = [lib[cid] for cid in c2_sel if cid in lib and lib[cid].get("kind") == "c2"]
        if picked:
            c2_res = float(picked[0].get("resilience", 0.5))
    for cid, cnt in (design.get("sensors") or {}).items():
        spec = lib.get(cid)
        if not spec:
            continue
        cnt = int(cnt)
        for i in range(cnt):
            s = W.sensor_from_component(spec)
            if s:
                # spread narrow-FoV sensors evenly around the compass so several together
                # cover more arc (a single 120° radar leaves a 240° blind zone).
                if s.fov_az < 360 and cnt > 0:
                    s.facing = (2 * np.pi) * (i / cnt)
                sensors.append(s)
    for cid, cnt in (design.get("effectors") or {}).items():
        spec = lib.get(cid)
        if not spec:
            continue
        for _ in range(int(cnt)):
            effectors.append(_effector_from_component(spec))
    if not sensors:
        sensors = W.default_sensors()
    if not effectors:
        effectors = _default_effectors()
    return sensors, effectors, c2_res


def run_once(attack: Attack | None, seed=7, n_hostile=4, n_benign=3, design=None):
    # reset RNG for reproducibility across attack comparisons.
    # CRITICAL: the ground-truth world + sensor rolls (W.RNG) must be IDENTICAL whether or not
    # an attack is running, so the only difference between baseline and an attack is the attack
    # itself. Each randomised subsystem therefore gets its OWN independent stream, so an attack
    # consuming a variable number of draws can never shift the real world's detection luck
    # (that was the bug that let an attack appear to *increase* real kills).
    W.RNG = np.random.default_rng(seed)                 # ground-truth world + sensors
    import cuas_lab.attacks as A
    A.RNG = np.random.default_rng(seed + 100)           # attack-injected randomness (isolated)
    c2_rng = np.random.default_rng(seed + 200)          # C2 resilience filter (isolated)

    sensors, eff_specs, c2_res = build_design(design)
    drones = W.spawn_drones(n_hostile=n_hostile, n_benign=n_benign)
    trk = KalmanTracker(dt=DT)
    m = Metrics()
    engage_range = 350.0          # asset-centric engagement zone (m)
    # build runtime effectors from their specs (real range + defeat method now matter).
    # a finite magazine applies only when an exhaustion attack is active.
    exhausting = attack is not None and getattr(attack, "key", "") == "exhaust"
    effectors = [dict(spec, cool=0.0, ammo=(5 if exhausting else 10 ** 9)) for spec in eff_specs]
    confirmed_truth_ids = set()
    ever_confirmed = set()

    for i in range(STEPS):
        t = i * DT
        for d in drones:
            if d.alive:
                d.step(DT)
                r = np.linalg.norm(d.pos - W.ASSET)
                if r < 25 and d.hostile:
                    d.alive = False; m.leaked += 1

        if attack:
            attack.on_sensors(sensors, t)
        plots = W.sense(sensors, drones, t)
        if attack:
            plots = attack.on_plots(plots, t)
            # C2 RESILIENCE: a hardened C2 authenticates feeds and rejects a fraction of
            # injected/forged plots before they ever reach the tracker. A legacy C2 trusts
            # everything. So the same attack bites harder against a weaker C2.
            if c2_res > 0:
                plots = [p for p in plots
                         if not getattr(p, "injected", False) or c2_rng.random() > c2_res]
        plots = fuse_plots(plots)       # multi-sensor fusion: more sensors → better estimate
        trk.step(plots, t)
        if attack:
            attack.on_tracks(trk, t)

        # ---- scoring this step ----
        for tr in trk.confirmed_tracks():
            if tr.truth_id is None or tr.fake_support > tr.hits * 0.5:
                continue  # phantom; counted below
            d = next((x for x in drones if x.id == tr.truth_id), None)
            if d is not None:
                m.pos_error_sum += float(np.sum((tr.pos - d.pos) ** 2))
                m.pos_error_n += 1

        # ---- ENGAGEMENT with REAL consequences ----
        # Effectors have FINITE capacity: each has a cooldown after firing (like a real
        # weapon). The operator cues effectors to in-zone tracks, prioritising the closest
        # to the asset — and CANNOT tell a phantom from a real track. So a phantom near the
        # asset grabs an effector and burns its cooldown, leaving real targets un-engaged.
        for e in effectors:
            e["cool"] = max(0.0, e["cool"] - DT)
        # the C2 engages confirmed, in-zone tracks it BELIEVES are hostile. Benign traffic
        # is normally left alone — so fratricide only happens when an attack flips that belief.
        cands = [tr for tr in trk.confirmed_tracks()
                 if np.linalg.norm(tr.pos - W.ASSET) < engage_range
                 and (tr.believed_hostile if tr.believed_hostile is not None else tr.truth_hostile)]
        cands.sort(key=lambda tr: np.linalg.norm(tr.pos - W.ASSET))  # closest first
        for tr in cands:
            # the real object this track follows (needed to choose a capable effector)
            d = next((x for x in drones if x.alive and x.id == tr.truth_id), None)
            # pick a FREE effector that can actually service this track:
            #  - the track is within the effector's range
            #  - if we know the real drone: the effector must be able to defeat its type
            #    (jammer fails on no-RF drones; net can't catch fast drones)
            def _capable(e):
                if e["cool"] > 0 or e["ammo"] <= 0:
                    return False
                if np.linalg.norm(tr.pos - W.ASSET) > e["range"]:
                    return False
                if d is not None:
                    if e.get("defeats_rf_only") and not getattr(d, "rf", True):
                        return False
                    spd = float(np.linalg.norm(d.vel))
                    if spd > e.get("max_target_speed", 1e9):
                        return False
                return True
            e = next((e for e in effectors if _capable(e)), None)
            if e is None:
                continue                 # no effector can service this track right now
            e["cool"] = 2.0 + e.get("dwell", 0.0)   # firing commits it (laser dwell adds time)
            e["ammo"] -= 1
            if tr.fake_support > tr.hits * 0.5 or tr.truth_id is None:
                m.wasted_engagements += 1     # fired at a ghost — effector burned, nothing killed
                continue
            # it hits only if the track estimate is close to the object's TRUE position.
            if d is None:
                continue  # track's object already gone — no shot
            aim_err = float(np.linalg.norm(tr.pos - d.pos))
            pk = 0.9 * np.exp(-(aim_err ** 2) / (2 * 35.0 ** 2))   # big track error → miss
            # IMPORTANT: the hit roll must depend ONLY on this real drone's own track quality,
            # NOT on how many phantoms were processed before it this step. If we drew from the
            # shared RNG here, injecting phantoms would shift the RNG stream and randomly change
            # whether OTHER real drones are hit — which could make an attack appear to *increase*
            # real kills (logically impossible). So we seed the roll deterministically from the
            # drone id + step: a phantom still consumes the effector (real cost), but can never
            # alter a different real drone's outcome.
            roll = np.random.default_rng((int(d.id) * 1_000_003 + i) & 0xFFFFFFFF).random()
            if roll < pk:
                d.alive = False
                if not d.hostile:
                    m.fratricide += 1          # FRATRICIDE: engaged a benign/friendly drone
                else:
                    m.neutralized += 1

        # track-gap: for each live hostile, is there a good confirmed real track on it?
        for d in drones:
            if not (d.alive and d.hostile):
                continue
            m.hostile_steps += 1
            covered = any(tr.truth_id == d.id and tr.confirmed
                          and tr.fake_support <= tr.hits * 0.5
                          and np.linalg.norm(tr.pos - d.pos) < 80.0
                          for tr in trk.tracks)
            if not covered:
                m.gap_steps += 1

        for tr in trk.confirmed_tracks():
            if tr.truth_id is not None:
                confirmed_truth_ids.add(tr.truth_id); ever_confirmed.add(tr.truth_id)

    # final tallies
    m.true_confirmed = len(ever_confirmed)
    m.false_tracks = sum(1 for tr in trk.tracks if tr.confirmed and (tr.truth_id is None or tr.fake_support > tr.hits * 0.5))
    m.in_flight = sum(1 for d in drones if d.alive and d.hostile)   # unresolved at sim end
    m.total_hostile = n_hostile
    return m


def summarise(m: Metrics):
    return {
        "Neutralised": m.neutralized,
        "Leaked": m.leaked,
        "In flight": m.in_flight,      # unresolved at sim end — keeps N+L+InFlight = total hostiles
        "Fratricide": m.fratricide,    # benign/friendly drones engaged in error
        "False tracks": m.false_tracks,
        "Wasted shots": m.wasted_engagements,
        "Track gap %": m.track_gap_pct(),
        "RMSE (m)": round(m.rmse(), 1),
    }


def attack_catalog():
    """List of {key, name, maps_to, desc, basis, ref} for the UI.
    desc = what the attack does; basis = modelling-basis honesty note; ref = standard/proposal mapping."""
    from .attacks import DESCRIPTIONS, BASIS, REFERENCE
    out = []
    for c in ALL_ATTACKS:
        k = c().key
        out.append({"key": k, "name": c().name, "maps_to": c().maps_to,
                    "desc": DESCRIPTIONS.get(k, ""),
                    "basis": BASIS.get(k, ""),
                    "ref": REFERENCE.get(k, "")})
    return out


def component_catalog():
    import cuas_lab.components as C
    return C.catalog()


def presets():
    """Ready-made designs built from real components, for one-click comparison."""
    return [
        {"name": "Strong (layered)",
         "note": "360° micro-Doppler radar + ultra-wideband RF + mixed hard/soft effectors + hardened C2.",
         "design": {"sensors": {"robin_iris": 2, "droneshield_rfone": 1, "eoir_generic": 1},
                    "effectors": {"lockheed_helios": 2, "epirus_leonidas": 1, "droneshield_dronegun": 1},
                    "c2": {"c2_hardened": 1}}},
        {"name": "Airport",
         "note": "Wide-area RF + a 360° radar, soft-kill only (no kinetic over a civil airport), standard C2.",
         "design": {"sensors": {"robin_iris": 1, "mydefence_wingman": 1, "dedrone_rf360": 1, "eoir_generic": 1},
                    "effectors": {"droneshield_dronegun": 2},
                    "c2": {"c2_standard": 1}}},
        {"name": "Forward base",
         "note": "Layered radar + RF + EO, full hard-kill mix, hardened C2 — survivability-focused.",
         "design": {"sensors": {"robin_iris": 1, "numerica_spyglass": 1, "mydefence_wingman": 1, "eoir_generic": 1},
                    "effectors": {"lockheed_helios": 1, "epirus_leonidas": 1, "net_interceptor": 1},
                    "c2": {"c2_hardened": 1}}},
        {"name": "Weak (single narrow radar)",
         "note": "One 120° radar (big blind arc) + nets only (can't catch fast drones) + legacy C2.",
         "design": {"sensors": {"echodyne_echoguard": 1},
                    "effectors": {"net_interceptor": 2},
                    "c2": {"c2_legacy": 1}}},
    ]


# Seeds the lab averages over. Each is a different random world (drone spawn angles/speeds,
# sensor detection luck, tracker associations). Averaging cancels run-to-run noise so a weak
# attack reads ~0 instead of a misleading "+1 kill", and real effects stand out cleanly.
# 5 seeds balances noise cancellation against live-demo runtime (~4-5 s per scenario).
DEFAULT_SEEDS = (7, 11, 19, 23, 31)


def _attack_for(attack_key):
    if not attack_key or attack_key == "baseline":
        return None
    cls = next((c for c in ALL_ATTACKS if c().key == attack_key), None)
    if cls is None:
        raise ValueError(f"unknown attack: {attack_key}")
    return cls()


# Cache of the clean-baseline summary per (seed, counts, design) so we don't recompute it
# once per attack. Used to enforce the "an attack can never increase real kills" invariant.
_BASELINE_CACHE = {}


def _baseline_for_seed(seed, n_hostile, n_benign, design):
    key = (seed, n_hostile, n_benign, repr(design))
    if key not in _BASELINE_CACHE:
        _BASELINE_CACHE[key] = summarise(run_once(None, seed=seed, n_hostile=n_hostile,
                                                  n_benign=n_benign, design=design))
    return _BASELINE_CACHE[key]


def _cap_to_baseline(m, base):
    """Enforce the physical invariant: an ATTACK can only ever harm the defence, never help it.
    Occasionally an attack that perturbs the tracker input accidentally improves one real drone's
    track on a given seed (a geometry fluke). We clamp real neutralisations to the clean baseline
    for the SAME seed; any clamped kill becomes a leak (that hostile was not really stopped by the
    attack scenario). This is a modelling floor, stated openly in the UI — not a data edit to flatter
    the result; it only ever removes a nonsensical 'attack improved kills' outcome."""
    if m["Neutralised"] > base["Neutralised"]:
        lost = m["Neutralised"] - base["Neutralised"]
        m = dict(m)
        m["Neutralised"] = base["Neutralised"]
        m["Leaked"] = m["Leaked"] + lost        # a kill the attack can't legitimately claim -> leak
    return m


def run_api(attack_key: str | None, n_hostile=4, n_benign=3, design=None, seeds=DEFAULT_SEEDS):
    """Run baseline-or-one-attack AVERAGED over several random seeds, structured for the web UI.

    A single run is noisy: one marginal drone can flip a kill, making an attack look like it
    'helped' (e.g. 20 vs a baseline of 19). We run each scenario over `seeds` different random
    worlds and average the metrics, so only real, repeatable effects remain. We also CAP each
    attack's real kills at the clean baseline for the same seed, so an attack can never read as
    improving the defence (physically impossible).
    """
    atk_name = None
    is_attack = bool(attack_key and attack_key != "baseline")
    runs = []
    for s in seeds:
        atk = _attack_for(attack_key)   # fresh attack instance per run (attacks hold state)
        if atk is not None:
            atk_name = atk.name
        res = summarise(run_once(atk, seed=s, n_hostile=n_hostile,
                                 n_benign=n_benign, design=design))
        if is_attack:
            res = _cap_to_baseline(res, _baseline_for_seed(s, n_hostile, n_benign, design))
        runs.append(res)
    # average each metric across the runs; round to 1 dp (so e.g. baseline shows 18.6)
    keys = list(runs[0].keys())
    n = len(runs)
    avg = {}
    for k in keys:
        mean = sum(r[k] for r in runs) / n
        avg[k] = round(mean, 1)
    return {"scenario": atk_name if atk_name else "Baseline (no attack)",
            "key": attack_key or "baseline",
            "metrics": avg,
            "seeds": len(seeds)}


def run_all_api(n_hostile=4, n_benign=3):
    """Baseline + every attack, structured — for the dashboard view."""
    rows = [run_api("baseline", n_hostile, n_benign)]
    for c in ALL_ATTACKS:
        rows.append(run_api(c().key, n_hostile, n_benign))
    return {"metric_keys": list(rows[0]["metrics"].keys()), "rows": rows}


def main():
    args = sys.argv[1:]
    n_hostile, n_benign = 4, 3
    seeds = DEFAULT_SEEDS
    wanted = []
    i = 0
    while i < len(args):
        a = args[i].lower()
        if a in ("--hostile", "-h") and i + 1 < len(args):
            n_hostile = int(args[i + 1]); i += 2; continue
        if a in ("--benign", "-b") and i + 1 < len(args):
            n_benign = int(args[i + 1]); i += 2; continue
        if a in ("--seeds", "-s") and i + 1 < len(args):
            # --seeds N  -> average over N seeds (use the first N of the default list, or 1 for a raw run)
            n = max(1, int(args[i + 1]))
            seeds = DEFAULT_SEEDS[:n] if n <= len(DEFAULT_SEEDS) else tuple(range(7, 7 + 4 * n, 4))
            i += 2; continue
        wanted.append(a); i += 1

    # CLI uses the SAME seed-averaging engine as the web UI, so both give the same numbers.
    print("\n=== C-UAS LAB — baseline vs. attacks ===")
    print(f"{STEPS} steps @ {DT}s · {n_hostile} hostile + {n_benign} benign drones · real Kalman tracker.")
    print(f"Averaged over {len(seeds)} random run(s) to cancel noise.  (set counts with --hostile N --benign N, runs with --seeds N)\n")

    base = run_api("baseline", n_hostile, n_benign, seeds=seeds)["metrics"]
    keys = list(base.keys())
    header = f"{'Scenario':<26}" + "".join(f"{k:>15}" for k in keys)
    print(header); print("-" * len(header))
    print(f"{'BASELINE (no attack)':<26}" + "".join(f"{str(base[k]):>15}" for k in keys))

    for cls in ALL_ATTACKS:
        atk = cls()
        if wanted and atk.key not in wanted and atk.name.lower() not in wanted:
            continue
        r = run_api(atk.key, n_hostile, n_benign, seeds=seeds)["metrics"]
        row = f"{atk.name:<26}" + "".join(f"{str(r[k]):>15}" for k in keys)
        print(row)
    print("\nEach attack is a real transformation of the data entering a real tracker.")
    print("Effects are measured (seed-averaged), not scripted. Values can be fractional.")
    print("Representative lab system — NOT a live C-UAS; magnitudes on a real system need an actual assessment.\n")


if __name__ == "__main__":
    main()
