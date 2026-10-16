"""Ground-truth world: drones flying toward a protected asset, and sensor models
that observe them as noisy detections ("plots"). This is the *real* data the
tracker and fusion layers consume — and the data the attack harness corrupts.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field

ASSET = np.array([0.0, 0.0])          # protected asset at origin (metres)
RNG = np.random.default_rng(7)         # fixed seed → reproducible experiments


@dataclass
class Drone:
    id: int
    pos: np.ndarray                    # [x, y]  metres
    vel: np.ndarray                    # [vx, vy] m/s
    hostile: bool
    rcs: float                         # radar cross-section (m^2)
    rf: bool                           # emits an RF control link
    alive: bool = True

    def step(self, dt: float):
        # hostiles home in on the asset (strong steer, light wander so they actually arrive);
        # benign craft transit across the area.
        if self.hostile:
            desired = ASSET - self.pos
            steer, wander = 0.5, 0.015      # commit hard to the asset — every hostile is a real threat
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
    kind: str                          # 'radar' | 'rf' | 'eo'
    rng: float                         # detection range (m)
    pos_noise: float                   # std dev of position error (m)
    pd: float                          # probability of detection per scan
    min_rcs: float = 0.15              # smallest radar cross-section this radar can see
    fov_az: float = 360.0              # azimuth coverage (deg); <360 → a blind arc exists
    facing: float = 0.0                # centre bearing of the FoV (rad), set at layout time
    online: bool = True

    def in_fov(self, d: Drone) -> bool:
        if self.fov_az >= 360:
            return True
        bearing = np.arctan2(d.pos[1] - ASSET[1], d.pos[0] - ASSET[0])
        diff = abs((bearing - self.facing + np.pi) % (2 * np.pi) - np.pi)
        return diff <= np.radians(self.fov_az) / 2

    def detects(self, d: Drone) -> bool:
        if self.kind == "radar":
            return d.rcs >= self.min_rcs   # a more sensitive radar sees smaller drones
        if self.kind == "rf":
            return d.rf
        if self.kind == "eo":
            return True
        return False


@dataclass(eq=False)
class Plot:
    """A raw sensor detection at one timestep."""
    pos: np.ndarray
    sensor: str
    t: float
    truth_id: int | None               # which drone it came from (None = clutter/injected)
    truth_hostile: bool = False
    injected: bool = False             # set by the attack harness


def default_sensors() -> list[Sensor]:
    return [
        Sensor("X-band radar", "radar", rng=4000, pos_noise=18, pd=0.9),
        Sensor("RF/ESM",       "rf",    rng=5000, pos_noise=40, pd=0.85),
        Sensor("EO/IR",        "eo",    rng=2200, pos_noise=10, pd=0.8),
    ]


# map a real-component "kind" to the sim sensor kind + reasonable noise/pd from specs
_KIND_MAP = {"radar": "radar", "rf": "rf", "eo": "eo", "acoustic": "acoustic"}

def sensor_from_component(spec: dict) -> Sensor | None:
    """Build a sim Sensor from a real-component spec (components.py)."""
    k = _KIND_MAP.get(spec.get("kind"))
    if k is None:
        return None
    # noise/pd derived from the kind (radars precise, RF coarse DF, EO precise-but-short)
    noise = {"radar": 18, "rf": 45, "eo": 10, "acoustic": 35}[k]
    pd = {"radar": 0.9, "rf": 0.85, "eo": 0.8, "acoustic": 0.75}[k]
    # scale sim range to the map (real ranges are km; the sim world is ~1.2 km across)
    rng = min(float(spec.get("range_m", 3000)) / 3.0, 1600)
    min_rcs = float(spec.get("min_rcs", 0.15))   # real sensitivity: micro-Doppler radars see tiny UAS
    fov_az = float(spec.get("fov_az", 360))       # narrow-FoV sensors (e.g. 120°) have blind arcs
    s = Sensor(spec.get("name", k), k, rng=rng, pos_noise=noise, pd=pd, min_rcs=min_rcs, fov_az=fov_az)
    s.component = spec
    return s


def spawn_drones(n_hostile=4, n_benign=3) -> list[Drone]:
    drones = []
    did = 1
    for i in range(n_hostile + n_benign):
        hostile = i < n_hostile
        ang = RNG.uniform(0, 2 * np.pi)
        r = RNG.uniform(700, 1100)       # start within approach distance so they engage quickly
        pos = ASSET + r * np.array([np.cos(ang), np.sin(ang)])
        # velocity roughly toward asset
        to_asset = (ASSET - pos)
        to_asset = to_asset / (np.linalg.norm(to_asset) + 1e-9)
        spd = RNG.uniform(18, 40) if hostile else RNG.uniform(14, 22)
        typ = RNG.choice(["quad", "fpv", "fixed", "nano"])
        rcs = {"quad": 0.6, "fpv": 0.35, "fixed": 1.0, "nano": 0.08}[typ]
        drones.append(Drone(id=did, pos=pos.copy(), vel=to_asset * spd,
                            hostile=hostile, rcs=rcs, rf=True))
        did += 1
    return drones


def sense(sensors: list[Sensor], drones: list[Drone], t: float) -> list[Plot]:
    """Produce this timestep's raw plots from all online sensors."""
    plots: list[Plot] = []
    for s in sensors:
        if not s.online:
            continue
        for d in drones:
            if not d.alive:
                continue
            if np.linalg.norm(d.pos - s.pos_ref()) > s.rng:
                continue
            if not s.in_fov(d):          # narrow-FoV sensors have blind arcs
                continue
            if not s.detects(d):
                continue
            if RNG.random() > s.pd:
                continue
            noisy = d.pos + RNG.normal(0, s.pos_noise, 2)
            plots.append(Plot(pos=noisy, sensor=s.kind, t=t,
                              truth_id=d.id, truth_hostile=d.hostile))
    return plots


# sensors sit at the asset for simplicity
def _pos_ref(self):
    return ASSET
Sensor.pos_ref = _pos_ref
