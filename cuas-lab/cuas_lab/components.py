"""Real C-UAS component library.

Each entry models a REAL, fielded product using its manufacturer's PUBLISHED
specifications (range, frequency band, field of view, update rate, etc.). The specs
are real; the behaviour is simulated from those specs. This is "real components,
modelled physics" — not the actual hardware/firmware. Sources are noted per item.

Honesty flags you'll see:
  * "range_disclosed": False  — the vendor does NOT publish an effective range; the
     number used here is a sim assumption, clearly marked, not a spec.
  * "spec_note": "estimated"  — a field is an informed estimate, not a published figure.

Units: ranges in metres, bands in GHz/MHz as published, FoV in degrees.
Coverage spans major global vendors (US, Europe, Israel) and Singapore (ST Engineering),
new and legacy systems.
"""
from __future__ import annotations

# ----------------------------------------------------------------------------
# DETECTION SENSORS — radar
# ----------------------------------------------------------------------------
RADARS = {
    "robin_iris": {
        "name": "Robin Radar IRIS",
        "origin": "Netherlands",
        "kind": "radar",
        "band": "X-band FMCW (8.7–9.8 GHz)",
        "range_m": 5000,            # 5 km instrumented (12 km long-range mode)
        "range_long_m": 12000,
        "fov_az": 360, "fov_el": 60,
        "update_hz": 0.5,           # 30 rpm → full scan ~1 s
        "min_rcs": 0.01,            # micro-Doppler classifies very small UAS
        "extra": "12 W CW · 6° beam · angular acc. 0.6–0.75° · range acc. 0.6 m",
        "note": "360° 3D micro-Doppler; 5 km (12 km long-range mode). Ukraine-tested.",
        "src": "everythingrf.com / robinradar.com/products/iris-radar",
    },
    "echodyne_echoguard": {
        "name": "Echodyne EchoGuard",
        "origin": "USA",
        "kind": "radar",
        "band": "K-band ESA (24.45–24.65 GHz US / 24.05–24.25 GHz intl)",
        "range_m": 1000,            # >1 km small UAS (Phantom 4); >1.4 km larger; 6 km instrumented
        "fov_az": 120, "fov_el": 80,
        "update_hz": 10,            # electronically scanned, 10 Hz track rate, up to 20 tracks
        "min_rcs": 0.02,
        "extra": "6 km instrumented · up to 20 tracks · 1.25 kg · 50 W",
        "note": "Ultra-low SWaP electronically-scanned array; 10 Hz tracks; >1 km on small UAS.",
        "src": "radartutorial.eu EchoGuard datasheet; defenseadvancement.com",
    },
    "echodyne_echoshield": {
        "name": "Echodyne EchoShield",
        "origin": "USA",
        "kind": "radar",
        "band": "software-defined cognitive 4D ESA (metamaterials)",
        "range_m": 3000,            # ~3 km small UAS, >12 km larger platforms
        "range_long_m": 12000,
        "fov_az": 130, "fov_el": 90,
        "update_hz": 10,
        "min_rcs": 0.01,
        "extra": "<0.5° angular acc. az+el · hundreds of tracks · MIL-STD-810H · IP67",
        "note": "Longer-range 4D pulse-Doppler cognitive radar; ~3 km small UAS, >12 km larger. Customisable 130°×90° FoV.",
        "src": "everythingrf.com (EchoShield); echodyne.com newsroom",
    },
    "numerica_spyglass": {
        "name": "Numerica Spyglass",
        "origin": "USA",
        "kind": "radar",
        "band": "Ku-band phased array (software-defined)",
        "range_m": 3500,            # detects/tracks small UAS "beyond 3.5 km"
        "fov_az": 90, "fov_el": 30,
        "update_hz": 5,
        "min_rcs": 0.03,
        "note": "Software-defined Ku-band phased array; simultaneous Tx/Rx; detects small UAS beyond 3.5 km; embedded C2/AI.",
        "src": "unmannedairspace.info / uasvision.com (Numerica Spyglass)",
    },
    "blighter_a400": {
        "name": "Blighter A400 series",
        "origin": "UK",
        "kind": "radar",
        "band": "Ku-band FMCW e-scan",
        "range_m": 3600,            # 10 m – 3.6 km nano/micro/mini UAS; up to 10 km larger
        "range_long_m": 10000,
        "fov_az": 90, "fov_el": 20, # A402 90° / A422 180° / dual-A422 360°
        "min_rcs": 0.01,
        "extra": "D3 micro-Doppler · A402 90° / A422 180° / dual-A422 360° · W20 (20–30° el) or M10 (10–15° el)",
        "note": "Non-rotating e-scan Ku-band; detects nano/micro drones 10 m–3.6 km, larger to 10 km. Battle-proven.",
        "src": "blighter.com A400 datasheet BSS-1311; ukdefencejournal.org.uk",
    },
    "hensoldt_spexer2000": {
        "name": "Hensoldt Spexer 2000 3D MkIII",
        "origin": "Germany",
        "kind": "radar",
        "band": "X-band AESA (9.2–10 GHz)",
        "range_m": 2500,            # 2.5 km UAV multi-beam; up to 40 km single-beam (larger targets)
        "range_long_m": 40000,
        "fov_az": 120, "fov_el": 30,
        "update_hz": 3,             # 0.3 s update in UAV mode
        "min_rcs": 0.02,
        "extra": "up to 16 independent beams · 0.3 s UAV update · chosen for Bundeswehr Qualifizierte Fliegerabwehr",
        "note": "X-band AESA, 120° sector; 2.5 km on small/fast UAVs (0.3 s update), up to 40 km single-beam on larger targets.",
        "src": "edrmagazine.eu; hensoldt.net Spexer 2000 3D MkIII",
    },
    "src_gryphon_r1410": {
        "name": "SRC Gryphon R1410",
        "origin": "USA",
        "kind": "radar",
        "band": "X-band 3D AESA",
        "range_m": 7700,            # 7.7 km small UAS; 25 km small manned aircraft
        "range_long_m": 25000,
        "fov_az": 90, "fov_el": 30,
        "min_rcs": 0.02,
        "note": "3D AESA built for small low-flying targets; 7.7 km on small UAS (part of SRC Silent Archer C-UAS).",
        "src": "srcinc.com Gryphon R1400/R1410 datasheet",
    },
    "src_tpq50": {
        "name": "SRC AN/TPQ-50",
        "origin": "USA",
        "kind": "radar",
        "band": "L-band 3D",
        "range_m": 4000,            # multi-mission; exact small-UAS figure not published here
        "spec_note": "small-UAS detection range not separately published; 4 km is a sim assumption",
        "fov_az": 360, "fov_el": 30,
        "min_rcs": 0.05,
        "note": "L-band 3D multi-mission radar (air surveillance, counterfire, C-UAS, V-SHORAD). 360° coverage.",
        "src": "srcinc.com AN/TPQ-50 datasheet",
    },
}

