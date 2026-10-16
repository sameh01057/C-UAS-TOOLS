// C-UAS catalog — drone, sensor and effector types with modeled specs.
// Ranges are in map units (1 unit ≈ 10 m for display). Behaviour by TYPE is what
// makes layered defence necessary. Traffic is MIXED: some drones are hostile, many
// are benign commercial/civilian craft just passing through — the system must tell
// them apart, which is itself attackable.

export const DRONE_TYPES = {
  // ---- hostile / threat profiles ----
  quadcopter: {
    label: 'Quadcopter', nato: 'Group 1', speed: 1.3, rcs: 0.6, rf: true,
    size: 4, color: '#e8b84b', hostileBias: 0.5,
    desc: 'Small commercial rotorcraft. RF control link; moderate radar return.',
  },
  fpv: {
    label: 'FPV', nato: 'Group 1', speed: 3.2, rcs: 0.35, rf: true,
    size: 3, color: '#ef7d4b', hostileBias: 0.9,
    desc: 'Fast first-person-view attack drone. Too quick for nets; RF link present.',
  },
  fixedwing: {
    label: 'Fixed-wing', nato: 'Group 2', speed: 2.2, rcs: 1.0, rf: true,
    size: 6, color: '#6fb1ff', hostileBias: 0.6,
    desc: 'Longer-endurance fixed-wing. Larger radar return; often waypoint missions.',
  },
  nano: {
    label: 'Nano', nato: 'Group 1', speed: 1.0, rcs: 0.08, rf: true,
    size: 2, color: '#b98bff', hostileBias: 0.7,
    desc: 'Tiny drone — radar cross-section too small for radar; RF/acoustic catch it.',
  },
  autonomous: {
    label: 'Autonomous (no-RF)', nato: 'Group 1', speed: 1.4, rcs: 0.5, rf: false,
    size: 4, color: '#ff5d6c', hostileBias: 0.95,
    desc: 'No radio link — invisible to RF sensors AND immune to RF jammers. Radar/EO only; kinetic/HPM to stop.',
  },
  // ---- benign / commercial traffic (NOT to be engaged) ----
  survey: {
    label: 'Survey drone', nato: 'Group 1', speed: 1.1, rcs: 0.5, rf: true,
    size: 4, color: '#56c596', hostileBias: 0.0, benign: true,
    desc: 'Commercial mapping/survey quad on a lawful mission. Benign — must not be engaged.',
  },
  delivery: {
    label: 'Delivery drone', nato: 'Group 1', speed: 1.5, rcs: 0.7, rf: true,
    size: 5, color: '#56c596', hostileBias: 0.0, benign: true,
    desc: 'Commercial delivery craft transiting the area. Benign.',
  },
  agri: {
    label: 'Agri drone', nato: 'Group 1', speed: 0.9, rcs: 0.6, rf: true,
    size: 5, color: '#56c596', hostileBias: 0.0, benign: true,
    desc: 'Agricultural spraying drone near the perimeter. Benign.',
  },
}

export const HOSTILE_KEYS = ['quadcopter', 'fpv', 'fixedwing', 'nano', 'autonomous']
export const BENIGN_KEYS = ['survey', 'delivery', 'agri']

export const SENSOR_TYPES = {
  radar: {
    label: 'X-band radar', range: 150, color: '#4fd1c5',
    detects: (d) => d.rcs >= 0.15,
    note: 'Detects by radar cross-section. Nano drones slip under it.',
  },
  rf: {
    label: 'RF / ESM array', range: 190, color: '#f6ad55',
    detects: (d) => d.rf === true,
    note: 'Passive — only sees drones with an active radio link.',
  },
  eoir: {
    label: 'EO/IR camera', range: 95, color: '#90cdf4',
    detects: (d) => true, cued: true,
    note: 'Short range, narrow FoV — normally slewed to a cue. Degrades at night (EO).',
  },
  acoustic: {
    label: 'Acoustic', range: 70, color: '#9ae6b4',
    detects: (d) => true,
    note: 'Hears motor signature at short range; good against nano.',
  },
}

export const EFFECTOR_TYPES = {
  jammer: {
    label: 'RF jammer', range: 120, color: '#f6ad55', kind: 'soft',
    canDefeat: (d) => d.rf === true,
    note: 'Cuts the control/GNSS link. No effect on autonomous no-RF drones.',
  },
  laser: {
    label: 'Laser (HEL)', range: 110, color: '#fc8181', kind: 'hard', dwell: 1.4,
    canDefeat: () => true,
    note: 'Burns one target at a time; needs dwell. Works on any drone.',
  },
  hpm: {
    label: 'HPM (microwave)', range: 60, color: '#f687b3', kind: 'hard', area: true,
    canDefeat: () => true,
    note: 'Area effect — good against swarms. Short range.',
  },
  net: {
    label: 'Net interceptor', range: 90, color: '#a0aec0', kind: 'hard',
    canDefeat: (d) => d.speed <= 2.0,
    note: 'Captures slow drones; too slow for fast FPV.',
  },
}

// Single central protected asset with concentric defensive rings (like a real C-UAS site).
export const ASSET = { id: 'asset', label: 'PROTECTED ASSET', x: 500, y: 310 }
export const RINGS = {
  detect:  300,   // outer dashed — detection boundary
  warn:    200,   // yellow — warning ring (classify & alert)
  engage:  110,   // red — engagement zone (weapons free on hostiles)
}

// kept for compatibility; the asset is the single site now
export const SITES = [ASSET]
