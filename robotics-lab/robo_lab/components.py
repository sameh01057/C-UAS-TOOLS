"""Real robotics-perception component library.

Each entry models a REAL, fielded product using its manufacturer's PUBLISHED specifications
(range, field of view, update rate, etc.). The specs are real; the behaviour is simulated from
those specs. "Real components, modelled physics" — not the actual hardware/firmware.

Honesty flags: "range_disclosed": False marks a figure the vendor does not publish (sim
assumption, shown with * in the UI); "spec_note" marks an estimate; "origin" the vendor country.

Units: ranges in metres, FoV in degrees. Sensor ranges scaled ÷3 into the lab world at runtime.
"""
from __future__ import annotations

# ----------------------------------------------------------------------------
# PERCEPTION SENSORS — LiDAR / safety scanners
# ----------------------------------------------------------------------------
LIDARS = {
    "sick_microscan3": {
        "name": "SICK microScan3 (safety laser scanner)",
        "origin": "Germany",
        "kind": "lidar",
        "range_m": 9000,            # up to 9 m protective field / 40 m detection (safety scanner)
        "safety_field_m": 9,
        "fov_az": 275, "fov_el": 0,
        "update_hz": 30,
        "min_rcs": 0.02,
        "extra": "SIL2 / PLd safety-rated · 275° aperture · protective field to 9 m",
        "note": "Safety-rated 2D laser scanner widely used on AMRs for person-detection / safe-stop. 275° FoV leaves a rear blind arc.",
        "src": "sick.com microScan3 datasheet",
    },
    "ouster_os1": {
        "name": "Ouster OS1 (3D LiDAR)",
        "origin": "USA",
        "kind": "lidar",
        "range_m": 120,
        "fov_az": 360, "fov_el": 45,
        "update_hz": 20,
        "min_rcs": 0.03,
        "extra": "360° digital 3D LiDAR · up to 128 channels · 10–20 Hz",
        "note": "360° 3D LiDAR for navigation + obstacle detection; rich point cloud, not safety-rated by itself.",
        "src": "ouster.com OS1 datasheet",
    },
    "velodyne_puck": {
        "name": "Velodyne Puck (VLP-16)",
        "origin": "USA",
        "kind": "lidar",
        "range_m": 100,
        "fov_az": 360, "fov_el": 30,
        "update_hz": 10,
        "min_rcs": 0.04,
        "note": "Classic 16-channel 360° 3D LiDAR; common on mobile robots and AGVs.",
        "src": "velodynelidar.com VLP-16 datasheet",
    },
    "hokuyo_ust": {
        "name": "Hokuyo UST-10LX (2D LiDAR)",
        "origin": "Japan",
        "kind": "lidar",
        "range_m": 10000,           # 10 m typical / 30 m max on 2D scanning
        "fov_az": 270, "fov_el": 0,
        "update_hz": 40,
        "min_rcs": 0.05,
        "note": "Compact 270° 2D scanning LiDAR; popular for indoor AMR navigation and bump-stop zones.",
        "src": "hokuyo-usa.com UST-10LX datasheet",
    },
}

# ----------------------------------------------------------------------------
# PERCEPTION SENSORS — cameras (depth / vision)
# ----------------------------------------------------------------------------
CAMERAS = {
    "realsense_d455": {
        "name": "Intel RealSense D455 (depth camera)",
        "origin": "USA",
        "kind": "camera",
        "range_m": 6000,            # ~6 m usable depth
        "fov_az": 87, "fov_el": 58,
        "update_hz": 30,
        "note": "Stereo depth camera for close-range obstacle/person detection + classification; narrow FoV, degrades in low light.",
        "src": "intelrealsense.com D455 datasheet",
    },
    "zed_2i": {
        "name": "Stereolabs ZED 2i (stereo camera)",
        "origin": "USA",
        "kind": "camera",
        "range_m": 20000,           # up to 20 m depth
        "fov_az": 110, "fov_el": 70,
        "update_hz": 30,
        "note": "Wide-FoV stereo depth camera with on-board object detection; longer depth range than most RGB-D.",
        "src": "stereolabs.com ZED 2i datasheet",
    },
}

