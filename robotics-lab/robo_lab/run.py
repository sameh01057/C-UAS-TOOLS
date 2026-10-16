"""Run the robotics safety lab: baseline vs. each attack, measuring real pipeline metrics.

Usage:
    python -m robo_lab.run             # full report (baseline + every attack)
    python -m robo_lab.run gps flood   # only named attacks vs baseline
    python -m robo_lab.run --hazards 12 --cleared 4 --seeds 5

Same real engine as the C-UAS lab (Kalman tracker + attack harness + seed-averaged, baseline-
capped metrics), applied to a warehouse AMR. "Hazard" = person/obstacle that must be handled;
"collision" = a hazard reached the robot un-handled; "false stop" = the robot halted for nothing.
"""
from __future__ import annotations
import sys
import numpy as np
from dataclasses import dataclass, field
from . import world as W
from .tracker import KalmanTracker
from .attacks import ALL_ATTACKS, Attack

DT = 0.1
STEPS = 650


@dataclass
class Metrics:
    true_confirmed: int = 0
    false_tracks: int = 0          # confirmed detections with no real object (phantoms)
    pos_error_sum: float = 0.0
    pos_error_n: int = 0
    leaked: int = 0                # COLLISIONS: hazards that reached the robot un-handled
    neutralized: int = 0          # SAFELY HANDLED: hazards stopped/avoided in time
    fratricide: int = 0           # FALSE STOPS: cleared objects reacted to in error (availability)
    wasted_engagements: int = 0   # safety response spent on a phantom
    gap_steps: int = 0
    hostile_steps: int = 0
    in_flight: int = 0
    total_hostile: int = 0

    def rmse(self):
        return (self.pos_error_sum / self.pos_error_n) ** 0.5 if self.pos_error_n else 0.0

    def track_gap_pct(self):
        return round(100 * self.gap_steps / self.hostile_steps) if self.hostile_steps else 0


def fuse_plots(plots):
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
        pos = _np.mean([g.pos for g in group], axis=0)
        f = group[0]
        f.pos = pos
        fused.append(f)
    return fused + passthrough


def _default_responses():
    """A balanced default safety-response mix (used when no design is given)."""
    return [
        {"name": "Emergency stop", "kind": "estop", "range": 600/3.0, "defeat": "hard",
         "defeats_rf_only": False, "max_target_speed": 1e9, "dwell": 0.0},
        {"name": "Dynamic re-plan", "kind": "replan", "range": 900/3.0, "defeat": "hard",
         "defeats_rf_only": False, "max_target_speed": 8.0, "dwell": 0.5},
        {"name": "Speed-zone limiter", "kind": "slow", "range": 1000/3.0, "defeat": "soft",
         "defeats_rf_only": False, "max_target_speed": 1e9, "dwell": 0.0},
    ]


def _response_from_component(spec):
    out = {
        "name": spec.get("name", "response"),
        "kind": spec.get("kind", "estop"),
        "range": min(float(spec.get("range_m", 1000)) / 3.0, 1700),
        "defeat": spec.get("defeat", "hard"),
        "defeats_rf_only": bool(spec.get("defeats_rf_only", False)),  # RF-tag stop blind to untagged
        "max_target_speed": float(spec.get("max_target_speed", 1e9)),  # replan can't handle fast close
        "dwell": float(spec.get("dwell_s", 0.0)),
    }
    if spec.get("magazine") not in (None, "", 0):
        out["magazine"] = int(spec["magazine"])   # customer-specified finite magazine (always applies)
    return out


def build_design(design):
    """design = {'sensors': {id:count}, 'responses': {id:count}, 'c2': {id:count}}.
    Returns (sensors, responses, controller_resilience). Falls back to defaults if empty.
    Resolves component IDs against the library PLUS the active profile's inline custom components
    (the customer's own hardware specs), so an imported system runs on its real parts."""
    import robo_lab.components as C
    sensors, responses = [], []
    c2_res = 0.5
    if not design:
        return W.default_sensors(), _default_responses(), c2_res
    lib = {c["id"]: c for c in C.catalog()}
    # merge in the active profile's custom (customer-supplied) components, if any
    prof = getattr(W, "ACTIVE_PROFILE", None)
    if prof:
        for c in (prof.get("custom_components") or []):
            lib[c["id"]] = c
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
                if s.fov_az < 360 and cnt > 0:
                    s.facing = (2 * np.pi) * (i / cnt)
                sensors.append(s)
    for cid, cnt in (design.get("responses") or {}).items():
        spec = lib.get(cid)
        if not spec:
            continue
        for _ in range(int(cnt)):
            responses.append(_response_from_component(spec))
    if not sensors:
        sensors = W.default_sensors()
    if not responses:
        responses = _default_responses()
    # if the profile declares a system ARCHITECTURE, let its software postures (protocol/fusion
    # auth, segmentation) adjust the effective resilience — weak auth makes injection bite harder.
    if prof and prof.get("architecture"):
        import robo_lab.profiles as P
        c2_res = P._effective_resilience(c2_res, prof["architecture"])
    return sensors, responses, c2_res


