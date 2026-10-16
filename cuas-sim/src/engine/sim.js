// AEGIS simulation engine.
// Models a real C-UAS site: a central PROTECTED ASSET ringed by sensors and effectors,
// with concentric detection / warning / engagement zones. Drones (hostile + benign
// commercial traffic) approach on curved tracks; sensors emit noisy plots; a tracker
// forms confirmed tracks; tracks are classified, scored for threat, and — if hostile
// and inside the engagement zone — engaged.
//
// SECURITY LAYER: the attack toggles inject adversary effects (false plots, suppression,
// fusion poisoning, saturation, replay, sensor dropout) so the same realistic picture
// can be used to DEMONSTRATE security testing of the C2.

import { DRONE_TYPES, SENSOR_TYPES, EFFECTOR_TYPES, ASSET, RINGS, HOSTILE_KEYS, BENIGN_KEYS }
  from '../data/catalog.js'

let _id = 1
const uid = (p) => `${p}${_id++}`
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y)
const rand = (a, b) => a + Math.random() * (b - a)
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)]
const SENS_ABBR = { radar: 'RDR', rf: 'RF', eoir: 'EO', acoustic: 'AC' }

export class Sim {
  constructor(w = 1000, h = 620) { this.w = w; this.h = h; this._seq = 0; this.reset() }

  reset() {
    this.t = 0
    this.drones = []; this.plots = []; this.tracks = []; this.effshots = []; this.events = []
    this._seq = 0
    this.asset = { ...ASSET }
    this.sensors = this.layoutSensors()
    this.effectors = this.layoutEffectors()
    this.stats = { spawned: 0, neutralized: 0, leaked: 0, falseTracks: 0, suppressed: 0, fratricide: 0 }
    this.sensorOn = Object.fromEntries(this.sensors.map(s => [s.id, true]))
    this.show = { rawPlots: true, truth: false, trails: true }
    this.attacks = {
      falseTracks: false,   // false-track injection
      suppress: false,      // suppress real hostile tracks (continuous)
      poison: false,        // fusion poisoning — split + displace real track
      saturate: false,      // flooding / overload
      replay: false,        // replay / stale-track injection
      spoofClass: false,    // sensor spoofing — misclassify hostile as commercial
      spoofCmd: false,      // spoofed effector command — fratricide on benign
      gnss: false,          // GNSS spoof — divert a real track off-course
      sensorDrop: null,     // sensor-modality dropout (EO blind)
      exhaust: false,       // A4 effector exhaustion — drain finite shots
      latency: false,       // A5 delayed response — inject detect→engage lag
      slew: false,          // B4 weaponised automation — drag EO off the real threat
      silent: false,        // B5 silent compromise — attacks active but NO alarm
      roeBypass: false,     // C3 rules-of-engagement bypass — engage unclassified/outside zone
      cascade: false,       // E3 cascade / fail-open — one node fails, others follow
    }
    this.ammo = { hard: 6, soft: 10 }   // finite shots — small magazines so exhaustion bites
    this.downEffectors = new Set()
    this.silentActive = false
    this.autoRaids = true
    this._raidTimer = 2
    this.log('System initialised — AEGIS C-UAS simulator ready.')
    this.spawnWave('mixed', 6)   // seed initial traffic so the picture is never empty
  }

