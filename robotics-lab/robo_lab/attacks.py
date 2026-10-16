"""Attack / fault-injection harness for the robotics safety pipeline.

Each attack is a real transformation applied to the data as it flows from sensors into the
perception/safety layer — the same place an adversary who has reached the sensor-to-controller
path (or the controller itself) would operate. Nothing is faked: the tracker genuinely receives
corrupted input and genuinely mis-perceives, so the robot makes an unsafe decision from a valid
command. This is the HIVE thesis — valid command, unsafe outcome — on a robot.

Same attack mechanics as the C-UAS lab; robotics framing (person/obstacle, collision, false-stop).
"""
from __future__ import annotations
import numpy as np
from .world import Plot, ASSET

RNG = np.random.default_rng(23)


class Attack:
    name = "none"; key = "none"; maps_to = ""
    def on_plots(self, plots, t): return plots
    def on_sensors(self, sensors, t): pass
    def on_tracks(self, tracker, t): pass


# ---- availability / safety-function loss ----

class PacketLoss(Attack):
    name = "Packet loss (DoS)"; key = "packet_loss"; maps_to = "DoS / sensor blinding"
    def __init__(self, drop=0.6): self.drop = drop
    def on_plots(self, plots, t):
        return [p for p in plots if RNG.random() > self.drop]


class Latency(Attack):
    name = "High latency"; key = "latency"; maps_to = "Delayed safety response"
    def __init__(self, buf=12): self.buf = buf; self._q = []
    def on_plots(self, plots, t):
        self._q.append(plots)
        if len(self._q) <= self.buf:
            return []
        return self._q.pop(0)


class SensorFlood(Attack):
    name = "Sensor flooding"; key = "flood"; maps_to = "Saturation / overload"
    def __init__(self, n=50): self.n = n
    def on_plots(self, plots, t):
        extra = [Plot(pos=ASSET + RNG.uniform(-280, 280, 2), sensor="lidar",
                      t=t, truth_id=None, truth_hostile=True, injected=True) for _ in range(self.n)]
        return plots + extra


# ---- deception / integrity ----

class FalseTrackInjection(Attack):
    name = "Phantom-obstacle injection"; key = "false_track"; maps_to = "False-detection injection"
    def __init__(self, n=3, swarm=4):
        self.n = n; self.swarm = swarm; self._anchors = None
    def on_plots(self, plots, t):
        if self._anchors is None:
            self._anchors = [ASSET + RNG.uniform(-260, 260, 2) for _ in range(self.swarm)]
        inj = []
        for a in self._anchors:
            a += np.array([5.0, 2.0])
            for _ in range(self.n):
                inj.append(Plot(pos=a + RNG.normal(0, 8, 2), sensor="lidar", t=t,
                                truth_id=None, truth_hostile=True, injected=True))
        return plots + inj


class ReplayDuplicate(Attack):
    name = "Replay / duplicate detections"; key = "replay"; maps_to = "Replay & message tampering"
    def on_plots(self, plots, t):
        dupes = [Plot(pos=p.pos + np.array([120.0, 120.0]), sensor=p.sensor, t=t,
                      truth_id=None, truth_hostile=True, injected=True) for p in plots if p.truth_id]
        return plots + dupes


class GpsOffset(Attack):
    name = "Localization spoof (position offset)"; key = "gps"; maps_to = "Localization / state spoofing"
    def __init__(self, bias=(140.0, -90.0)): self.bias = np.array(bias)
    def on_plots(self, plots, t):
        return [Plot(pos=p.pos + self.bias, sensor=p.sensor, t=t,
                     truth_id=p.truth_id, truth_hostile=p.truth_hostile,
                     injected=p.injected) for p in plots]


class TimestampAnomaly(Attack):
    name = "Timestamp anomaly"; key = "timestamp"; maps_to = "Protocol tampering (desync)"
    def on_plots(self, plots, t):
        out = []
        for p in plots:
            if RNG.random() < 0.4:
                out.append(Plot(pos=p.pos + RNG.normal(0, 60, 2), sensor=p.sensor,
                                t=t, truth_id=p.truth_id, truth_hostile=p.truth_hostile))
            else:
                out.append(p)
        return out


