"""A real multi-target tracker: constant-velocity Kalman filter per track,
nearest-neighbour association with a gate, and M-of-N confirmation logic.

This is the component a cyber adversary actually attacks — by corrupting the
plots that feed it (injection, dropout, delay, malformed data). The tracker has
no idea whether a plot is genuine; that trust is the vulnerability.

Identical algorithm to the C-UAS lab's tracker — perception/state estimation is
domain-agnostic, which is exactly why the same attacks apply to any autonomous system.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
import itertools

_track_ids = itertools.count(1)


@dataclass(eq=False)
class Track:
    id: int
    x: np.ndarray                      # state [px, py, vx, vy]
    P: np.ndarray                      # covariance 4x4
    hits: int = 0
    misses: int = 0
    age: int = 0
    confirmed: bool = False
    truth_id: int | None = None        # last associated truth (for scoring only)
    truth_hostile: bool = False        # (= truth_hazard; name kept for shared engine code)
    believed_hostile: bool | None = None  # what the safety controller THINKS (attacks can flip this)
    fake_support: int = 0              # plots that were injected/clutter
    last_update_t: float = 0.0

    @property
    def pos(self):
        return self.x[:2]


class KalmanTracker:
    def __init__(self, dt=0.1, gate=90.0, confirm_hits=3, drop_misses=5,
                 q=4.0, r=25.0):
        self.dt = dt
        self.gate = gate
        self.confirm_hits = confirm_hits
        self.drop_misses = drop_misses
        self.tracks: list[Track] = []
        self.F = np.array([[1, 0, dt, 0],
                           [0, 1, 0, dt],
                           [0, 0, 1,  0],
                           [0, 0, 0,  1]], float)
        self.H = np.array([[1, 0, 0, 0],
                           [0, 1, 0, 0]], float)
        self.Q = np.eye(4) * q
        self.R = np.eye(2) * (r ** 2)

    def _predict(self, tr: Track):
        tr.x = self.F @ tr.x
        tr.P = self.F @ tr.P @ self.F.T + self.Q

    def _update(self, tr: Track, z: np.ndarray):
        y = z - self.H @ tr.x
        S = self.H @ tr.P @ self.H.T + self.R
        K = tr.P @ self.H.T @ np.linalg.inv(S)
        tr.x = tr.x + K @ y
        tr.P = (np.eye(4) - K @ self.H) @ tr.P

    def step(self, plots, t):
        for tr in self.tracks:
            self._predict(tr)
            tr.age += 1

        unused = list(plots)
        for tr in self.tracks:
            best, bd = None, self.gate
            for p in unused:
                dd = np.linalg.norm(p.pos - tr.pos)
                if dd < bd:
                    bd, best = dd, p
            if best is not None:
                self._update(tr, best.pos)
                tr.hits += 1
                tr.misses = 0
                tr.truth_id = best.truth_id
                tr.truth_hostile = best.truth_hostile
                tr.last_update_t = t
                if best.injected or best.truth_id is None:
                    tr.fake_support += 1
                unused.remove(best)
            else:
                tr.misses += 1

        for p in unused:
            x0 = np.array([p.pos[0], p.pos[1], 0.0, 0.0])
            tr = Track(id=next(_track_ids), x=x0, P=np.eye(4) * 500.0,
                       hits=1, truth_id=p.truth_id, truth_hostile=p.truth_hostile,
                       fake_support=1 if (p.injected or p.truth_id is None) else 0,
                       last_update_t=t)
            self.tracks.append(tr)

        for tr in self.tracks:
            if not tr.confirmed and tr.hits >= self.confirm_hits:
                tr.confirmed = True
        self.tracks = [tr for tr in self.tracks if tr.misses < self.drop_misses]

    def confirmed_tracks(self):
        return [t for t in self.tracks if t.confirmed]