  layoutSensors() {
    const a = ASSET
    const S = [
      { id: uid('sen'), type: 'radar',    x: a.x - 10,  y: a.y + 55, label: 'X-band radar' },
      { id: uid('sen'), type: 'radar',    x: a.x + 180, y: a.y - 70, label: 'X-band radar #2' },
      { id: uid('sen'), type: 'rf',       x: a.x + 20,  y: a.y - 10, label: 'RF/ESM array' },
      { id: uid('sen'), type: 'eoir',     x: a.x + 10,  y: a.y + 10, label: 'EO/IR camera' },
      { id: uid('sen'), type: 'acoustic', x: a.x - 60,  y: a.y - 30, label: 'Acoustic' },
    ]
    return S.map(s => ({ ...s, ...SENSOR_TYPES[s.type] }))
  }
  layoutEffectors() {
    const a = ASSET
    const E = [
      { id: uid('eff'), type: 'jammer', x: a.x - 45, y: a.y, cool: 0 },
      { id: uid('eff'), type: 'laser',  x: a.x + 45, y: a.y, cool: 0 },
      { id: uid('eff'), type: 'hpm',    x: a.x, y: a.y + 40, cool: 0 },
      { id: uid('eff'), type: 'net',    x: a.x, y: a.y - 40, cool: 0 },
    ]
    return E.map(e => ({ ...e, ...EFFECTOR_TYPES[e.type] }))
  }

  log(msg, kind = 'info') {
    this.events.unshift({ t: this.t.toFixed(0), msg, kind })
    if (this.events.length > 160) this.events.pop()
  }

  // ---- spawning ----
  spawnWave(kind = 'mixed', n = 7) {
    let keys
    if (kind === 'mixed')       keys = [...HOSTILE_KEYS, ...BENIGN_KEYS, ...BENIGN_KEYS]
    else if (kind === 'swarm')  keys = ['fpv', 'quadcopter', 'quadcopter']
    else if (kind === 'benign') keys = BENIGN_KEYS
    else                        keys = [kind]
    const count = kind === 'swarm' ? 14 : n
    for (let i = 0; i < count; i++) this._spawnOne(pick(keys), kind === 'swarm')
    if (kind === 'swarm') this.log(`Swarm inbound: ${count} cooperative aircraft at battlespace edge.`, 'warn')
  }
  spawnOne(kind) { this._spawnOne(kind, false) }

  _spawnOne(tKey, swarm) {
    const spec = DRONE_TYPES[tKey]
    const ang = rand(0, Math.PI * 2)
    // spawn just inside the detection ring so sensors can pick them up as they come in
    const r = RINGS.detect - rand(5, 40)
    const x = this.asset.x + Math.cos(ang) * r
    const y = this.asset.y + Math.sin(ang) * r
    const hostile = Math.random() < spec.hostileBias
    let tx, ty
    if (hostile) { tx = this.asset.x + rand(-25, 25); ty = this.asset.y + rand(-25, 25) }
    else {
      // benign craft transit across to the far side, passing near but not into the asset
      const a2 = ang + Math.PI + rand(-0.5, 0.5)
      tx = this.asset.x + Math.cos(a2) * (RINGS.detect + 30)
      ty = this.asset.y + Math.sin(a2) * (RINGS.detect + 30)
    }
    const heading = Math.atan2(ty - y, tx - x)
    this.drones.push({
      id: uid('drn'), type: tKey, ...spec, swarm: !!swarm,
      x, y, tx, ty, heading, hostile, benign: !!spec.benign,
      trail: [], alive: true, prevInside: { warn: false, engage: false },
    })
    this.stats.spawned++
    this.log(`New ${spec.label.toLowerCase()} entered the battlespace.`, 'info')
  }