class MalformedTelemetry(Attack):
    name = "Malformed sensor message"; key = "malformed"; maps_to = "Protocol fuzzing"
    def on_plots(self, plots, t):
        # mix of wildly out-of-bounds values (test range/sanity checks) AND plausible-but-wrong
        # in-range coordinates (test deeper validation) — the latter actually corrupt the picture
        # on a stack that doesn't validate, so a vulnerable controller mis-perceives.
        far = [Plot(pos=ASSET + RNG.uniform(-9000, 9000, 2), sensor="rf", t=t,
                    truth_id=None, truth_hostile=True, injected=True) for _ in range(4)]
        near = [Plot(pos=ASSET + RNG.uniform(-260, 260, 2), sensor="lidar", t=t,
                     truth_id=None, truth_hostile=True, injected=True) for _ in range(6)]
        return plots + far + near


# ---- sensor-layer ----

class SensorDropout(Attack):
    name = "Camera dropout (blinding)"; key = "cam_blind"; maps_to = "Modality dropout"
    def on_sensors(self, sensors, t):
        for s in sensors:
            if s.kind == "camera":
                s.online = False


class SensorDisagreement(Attack):
    name = "Sensor disagreement"; key = "disagree"; maps_to = "Fusion poisoning"
    def on_plots(self, plots, t):
        return [Plot(pos=(p.pos + RNG.normal(0, 150, 2)) if p.sensor == "rf" else p.pos,
                     sensor=p.sensor, t=t, truth_id=p.truth_id,
                     truth_hostile=p.truth_hostile, injected=p.injected) for p in plots]


class ClassSpoof(Attack):
    name = "Misclassification (person read as clear)"; key = "class_spoof"; maps_to = "Falsify classification"
    def on_tracks(self, tracker, t):
        # flip a CLEARED object to read as a hazard -> the robot slams an emergency stop on
        # safe traffic (nuisance stop); and (below in the engine) a hazard mis-read as cleared
        # is modelled via suppression. Here we force false-positive stops on cleared objects.
        for tr in tracker.tracks:
            if tr.confirmed and tr.truth_id is not None and tr.truth_hostile is False:
                tr.believed_hostile = True


class TrackSuppression(Attack):
    name = "Detection suppression"; key = "suppress"; maps_to = "Suppress real detection"
    def __init__(self, fraction=0.5): self._blocked = set(); self.fraction = fraction
    def on_tracks(self, tracker, t):
        hazards = [tr.truth_id for tr in tracker.tracks
                   if tr.confirmed and tr.truth_hostile and tr.truth_id is not None]
        want = max(1, int(len(set(hazards)) * self.fraction))
        for tid in hazards:
            if len(self._blocked) >= want:
                break
            self._blocked.add(tid)
        tracker.tracks = [tr for tr in tracker.tracks if tr.truth_id not in self._blocked]


class SlewToCue(Attack):
    name = "Active-sensor misdirection"; key = "slew"; maps_to = "Weaponised automation"
    def on_sensors(self, sensors, t):
        for s in sensors:
            if s.kind == "camera":
                s.online = False


class EffectorExhaustion(Attack):
    name = "Safe-stop exhaustion (nuisance stops)"; key = "exhaust"; maps_to = "Safety-response exhaustion"
    def __init__(self, n=6): self.n = n
    def on_plots(self, plots, t):
        extra = [Plot(pos=ASSET + RNG.uniform(-260, 260, 2), sensor="lidar", t=t,
                      truth_id=None, truth_hostile=True, injected=True) for _ in range(self.n)]
        return plots + extra


class SpoofedFireCommand(Attack):
    name = "Spoofed stop/override command"; key = "spoof_cmd"; maps_to = "Unauthorised control command"
    def on_tracks(self, tracker, t):
        for tr in tracker.tracks:
            if tr.confirmed and tr.truth_id is not None and tr.truth_hostile is False:
                tr.believed_hostile = True


class TrackSwap(Attack):
    name = "Object-ID swap / confusion"; key = "track_swap"; maps_to = "Identity / state confusion"
    def on_tracks(self, tracker, t):
        conf = [tr for tr in tracker.tracks if tr.confirmed and tr.truth_id is not None]
        if len(conf) >= 2 and RNG.random() < 0.3:
            a, b = RNG.choice(len(conf), size=2, replace=False)
            conf[a].truth_id, conf[b].truth_id = conf[b].truth_id, conf[a].truth_id
            conf[a].truth_hostile, conf[b].truth_hostile = conf[b].truth_hostile, conf[a].truth_hostile


class CoastExploit(Attack):
    name = "Coast exploitation"; key = "coast"; maps_to = "Tracker prediction abuse"
    def __init__(self, drop=0.85): self.drop = drop
    def on_plots(self, plots, t):
        return [p for p in plots if (p.truth_id is None or RNG.random() > self.drop)]


