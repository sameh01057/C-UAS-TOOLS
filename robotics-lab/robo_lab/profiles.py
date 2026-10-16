"""Robot PROFILES — make the lab general without touching the engine.

A profile is plain data that describes ONE kind of autonomous system: what its objects are
(hazard vs cleared), what the outcomes are called (handled / collision / false-stop), which real
components it can use, and a few world parameters (approach speeds, object classes). The engine
(tracker + 17 attacks + metrics math) is identical for every profile — that is the whole point:
the same attack method degrades any autonomy stack that trusts its sensors.

Adding a new robot (e.g. an autonomous fishing boat) = adding one profile here, or loading a
profile JSON through the UI's "Add your robot" panel. No engine code changes.

Built-in profiles ship below. The default ("amr") reproduces the original warehouse-AMR lab
exactly, so existing behaviour is unchanged.

A profile schema (all keys optional except id/name; sensible defaults fill the rest):
{
  "id": "fishing_boat",
  "name": "Autonomous fishing boat",
  "robot_class": "Marine autonomous surface vessel",
  "standard": "IMO COLREGs / MASS guidelines",
  "terms": {                      # the vocabulary shown in the UI + metrics
     "hazard": "vessel / rock / net",       "cleared": "buoy / permitted craft",
     "handled": "Safely avoided",           "leaked": "Collision at sea",
     "false":  "Needless stop",             "count_hazard": "Hazards", "count_cleared": "Cleared"
  },
  "world": { "hazard_speed": [10, 30], "cleared_speed": [6, 14],
             "object_classes": [ {"name":"vessel","reflectivity":1.0,"rf":true},
                                 {"name":"rock","reflectivity":0.6,"rf":false}, ... ] },
  "components": {                 # which component IDs (from components.py) this profile offers
     "sensors": ["marine_radar","ais_receiver","sonar","camera_generic","gnss"],
     "responses": ["engine_cut","course_replan","slow_zone"],
     "controllers": ["ctrl_hardened","ctrl_standard","ctrl_legacy"]
  },
  "default_design": { "sensors": {...}, "responses": {...}, "c2": {...} }
}
"""
from __future__ import annotations
import copy

# ---- default vocabulary (warehouse AMR) — also the fallback for any missing key ----
_DEFAULT_TERMS = {
    "hazard": "person / obstacle", "cleared": "cleared object",
    "handled": "Safely handled",  "leaked": "Collisions",
    "false": "False stops",       "count_hazard": "Hazards", "count_cleared": "Cleared",
}

# ---- object classes per profile: (name, reflectivity 0..1, emits_rf) ----
# reflectivity ~ how well a ranging sensor sees it; emits_rf ~ carries a tag/beacon/transponder.
_AMR_CLASSES = [
    {"name": "person",   "reflectivity": 0.5,  "rf": True},
    {"name": "forklift", "reflectivity": 1.0,  "rf": True},
    {"name": "pallet",   "reflectivity": 0.7,  "rf": False},
    {"name": "debris",   "reflectivity": 0.08, "rf": False},
]

PROFILES = {
    "amr": {
        "id": "amr",
        "name": "Warehouse AMR",
        "robot_class": "Autonomous mobile robot",
        "standard": "ISO 3691-4",
        "terms": dict(_DEFAULT_TERMS),
        "world": {"hazard_speed": [14, 34], "cleared_speed": [10, 18],
                  "object_classes": _AMR_CLASSES},
        # components: None => offer ALL components in the library (back-compatible default)
        "components": None,
    },

    # ---- Autonomous fishing boat — the worked example of adding a new robot ----
    "fishing_boat": {
        "id": "fishing_boat",
        "name": "Autonomous fishing boat",
        "robot_class": "Marine autonomous surface vessel (MASS)",
        "standard": "IMO COLREGs / MASS guidelines",
        "terms": {
            "hazard": "vessel / rock / net", "cleared": "buoy / permitted craft",
            "handled": "Safely avoided", "leaked": "Collisions at sea",
            "false": "Needless stops", "count_hazard": "Hazards", "count_cleared": "Cleared craft",
        },
        "world": {"hazard_speed": [8, 26], "cleared_speed": [4, 12],
                  "object_classes": [
                      {"name": "vessel", "reflectivity": 1.0, "rf": True},    # has AIS transponder
                      {"name": "small_craft", "reflectivity": 0.6, "rf": True},
                      {"name": "rock", "reflectivity": 0.8, "rf": False},     # no transponder
                      {"name": "net_buoy", "reflectivity": 0.2, "rf": False},
                  ]},
        "components": {
            "sensors": ["marine_radar", "ais_receiver", "sonar", "realsense_d455", "gnss_marine"],
            "responses": ["engine_cut", "course_replan", "slow_zone"],
            "controllers": ["ctrl_hardened", "ctrl_standard", "ctrl_legacy"],
        },
        "default_design": {
            "sensors": {"marine_radar": 1, "ais_receiver": 1, "sonar": 1, "realsense_d455": 1},
            "responses": {"engine_cut": 1, "course_replan": 1},
            "c2": {"ctrl_hardened": 1},
        },
    },
}


