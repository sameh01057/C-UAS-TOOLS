import React, { useRef, useState, useEffect } from 'react'
import { Sim, pad } from '../engine/sim.js'
import { DRONE_TYPES } from '../data/catalog.js'
import { ATTACK_INFO } from '../data/attacks.js'
import Stage from './Stage.jsx'

function activeAttackKeys(sim) {
  const keys = []
  for (const [k, v] of Object.entries(sim.attacks)) {
    if (k === 'sensorDrop') { if (v === 'eoir') keys.push('eoBlind'); continue }
    if (v) keys.push(k)
  }
  return keys
}

const simRef = { current: null }
const threatClass = (t) => t === 'HIGH' ? 'thi' : t === 'MEDIUM' ? 'tmed' : 'tlow'
const tagClass = (c) => c === 'phantom' ? 'phantom' : c === 'commercial' ? 'commercial' : c === 'unknown' ? 'unknown' : 'hostile'

// A small ⓘ marker carrying hover text (used on every component + attack).
const Info = ({ tip }) => tip ? <span className="iq" data-tip={tip}>ⓘ</span> : null
// Build the attack tooltip from ATTACK_INFO (what it does + the effect to watch).
const attackTip = (k) => {
  const i = ATTACK_INFO[k]
  return i ? `${i.does}  ·  Effect: ${i.effect}` : ''
}