# ----------------------------------------------------------------------------
# DETECTION SENSORS — RF / ESM (passive)
# ----------------------------------------------------------------------------
RF_SENSORS = {
    "mydefence_wingman": {
        "name": "MyDefence Wingman",
        "origin": "Denmark",
        "kind": "rf",
        "band": "200 MHz – 6 GHz",
        "range_m": 6000,
        "fov_az": 360, "fov_el": 0,
        "df_accuracy_deg": 30,
        "note": "Passive RF, 360°, detect <10 s, DF ±30°.",
        "src": "mydefence.com/products/wingman-drone-detector",
    },
    "dedrone_rf360": {
        "name": "Dedrone RF-360",
        "origin": "Germany/USA",
        "kind": "rf",
        "band": "RF (comms + control links)",
        "range_m": 5000,
        "fov_az": 360, "fov_el": 0,
        "note": "Passive network RF; detect/classify/localise drone + controller; strong in RF-noisy sites.",
        "src": "dedrone.com/sensors/rf-360",
    },
    "droneshield_rfone": {
        "name": "DroneShield RfOne / RfRecon",
        "origin": "Australia",
        "kind": "rf",
        "band": "up to 7.1 GHz (ultra-wideband)",
        "range_m": 8000,
        "fov_az": 360, "fov_el": 0,
        "note": "Ultra-wideband passive RF; continuous wide-spectrum monitoring.",
        "src": "droneshield.com (RfOne / ultra-wideband)",
    },
    "rohde_ardronis": {
        "name": "Rohde & Schwarz ARDRONIS",
        "origin": "Germany",
        "kind": "rf",
        "band": "20 MHz – 6 GHz (single antenna)",
        "range_m": 5000,
        "range_disclosed": False,   # R&S publishes band + capability, not a hard range figure
        "spec_note": "effective range not published by R&S; 5 km is a sim assumption",
        "fov_az": 360, "fov_el": 0,
        "note": "Wide-spectrum RF detection/DF across 20 MHz–6 GHz with one antenna; profile-based auto-separation defeats frequency-hopping. 100+ fielded.",
        "src": "everythingrf.com; rohde-schwarz.com (ARDRONIS)",
    },
    "aaronia_aartos": {
        "name": "Aaronia AARTOS DDS",
        "origin": "Germany",
        "kind": "rf",
        "band": "100 MHz – 20 GHz (model-dependent; X9 400 MHz–6 GHz)",
        "range_m": 14000,           # X9 ~14 km commercial; long-range to 40–80 km
        "range_long_m": 40000,
        "fov_az": 360, "fov_el": 0,
        "note": "Real-time wide-spectrum RF; X9 ~14 km on commercial drones (long-range to 40 km, military UAV to 80 km). AI false-alarm rejection.",
        "src": "everythingrf.com; edrmagazine.eu (AARTOS)",
    },
    "dji_aeroscope": {
        "name": "DJI AeroScope (LEGACY)",
        "origin": "China",
        "kind": "rf",
        "band": "DJI DroneID / OcuSync downlink",
        "range_m": 5000,            # up to ~5 km (city); ~50 km variants quoted historically
        "legacy": True,
        "fov_az": 360, "fov_el": 0,
        "note": "LEGACY/discontinued. Decoded DJI DroneID telemetry to ID drone + pilot location. Only sees DJI; DJI has since changed/closed the protocol — a cautionary 'single-vendor dependency' example.",
        "src": "DJI AeroScope (product discontinued 2024); widely documented",
    },
}