  // ---- step ----
  step(dt = 0.1) {
    this.t += dt
    this.plots = []; this.effshots = []

    if (this.autoRaids) {
      this._raidTimer -= dt
      if (this._raidTimer <= 0) {
        this._raidTimer = rand(6, 11)
        Math.random() < 0.4 ? this.spawnWave('swarm') : this.spawnWave('mixed', 5)
      }
    }

    // move (curved, with trails)
    for (const d of this.drones) {
      if (!d.alive) continue
      const desired = Math.atan2(d.ty - d.y, d.tx - d.x)
      let diff = desired - d.heading
      while (diff > Math.PI) diff -= 2 * Math.PI
      while (diff < -Math.PI) diff += 2 * Math.PI
      d.heading += diff * 0.05 + rand(-0.14, 0.14)
      d.x += Math.cos(d.heading) * d.speed
      d.y += Math.sin(d.heading) * d.speed
      if (this.t % 0.3 < dt) { d.trail.push({ x: d.x, y: d.y }); if (d.trail.length > 40) d.trail.shift() }

      const rA = dist(this.asset, d)
      // zone-crossing events
      if (hostileInbound(d)) {
        if (rA < RINGS.warn && !d.prevInside.warn) {
          d.prevInside.warn = true
          this.log(`Track ${seqOf(d)} classified ${d.label.toLowerCase()}, inbound — inside warning ring.`, 'warn')
        }
        if (rA < RINGS.engage && !d.prevInside.engage) {
          d.prevInside.engage = true
          this.log(`TRACK ${seqOf(d)} (${d.label}) PENETRATED ENGAGEMENT ZONE — ${Math.round(rA * 10)} ft from asset.`, 'bad')
        }
      }
      const atTarget = Math.hypot(d.tx - d.x, d.ty - d.y) < 10
      // "departed" = moved well outside the detection ring (so it had its time inbound first)
      d.wasInside = d.wasInside || rA < RINGS.detect
      const departed = d.wasInside && rA > RINGS.detect + 25
      const offMap = d.x < -80 || d.x > this.w + 80 || d.y < -80 || d.y > this.h + 80
      if (atTarget && d.hostile) { d.alive = false; this.stats.leaked++; this.log(`LEAK: ${d.label} reached the asset.`, 'bad') }
      else if (atTarget || departed || offMap) d.alive = false
    }
    this.drones = this.drones.filter(d => d.alive)

    // sensor plotting
    for (const s of this.sensors) {
      if (!this.sensorOn[s.id] || this.attacks.sensorDrop === s.type) continue
      for (const d of this.drones) {
        if (dist(s, d) > s.range || !s.detects(d)) continue
        this.plots.push({ x: d.x + rand(-6, 6), y: d.y + rand(-6, 6),
                          truth: d.id, truthHostile: d.hostile, sensor: s.type, fake: false })
      }
    }
    // attack plots
    if (this.attacks.falseTracks) {
      // persistent clustered phantoms near the asset so they confirm and steal cycles
      const cx = this.asset.x + rand(-RINGS.engage, RINGS.engage), cy = this.asset.y + rand(-RINGS.engage, RINGS.engage)
      for (let i = 0; i < 5; i++)
        this.plots.push({ x: cx + rand(-12, 12), y: cy + rand(-12, 12), truth: null, truthHostile: false, sensor: 'rf', fake: true })
    }
    if (this.attacks.saturate) {
      for (let i = 0; i < 30; i++)
        this.plots.push({ x: rand(0, this.w), y: rand(0, this.h), truth: null, truthHostile: false, sensor: 'radar', fake: true })
      // cluster some inside the engagement zone so they actively steal effector cycles
      for (let i = 0; i < 12; i++)
        this.plots.push({ x: this.asset.x + rand(-RINGS.engage, RINGS.engage), y: this.asset.y + rand(-RINGS.engage, RINGS.engage),
                          truth: null, truthHostile: false, sensor: 'radar', fake: true })
    }

    this._tracker()
    this._attackTracks()
    this._engage()
    for (const e of this.effectors) if (e.cool > 0) e.cool -= dt
  }