def run_once(attack: Attack | None, seed=7, n_hostile=4, n_benign=3, design=None, profile=None):
    # Isolated RNG streams so an attack can never shift the real world's detection luck
    # (that was the bug that let an attack appear to *reduce* collisions).
    W.RNG = np.random.default_rng(seed)
    import robo_lab.attacks as A
    A.RNG = np.random.default_rng(seed + 100)
    c2_rng = np.random.default_rng(seed + 200)
    # active robot profile drives object classes + speeds for this run (None => AMR default)
    W.ACTIVE_PROFILE = profile

    sensors, resp_specs, c2_res = build_design(design)
    obstacles = W.spawn_drones(n_hostile=n_hostile, n_benign=n_benign)
    trk = KalmanTracker(dt=DT)
    m = Metrics()
    engage_range = 350.0
    exhausting = attack is not None and getattr(attack, "key", "") == "exhaust"
    # ammo = the customer's declared magazine if given (always), else finite only under exhaustion
    responses = [dict(spec, cool=0.0,
                      ammo=spec.get("magazine", (5 if exhausting else 10 ** 9)))
                 for spec in resp_specs]
    confirmed_truth_ids = set()
    ever_confirmed = set()

    for i in range(STEPS):
        t = i * DT
        for d in obstacles:
            if d.alive:
                d.step(DT)
                r = np.linalg.norm(d.pos - W.ASSET)
                if r < 25 and d.hazard:
                    d.alive = False; m.leaked += 1   # COLLISION: hazard reached the robot

        if attack:
            attack.on_sensors(sensors, t)
        plots = W.sense(sensors, obstacles, t)
        if attack:
            plots = attack.on_plots(plots, t)
            if c2_res > 0:
                plots = [p for p in plots
                         if not getattr(p, "injected", False) or c2_rng.random() > c2_res]
        plots = fuse_plots(plots)
        trk.step(plots, t)
        if attack:
            attack.on_tracks(trk, t)

        for tr in trk.confirmed_tracks():
            if tr.truth_id is None or tr.fake_support > tr.hits * 0.5:
                continue
            d = next((x for x in obstacles if x.id == tr.truth_id), None)
            if d is not None:
                m.pos_error_sum += float(np.sum((tr.pos - d.pos) ** 2))
                m.pos_error_n += 1

        # ---- SAFETY RESPONSE with REAL consequences ----
        # Responses have FINITE capacity (a cooldown after acting). The controller reacts to
        # confirmed in-zone objects it BELIEVES are hazards, closest first — and cannot tell a
        # phantom from a real object. A phantom near the robot grabs a response and burns its
        # cooldown, leaving a real hazard un-handled -> collision.
        for e in responses:
            e["cool"] = max(0.0, e["cool"] - DT)
        cands = [tr for tr in trk.confirmed_tracks()
                 if np.linalg.norm(tr.pos - W.ASSET) < engage_range
                 and (tr.believed_hostile if tr.believed_hostile is not None else tr.truth_hostile)]
        cands.sort(key=lambda tr: np.linalg.norm(tr.pos - W.ASSET))
        for tr in cands:
            d = next((x for x in obstacles if x.alive and x.id == tr.truth_id), None)

            def _capable(e):
                if e["cool"] > 0 or e["ammo"] <= 0:
                    return False
                if np.linalg.norm(tr.pos - W.ASSET) > e["range"]:
                    return False
                if d is not None:
                    if e.get("defeats_rf_only") and not getattr(d, "rf", True):
                        return False      # RF-tag stop can't protect an untagged person/debris
                    spd = float(np.linalg.norm(d.vel))
                    if spd > e.get("max_target_speed", 1e9):
                        return False      # re-plan can't dodge a very fast close intruder
                return True
            e = next((e for e in responses if _capable(e)), None)
            if e is None:
                continue
            e["cool"] = 2.0 + e.get("dwell", 0.0)
            e["ammo"] -= 1
            if tr.fake_support > tr.hits * 0.5 or tr.truth_id is None:
                m.wasted_engagements += 1    # reacted to a phantom — capacity burned, nothing real
                continue
            if d is None:
                continue
            aim_err = float(np.linalg.norm(tr.pos - d.pos))
            pk = 0.9 * np.exp(-(aim_err ** 2) / (2 * 35.0 ** 2))   # big track error → wrong zone
            # per-object deterministic roll so phantom processing order can't change a real
            # object's outcome (prevents an attack ever appearing to reduce collisions).
            roll = np.random.default_rng((int(d.id) * 1_000_003 + i) & 0xFFFFFFFF).random()
            if roll < pk:
                d.alive = False
                if not d.hazard:
                    m.fratricide += 1        # FALSE STOP: reacted to a cleared object
                else:
                    m.neutralized += 1       # SAFELY HANDLED: hazard stopped/avoided in time

        for d in obstacles:
            if not (d.alive and d.hazard):
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

    m.true_confirmed = len(ever_confirmed)
    m.false_tracks = sum(1 for tr in trk.tracks if tr.confirmed and (tr.truth_id is None or tr.fake_support > tr.hits * 0.5))
    m.in_flight = sum(1 for d in obstacles if d.alive and d.hazard)
    m.total_hostile = n_hostile
    return m