# ----------------------------------------------------------------------------
# DETECTION SENSORS — EO/IR & acoustic
# ----------------------------------------------------------------------------
EO_ACOUSTIC = {
    "eoir_generic": {
        "name": "EO/IR gimbal (slew-to-cue)",
        "origin": "generic",
        "kind": "eo",
        "band": "Electro-optical + thermal",
        "range_m": 2000,
        "fov_az": 30, "fov_el": 20,
        "note": "Narrow FoV; cued by radar/RF; visual/thermal ID. Degrades at night (EO).",
        "src": "industry-typical EO/IR C-UAS gimbal",
    },
    "squarehead_discovair": {
        "name": "Squarehead Discovair G2+",
        "origin": "Norway",
        "kind": "acoustic",
        "band": "Acoustic signature",
        "range_m": 500,             # min 500 m for Group 1 UAS
        "fov_az": 360, "fov_el": 0, # 100° per sensor; G2+ 360° hemispheric mode
        "note": "Passive acoustic; ≥500 m on small UAS. No line-of-sight needed — works in urban canyons, behind cover, darkness/fog. 360° hemispheric mode. Non-emitting.",
        "src": "everythingrf.com (Squarehead Acoustic CUAS); robinradar.com",
    },
    "acoustic_generic": {
        "name": "Acoustic array (generic)",
        "origin": "generic",
        "kind": "acoustic",
        "band": "Acoustic signature",
        "range_m": 500,
        "fov_az": 360, "fov_el": 0,
        "note": "Short-range passive; good on small/low drones; no RF/RCS dependency.",
        "src": "industry-typical acoustic C-UAS",
    },
}