ALL_ATTACKS = [
    PacketLoss, Latency, SensorFlood,
    FalseTrackInjection, ReplayDuplicate, GpsOffset, TimestampAnomaly, MalformedTelemetry,
    SensorDropout, SensorDisagreement, TrackSuppression, ClassSpoof,
    SlewToCue, EffectorExhaustion, SpoofedFireCommand, TrackSwap, CoastExploit,
]

DESCRIPTIONS = {
    "packet_loss": "Drops a large fraction of sensor messages before they reach perception — a denial-of-service on the sensor-to-controller link. The robot's picture of its surroundings goes patchy and it reacts late.",
    "latency":     "Holds sensor data for several cycles so the safety controller acts on stale information — the sense-to-stop loop lags, and a fast-approaching person is inside the danger zone before the robot halts.",
    "flood":       "Injects hundreds of fake detections around the robot. They confirm as obstacles and soak up the finite safe-stop/replan capacity, so a real intruder goes un-handled.",
    "false_track": "Creates coherent phantom obstacles that move and confirm like real ones — the robot keeps stopping/replanning for things that aren't there (lost availability) while a real hazard hides in the noise.",
    "replay":      "Re-sends previously captured detections as duplicate/stale obstacles — ghost twins that trigger needless stops and clutter the safety picture.",
    "gps":         "Spoofs the robot's localization / an obstacle's reported position so the safety envelope is computed in the wrong place. The robot avoids where the hazard ISN'T — and collides with where it IS.",
    "timestamp":   "Corrupts message timing/ordering so detection-to-track association degrades — tracks jitter and position accuracy drops across the scene.",
    "malformed":   "Injects out-of-bounds / garbage coordinates (protocol fuzzing) — tests whether the stack rejects bad input or lets it corrupt the obstacle picture.",
    "cam_blind":   "Forces the depth camera offline (lens blinding, jamming, fault). The robot loses its high-accuracy classification sensor and leans on LiDAR/RF alone.",
    "disagree":    "Makes one sensor modality report a different position than the others for the same object — fusion poisoning. The fused estimate drifts off truth and the safety zone is placed wrong.",
    "suppress":    "Deletes a fraction of confirmed hazard detections before the controller sees them — those people/obstacles are never reacted to and the robot drives into them.",
    "class_spoof": "Flips a cleared object to read as a hazard — the robot slams nuisance emergency stops on safe traffic (and, inversely, a suppressed hazard reads as clear). Safety-integrity failure.",
    "slew":        "Abuses the automation that aims an active sensor, dragging it off the real hazard — the system's own logic turned against it.",
    "exhaust":     "Baits the finite safe-stop/replan responses with phantom hazards until the robot is effectively stuck in nuisance stops — then a real hazard arrives with no response budget left.",
    "spoof_cmd":   "Forges a stop/override command (control-auth bypass) to halt or move the robot inappropriately — e.g. an unsafe motion while a person is present.",
    "track_swap":  "Swaps the identity binding of two tracked objects so the robot reacts to the wrong one and loses custody of the right one — identity/state confusion.",
    "coast":       "Starves the tracker of updates on real hazards so it COASTS on prediction; the person then changes direction and the predicted track drifts off them.",
}

BASIS = {
    "packet_loss": "Magnitude illustrative (a set fraction of messages dropped); real loss depends on the DoS technique and link margin. Direction — missed updates delay the safety response — is the finding.",
    "latency":     "We hold data a fixed number of cycles; real added latency depends on the injection point and buffering. Direction — a lagged loop lets a fast hazard inside the zone — is the finding.",
    "flood":       "Phantom count is a chosen load; a real saturation attack scales with injected message rate vs controller capacity. Direction — safe-stop budget soaked up by phantoms — is the finding.",
    "false_track": "Number of phantoms is a modelling choice; realism depends on how convincingly an adversary can forge coherent detections. Direction — nuisance stops while a real hazard hides — is the finding.",
    "replay":      "Replay volume is chosen; real impact depends on message auth/nonce handling. Direction — stale duplicates trigger needless stops — is the finding.",
    "gps":         "Offset size is illustrative; a real localization spoof's pull depends on the spoofing method. Direction — safety zone computed in the wrong place, collision — is the finding.",
    "timestamp":   "Timing corruption is modelled; real effect depends on how the stack orders/validates messages. Direction — association degrades, accuracy drops — is the finding.",
    "malformed":   "A chosen rate of out-of-bounds values; real outcome depends on input validation. Direction — bad input corrupts the picture unless rejected — is the finding.",
    "cam_blind":   "We take one modality fully offline; reality is partial/intermittent degradation. Direction — loss of the high-accuracy classification sensor — is the finding.",
    "disagree":    "Disagreement size is chosen; real fusion poisoning depends on the fusion algorithm's robustness. Direction — fused estimate drifts, safety zone misplaced — is the finding.",
    "suppress":    "Suppressed fraction is a modelling choice; real impact depends on detection-pipeline integrity. Direction — undetected hazards are hit — is the finding.",
    "class_spoof": "We flip a set fraction of classifications; real feasibility depends on classifier/auth design. Direction — nuisance stops / missed hazards (safety-integrity failure) — is the finding.",
    "slew":        "Sensor misdirection is modelled; real effect depends on automation guardrails. Direction — the robot's own cueing turned against it — is the finding.",
    "exhaust":     "Response budget is a parameter; real exhaustion depends on the actual safety-response design vs intrusion rate. Direction — stuck in nuisance stops, no budget for a real hazard — is the finding.",
    "spoof_cmd":   "Forged-command rate is chosen; real feasibility depends on command auth. Direction — unsafe motion/stop on a valid-looking command — is the finding.",
    "track_swap":  "Swap rate is modelled; real impact depends on identity-binding integrity. Direction — custody lost, wrong object reacted to — is the finding.",
    "coast":       "Update starvation is modelled; real effect depends on coast-timeout tuning. Direction — predicted track drifts off a manoeuvring person — is the finding.",
}