export default function App() {
  if (!simRef.current) simRef.current = new Sim()
  const sim = simRef.current
  const [tick, setTick] = useState(0)
  const [running, setRunning] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [picked, setPicked] = useState(null)
  const [detPerSec, setDetPerSec] = useState(0)
  const raf = useRef(0)
  const detAcc = useRef({ n: 0, last: 0 })
  const [, force] = useState(0)

  useEffect(() => {
    let last = performance.now()
    const loop = (now) => {
      if (running) {
        const budget = 90 / speed
        if (now - last > budget) {
          sim.step(0.1); last = now; setTick(t => t + 1)
          detAcc.current.n += sim.plots.filter(p => !p.fake).length
          if (now - detAcc.current.last > 1000) { setDetPerSec(detAcc.current.n); detAcc.current.n = 0; detAcc.current.last = now }
        }
      }
      raf.current = requestAnimationFrame(loop)
    }
    raf.current = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf.current)
  }, [running, speed, sim])

  // Custom hover tooltip for every [data-tip] (ⓘ marker) — follows the mouse, like the lab's.
  useEffect(() => {
    let tip = document.getElementById('simtip')
    if (!tip) { tip = document.createElement('div'); tip.id = 'simtip'; document.body.appendChild(tip) }
    const over = (e) => {
      const el = e.target.closest && e.target.closest('[data-tip]')
      if (el && el.dataset.tip) { tip.textContent = el.dataset.tip; tip.style.display = 'block' }
    }
    const move = (e) => {
      if (tip.style.display === 'block') {
        let x = e.clientX + 14, y = e.clientY + 14
        if (x + 350 > window.innerWidth) x = e.clientX - 356
        if (y + 120 > window.innerHeight) y = e.clientY - 120
        tip.style.left = x + 'px'; tip.style.top = y + 'px'
      }
    }
    const out = (e) => { if (e.target.closest && e.target.closest('[data-tip]')) tip.style.display = 'none' }
    document.addEventListener('mouseover', over)
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseout', out)
    return () => { document.removeEventListener('mouseover', over); document.removeEventListener('mousemove', move); document.removeEventListener('mouseout', out) }
  }, [])

  const refresh = () => force(n => n + 1)
  const toggleSensor = (id) => { sim.sensorOn[id] = !sim.sensorOn[id]; refresh() }
  const toggleShow = (k) => { sim.show[k] = !sim.show[k]; refresh() }
  const toggleAttack = (k) => { sim.attacks[k] = !sim.attacks[k]; sim.log(`ATTACK ${k} ${sim.attacks[k] ? 'ENABLED' : 'disabled'}.`, sim.attacks[k] ? 'bad' : 'info'); refresh() }
  const dropSensor = (type) => { sim.attacks.sensorDrop = sim.attacks.sensorDrop === type ? null : type; refresh() }

  const anyAttack = Object.values(sim.attacks).some(Boolean)
  const st = sim.stats
  const vis = sim.visibleTracks().filter(t => t.confirmed)
  const phantomCount = vis.filter(t => t.classification === 'phantom').length
  const integrity = sim.pictureIntegrity()

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand">AEGIS <small>C-UAS Operations &amp; Security Simulator</small></div>
        <div className="metrics">
          <div className="m"><div className="mv">{sim.t.toFixed(0)}s</div><div className="mk">SIM</div></div>
          <div className="m"><div className="mv">{sim.drones.length}</div><div className="mk">TARGETS</div></div>
          <div className="m"><div className="mv">{vis.length}{phantomCount ? <span className="ph">+{phantomCount}</span> : ''}</div><div className="mk">TRACKS</div></div>
          <div className="m"><div className="mv">{detPerSec}</div><div className="mk">DET/S</div></div>
          <div className="m"><div className="mv" style={{ color: integrity >= 85 ? 'var(--good)' : integrity >= 60 ? 'var(--warn)' : 'var(--bad)' }}>{integrity}%</div><div className="mk">PICTURE OK</div></div>
        </div>
        <div className="spacer" />
        <button className="btn primary" onClick={() => setRunning(r => !r)}>{running ? '⏸ Pause' : '▶ Start'}</button>
        <button className="btn danger" onClick={() => { sim.reset(); setRunning(false); setPicked(null); refresh() }}>■ Reset</button>
      </div>

      <div className="main">
        {/* LEFT */}
        <div className="col left">
          <h3>Sensors</h3>
          {sim.sensors.map(s => (
            <div className="toggle" key={s.id}>
              <label><span className="swatch" style={{ background: s.color }} />{s.label}
                <Info tip={`${s.note || ''}  ·  Range ${s.range} units  ·  click to toggle this sensor on/off`} /></label>
              <div className={'switch' + (sim.sensorOn[s.id] && sim.attacks.sensorDrop !== s.type ? ' on' : '')} onClick={() => toggleSensor(s.id)}><i /></div>
            </div>
          ))}

          <h3>Effectors</h3>
          {sim.effectors.map(e => (
            <div className="toggle" key={e.id}>
              <label><span className="swatch" style={{ background: e.color }} />{e.label}
                <Info tip={`${e.note || ''}  ·  ${e.kind === 'soft' ? 'Soft-kill' : 'Hard-kill'}  ·  Range ${e.range} units${e.area ? '  ·  area effect' : ''}${e.dwell ? `  ·  dwell ${e.dwell}s` : ''}`} /></label>
              <span className="emeta">{e.kind}</span>
            </div>
          ))}

          <h3>Display</h3>
          {[['rawPlots', 'Raw plots'], ['truth', 'Ground truth'], ['trails', 'Trails']].map(([k, l]) => (
            <div className="toggle" key={k}><label>{l}</label>
              <div className={'switch' + (sim.show[k] ? ' on' : '')} onClick={() => toggleShow(k)}><i /></div></div>
          ))}

          <div className="attackbox" style={{ marginTop: 16 }}>
            <h3>⚠ Red Team / Security</h3>
            <div className="hint">Attack the C2 the way a cyber adversary would — the security demo. Grouped by test type.</div>

            <div className="atkgrp">A · Mission failure</div>
            {[['saturate', 'Saturate / overload (DoS)'], ['exhaust', 'Effector exhaustion'], ['latency', 'Delayed response (lag)']].map(([k, l]) => (
              <div className="toggle" key={k}><label>{l}<Info tip={attackTip(k)} /></label>
                <div className={'switch atk' + (sim.attacks[k] ? ' on' : '')} onClick={() => toggleAttack(k)}><i /></div></div>
            ))}
            <div className="toggle"><label>Blind EO (night / jam)<Info tip={attackTip('eoBlind')} /></label>
              <div className={'switch atk' + (sim.attacks.sensorDrop === 'eoir' ? ' on' : '')} onClick={() => dropSensor('eoir')}><i /></div></div>

            <div className="atkgrp">B · Deception</div>
            {[['falseTracks', 'False-track injection'], ['replay', 'Replay / stale inject'], ['suppress', 'Suppress real track'],
              ['poison', 'Fusion poisoning (desync)'], ['spoofClass', 'Falsify classification'], ['gnss', 'GNSS spoof / divert'],
              ['slew', 'Weaponise automation (slew)'], ['silent', 'Silent compromise (no alarm)']].map(([k, l]) => (
              <div className="toggle" key={k}><label>{l}<Info tip={attackTip(k)} /></label>
                <div className={'switch atk' + (sim.attacks[k] ? ' on' : '')} onClick={() => toggleAttack(k)}><i /></div></div>
            ))}

            <div className="atkgrp">C · Fratricide / command</div>
            {[['spoofCmd', 'Spoofed fire cmd'], ['roeBypass', 'RoE bypass']].map(([k, l]) => (
              <div className="toggle" key={k}><label>{l}<Info tip={attackTip(k)} /></label>
                <div className={'switch atk' + (sim.attacks[k] ? ' on' : '')} onClick={() => toggleAttack(k)}><i /></div></div>
            ))}

            <div className="atkgrp">E · Integrity / availability</div>
            {[['cascade', 'Cascade / fail-open']].map(([k, l]) => (
              <div className="toggle" key={k}><label>{l}<Info tip={attackTip(k)} /></label>
                <div className={'switch atk' + (sim.attacks[k] ? ' on' : '')} onClick={() => toggleAttack(k)}><i /></div></div>
            ))}
          </div>

          {/* Non-visual tests — honestly presented as assessed off the radar picture */}
          <div className="attackbox net" style={{ marginTop: 14 }}>
            <h3>D/E/F · C2 Internals &amp; Network</h3>
            <div className="hint">These are tested off the radar picture — on the C2 software, hosts and network. Shown for completeness; see the proposal §16.</div>
            {[
              ['Lateral movement → site network', 'Pivot from C-UAS net into the facility'],
              ['Pivot into OT / ICS', 'Reach control systems of the protected site'],
              ['Data exfiltration of posture', 'Leak sensor placement / coverage gaps'],
              ['Remote code execution (C2)', 'Run code on the C2 via a software flaw'],
              ['Firmware / supply-chain tamper', 'Backdoored firmware or hijacked update'],
              ['Insider / credential abuse', 'Legitimate access misused'],
            ].map(([n, eff]) => (
              <div className="netrow" key={n}><div className="nn">{n}<Info tip={eff} /></div><div className="ne">{eff}</div></div>
            ))}
          </div>
        </div>

        {/* CENTER */}
        <div className="stage">
          {anyAttack && !sim.alarmHidden() && <div className="banner">⚠ SYSTEM UNDER ATTACK — operator picture may be false</div>}
          {sim.alarmHidden() && <div className="banner ok">● ALL SYSTEMS NOMINAL</div>}
          <Stage sim={sim} tick={tick} onPick={setPicked} />

          {/* AMMO indicator (shows when exhaustion attack is armed) */}
          {sim.attacks.exhaust && (
            <div className="ammo">HARD-KILL AMMO <b className={sim.ammo.hard <= 0 ? 'out' : ''}>{sim.ammo.hard}</b></div>
          )}

          {/* Live effect readout — explains every running attack in plain words */}
          {activeAttackKeys(sim).length > 0 && (
            <div className="effreadout">
              <div className="eh">ACTIVE ATTACKS — live effect</div>
              {activeAttackKeys(sim).map(k => {
                const info = ATTACK_INFO[k]; if (!info) return null
                return <div className="er" key={k}>
                  <div className="ern">▸ {info.name}</div>
                  <div className="ere"><b>Doing:</b> {info.does} <br /><b>Effect:</b> {info.effect}</div>
                </div>
              })}
            </div>
          )}
          <div className="controls">
            <span className="spd">Speed
              <input type="range" min="1" max="4" step="1" value={speed} onChange={e => setSpeed(+e.target.value)} />
              {speed}x</span>
            <button className="btn sm primary" onClick={() => { sim.spawnWave('mixed', 7); refresh() }}>+ Mixed wave</button>
            <button className="btn sm" onClick={() => { sim.spawnOne('quadcopter'); refresh() }}>+ Quad</button>
            <button className="btn sm" onClick={() => { sim.spawnOne('fixedwing'); refresh() }}>+ Fixed-wing</button>
            <button className="btn sm" onClick={() => { sim.spawnWave('swarm'); refresh() }}>+ Swarm</button>
            <button className="btn sm" onClick={() => { sim.spawnWave('benign'); refresh() }}>+ Commercial</button>
            <label className="cbx"><input type="checkbox" checked={sim.autoRaids} onChange={() => { sim.autoRaids = !sim.autoRaids; refresh() }} /> Auto raids</label>
          </div>
          <div className="legend">
            <span><span style={{ width: 10, height: 10, border: '1.5px solid #e8b84b', marginRight: 5, display: 'inline-block' }} />track</span>
            <span><span style={{ width: 10, height: 10, border: '1.5px solid #56c596', marginRight: 5, display: 'inline-block' }} />commercial</span>
            <span><span style={{ width: 10, height: 10, border: '1.5px dashed #ff5d6c', marginRight: 5, display: 'inline-block' }} />phantom</span>
            <span style={{ color: '#ff5d6c99' }}>● engage</span><span style={{ color: '#e8b84b99' }}>● warn</span>
          </div>
        </div>

        {/* RIGHT */}
        <div className="col right">
          <h3>Status</h3>
          <div className="stats">
            <div className="stat good"><div className="v">{st.neutralized}</div><div className="k">Neutralised</div></div>
            <div className="stat bad"><div className="v">{st.leaked}</div><div className="k">Leaked</div></div>
            <div className="stat bad"><div className="v">{st.falseTracks}</div><div className="k">False tracks</div></div>
            <div className="stat bad"><div className="v">{st.suppressed}</div><div className="k">Suppressed</div></div>
            <div className="stat bad"><div className="v">{st.fratricide}</div><div className="k">Fratricide</div></div>
          </div>

          <h3>Track table</h3>
          {vis.length === 0 && <div style={{ color: 'var(--muted)', fontSize: 12 }}>No confirmed tracks.</div>}
          {vis.length > 0 && (
            <table className="ttab">
              <thead><tr><th>ID</th><th>Class</th><th>Spd</th><th>Rng</th><th>Sensors</th><th>Threat</th></tr></thead>
              <tbody>
                {vis.slice(0, 20).sort((a, b) => sim.trackRange(a) - sim.trackRange(b)).map(t => {
                  const threat = sim.trackThreat(t)
                  return <tr key={t.id}>
                    <td>T{pad(t.id)}</td>
                    <td><span className={'tag ' + tagClass(t.classification)}>{t.classification}</span></td>
                    <td>{sim.trackSpeed(t)}</td>
                    <td>{sim.trackRange(t)}mi</td>
                    <td className="sens">{(t.sensorsList || []).join('·') || '—'}</td>
                    <td><span className={'threat ' + threatClass(threat)}>{threat}</span></td>
                  </tr>
                })}
              </tbody>
            </table>
          )}

          {picked && (
            <>
              <h3>Selected contact</h3>
              <div className="item">
                <div className="nm"><span className="swatch" style={{ background: DRONE_TYPES[picked.type].color }} />{picked.label} {picked.benign ? '· benign' : picked.hostile ? '· HOSTILE' : ''}</div>
                <div className="sub">{DRONE_TYPES[picked.type].nato} · speed {picked.speed} · RCS {picked.rcs} · {picked.rf ? 'RF link' : 'NO RF'}</div>
                <div className="sub" style={{ marginTop: 4 }}>{DRONE_TYPES[picked.type].desc}</div>
              </div>
            </>
          )}

          <h3>Event log</h3>
          <div className="log">
            {sim.events.slice(0, 46).map((e, i) => (
              <div className="row" key={i}><span className="t">{e.t}s</span><span className={e.kind}>{e.msg}</span></div>
            ))}
          </div>
        </div>
      </div>

      <div className="footer">
        <span><b>C-UAS Security Simulator.</b> A model of how a counter-UAS system works and how each class of cyber attack degrades it.</span>
        <span className="disc">Modelled simulation — effects are faithful in kind to real attacks; exact impact on any live system is determined only by an actual security assessment. Not a live exploit or a real system.</span>
      </div>
    </div>
  )
}