# ----------------------------------------------------------------------------
# EFFECTORS
# ----------------------------------------------------------------------------
EFFECTORS = {
    # --- RF / GNSS jammers (soft-kill) ---
    "droneshield_dronegun": {
        "name": "DroneShield DroneGun Mk4",
        "origin": "Australia",
        "kind": "rf_jammer", "defeat": "soft",
        "range_m": 1000,            # ASSUMED for the sim — real range NOT publicly disclosed by DroneShield
        "range_disclosed": False,
        "band": "wide ISM bands + GNSS",
        "defeats_rf_only": True,
        "extra": "3.2 kg · >1 h operation · IP67 · disrupts C2/GNSS/video of multiple UAS",
        "note": "Hand-held RF/GNSS jammer; no effect on no-RF drones. NOTE: effective range is not publicly disclosed by the manufacturer — the 1 km here is a sim assumption, not a spec.",
        "src": "everythingrf.com / janes.com (DroneGun Mk4)",
    },
    "flexforce_dronebuster": {
        "name": "Flex Force Dronebuster",
        "origin": "USA",
        "kind": "rf_jammer", "defeat": "soft",
        "range_m": 1000,            # mfr "takeover range ~800–1400 m"; real effect scales with drone–controller distance
        "band": "ISM bands + GPS/GNSS (shaped beam)",
        "defeats_rf_only": True,
        "extra": "~800–1400 m takeover range · 4.9 lb · 3 h jam / 10 h detect · DoD-authorised",
        "note": "Hand-held RF/GNSS jammer; ISM + GPS with a shaped beam to limit GNSS spillover. No effect on no-RF drones.",
        "src": "supplycore.com Flex Force datasheet; asianmilitaryreview.com",
    },
    "battelle_dronedefender": {
        "name": "Battelle DroneDefender (LEGACY)",
        "origin": "USA",
        "kind": "rf_jammer", "defeat": "soft",
        "range_m": 400,             # ~400 m quoted historically
        "range_disclosed": False,
        "legacy": True,
        "band": "ISM + GNSS",
        "defeats_rf_only": True,
        "note": "LEGACY. One of the first point-and-shoot RF jammers (~400 m). Superseded by newer hand-helds; kept as an older-generation reference.",
        "src": "Battelle DroneDefender (legacy), widely documented",
    },
    # --- High-power microwave (hard-kill, area / counter-swarm) ---
    "epirus_leonidas": {
        "name": "Epirus Leonidas (HPM)",
        "origin": "USA",
        "kind": "hpm", "defeat": "hard",
        "range_m": 1000,            # ~1 km "Final Protective Fires" core; "tactically relevant range"
        "area_effect": True,
        "defeats_rf_only": False,
        "note": "Solid-state GaN high-power microwave; counter-SWARM. Live-fire demo: 61/61 drones, incl. a 49-drone swarm in one pulse.",
        "src": "epirusinc.com press releases; en.wikipedia.org/wiki/Epirus_Leonidas",
    },
    # --- High-energy lasers (hard-kill) ---
    "lockheed_helios": {
        "name": "Lockheed HELIOS (laser)",
        "origin": "USA",
        "kind": "laser", "defeat": "hard",
        "range_m": 5000,            # comparable to RIM-116, ~5 nm
        "dwell_s": 1.5,
        "defeats_rf_only": False,
        "note": "60 kW-class high-energy laser (growth to 150 kW); hard-kill + optical dazzler; one target at a time, needs dwell. Fielded on USN Flight IIA DDG / Aegis.",
        "src": "lockheedmartin.com HELIOS; en.wikipedia.org/wiki/HELIOS",
    },
    # --- Kinetic / interceptor (hard-kill) ---
    "fortem_dronehunter": {
        "name": "Fortem DroneHunter (net)",
        "origin": "USA",
        "kind": "net", "defeat": "hard",
        "range_m": 900,
        "max_target_speed": 20,
        "defeats_rf_only": False,
        "note": "Autonomous interceptor drone that nets a target; captures slow drones, too slow for fast FPV.",
        "src": "Fortem DroneHunter class",
    },
    "net_interceptor": {
        "name": "Net interceptor (generic)",
        "origin": "generic",
        "kind": "net", "defeat": "hard",
        "range_m": 900,
        "max_target_speed": 20,
        "defeats_rf_only": False,
        "note": "Captures slow drones with a net; too slow for fast FPV.",
        "src": "Fortem DroneHunter class",
    },
    "skywall_100": {
        "name": "OpenWorks SkyWall 100 (net)",
        "origin": "UK",
        "kind": "net", "defeat": "hard",
        "range_m": 100,             # effective range up to 100 m
        "max_target_speed": 25,
        "defeats_rf_only": False,
        "extra": "12 kg · compressed-air launch · parachute recovery of captured drone",
        "note": "Hand-held compressed-air net launcher; captures a drone intact (parachute recovery) up to ~100 m. Very short range; one shot then reload.",
        "src": "norskluftvern.com; officer.com (SkyWall 100)",
    },
    "anduril_anvil": {
        "name": "Anduril Anvil / Anvil-M",
        "origin": "USA",
        "kind": "kinetic", "defeat": "hard",
        "range_m": 2000,
        "range_disclosed": False,
        "spec_note": "engagement range not published; 2 km is a sim assumption",
        "max_target_speed": 130,    # ~200 mph interceptor; handles Group 1–2 (<~300 mph) targets
        "defeats_rf_only": False,
        "note": "Autonomous ramming interceptor (Anvil-M adds a munition); ~200 mph. Counters Group 1–2 drones. Pairs with Lattice C2. Engagement range not publicly disclosed.",
        "src": "c4isrnet.com / defensenews.com (Anvil-M, 2023)",
    },
    "raytheon_coyote_b2": {
        "name": "Raytheon Coyote Block 2",
        "origin": "USA",
        "kind": "kinetic", "defeat": "hard",
        "range_m": 10000,           # Block 2+ "rapid intercepts exceeding 10 km"
        "area_effect": False,
        "defeats_rf_only": False,
        "note": "Rail-launched kinetic interceptor with warhead; defeats single drones or swarms at >10 km, higher altitudes than most effectors. Expendable (one per engagement).",
        "src": "armyrecognition.com; norskluftvern.com (Coyote Block 2)",
    },
    # --- Integrated national systems (detect+defeat in one) ---
    "stengg_agil": {
        "name": "ST Engineering AGIL (laser)",
        "origin": "Singapore",
        "kind": "laser", "defeat": "hard",
        "range_m": 1000,            # 3 kW HEL effector engagements up to 1 km; sighting to 1.5 km
        "dwell_s": 2.0,
        "defeats_rf_only": False,
        "extra": "AI/ML waveform recognition · omni+directional sense & jam 300–1000 m · RF + laser effectors · land/vehicle/vessel",
        "note": "Singapore (ST Engineering) multi-layer C-UAS. 3 kW laser effector to ~1 km (sighting to 1.5 km), plus RF jamming 300–1000 m. Soft- and hard-kill in one AI-driven suite.",
        "src": "stengg.com AGIL Counter-Drone brochure; militaryembedded.com",
    },
    "stengg_agil_rf": {
        "name": "ST Engineering AGIL (RF effector)",
        "origin": "Singapore",
        "kind": "rf_jammer", "defeat": "soft",
        "range_m": 1000,            # omni/directional jam coverage 300–1000 m
        "band": "drone C2 / GNSS",
        "defeats_rf_only": True,
        "note": "Singapore (ST Engineering) RF effector of the AGIL suite; omni- and directional jamming, 300–1000 m coverage. Soft-kill; no effect on no-RF drones.",
        "src": "stengg.com AGIL Counter-Drone brochure; militaryembedded.com",
    },
    "rafael_dronedome": {
        "name": "Rafael Drone Dome (RF)",
        "origin": "Israel",
        "kind": "rf_jammer", "defeat": "soft",
        "range_m": 4000,            # RF jamming "effective range 3–5 km"
        "band": "drone C2 + GNSS",
        "defeats_rf_only": True,
        "extra": "Integrated system: RPS-42/82 radar (to 30 km), EO to 8 km, RF jam 3–5 km, optional ~2 km laser",
        "note": "Israel (Rafael) integrated C-UAS. RF jamming 3–5 km (optional laser ~2 km). Full detect-to-defeat system; the RF soft-kill layer is modelled here.",
        "src": "norskluftvern.com; everythingrf.com (Drone Dome)",
    },
}