  _tracker() {
    const GATE = 26
    for (const tr of this.tracks) { tr.hits = 0; tr.age += 1; tr.sensorsSeen = new Set() }
    for (const p of this.plots) {
      let best = null, bd = GATE
      for (const tr of this.tracks) { const dd = dist(tr, p); if (dd < bd) { bd = dd; best = tr } }
      if (best) {
        const nx = best.x + (p.x - best.x) * 0.35, ny = best.y + (p.y - best.y) * 0.35
        best.vx = nx - best.x; best.vy = ny - best.y; best.x = nx; best.y = ny
        best.hits++; best.support = Math.min(best.support + 1, 8)
        best.truth = p.truth; best.truthHostile = p.truthHostile
        best.sensorsSeen.add(p.sensor)
        if (p.fake) best.fakeSupport = (best.fakeSupport || 0) + 1
      } else {
        const tr = { id: ++this._seq, x: p.x, y: p.y, vx: 0, vy: 0, support: 1, hits: 1, age: 0,
          confirmed: false, classification: 'unknown', truth: p.truth, truthHostile: p.truthHostile,
          sensorsSeen: new Set([p.sensor]), sensorsList: [], fakeSupport: p.fake ? 1 : 0,
          suppressed: false, poisonChildren: 0 }
        this.tracks.push(tr)
      }
    }
    for (const tr of this.tracks) {
      if (tr.sensorsSeen && tr.sensorsSeen.size) tr.sensorsList = [...tr.sensorsSeen].map(s => SENS_ABBR[s] || s)
      if (!tr.confirmed && tr.support >= 3) { tr.confirmed = true; this.log(`Track T${pad(tr.id)} confirmed — classification pending.`, 'info') }
      if (tr.confirmed && tr.classification === 'unknown' && tr.age > 10) {
        if (tr.fakeSupport > tr.support / 2) { tr.classification = 'phantom'; this.stats.falseTracks++ }
        else if (tr.truth) {
          // positive ID of small/fast threats needs EO/IR; if EO is blinded they stay UNKNOWN (not engaged)
          const d = this.drones.find(x => x.id === tr.truth)
          const needsEO = d && !d.benign && (d.type === 'nano' || d.type === 'fpv' || d.type === 'autonomous')
          const eoUp = this.attacks.sensorDrop !== 'eoir' && !this.attacks.slew   // slew also denies EO ID
          if (needsEO && !eoUp) { /* stays unknown — cannot positively identify → not engaged */ }
          else tr.classification = this._classFromTruth(tr.truth)
        }
      }
      if (tr.hits === 0) tr.support -= 1
    }
    this.tracks = this.tracks.filter(tr => {
      if (tr.support > 0) return true
      if (this.attacks.replay && tr.confirmed && Math.random() < 0.6) { tr.support = 2; tr.replayed = true; tr.classification = 'phantom'; return true }
      return false
    })
  }

  _classFromTruth(id) {
    const d = this.drones.find(x => x.id === id)
    if (!d) return 'unknown'
    if (d.benign) return 'commercial'
    return d.type === 'fpv' || d.type === 'autonomous' ? d.type : (d.type === 'fixedwing' ? 'fixed-wing' : d.type)
  }