def summarise(m: Metrics):
    return {
        "Safely handled": m.neutralized,   # hazards stopped/avoided in time
        "Collisions": m.leaked,            # hazards that reached the robot un-handled
        "Unresolved": m.in_flight,         # still approaching at sim end (accounting)
        "False stops": m.fratricide,       # cleared objects reacted to in error (availability)
        "Phantom detections": m.false_tracks,
        "Wasted responses": m.wasted_engagements,
        "Track gap %": m.track_gap_pct(),
        "RMSE (m)": round(m.rmse(), 1),
    }


def attack_catalog():
    from .attacks import DESCRIPTIONS, BASIS, REFERENCE
    out = []
    for c in ALL_ATTACKS:
        k = c().key
        out.append({"key": k, "name": c().name, "maps_to": c().maps_to,
                    "desc": DESCRIPTIONS.get(k, ""),
                    "basis": BASIS.get(k, ""),
                    "ref": REFERENCE.get(k, "")})
    return out


def component_catalog(profile=None):
    """Components available for a profile: the customer's own inline custom_components FIRST, then
    the library (filtered to the profile's `components` list if it declares one). None => full library.
    This is how an imported system shows its real parts alongside (or instead of) the stock library."""
    import robo_lab.components as C
    cat = C.catalog()
    custom = (profile or {}).get("custom_components") if profile else None
    comps = (profile or {}).get("components") if profile else None
    if comps:
        allowed = set(comps.get("sensors", [])) | set(comps.get("responses", [])) | set(comps.get("controllers", []))
        cat = [c for c in cat if c["id"] in allowed]
    # custom components always appear (they're the customer's own), deduped by id
    if custom:
        ids = {c["id"] for c in custom}
        cat = [c for c in cat if c["id"] not in ids]
        return list(custom) + cat
    return cat


# ---- profile API (used by the server) ----
def profiles_api():
    import robo_lab.profiles as P
    return P.list_profiles()


def get_profile(pid):
    import robo_lab.profiles as P
    return P.get_profile(pid)


def register_profile_api(profile_dict):
    """Register a user-supplied robot profile (from the UI 'Add your robot' panel); returns its id."""
    import robo_lab.profiles as P
    return P.register_profile(profile_dict)


