"""Ground-truth world for an autonomous mobile robot (AMR) on a warehouse floor, and the
sensor models that observe it as noisy detections ("plots").

The robot operates at the origin's zone. "Hazards" are people/obstacles moving into its path
that MUST be detected and safely handled (stop/avoid). "Cleared" objects are things correctly
judged safe to pass — they test whether the safety system wrongly halts for nothing.

This is the *real* data the perception tracker and fusion layers consume — and the data the
attack harness corrupts. Same engine shape as the C-UAS lab; robotics semantics.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field

ASSET = np.array([0.0, 0.0])          # the robot / its protected operating point (metres)
RNG = np.random.default_rng(7)         # fixed seed → reproducible experiments


@dataclass
class Obstacle:
    """A person or object in the robot's environment.
    hazard=True  -> on a path/behaviour that will intrude the robot's safety envelope.
    hazard=False -> a 'cleared' object correctly passable (tests false-stops / availability).
    """
    id: int
    pos: np.ndarray                    # [x, y]  metres
    vel: np.ndarray                    # [vx, vy] m/s
    hazard: bool
    reflectivity: float                # how well LiDAR/radar sees it (like RCS; small/dark = low)
    emits_rf: bool                     # carries an RF tag/beacon (e.g. worker wearable, AGV radio)
    alive: bool = True                 # still unresolved (not yet handled or collided)

    # kept as aliases so the shared tracker/attack code (written for the C-UAS lab) works unchanged
    @property
    def hostile(self):
        return self.hazard

    @property
    def rcs(self):
        return self.reflectivity

    @property
    def rf(self):
        return self.emits_rf

    def step(self, dt: float):
        # hazards move toward the robot's zone (an intrusion); cleared objects transit past.
        if self.hazard:
            desired = ASSET - self.pos
            steer, wander = 0.5, 0.015
        else:
            desired = -self.pos
            steer, wander = 0.05, 0.05
        d = desired / (np.linalg.norm(desired) + 1e-9)
        speed = np.linalg.norm(self.vel) + 1e-9
        heading = self.vel / speed
        new_h = heading + steer * d + RNG.normal(0, wander, 2)
        new_h = new_h / (np.linalg.norm(new_h) + 1e-9)
        self.vel = new_h * speed
        self.pos = self.pos + self.vel * dt


@dataclass
class Sensor:
    name: str
    kind: str                          # 'lidar' | 'camera' | 'radar' | 'ultrasonic' | 'rf'
    rng: float                         # detection range (m)
    pos_noise: float                   # std dev of position error (m)
    pd: float                          # probability of detection per scan
    min_rcs: float = 0.15              # smallest reflectivity this sensor can see
    fov_az: float = 360.0              # azimuth coverage (deg); <360 → a blind arc exists
    facing: float = 0.0                # centre bearing of the FoV (rad), set at layout time
    online: bool = True

    def in_fov(self, d) -> bool:
        if self.fov_az >= 360:
            return True
        bearing = np.arctan2(d.pos[1] - ASSET[1], d.pos[0] - ASSET[0])
        diff = abs((bearing - self.facing + np.pi) % (2 * np.pi) - np.pi)
        return diff <= np.radians(self.fov_az) / 2

    def detects(self, d) -> bool:
        if self.kind in ("lidar", "radar", "ultrasonic"):
            return d.reflectivity >= self.min_rcs   # ranging sensors need enough return
        if self.kind == "rf":
            return d.emits_rf                        # only sees RF-tagged objects
        if self.kind == "camera":
            return True                              # camera sees anything in FoV (in daylight)
        return False


@dataclass(eq=False)
class Plot:
    """A raw sensor detection at one timestep."""
    pos: np.ndarray
    sensor: str
    t: float
    truth_id: int | None               # which obstacle it came from (None = clutter/injected)
    truth_hostile: bool = False        # (= truth_hazard; name kept for shared engine code)
    injected: bool = False             # set by the attack harness


def default_sensors() -> list[Sensor]:
    return [
        Sensor("Safety LiDAR", "lidar", rng=1800, pos_noise=12, pd=0.92),
        Sensor("Depth camera", "camera", rng=1200, pos_noise=10, pd=0.85),
        Sensor("RF tag reader", "rf", rng=2000, pos_noise=40, pd=0.85),
    ]


_KIND_MAP = {"lidar": "lidar", "camera": "camera", "radar": "radar",
             "ultrasonic": "ultrasonic", "rf": "rf"}


def sensor_from_component(spec: dict):
    """Build a sim Sensor from a real-component spec (components.py)."""
    k = _KIND_MAP.get(spec.get("kind"))
    if k is None:
        return None
    noise = {"lidar": 12, "camera": 10, "radar": 18, "ultrasonic": 20, "rf": 45}[k]
    pd = {"lidar": 0.92, "camera": 0.85, "radar": 0.9, "ultrasonic": 0.8, "rf": 0.85}[k]
    rng = min(float(spec.get("range_m", 3000)) / 3.0, 1600)
    min_rcs = float(spec.get("min_rcs", 0.15))
    fov_az = float(spec.get("fov_az", 360))
    s = Sensor(spec.get("name", k), k, rng=rng, pos_noise=noise, pd=pd, min_rcs=min_rcs, fov_az=fov_az)
    s.component = spec
    return s


# Active robot profile for spawning (set by run_once). None => the default warehouse-AMR behaviour,
# so nothing changes unless a profile is explicitly selected.
ACTIVE_PROFILE = None


def spawn_drones(n_hostile=4, n_benign=3):
    """Named spawn_drones for engine compatibility; spawns hazards (n_hostile) + cleared (n_benign).
    Object classes + approach speeds come from the ACTIVE_PROFILE when one is set, else AMR defaults."""
    world = (ACTIVE_PROFILE or {}).get("world", {}) if ACTIVE_PROFILE else {}
    classes = world.get("object_classes") or [
        {"name": "person", "reflectivity": 0.5, "rf": True},
        {"name": "forklift", "reflectivity": 1.0, "rf": True},
        {"name": "pallet", "reflectivity": 0.7, "rf": False},
        {"name": "debris", "reflectivity": 0.08, "rf": False},
    ]
    hs = world.get("hazard_speed", [14, 34])
    cs = world.get("cleared_speed", [10, 18])
    obstacles = []
    oid = 1
    for i in range(n_hostile + n_benign):
        hazard = i < n_hostile
        ang = RNG.uniform(0, 2 * np.pi)
        r = RNG.uniform(700, 1100)
        pos = ASSET + r * np.array([np.cos(ang), np.sin(ang)])
        to_asset = (ASSET - pos)
        to_asset = to_asset / (np.linalg.norm(to_asset) + 1e-9)
        spd = RNG.uniform(hs[0], hs[1]) if hazard else RNG.uniform(cs[0], cs[1])
        idx = int(RNG.integers(0, len(classes)))
        cl = classes[idx]
        obstacles.append(Obstacle(id=oid, pos=pos.copy(), vel=to_asset * spd,
                                  hazard=hazard, reflectivity=float(cl.get("reflectivity", 0.5)),
                                  emits_rf=bool(cl.get("rf", True))))
        oid += 1
    return obstacles


def sense(sensors: list[Sensor], obstacles, t: float) -> list[Plot]:
    """Produce this timestep's raw plots from all online sensors."""
    plots: list[Plot] = []
    for s in sensors:
        if not s.online:
            continue
        for d in obstacles:
            if not d.alive:
                continue
            if np.linalg.norm(d.pos - s.pos_ref()) > s.rng:
                continue
            if not s.in_fov(d):
                continue
            if not s.detects(d):
                continue
            if RNG.random() > s.pd:
                continue
            noisy = d.pos + RNG.normal(0, s.pos_noise, 2)
            plots.append(Plot(pos=noisy, sensor=s.kind, t=t,
                              truth_id=d.id, truth_hostile=d.hazard))
    return plots


def _pos_ref(self):
    return ASSET
Sensor.pos_ref = _pos_ref