def _merge_terms(terms):
    out = dict(_DEFAULT_TERMS)
    out.update(terms or {})
    return out


# which groups a custom component may declare, and the kinds valid in each (for light validation)
_VALID_GROUPS = {"lidar", "camera", "ranging", "marine", "response", "c2"}


def _normalise_custom_components(profile):
    """A profile may carry its OWN hardware specs inline via `custom_components` (a list of full
    component dicts, each with id/group/kind/...). This is the 'import your actual system' path:
    the customer's real sensors/effectors/C2 travel with the profile, no library entry needed.
    Returns a cleaned list; each gets a sensible `group` so the UI and engine place it correctly."""
    raw = profile.get("custom_components") or []
    out = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        c = dict(c)
        cid = (c.get("id") or c.get("name") or "").strip().lower().replace(" ", "_")
        if not cid:
            continue
        c["id"] = cid
        kind = c.get("kind", "")
        # infer a group if not given, from the kind
        if c.get("group") not in _VALID_GROUPS:
            if kind == "c2":
                c["group"] = "c2"
            elif kind in ("estop", "replan", "slow", "rf_stop", "rf_jammer", "laser", "net", "hpm", "kinetic"):
                c["group"] = "response"
            elif kind in ("lidar", "camera"):
                c["group"] = kind
            else:
                c["group"] = "ranging"   # radar/rf/ultrasonic/unknown sensors
        c.setdefault("origin", "customer")
        c.setdefault("src", "customer-supplied spec")
        c.setdefault("custom", True)
        out.append(c)
    return out


# ---------------------------------------------------------------------------
# System ARCHITECTURE (import-your-system): the software/C2 + network layers that a real
# C-UAS/robot system has beyond its sensors/effectors. Mirrors the proposal's §14 attack-surface
# map. Each field is tagged so the UI/report can say honestly whether it DRIVES THE SIM or only
# RECORDS SCOPE for the Swarm audit — the lab sim models the physical kill-chain, not C2 code.
#
# architecture = {
#   # software / C2 sub-layers — a posture 0..1 each (1 = hardened); [sim] ones feed resilience
#   "fusion_auth":      0.5,   # [sim] sensor nodes authenticated to fusion
#   "protocol_auth":    0.5,   # [sim] SAPIENT/CoT message auth + replay protection
#   "console":          0.5,   # [scope] operator console/HMI hardening
#   "apis":             0.5,   # [scope] integration API authz/command integrity
#   "external_c2":      0.5,   # [scope] TAK/force-network link trust
#   "protocols": ["SAPIENT","CoT/TAK","proprietary"],  # [scope] which the system speaks
#   "uses_ml":          True,  # [scope+sim] ML fusion/classification present -> adversarial-ML in scope
#   # network / infrastructure
#   "segmentation":     0.5,   # [sim] isolation of the C-UAS net from the site
#   "ot_exposed":       True,  # [sim] reachable path into site OT -> lateral-movement severity flag
#   # connections / data-flows (what talks to what) — [scope] attack-surface inventory
#   "connections": [ {"from":"radar","to":"fusion","via":"SAPIENT","exposed":false}, ... ]
# }
_SIM_POSTURE_KEYS = ("fusion_auth", "protocol_auth", "segmentation")  # these move the sim