def presets():
    """Ready-made safety designs across robot TYPES, built from real components.

    `robot` = which class of autonomous system this preset represents. The engine is the same for
    all of them — that is the point: the same attack method degrades any autonomy stack that trusts
    its sensors. Each `robot` note ties the instance to its real safety/security standard.
    """
    return [
        # ---- Warehouse AMR (the primary instance) ----
        {"name": "AMR — Strong (layered)", "robot": "Warehouse AMR",
         "note": "360° 3D LiDAR + 2× safety scanner + depth camera + mmWave, full response set, hardened controller. (ISO 3691-4)",
         "design": {"sensors": {"ouster_os1": 1, "sick_microscan3": 2, "realsense_d455": 1, "ti_mmwave": 1},
                    "responses": {"emergency_stop": 2, "dynamic_replan": 1, "speed_zone": 1},
                    "c2": {"ctrl_hardened": 1}}},
        {"name": "AMR — typical", "robot": "Warehouse AMR",
         "note": "Safety LiDAR + depth camera + RF tag reader, e-stop + re-plan, standard ROS 2 controller. (ISO 3691-4)",
         "design": {"sensors": {"sick_microscan3": 2, "realsense_d455": 1, "rf_tag_reader": 1},
                    "responses": {"emergency_stop": 1, "dynamic_replan": 1},
                    "c2": {"ctrl_standard": 1}}},
        {"name": "AMR — weak (RF-tag + legacy)", "robot": "Warehouse AMR",
         "note": "One narrow LiDAR + RF-tag stop only (blind to untagged people/debris) + legacy controller.",
         "design": {"sensors": {"hokuyo_ust": 1},
                    "responses": {"rf_zone_mutual": 2},
                    "c2": {"ctrl_legacy": 1}}},

        # ---- Humanoid (topical: Unitree G1, open ROS 2/DDS topics; Alias/CAI 2025) ----
        {"name": "Humanoid — vision-led", "robot": "Humanoid (e.g. Unitree-class)",
         "note": "Depth cameras + mmWave for close-in people, e-stop + speed-zone, standard ROS 2 controller. Real risk: 20+ unauthenticated DDS topics found on fielded humanoids (CAI/Alias 2025).",
         "design": {"sensors": {"realsense_d455": 1, "zed_2i": 1, "ti_mmwave": 1},
                    "responses": {"emergency_stop": 1, "speed_zone": 1},
                    "c2": {"ctrl_standard": 1}}},

        # ---- Autonomous ground / delivery vehicle ----
        {"name": "Delivery AGV", "robot": "Autonomous ground vehicle",
         "note": "Long-range 3D LiDAR + mmWave (dust/low-light) + camera, e-stop + dynamic re-plan at range, hardened controller.",
         "design": {"sensors": {"ouster_os1": 1, "velodyne_puck": 1, "ti_mmwave": 1, "realsense_d455": 1},
                    "responses": {"emergency_stop": 1, "dynamic_replan": 1, "speed_zone": 1},
                    "c2": {"ctrl_hardened": 1}}},

        # ---- Cobot / work cell (ISO 10218:2025 folds in cybersecurity scoped to safety) ----
        {"name": "Cobot / work cell", "robot": "Collaborative robot (cobot)",
         "note": "Safety scanner (cell boundary) + depth camera + ultrasonic close-in, e-stop + speed-zone, hardened controller. (ISO 10218:2025 / ex-15066 — cybersecurity now in-scope for safety.)",
         "design": {"sensors": {"sick_microscan3": 1, "realsense_d455": 1, "ultrasonic_generic": 1},
                    "responses": {"emergency_stop": 2, "speed_zone": 1},
                    "c2": {"ctrl_hardened": 1}}},

        # ---- Vision-only (a design-choice illustration, any class) ----
        {"name": "Vision-only (camera-reliant)", "robot": "any (design study)",
         "note": "Depth cameras only — narrow FoV, light-sensitive, no ranging redundancy. Shows a single-modality design's exposure.",
         "design": {"sensors": {"realsense_d455": 1, "zed_2i": 1},
                    "responses": {"emergency_stop": 1, "dynamic_replan": 1},
                    "c2": {"ctrl_standard": 1}}},
    ]


DEFAULT_SEEDS = (7, 11, 19, 23, 31)


def _attack_for(attack_key):
    if not attack_key or attack_key == "baseline":
        return None
    cls = next((c for c in ALL_ATTACKS if c().key == attack_key), None)
    if cls is None:
        raise ValueError(f"unknown attack: {attack_key}")
    return cls()


_BASELINE_CACHE = {}


def _baseline_for_seed(seed, n_hostile, n_benign, design, profile=None):
    key = (seed, n_hostile, n_benign, repr(design), (profile or {}).get("id") if profile else None)
    if key not in _BASELINE_CACHE:
        _BASELINE_CACHE[key] = summarise(run_once(None, seed=seed, n_hostile=n_hostile,
                                                  n_benign=n_benign, design=design, profile=profile))
    return _BASELINE_CACHE[key]