# ----------------------------------------------------------------------------
# C2 / COMPUTE — the "brain": fuses sensors, decides, commands effectors.
# This is where the software attack surface lives (SAPIENT, TAK/CoT, APIs, fusion).
# ----------------------------------------------------------------------------
C2_NODES = {
    "c2_hardened": {
        "name": "Hardened C2 (authenticated, redundant)",
        "kind": "c2", "resilience": 0.9,
        "note": "Authenticated sensor feeds, message integrity, redundant nodes — resists injection/replay/poisoning best.",
        "src": "security-hardened C2 baseline",
    },
    "c2_standard": {
        "name": "Standard C2 (SAPIENT/TAK, basic auth)",
        "kind": "c2", "resilience": 0.5,
        "note": "SAPIENT (BSI Flex 335) / Cursor-on-Target interfaces with basic auth — typical fielded C2; partially resists data-layer attacks.",
        "src": "typical fielded C-UAS C2; SAPIENT / TAK-CoT standards",
    },
    "c2_legacy": {
        "name": "Legacy C2 (unauthenticated feeds)",
        "kind": "c2", "resilience": 0.15,
        "note": "Trusts sensor feeds without authentication — highly exposed to false-track injection, replay, spoofing.",
        "src": "legacy / unauthenticated C2",
    },
}

ALL = {"radar": RADARS, "rf": RF_SENSORS, "eo_acoustic": EO_ACOUSTIC,
       "effector": EFFECTORS, "c2": C2_NODES}


def catalog():
    """Flat list for the UI: every component with its category and specs."""
    out = []
    for group, items in ALL.items():
        for key, spec in items.items():
            out.append({"id": key, "group": group, **spec})
    return out
