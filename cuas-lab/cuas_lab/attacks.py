"""Attack / fault-injection harness.

Each attack is a real transformation applied to the data as it flows from sensors
into the tracker/fusion layer — the same place a cyber adversary who has reached
the sensor-to-C2 path (or the C2 itself) would operate. Nothing here is faked:
the tracker genuinely receives corrupted input and genuinely mis-tracks.

Maps to the proposal's test catalogue (Section 16): false-track injection,
replay/duplicate, packet loss (DoS), latency, timestamp/GPS anomaly, malformed
telemetry, sensor flooding, sensor disagreement/dropout, track suppression.
"""
from __future__ import annotations
import numpy as np
from .world import Plot, ASSET

RNG = np.random.default_rng(23)


class Attack:
    """Base: transform the plot list for this timestep. Override one of the hooks."""
    name = "none"
    key = "none"
    maps_to = ""

    def on_plots(self, plots, t):      # modify/return the plot stream
        return plots

    def on_sensors(self, sensors, t):  # optionally disable sensors
        pass

    def on_tracks(self, tracker, t):   # optionally tamper with tracks directly
        pass


# ---- availability / mission-failure ----

class PacketLoss(Attack):
    name = "Packet loss (DoS)"; key = "packet_loss"; maps_to = "DoS / blinding"
    def __init__(self, drop=0.6): self.drop = drop
    def on_plots(self, plots, t):
        return [p for p in plots if RNG.random() > self.drop]


class Latency(Attack):
    name = "High latency"; key = "latency"; maps_to = "Delayed response"
    def __init__(self, buf=12): self.buf = buf; self._q = []
    def on_plots(self, plots, t):
        # hold plots for `buf` steps → tracker acts on stale data
        self._q.append(plots)
        if len(self._q) <= self.buf:
            return []
        return self._q.pop(0)


class SensorFlood(Attack):
    name = "Sensor flooding"; key = "flood"; maps_to = "Saturation / overload"
    def __init__(self, n=50): self.n = n
    def on_plots(self, plots, t):
        # concentrate many phantoms INSIDE the engagement zone (<300 m) so they confirm
        # as tracks and compete for the finite effectors — real saturation.
        extra = [Plot(pos=ASSET + RNG.uniform(-280, 280, 2), sensor="radar",
                      t=t, truth_id=None, truth_hostile=True, injected=True) for _ in range(self.n)]
        return plots + extra


# ---- deception / integrity ----

class FalseTrackInjection(Attack):
    name = "False-track injection"; key = "false_track"; maps_to = "False-track injection"
    def __init__(self, n=3, swarm=4):
        self.n = n; self.swarm = swarm
        self._anchors = None
    def on_plots(self, plots, t):
        # several coherent moving phantoms near the asset — they confirm as real tracks,
        # enter the zone, and soak up finite effectors (so real hostiles get through).
        if self._anchors is None:
            self._anchors = [ASSET + RNG.uniform(-260, 260, 2) for _ in range(self.swarm)]
        inj = []
        for a in self._anchors:
            a += np.array([5.0, 2.0])
            for _ in range(self.n):
                inj.append(Plot(pos=a + RNG.normal(0, 8, 2), sensor="rf", t=t,
                                truth_id=None, truth_hostile=True, injected=True))
        return plots + inj


class ReplayDuplicate(Attack):
    name = "Replay / duplicate tracks"; key = "replay"; maps_to = "Replay & message tampering"
    def __init__(self): self._seen = []
    def on_plots(self, plots, t):
        # duplicate real plots with an offset → ghost twins of real tracks
        dupes = [Plot(pos=p.pos + np.array([120.0, 120.0]), sensor=p.sensor, t=t,
                      truth_id=None, truth_hostile=True, injected=True) for p in plots if p.truth_id]
        return plots + dupes


class GpsOffset(Attack):
    name = "GPS / position offset"; key = "gps"; maps_to = "Sensor spoofing (GNSS)"
    def __init__(self, bias=(140.0, -90.0)): self.bias = np.array(bias)
    def on_plots(self, plots, t):
        # shift genuine detections → tracks drift off true position
        return [Plot(pos=p.pos + self.bias, sensor=p.sensor, t=t,
                     truth_id=p.truth_id, truth_hostile=p.truth_hostile,
                     injected=p.injected) for p in plots]