# ----------------------------------------------------------------------------
# PERCEPTION SENSORS — radar / ultrasonic / RF
# ----------------------------------------------------------------------------
RANGING = {
    "ti_mmwave": {
        "name": "TI mmWave radar (IWR6843)",
        "origin": "USA",
        "kind": "radar",
        "range_m": 30000,           # tens of metres; robust in dust/smoke/low-light
        "fov_az": 120, "fov_el": 30,
        "update_hz": 20,
        "min_rcs": 0.03,
        "note": "mmWave radar for obstacle detection in dust/smoke/darkness where cameras/LiDAR struggle.",
        "src": "ti.com IWR6843 datasheet",
    },
    "ultrasonic_generic": {
        "name": "Ultrasonic proximity array",
        "origin": "generic",
        "kind": "ultrasonic",
        "range_m": 4000,            # a few metres close-in
        "fov_az": 360, "fov_el": 0,
        "min_rcs": 0.1,
        "note": "Short-range close-in proximity sensing; cheap last-line bump protection, low resolution.",
        "src": "industry-typical ultrasonic array",
    },
    "rf_tag_reader": {
        "name": "RF safety-tag reader (UWB/RFID)",
        "origin": "generic",
        "kind": "rf",
        "range_m": 6000,
        "fov_az": 360, "fov_el": 0,
        "note": "Detects workers/vehicles carrying an RF safety tag (UWB/RFID). Only sees tagged objects — blind to untagged people/debris.",
        "src": "industry-typical UWB/RFID safety system",
    },
}

# ----------------------------------------------------------------------------
# SAFETY RESPONSES (the "effectors": what the robot does about a hazard)
# ----------------------------------------------------------------------------
RESPONSES = {
    "emergency_stop": {
        "name": "Emergency stop (safe-rated)",
        "origin": "generic",
        "kind": "estop", "defeat": "hard",
        "range_m": 600,             # acts when a hazard is within the protective field
        "defeats_rf_only": False,
        "max_target_speed": 1e9,
        "note": "Safety-rated immediate halt when a hazard enters the protective field. Always applicable; the baseline safe response.",
        "src": "ISO 13849 / IEC 61508 safe-stop function",
    },
    "dynamic_replan": {
        "name": "Dynamic re-plan (avoidance)",
        "origin": "generic",
        "kind": "replan", "defeat": "hard",
        "range_m": 900,             # needs room/time, so it works at longer range
        "defeats_rf_only": False,
        "max_target_speed": 8.0,    # can't replan around a very fast intruder — must stop instead
        "dwell_s": 0.5,
        "note": "Re-routes around a detected obstacle at range; keeps the robot moving. Fails for a fast close intruder (then only a stop helps).",
        "src": "navigation-stack local planner (e.g. ROS Nav2 / TEB)",
    },
    "speed_zone": {
        "name": "Speed-zone limiter (slow field)",
        "origin": "generic",
        "kind": "slow", "defeat": "soft",
        "range_m": 1000,
        "defeats_rf_only": False,
        "max_target_speed": 1e9,
        "note": "Slows the robot in a warning field so a later stop is effective. Soft measure; mitigates, doesn't resolve on its own.",
        "src": "ISO 3691-4 warning/protective field speed control",
    },
    "rf_zone_mutual": {
        "name": "RF mutual-awareness stop (tag-based)",
        "origin": "generic",
        "kind": "rf_stop", "defeat": "soft",
        "range_m": 1200,
        "defeats_rf_only": True,     # only works for RF-TAGGED people/vehicles — blind to untagged
        "max_target_speed": 1e9,
        "note": "Stops/slows when an RF-tagged worker or vehicle is near. Only protects TAGGED objects — an untagged person or debris gets no response.",
        "src": "UWB/RFID mutual-awareness safety system",
    },
}

# ----------------------------------------------------------------------------
# SAFETY CONTROLLER / COMPUTE — the "brain": fuses sensors, decides, commands responses.
# Where the software attack surface lives (ROS/DDS, message auth, state integrity).
# ----------------------------------------------------------------------------
CONTROLLERS = {
    "ctrl_hardened": {
        "name": "Hardened safety controller (authenticated, redundant)",
        "kind": "c2", "resilience": 0.9,
        "note": "Authenticated sensor feeds, message integrity, redundant safety channel — resists injection/replay/spoofing best.",
        "src": "security-hardened safety controller baseline",
    },
    "ctrl_standard": {
        "name": "Standard controller (ROS 2/DDS, basic auth)",
        "kind": "c2", "resilience": 0.5,
        "note": "ROS 2 / DDS with basic security — typical fielded AMR stack; partially resists data-layer attacks.",
        "src": "typical fielded AMR controller (ROS 2 / DDS)",
    },
    "ctrl_legacy": {
        "name": "Legacy controller (unauthenticated topics)",
        "kind": "c2", "resilience": 0.15,
        "note": "Trusts sensor topics without authentication — highly exposed to false-detection injection, replay, spoofing.",
        "src": "legacy / unauthenticated robot controller",
    },
}