  _attackTracks() {
    // SUPPRESS — continuously hide ALL confirmed hostile tracks from the operator
    if (this.attacks.suppress) {
      for (const t of this.tracks) {
        if (t.confirmed && t.truthHostile && !t.suppressed) {
          t.suppressed = true; this.stats.suppressed++
          this.log(`ATTACK: hostile track T${pad(t.id)} SUPPRESSED (hidden from operator).`, 'bad')
        }
      }
    } else { for (const t of this.tracks) if (t.suppressed) t.suppressed = false }

    // FUSION POISON — split a real track into ghosts AND displace the real one
    if (this.attacks.poison) {
      const real = this.tracks.find(t => t.confirmed && t.truth && !t.poisonChildren)
      if (real) {
        real.poisonChildren = 3
        real.x += rand(-40, 40); real.y += rand(-40, 40)   // correlation desync displaces the true track
        real.classification = 'unknown'                     // fusion can no longer resolve it
        for (let i = 0; i < 3; i++)
          this.tracks.push({ id: ++this._seq, x: real.x + rand(-35, 35), y: real.y + rand(-35, 35), vx: 0, vy: 0,
            support: 4, hits: 1, age: 20, confirmed: true, classification: 'phantom', truth: null, truthHostile: false,
            sensorsSeen: new Set(['radar']), sensorsList: ['RDR'], fakeSupport: 4, suppressed: false, poisonChildren: 0, ghost: true })
        this.log(`ATTACK: fusion POISONED — track T${pad(real.id)} desynced and split into ghosts.`, 'bad'); this.stats.falseTracks += 3
      }
    }

    // SPOOF CLASSIFICATION — sensor spoofing makes a hostile read as COMMERCIAL (never engaged)
    if (this.attacks.spoofClass) {
      const real = this.tracks.find(t => t.confirmed && t.truthHostile && t.classification !== 'commercial' && !t.spoofed)
      if (real) { real.spoofed = true; real.classification = 'commercial'
        this.log(`ATTACK: track T${pad(real.id)} SPOOFED hostile→COMMERCIAL (will not be engaged).`, 'bad') }
    } else { for (const t of this.tracks) if (t.spoofed) { t.spoofed = false } }

    // GNSS SPOOF — drag a confirmed track steadily off its true course (visible divert)
    if (this.attacks.gnss) {
      const t = this.tracks.find(x => x.confirmed && x.truth)
      if (t) {
        if (!t.gnssDir) t.gnssDir = { dx: rand(-1, 1), dy: rand(-1, 1) }
        const trueD = this.drones.find(d => d.id === t.truth)
        const ox = trueD ? trueD.x : t.x, oy = trueD ? trueD.y : t.y
        t.x += t.gnssDir.dx * 3; t.y += t.gnssDir.dy * 3     // steady pull
        t.gnss = { ox, oy }                                   // remember true pos for divert arrow
      }
    } else { for (const t of this.tracks) if (t.gnss) { t.gnss = null; t.gnssDir = null } }

    // REPLAY INJECTION — re-inject a previously-seen (now-departed) track at a stale position
    if (this.attacks.replay && Math.random() < 0.15 && this._lastSeen) {
      const s = this._lastSeen
      this.tracks.push({ id: ++this._seq, x: s.x, y: s.y, vx: 0, vy: 0, support: 4, hits: 1, age: 20,
        confirmed: true, classification: 'phantom', truth: null, truthHostile: false,
        sensorsSeen: new Set(['rf']), sensorsList: ['RF'], fakeSupport: 4, suppressed: false, poisonChildren: 0, replayed: true })
      this.log(`ATTACK: REPLAYED a stale track at ${Math.round(s.x)},${Math.round(s.y)}.`, 'bad'); this.stats.falseTracks++
    }
    // remember a real track position for later replay
    const live = this.tracks.find(t => t.confirmed && t.truth)
    if (live) this._lastSeen = { x: live.x, y: live.y }

    // E3 CASCADE / FAIL-OPEN — take a node down; failures propagate to more nodes
    if (this.attacks.cascade) {
      if (this.downEffectors.size < this.effectors.length && Math.random() < 0.02) {
        const up = this.effectors.filter(e => !this.downEffectors.has(e.id))
        const victim = up[Math.floor(Math.random() * up.length)]
        if (victim) { this.downEffectors.add(victim.id)
          this.log(`CASCADE: ${victim.label} node FAILED — failure propagating (fail-open).`, 'bad') }
      }
    } else if (this.downEffectors.size) { this.downEffectors.clear() }

    // B4 WEAPONISED AUTOMATION (slew-to-cue) — force EO to chase a decoy away from real threats
    if (this.attacks.slew) {
      const eo = this.sensors.find(s => s.type === 'eoir')
      if (eo) { // drag EO toward a corner / decoy, away from the true inbound
        eo.x += (50 - eo.x) * 0.02; eo.y += (50 - eo.y) * 0.02
        if (this.t % 3 < 0.1) this.log('ATTACK: slew-to-cue abused — EO dragged off the real threat.', 'bad')
      }
    }

    // B5 SILENT COMPROMISE — system IS under attack but suppresses all alarms
    this.silentActive = this.attacks.silent &&
      (this.attacks.falseTracks || this.attacks.suppress || this.attacks.spoofClass || this.attacks.poison)
  }