def _effective_resilience(base_res, architecture):
    """Blend the controller's base resilience with the software postures that genuinely bear on
    data-layer attacks (fusion auth, protocol auth, segmentation). The engine's resilience governs
    how well injected/forged plots are rejected, so weak protocol/fusion auth should LOWER it.
    Conservative: the effective value is pulled toward the weakest relevant posture, never raised
    above the controller's own rating."""
    if not architecture:
        return base_res
    postures = [architecture[k] for k in _SIM_POSTURE_KEYS
                if isinstance(architecture.get(k), (int, float))]
    if not postures:
        return base_res
    weakest = min(postures)
    # effective = average of base and the weakest relevant posture, capped at base (never helps)
    eff = (base_res + weakest) / 2.0
    return max(0.0, min(base_res, eff))


def attack_surface_summary(architecture):
    """A structured attack-surface inventory for the Swarm audit + the report (scope-capture).
    Returns a list of {layer, detail, drives_sim} rows. Honest: marks which rows affect the sim."""
    a = architecture or {}
    rows = []
    def post(v):
        if not isinstance(v, (int, float)): return "not specified"
        return "hardened" if v >= 0.8 else ("standard" if v >= 0.4 else "weak/unauthenticated")
    rows.append({"layer": "Sensor→fusion protocol auth", "detail": post(a.get("protocol_auth")), "drives_sim": True})
    rows.append({"layer": "Fusion node authentication", "detail": post(a.get("fusion_auth")), "drives_sim": True})
    rows.append({"layer": "Network segmentation", "detail": post(a.get("segmentation")), "drives_sim": True})
    rows.append({"layer": "OT / site boundary", "detail": ("EXPOSED — lateral-movement risk" if a.get("ot_exposed") else "isolated"), "drives_sim": True})
    rows.append({"layer": "Operator console / HMI", "detail": post(a.get("console")), "drives_sim": False})
    rows.append({"layer": "Integration APIs / command bus", "detail": post(a.get("apis")), "drives_sim": False})
    rows.append({"layer": "External C2 link (TAK/force net)", "detail": post(a.get("external_c2")), "drives_sim": False})
    if a.get("protocols"):
        rows.append({"layer": "Protocols in use", "detail": ", ".join(a["protocols"]), "drives_sim": False})
    rows.append({"layer": "AI/ML fusion/classification", "detail": ("present — adversarial-ML in scope (§16.9)" if a.get("uses_ml") else "not used"), "drives_sim": False})
    for c in (a.get("connections") or []):
        rows.append({"layer": "Data flow",
                     "detail": f"{c.get('from','?')} → {c.get('to','?')} via {c.get('via','?')}" + ("  [EXPOSED]" if c.get("exposed") else ""),
                     "drives_sim": False})
    return rows


def get_profile(pid):
    """Return a profile by id, with defaults filled. Falls back to 'amr'."""
    p = copy.deepcopy(PROFILES.get(pid or "amr", PROFILES["amr"]))
    p["terms"] = _merge_terms(p.get("terms"))
    p.setdefault("world", {})
    p["world"].setdefault("hazard_speed", [14, 34])
    p["world"].setdefault("cleared_speed", [10, 18])
    p["world"].setdefault("object_classes", _AMR_CLASSES)
    p.setdefault("components", None)
    p["custom_components"] = _normalise_custom_components(p)
    p.setdefault("architecture", None)
    return p


def register_profile(profile: dict):
    """Validate + add a user-supplied profile (from the UI 'Add your robot' panel). Returns its id.
    Kept permissive: missing keys get defaults, so a minimal profile still works."""
    if not isinstance(profile, dict):
        raise ValueError("profile must be an object")
    pid = (profile.get("id") or profile.get("name") or "custom").strip().lower().replace(" ", "_")
    if not pid:
        raise ValueError("profile needs an id or name")
    prof = copy.deepcopy(profile)
    prof["id"] = pid
    prof.setdefault("name", pid)
    PROFILES[pid] = prof
    return pid


def list_profiles():
    """Light list for the UI dropdown."""
    return [{"id": p["id"], "name": p["name"],
             "robot_class": p.get("robot_class", ""), "standard": p.get("standard", "")}
            for p in (get_profile(k) for k in PROFILES)]