# ----------------------------------------------------------------------------
# MARINE perception + responses — for the autonomous-fishing-boat profile (worked example of
# extending the lab to a new robot type). Real published-spec figures where available.
# ----------------------------------------------------------------------------
MARINE = {
    "marine_radar": {
        "name": "Marine radar (4 kW radome)",
        "origin": "generic",
        "kind": "radar",
        "range_m": 48000,           # up to ~48 NM; IMO: small vessel w/ reflector detectable at ~5 NM
        "fov_az": 360, "fov_el": 0,
        "update_hz": 1,
        "min_rcs": 0.2,             # small/low craft and buoys are weak returns in sea clutter
        "note": "X-band marine radar; 360° but weak on small low-RCS craft and in sea clutter. IMO detectability ~5 NM for a small vessel with a reflector.",
        "src": "IMO radar performance standard; small-craft radar guidance (yachtingmonthly)",
    },
    "ais_receiver": {
        "name": "AIS receiver (transponder-based)",
        "origin": "generic",
        "kind": "rf",
        "range_m": 22000,           # VHF line-of-sight, ~12-20 NM
        "fov_az": 360, "fov_el": 0,
        "note": "Receives AIS transponder broadcasts from other vessels (~12-20 NM). ONLY sees AIS-equipped craft — blind to rocks, nets, and small boats without a transponder.",
        "src": "AIS line-of-sight range guidance (practical-sailor / yachtingmonthly)",
    },
    "sonar": {
        "name": "Forward-looking sonar",
        "origin": "generic",
        "kind": "ultrasonic",
        "range_m": 600,             # tens-to-hundreds of metres forward obstacle detection
        "fov_az": 90, "fov_el": 0,
        "min_rcs": 0.1,
        "note": "Forward-looking sonar for sub-surface / close obstacles (rocks, nets). Narrow forward arc; short range.",
        "src": "forward-looking sonar for ASV obstacle avoidance (ardupilot discuss)",
    },
    "gnss_marine": {
        "name": "Marine GNSS (position/heading)",
        "origin": "generic",
        "kind": "rf",
        "range_m": 60000,
        "fov_az": 360, "fov_el": 0,
        "note": "GNSS position/heading source for the vessel's own navigation. Spoofable — a localization attack pulls the whole collision-avoidance plot off true.",
        "src": "GNSS for marine autonomous navigation",
    },
    "engine_cut": {
        "name": "Engine cut / crash-stop",
        "origin": "generic",
        "kind": "estop", "defeat": "hard",
        "range_m": 600,
        "defeats_rf_only": False, "max_target_speed": 1e9,
        "note": "Immediate propulsion cut when a hazard is close. Slow to take effect at sea (momentum) but the last-line response.",
        "src": "ASV safe-stop behaviour",
    },
    "course_replan": {
        "name": "Course re-plan (COLREGs avoidance)",
        "origin": "generic",
        "kind": "replan", "defeat": "hard",
        "range_m": 900, "defeats_rf_only": False, "max_target_speed": 8.0, "dwell_s": 0.5,
        "note": "Re-routes around a detected hazard at range per COLREGs. Needs sea-room and time; fails for a fast close contact.",
        "src": "COLREGs-compliant ASV path planning",
    },
}

ALL = {"lidar": LIDARS, "camera": CAMERAS, "ranging": RANGING,
       "marine": MARINE, "response": RESPONSES, "c2": CONTROLLERS}

# group mapping for the UI (which library dict -> which design slot)
SENSOR_GROUPS = {"lidar", "camera", "ranging"}


def catalog():
    out = []
    for group, items in ALL.items():
        for key, spec in items.items():
            out.append({"id": key, "group": group, **spec})
    return out