  _engage() {
    for (const e of this.effectors) {
      if (e.cool > 0) continue
      if (this.downEffectors.has(e.id)) continue                   // E3 cascade: this node is down
      // A4 effector exhaustion: ALL effectors draw on finite magazines; when empty they can't fire
      if (this.attacks.exhaust) {
        const mag = e.kind === 'hard' ? this.ammo.hard : this.ammo.soft
        if (mag <= 0) continue
      }
      // Phantom tracks steal effector cycles: a phantom near the asset grabs this effector first,
      // burning its cooldown so the real hostile is NOT engaged this cycle. (saturate/falseTracks/
      // replay/poison all create phantoms the C2 can't tell from real.)
      if (this.attacks.saturate || this.attacks.falseTracks || this.attacks.replay || this.attacks.poison) {
        const ph = this.tracks.find(t => t.confirmed && t.classification === 'phantom' && dist(e, t) < e.range)
        if (ph && Math.random() < 0.7) {
          this.effshots.push({ x1: e.x, y1: e.y, x2: ph.x, y2: ph.y, kind: 'waste' })
          e.cool = e.kind === 'hard' ? 0.6 : 0.4
          if (this.attacks.exhaust) { if (e.kind === 'hard') this.ammo.hard = Math.max(0, this.ammo.hard - 1); else this.ammo.soft = Math.max(0, this.ammo.soft - 1) }
          continue   // wasted this cycle on a ghost
        }
      }
      let target = null, targetTr = null, bd = e.range
      for (const d of this.drones) {
        const tr = this.tracks.find(t => t.truth === d.id && t.confirmed && !t.suppressed)
        if (!tr) continue
        // C3 RoE bypass: normally require hostile class + inside engagement zone; bypass drops both checks
        if (!this.attacks.roeBypass) {
          if (!isHostileClass(tr.classification)) continue
          if (dist(this.asset, d) > RINGS.engage + 15) continue
        }
        if (!e.canDefeat(d)) continue
        const dd = dist(e, d); if (dd < bd) { bd = dd; target = d; targetTr = tr }
      }
      if (target) {
        // A5 delayed response: inject heavy lag so close/fast hostiles slip inside before a shot
        if (this.attacks.latency && Math.random() < 0.8) { e.cool = 2.2; continue }
        // effector aims at the TRACK position (what the C2 believes), not ground truth
        const aimX = targetTr ? targetTr.x : target.x, aimY = targetTr ? targetTr.y : target.y
        this.effshots.push({ x1: e.x, y1: e.y, x2: aimX, y2: aimY, kind: e.kind })
        e.cool = e.kind === 'hard' ? 0.6 : 0.4
        if (this.attacks.exhaust) {
          if (e.kind === 'hard') this.ammo.hard = Math.max(0, this.ammo.hard - 1)
          else this.ammo.soft = Math.max(0, this.ammo.soft - 1)
        }
        // GNSS spoof: the track is diverted from the real drone, so the shot MISSES
        const diverted = targetTr && targetTr.gnss && dist({ x: aimX, y: aimY }, target) > 18
        if (diverted) {
          this.log(`${e.label} MISSED ${target.label} — fired at spoofed position.`, 'bad')
        } else if (this.attacks.roeBypass && target.benign) {
          if (Math.random() < 0.6) { target.alive = false; this.stats.fratricide++
            this.log(`⚠ FRATRICIDE: RoE bypassed — ${e.label} engaged BENIGN ${target.label}.`, 'bad') }
        } else if (Math.random() < 0.6) {
          target.alive = false; this.stats.neutralized++; this.log(`${e.label} NEUTRALISED ${target.label} (hostile).`, 'good')
        }
      }
    }
    if (this.attacks.exhaust && this.ammo.hard <= 0 && this.t % 2 < 0.1)
      this.log('Effector magazines EXHAUSTED — hard-kill unavailable.', 'bad')
    // wasted shots on phantoms (saturation / poisoning)
    if (this.attacks.saturate || this.attacks.poison) {
      const ghost = this.tracks.find(t => t.confirmed && t.classification === 'phantom' && dist(this.asset, t) < RINGS.engage + 20)
      if (ghost) for (const e of this.effectors) {
        if (e.cool > 0) continue
        if (dist(e, ghost) < e.range && Math.random() < 0.3) {
          this.effshots.push({ x1: e.x, y1: e.y, x2: ghost.x, y2: ghost.y, kind: 'waste' })
          e.cool = 0.5; this.log(`${e.label} fired at PHANTOM track T${pad(ghost.id)} (effector wasted).`, 'bad')
        }
      }
    }
    // SPOOFED EFFECTOR COMMAND — forge a fire order against a BENIGN commercial drone (fratricide)
    if (this.attacks.spoofCmd) {
      const benign = this.drones.find(d => d.benign && dist(this.asset, d) < RINGS.warn)
      if (benign) for (const e of this.effectors) {
        if (e.cool > 0) continue
        if (dist(e, benign) < e.range && Math.random() < 0.25) {
          this.effshots.push({ x1: e.x, y1: e.y, x2: benign.x, y2: benign.y, kind: 'frat' })
          e.cool = 0.6
          if (Math.random() < 0.5) { benign.alive = false; this.stats.fratricide++
            this.log(`⚠ FRATRICIDE: forged command — ${e.label} engaged BENIGN ${benign.label}.`, 'bad') }
          break
        }
      }
    }
  }

