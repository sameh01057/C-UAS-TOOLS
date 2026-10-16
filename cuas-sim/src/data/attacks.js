// Human-readable description of each attack: what it does, and the effect to watch for.
// Keyed by the attack flag in sim.attacks (plus 'eoBlind' for the sensorDrop case).

export const ATTACK_INFO = {
  saturate:    { name: 'Saturate / overload (DoS)', does: 'Floods the tracker with hundreds of fake plots.', effect: 'Map fills with phantoms; DET/S spikes; real threats lost in the noise.' },
  exhaust:     { name: 'Effector exhaustion', does: 'Drains finite hard-kill magazines against decoys.', effect: 'AMMO hits 0 → laser/HPM/net stop firing → next real hostile gets through.' },
  latency:     { name: 'Delayed response', does: 'Injects lag into the detect→engage loop.', effect: 'Effectors hesitate; hostiles close the distance before a shot lands.' },
  eoBlind:     { name: 'Blind EO (night / jam)', does: 'Forces the EO/IR sensor offline.', effect: 'EO coverage ring disappears; identification degrades, radar/RF only.' },

  falseTracks: { name: 'False-track injection', does: 'Forges sensor plots near the asset.', effect: 'Phantom (dashed red) tracks appear and get confirmed as real.' },
  replay:      { name: 'Replay / stale inject', does: 'Re-sends a previously captured track.', effect: 'A stale phantom reappears where a drone used to be.' },
  suppress:    { name: 'Suppress real track', does: 'Hides confirmed hostile tracks from the operator.', effect: 'Real hostiles vanish from the screen (shown as faint "HIDDEN" ghosts) and are never engaged → they leak.' },
  poison:      { name: 'Fusion poisoning (desync)', does: 'Breaks plot-to-track correlation.', effect: 'A real track is displaced and split into multiple ghost tracks.' },
  spoofClass:  { name: 'Falsify classification', does: 'Spoofs a hostile to read as COMMERCIAL.', effect: 'Track turns green ("SPOOFED") and is treated as benign → never engaged.' },
  gnss:        { name: 'GNSS spoof / divert', does: 'Feeds false navigation to a track.', effect: 'The track is dragged off its true course (divert arrow shown).' },
  slew:        { name: 'Weaponise automation (slew)', does: 'Abuses slew-to-cue with a false cue.', effect: 'The EO/IR camera is dragged to a corner, away from the real threat.' },
  silent:      { name: 'Silent compromise', does: 'Suppresses all operator alarms while attacks run.', effect: 'Banner reads "ALL SYSTEMS NOMINAL" even though the system is compromised.' },

  spoofCmd:    { name: 'Spoofed fire command', does: 'Forges an engagement order against a benign drone.', effect: 'FRATRICIDE — a bright red beam engages a commercial drone; counter rises.' },
  roeBypass:   { name: 'RoE bypass', does: 'Defeats the rules-of-engagement checks.', effect: 'Effectors fire without classification / outside the zone — can hit benign traffic.' },

  cascade:     { name: 'Cascade / fail-open', does: 'Fails one node; the failure propagates.', effect: 'Effector nodes drop one by one (marked ✕ DOWN) until defence collapses.' },
}