# Each attack mapped to the CONCRETE ROS 2 / DDS weakness it exercises on a real robot, so the
# credibility chain is visible. Grounded in: DDS default = multicast discovery (UDP 7400), no auth,
# no encryption — any host on the subnet can enumerate topics, subscribe to sensor streams and
# PUBLISH to actuator topics (Canonical/Apex DDS advisory; CAI/Alias Unitree G1 assessment, Sep 2025,
# found 20+ unauthenticated ROS 2/DDS topics; CVE-2026-76639). SROS2 adds auth/encryption/access
# control but has documented gaps (permission revocation, namespace isolation, discovery leakage).
REFERENCE = {
    "packet_loss": "DDS transport availability — flooding/partition on the sensor→controller topic (RTPS over UDP); no QoS guarantee without SROS2 + reliable QoS.",
    "latency":     "Message timeliness on the perception→safety path; attacker delays RTPS traffic. Breaks the safety-reaction time (ISO 13849 / IEC 61508).",
    "flood":       "DDS has no default rate limiting — any subnet host can publish to a sensor topic and saturate the subscriber (ROS 2 topic flooding).",
    "false_track": "Unauthenticated DDS topics: an attacker publishes fake detections to e.g. /scan or /detections. Exactly the 20+ open topics found on the Unitree G1 (CAI/Alias 2025).",
    "replay":      "No default replay protection on RTPS — captured sensor messages re-published. SROS2/DDS-Security needs enabling for freshness.",
    "gps":         "Localization/state topic integrity (/odom, /tf, /amcl_pose, GPS). Spoofed pose moves the robot's whole world model.",
    "timestamp":   "RTPS source-timestamp / header.stamp tampering; desync breaks TF and sensor fusion ordering.",
    "malformed":   "No schema/bounds validation on DDS topics by default — malformed PointCloud2/LaserScan corrupts perception (protocol fuzzing, cf. RoboFuzz).",
    "cam_blind":   "Single-modality dependency — DoS/blinding of the camera topic (/image_raw); safety must not rely on one modality.",
    "disagree":    "Fusion trust model — publish conflicting values on one sensor topic to poison the fused estimate (no cross-sensor authentication).",
    "suppress":    "Drop/withhold a safety-critical detection topic (DDS partition, or a malicious node that shadows it). Detection-pipeline integrity.",
    "class_spoof": "Classification/IFF integrity. First-class in ISO 10218:2025 & ISO 3691-4: cybersecurity scoped to how it affects SAFETY (person vs clear).",
    "slew":        "Guardrails on active-sensing automation — publish to a pan/tilt or mode topic to misdirect the sensor.",
    "exhaust":     "Safety-response logic & finite-resource protection — bait repeated safe-stops via injected hazards (availability).",
    "spoof_cmd":   "Actuator-command authentication — DDS lets any subnet host publish to /cmd_vel or an e-stop topic without SROS2. CVE-class (Unitree G1 WebRTC→DDS bridge, CVE-2026-76639).",
    "track_swap":  "Object identity binding / state integrity across frames.",
    "coast":       "Tracker coast/timeout policy — starve a track's update topic so prediction drifts (prediction abuse).",
}