  // helpers for UI
  trackSpeed(tr) { return Math.round(Math.hypot(tr.vx, tr.vy) * 22) }         // ~mph
  trackRange(tr) { return (dist(this.asset, tr) / 190).toFixed(1) }           // ~miles
  trackThreat(tr) {
    if (tr.classification === 'phantom' || tr.classification === 'commercial') return tr.classification === 'commercial' ? 'LOW' : 'HIGH'
    const r = dist(this.asset, tr)
    if (r < RINGS.engage) return 'HIGH'
    if (r < RINGS.warn) return 'MEDIUM'
    return 'LOW'
  }
  visibleTracks() { return this.tracks.filter(t => !t.suppressed) }

  // Operator picture integrity: of what the operator sees + should see, how much is correct.
  // Falls when phantoms are injected, real tracks are hidden/misclassified, or positions diverted.
  pictureIntegrity() {
    const vis = this.visibleTracks().filter(t => t.confirmed)
    if (vis.length === 0 && this.drones.length === 0) return 100
    let good = 0, bad = 0
    for (const t of vis) {
      if (t.classification === 'phantom' || !t.truth) bad++          // phantom shown as real
      else if (t.spoofed) bad++                                       // misclassified
      else if (t.gnss) bad++                                          // position diverted
      else good++
    }
    // hidden real hostiles count against integrity (operator is missing them)
    const hidden = this.tracks.filter(t => t.suppressed && t.confirmed).length
    bad += hidden
    const total = good + bad
    if (total === 0) return 100
    return Math.round(100 * good / total)
  }
  // true if an attack is active but the operator alarm is being hidden (silent compromise)
  alarmHidden() { return this.silentActive }
  anyAttackActive() { return Object.entries(this.attacks).some(([k, v]) => k === 'sensorDrop' ? v : v) }
}

function isHostileClass(c) { return c && c !== 'unknown' && c !== 'commercial' && c !== 'phantom' }
function hostileInbound(d) { return d.hostile }
function seqOf(d) { return d._seq ? `T${pad(d._seq)}` : (d.label || '') }
function pad(n) { return String(n).padStart(3, '0') }
export { pad }