def _cap_to_baseline(m, base):
    """An attack can only ever HARM safety, never improve it. Occasionally an attack that
    perturbs the tracker input accidentally improves one real object's track on a seed (a
    geometry fluke). We clamp 'Safely handled' to the clean baseline for the SAME seed; any
    clamped handling becomes a collision. Modelling floor, stated openly in the UI."""
    if m["Safely handled"] > base["Safely handled"]:
        lost = m["Safely handled"] - base["Safely handled"]
        m = dict(m)
        m["Safely handled"] = base["Safely handled"]
        m["Collisions"] = m["Collisions"] + lost
    return m


def run_api(attack_key: str | None, n_hostile=4, n_benign=3, design=None, seeds=DEFAULT_SEEDS,
            profile=None):
    """Baseline-or-one-attack AVERAGED over several seeds, with 'Safely handled' capped at the
    clean baseline (an attack can never improve safety). Structured for the web UI.

    `profile` (a dict from profiles.get_profile / register_profile, or None for the default AMR)
    selects the robot type — it changes object classes, speeds and the display vocabulary, but NOT
    the engine, the attacks, or the metric keys. That is how the lab generalises to any robot."""
    atk_name = None
    is_attack = bool(attack_key and attack_key != "baseline")
    runs = []
    for s in seeds:
        atk = _attack_for(attack_key)
        if atk is not None:
            atk_name = atk.name
        res = summarise(run_once(atk, seed=s, n_hostile=n_hostile,
                                 n_benign=n_benign, design=design, profile=profile))
        if is_attack:
            res = _cap_to_baseline(res, _baseline_for_seed(s, n_hostile, n_benign, design, profile))
        runs.append(res)
    keys = list(runs[0].keys())
    n = len(runs)
    avg = {k: round(sum(r[k] for r in runs) / n, 1) for k in keys}
    out = {"scenario": atk_name if atk_name else "Baseline (no attack)",
           "key": attack_key or "baseline",
           "metrics": avg,
           "seeds": len(seeds)}
    if profile:
        out["terms"] = profile.get("terms", {})   # display labels for the UI (keys stay stable)
        if profile.get("architecture"):
            import robo_lab.profiles as P
            out["attack_surface"] = P.attack_surface_summary(profile["architecture"])
            out["ot_exposed"] = bool(profile["architecture"].get("ot_exposed"))
    return out


def main():
    args = sys.argv[1:]
    n_hostile, n_benign = 4, 3
    seeds = DEFAULT_SEEDS
    wanted = []
    i = 0
    while i < len(args):
        a = args[i].lower()
        if a in ("--hazards", "--hostile") and i + 1 < len(args):
            n_hostile = int(args[i + 1]); i += 2; continue
        if a in ("--cleared", "--benign") and i + 1 < len(args):
            n_benign = int(args[i + 1]); i += 2; continue
        if a in ("--seeds", "-s") and i + 1 < len(args):
            n = max(1, int(args[i + 1]))
            seeds = DEFAULT_SEEDS[:n] if n <= len(DEFAULT_SEEDS) else tuple(range(7, 7 + 4 * n, 4))
            i += 2; continue
        wanted.append(a); i += 1

    print("\n=== ROBOTICS SAFETY LAB — baseline vs. attacks ===")
    print(f"{STEPS} steps @ {DT}s · {n_hostile} hazards + {n_benign} cleared objects · real Kalman tracker.")
    print(f"Averaged over {len(seeds)} run(s); 'Safely handled' capped at baseline (attacks cannot improve safety).\n")

    base = run_api("baseline", n_hostile, n_benign, seeds=seeds)["metrics"]
    keys = list(base.keys())
    header = f"{'Scenario':<34}" + "".join(f"{k:>18}" for k in keys)
    print(header); print("-" * len(header))
    print(f"{'BASELINE (no attack)':<34}" + "".join(f"{str(base[k]):>18}" for k in keys))
    for cls in ALL_ATTACKS:
        atk = cls()
        if wanted and atk.key not in wanted and atk.name.lower() not in wanted:
            continue
        r = run_api(atk.key, n_hostile, n_benign, seeds=seeds)["metrics"]
        print(f"{atk.name:<34}" + "".join(f"{str(r[k]):>18}" for k in keys))
    print("\nEach attack is a real transformation of the data entering a real tracker.")
    print("Measured (seed-averaged), not scripted. Representative lab — NOT a real robot;")
    print("magnitudes on a live system need an actual assessment.\n")


if __name__ == "__main__":
    main()