class TimestampAnomaly(Attack):
    name = "Timestamp anomaly"; key = "timestamp"; maps_to = "Protocol tampering (desync)"
    def on_plots(self, plots, t):
        # randomly reorder/stale a fraction → association degrades
        out = []
        for p in plots:
            if RNG.random() < 0.4:
                out.append(Plot(pos=p.pos + RNG.normal(0, 60, 2), sensor=p.sensor,
                                t=t, truth_id=p.truth_id, truth_hostile=p.truth_hostile))
            else:
                out.append(p)
        return out


class MalformedTelemetry(Attack):
    name = "Malformed telemetry"; key = "malformed"; maps_to = "Protocol fuzzing"
    def on_plots(self, plots, t):
        # mix of wildly out-of-bounds values (test range/sanity checks) AND plausible-but-wrong
        # in-range coordinates (test deeper validation). The in-range garbage actually corrupts the
        # picture on a C2 that doesn't validate — so malformed input genuinely bites a weak C2,
        # and a hardened C2 filtering it becomes a measurable defence (not a dead attack).
        far = [Plot(pos=ASSET + RNG.uniform(-9000, 9000, 2), sensor="rf", t=t,
                    truth_id=None, truth_hostile=True, injected=True) for _ in range(4)]
        near = [Plot(pos=ASSET + RNG.uniform(-260, 260, 2), sensor="radar", t=t,
                     truth_id=None, truth_hostile=True, injected=True) for _ in range(6)]
        return plots + far + near


class ProtocolFuzzing(Attack):
    """A protocol-aware FUZZER against the sensor-to-C2 messages (proposal §16.3: SAPIENT protobuf /
    Cursor-on-Target XML). Unlike 'Malformed telemetry' (a few junk coordinates), this systematically
    emits the real CLASSES of malformed/stateful message a protocol fuzzer produces, each stressing a
    different validation path:
      - out-of-range / boundary values (does the C2 range-check fields?)
      - type / NaN / infinity violations (does it reject non-finite numbers before they hit the filter?)
      - oversized / flooded batches (does it bound message volume?)
      - out-of-order / stale-timestamp messages (does it enforce sequencing?)
    A C2 that validates input rejects these (resilience filter below). A C2 that does NOT lets them
    reach the tracker: NaN/inf poisons the Kalman update and can corrupt or drop REAL tracks — the
    dangerous case a fuzzer is meant to find. This is modelled at the plot layer; a real engagement
    fuzzes the actual protocol bytes with a protocol-aware/ICS fuzzer.
    """
    key = "proto_fuzz"; name = "Protocol fuzzing (SAPIENT/CoT)"; maps_to = "Protocol fuzzing"

    def __init__(self, n=6):
        self.n = n
        self._i = 0

    def on_plots(self, plots, t):
        out = list(plots)
        self._i += 1
        # 1) out-of-range / boundary field values
        out += [Plot(pos=ASSET + RNG.uniform(-50000, 50000, 2), sensor="radar", t=t,
                     truth_id=None, truth_hostile=True, injected=True) for _ in range(self.n // 2)]
        # 2) type / non-finite violations: NaN and +/-inf coordinates. If the C2 doesn't reject these,
        #    the association/Kalman maths propagates NaN and can wreck a real nearby track.
        bad_vals = [np.nan, np.inf, -np.inf]
        for v in bad_vals:
            out.append(Plot(pos=np.array([v, RNG.uniform(-200, 200)]), sensor="rf", t=t,
                            truth_id=None, truth_hostile=True, injected=True))
        # 3) oversized / flooded batch (volume the parser/queue must bound)
        out += [Plot(pos=ASSET + RNG.uniform(-300, 300, 2), sensor="rf", t=t,
                     truth_id=None, truth_hostile=True, injected=True) for _ in range(self.n)]
        # 4) out-of-order / stale: replay a couple of this step's real plots with a stale marker
        for p in plots[:2]:
            if p.truth_id is not None:
                out.append(Plot(pos=p.pos.copy(), sensor=p.sensor, t=t - 5.0,  # stale timestamp
                                truth_id=None, truth_hostile=True, injected=True))
        return out


# ---- sensor-layer ----

class SensorDropout(Attack):
    name = "Sensor dropout (EO blind)"; key = "eo_blind"; maps_to = "Modality dropout"
    def on_sensors(self, sensors, t):
        for s in sensors:
            if s.kind == "eo":
                s.online = False


class SensorDisagreement(Attack):
    name = "Sensor disagreement"; key = "disagree"; maps_to = "Fusion poisoning"
    def on_plots(self, plots, t):
        # make RF plots disagree spatially with radar/EO on the same targets
        return [Plot(pos=(p.pos + RNG.normal(0, 150, 2)) if p.sensor == "rf" else p.pos,
                     sensor=p.sensor, t=t, truth_id=p.truth_id,
                     truth_hostile=p.truth_hostile, injected=p.injected) for p in plots]


class ClassSpoof(Attack):
    name = "Classification spoof (fratricide)"; key = "class_spoof"; maps_to = "Falsify identification"
    def on_tracks(self, tracker, t):
        # flip BENIGN tracks to read as hostile → the C2 engages friendly/benign traffic.
        for tr in tracker.tracks:
            if tr.confirmed and tr.truth_id is not None and tr.truth_hostile is False:
                tr.believed_hostile = True


class TrackSuppression(Attack):
    name = "Track suppression"; key = "suppress"; maps_to = "Suppress real track"
    def __init__(self, fraction=0.5): self._blocked = set(); self.fraction = fraction
    def on_tracks(self, tracker, t):
        # suppress a FRACTION of confirmed hostile targets, then keep them hidden every step.
        hostiles = [tr.truth_id for tr in tracker.tracks
                    if tr.confirmed and tr.truth_hostile and tr.truth_id is not None]
        want = max(1, int(len(set(hostiles)) * self.fraction))
        for tid in hostiles:
            if len(self._blocked) >= want:
                break
            self._blocked.add(tid)
        tracker.tracks = [tr for tr in tracker.tracks if tr.truth_id not in self._blocked]


class SlewToCue(Attack):
    name = "Slew-to-cue abuse"; key = "slew"; maps_to = "Weaponised automation"
    def on_sensors(self, sensors, t):
        # abuse the automation that points the EO/IR at a cue — drag it offline so the
        # system loses the high-accuracy sensor it relies on for small/fast confirmation.
        for s in sensors:
            if s.kind == "eo":
                s.online = False


class EffectorExhaustion(Attack):
    name = "Effector exhaustion"; key = "exhaust"; maps_to = "Effector exhaustion"
    def __init__(self, n=6): self.n = n
    def on_plots(self, plots, t):
        # spawn phantom threats to bait finite effectors into firing until magazines run dry.
        extra = [Plot(pos=ASSET + RNG.uniform(-260, 260, 2), sensor="radar", t=t,
                      truth_id=None, truth_hostile=True, injected=True) for _ in range(self.n)]
        return plots + extra
    def on_tracks(self, tracker, t):
        pass


class SpoofedFireCommand(Attack):
    name = "Spoofed fire command (RoE bypass)"; key = "spoof_cmd"; maps_to = "Unauthorised effector command"
    def on_tracks(self, tracker, t):
        # forge the engagement decision: mark benign traffic as hostile to force a shot on it.
        for tr in tracker.tracks:
            if tr.confirmed and tr.truth_id is not None and tr.truth_hostile is False:
                tr.believed_hostile = True


class TrackSwap(Attack):
    name = "Track-ID swap / confusion"; key = "track_swap"; maps_to = "Identity / state confusion"
    def on_tracks(self, tracker, t):
        # swap the truth binding of two confirmed tracks → the system engages the wrong object.
        conf = [tr for tr in tracker.tracks if tr.confirmed and tr.truth_id is not None]
        if len(conf) >= 2 and RNG.random() < 0.3:
            a, b = RNG.choice(len(conf), size=2, replace=False)
            conf[a].truth_id, conf[b].truth_id = conf[b].truth_id, conf[a].truth_id
            conf[a].truth_hostile, conf[b].truth_hostile = conf[b].truth_hostile, conf[a].truth_hostile


class CoastExploit(Attack):
    name = "Coast exploitation"; key = "coast"; maps_to = "Tracker prediction abuse"
    def __init__(self, drop=0.85): self.drop = drop
    def on_plots(self, plots, t):
        # starve the tracker of updates on real targets so it COASTS on prediction; the real
        # drone then manoeuvres and the predicted track drifts off it.
        return [p for p in plots if (p.truth_id is None or RNG.random() > self.drop)]


ALL_ATTACKS = [
    PacketLoss, Latency, SensorFlood,
    FalseTrackInjection, ReplayDuplicate, GpsOffset, TimestampAnomaly, MalformedTelemetry,
    ProtocolFuzzing,
    SensorDropout, SensorDisagreement, TrackSuppression, ClassSpoof,
    SlewToCue, EffectorExhaustion, SpoofedFireCommand, TrackSwap, CoastExploit,
]

# One-line explanation per attack — surfaced as a hover tooltip in the UI.
DESCRIPTIONS = {
    "packet_loss": "Drops a large fraction of sensor messages before they reach the tracker — simulates a denial-of-service on the sensor-to-C2 link. Tracking degrades as updates go missing.",
    "latency":     "Holds sensor data for several cycles so the C2 acts on stale information — the detect-to-engage loop lags, and fast or close drones slip inside before a shot lands.",
    "flood":       "Injects hundreds of fake plots inside the engagement zone. They confirm as tracks and soak up the finite effectors, so real hostiles go un-engaged.",
    "false_track": "Creates coherent phantom drones that move and confirm like real tracks — the operator chases ghosts while real threats hide in the noise.",
    "replay":      "Re-sends previously captured plots as duplicate/stale tracks — ghost twins of real contacts that waste effector cycles and clutter the picture.",
    "gps":         "Spoofs reported position so a track is pulled off the real drone. The effector is cued to where the track SAYS the drone is — and misses. The real drone flies on.",
    "timestamp":   "Corrupts message timing/ordering so plot-to-track association degrades — tracks jitter and accuracy drops across the picture.",
    "malformed":   "Injects out-of-bounds / garbage coordinates (protocol fuzzing) — tests whether the tracker rejects bad input or lets it corrupt the track picture.",
    "proto_fuzz":  "A protocol-aware fuzzer against the SAPIENT/CoT sensor feed: out-of-range fields, NaN/infinity values, oversized batches, and stale/out-of-order messages. A validating C2 rejects them; a non-validating one lets NaN/inf and junk reach the tracker — corrupting or dropping real tracks. Finds the crashes and bad-input handling a scanner misses.",
    "eo_blind":    "Forces the EO/IR sensor offline (night, jamming). The system loses its high-accuracy confirmation sensor and leans on radar/RF alone.",
    "disagree":    "Makes one sensor modality report a different position than the others for the same target — fusion poisoning. The fused estimate drifts off truth.",
    "suppress":    "Deletes a fraction of confirmed hostile tracks before the operator sees them — those threats are never engaged and leak straight through.",
    "class_spoof": "Flips benign/friendly tracks to read as hostile — the system engages civilian/friendly traffic. FRATRICIDE.",
    "slew":        "Abuses the slew-to-cue automation to drag the EO/IR camera off the real threat — the system's own logic turned against it.",
    "exhaust":     "Baits the finite effectors into firing at phantom threats until magazines run dry — then the next real drone gets through unopposed.",
    "spoof_cmd":   "Forges the engagement decision (RoE bypass) to fire on the wrong target — e.g. benign traffic. FRATRICIDE via command, not classification.",
    "track_swap":  "Swaps the identity binding of two tracks so the system engages the wrong object and loses custody of the right one — identity/state confusion.",
    "coast":       "Starves the tracker of updates on real targets so it COASTS on prediction; the real drone then manoeuvres and the predicted track drifts off it.",
}

# MODELLING BASIS (finding A): the lab is honest that the *direction* of each effect is the
# finding, and the *magnitude* is a modelling choice — not a measured figure from a real system.
# This note travels into the UI tooltip and the CSV so no one over-reads a specific number.
BASIS = {
    "packet_loss": "Magnitude illustrative (we drop a set fraction of messages); on a real link the loss rate depends on the DoS technique and link margin. Direction — missed updates degrade tracking — is the finding.",
    "latency":     "We hold data a fixed number of cycles; real added latency depends on the injection point and buffering. Direction — a lagged loop lets fast/close drones slip in — is the finding.",
    "flood":       "Phantom count is a chosen load; a real saturation attack scales with injected message rate vs C2 capacity. Direction — finite effectors soak up on phantoms — is the finding.",
    "false_track": "Number of phantoms is a modelling choice; realism depends on how convincingly an adversary can forge coherent tracks. Direction — operator chases ghosts — is the finding.",
    "replay":      "Replay volume is chosen; real impact depends on message auth/nonce handling. Direction — stale duplicates waste cycles — is the finding.",
    "gps":         "Offset size is illustrative; a real GNSS spoof's pull depends on spoofer power/geometry. Direction — track pulled off the drone, effector misses — is the finding.",
    "timestamp":   "Timing corruption is modelled; real effect depends on how the C2 orders/validates messages. Direction — association degrades, accuracy drops — is the finding.",
    "malformed":   "A chosen rate of out-of-bounds values; real outcome depends on input validation. Direction — bad input corrupts the picture unless rejected — is the finding.",
    "proto_fuzz":  "Mutation classes (range, type/NaN/inf, volume, ordering) are modelled at the plot layer; a real engagement fuzzes the actual SAPIENT-protobuf/CoT-XML bytes with a protocol-aware/ICS fuzzer. Direction — unvalidated malformed input reaches and corrupts the tracker — is the finding.",
    "eo_blind":    "We take one modality fully offline; reality is partial/intermittent degradation. Direction — loss of the high-accuracy confirm sensor — is the finding.",
    "disagree":    "Disagreement size is chosen; real fusion poisoning depends on the fusion algorithm's robustness. Direction — fused estimate drifts off truth — is the finding.",
    "suppress":    "Suppressed fraction is a modelling choice; real impact depends on track-management integrity. Direction — deleted tracks leak unopposed — is the finding.",
    "class_spoof": "We flip a set fraction of IDs; real feasibility depends on classifier/auth design. Direction — friendly traffic engaged (FRATRICIDE) — is the finding.",
    "slew":        "Slew abuse is modelled; real effect depends on automation guardrails. Direction — the system's own cueing turned against it — is the finding.",
    "exhaust":     "Magazine size is a parameter; real exhaustion depends on actual loadout vs raid size. Direction — depleted effectors leave the next drone unopposed — is the finding.",
    "spoof_cmd":   "Forged-command rate is chosen; real feasibility depends on command auth/RoE enforcement. Direction — fire on the wrong target (FRATRICIDE) — is the finding.",
    "track_swap":  "Swap rate is modelled; real impact depends on identity-binding integrity. Direction — custody lost, wrong object engaged — is the finding.",
    "coast":       "Update starvation is modelled; real effect depends on coast timeout tuning. Direction — predicted track drifts off a manoeuvring drone — is the finding.",
}

# STANDARD / PROPOSAL MAPPING (finding B): ties each attack to the real interface or standard
# whose weakness it exercises, so the credibility chain to the proposal is visible in the tool.
REFERENCE = {
    "packet_loss": "Sensor→C2 transport availability (SAPIENT / TAK-CoT over the network).",
    "latency":     "Message timeliness in the SAPIENT / Cursor-on-Target data path.",
    "flood":       "SAPIENT/CoT message-rate handling & C2 saturation limits.",
    "false_track": "SAPIENT detection/track message authenticity (unauthenticated feeds).",
    "replay":      "Message freshness/replay protection (nonce/sequence) on sensor feeds.",
    "gps":         "GNSS integrity of the sensor/track position source.",
    "timestamp":   "Message time sync & ordering (SAPIENT timestamping).",
    "malformed":   "Input validation / protocol conformance at the C2 ingest.",
    "proto_fuzz":  "Protocol conformance & robustness of the SAPIENT/CoT parser and tracker — bounds, type/finite checks, volume limits, sequence enforcement (OWASP/ICS fuzzing).",
    "eo_blind":    "Multi-sensor redundancy — single-modality dependency.",
    "disagree":    "Sensor-fusion trust model (fusion poisoning resistance).",
    "suppress":    "Track-management integrity (confirmed-track deletion).",
    "class_spoof": "Classification/identity integrity & IFF — fratricide safety.",
    "slew":        "Automation guardrails on slew-to-cue (weaponised automation).",
    "exhaust":     "Effector tasking logic & finite-resource protection.",
    "spoof_cmd":   "Engagement-command authentication & RoE enforcement.",
    "track_swap":  "Track identity binding / state integrity.",
    "coast":       "Tracker coast/timeout policy (prediction abuse).",
}
