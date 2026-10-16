import React, { useRef, useEffect } from 'react'
import { DRONE_TYPES, RINGS } from '../data/catalog.js'
import { pad } from '../engine/sim.js'

const CLASS_COLOR = {
  unknown: '#8a97a6', commercial: '#56c596', 'fixed-wing': '#6fb1ff',
  quadcopter: '#e8b84b', fpv: '#ef7d4b', nano: '#b98bff', autonomous: '#ff5d6c',
  phantom: '#ff5d6c', hostile: '#e8b84b',
}
const classColor = (c) => CLASS_COLOR[c] || '#e8b84b'

export default function Stage({ sim, tick, onPick }) {
  const ref = useRef(null)

  useEffect(() => {
    const cv = ref.current
    const ctx = cv.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    const rect = cv.getBoundingClientRect()
    cv.width = rect.width * dpr; cv.height = rect.height * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    const sx = rect.width / sim.w, sy = rect.height / sim.h
    const sc = (sx + sy) / 2
    const X = (x) => x * sx, Y = (y) => y * sy
    const A = sim.asset

    ctx.clearRect(0, 0, rect.width, rect.height)

    // defensive range rings
    const ring = (r, color, dash) => {
      ctx.beginPath(); ctx.arc(X(A.x), Y(A.y), r * sc, 0, Math.PI * 2)
      ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.setLineDash(dash || []); ctx.stroke(); ctx.setLineDash([])
    }
    ring(RINGS.detect, '#39506022', [6, 8])
    ring(RINGS.warn,   '#e8b84b55')
    ring(RINGS.engage, '#ff5d6c66')

    // sensor coverage (subtle)
    for (const s of sim.sensors) {
      if (!sim.sensorOn[s.id] || sim.attacks.sensorDrop === s.type) continue
      ctx.beginPath(); ctx.arc(X(s.x), Y(s.y), s.range * sc, 0, Math.PI * 2)
      ctx.strokeStyle = s.color + '15'; ctx.lineWidth = 1; ctx.stroke()
    }

    // asset
    ctx.save(); ctx.translate(X(A.x), Y(A.y))
    ctx.fillStyle = '#2dd4bf'
    ctx.beginPath(); ctx.moveTo(0, -9); ctx.lineTo(8, 7); ctx.lineTo(-8, 7); ctx.closePath(); ctx.fill()
    ctx.restore()
    ctx.fillStyle = '#9fb0bf'; ctx.font = '10px ui-monospace'
    ctx.fillText(A.label, X(A.x) + 12, Y(A.y) + 4)

    // sensors + labels
    for (const s of sim.sensors) {
      const off = !sim.sensorOn[s.id] || sim.attacks.sensorDrop === s.type
      ctx.fillStyle = off ? '#33404d' : s.color
      ctx.fillRect(X(s.x) - 4, Y(s.y) - 4, 8, 8)
      ctx.fillStyle = off ? '#44525f' : s.color + 'cc'; ctx.font = '9px ui-monospace'
      ctx.fillText(s.label, X(s.x) + 8, Y(s.y) + 3)
    }
    // effectors (mark DOWN from cascade, and 0-ammo from exhaustion)
    const down = sim.downEffectors
    const exhausted = sim.attacks.exhaust && sim.ammo.hard <= 0
    for (const e of sim.effectors) {
      const isDown = down.has(e.id)
      const isOut = exhausted && e.kind === 'hard'
      ctx.beginPath(); ctx.moveTo(X(e.x), Y(e.y) - 6); ctx.lineTo(X(e.x) - 5, Y(e.y) + 4); ctx.lineTo(X(e.x) + 5, Y(e.y) + 4)
      ctx.closePath(); ctx.fillStyle = (isDown || isOut) ? '#55606b' : e.color; ctx.fill()
      if (isDown) { ctx.strokeStyle = '#ff5d6c'; ctx.lineWidth = 1.5
        ctx.beginPath(); ctx.moveTo(X(e.x) - 7, Y(e.y) - 7); ctx.lineTo(X(e.x) + 7, Y(e.y) + 7)
        ctx.moveTo(X(e.x) + 7, Y(e.y) - 7); ctx.lineTo(X(e.x) - 7, Y(e.y) + 7); ctx.stroke()
        ctx.fillStyle = '#ff5d6c'; ctx.font = '8px ui-monospace'; ctx.fillText('DOWN', X(e.x) + 9, Y(e.y) + 3) }
      else if (isOut) { ctx.fillStyle = '#ff5d6c'; ctx.font = '8px ui-monospace'; ctx.fillText('0 ammo', X(e.x) + 9, Y(e.y) + 3) }
    }

    // slewed EO — draw a dashed arrow showing it's been dragged off
    if (sim.attacks.slew) {
      const eo = sim.sensors.find(s => s.type === 'eoir')
      if (eo) {
        ctx.strokeStyle = '#ff5d6c'; ctx.lineWidth = 1; ctx.setLineDash([3, 3])
        ctx.beginPath(); ctx.moveTo(X(A.x), Y(A.y)); ctx.lineTo(X(eo.x), Y(eo.y)); ctx.stroke(); ctx.setLineDash([])
        ctx.fillStyle = '#ff5d6c'; ctx.font = '8px ui-monospace'; ctx.fillText('EO slewed off', X(eo.x) - 10, Y(eo.y) - 8)
      }
    }

    // engagement beams
    for (const sh of sim.effshots) {
      ctx.beginPath(); ctx.moveTo(X(sh.x1), Y(sh.y1)); ctx.lineTo(X(sh.x2), Y(sh.y2))
      ctx.strokeStyle = sh.kind === 'frat' ? '#ff2d55' : sh.kind === 'waste' ? '#ff5d6c' : sh.kind === 'hard' ? '#fc8181' : '#f6ad55'
      ctx.lineWidth = sh.kind === 'frat' ? 2.5 : sh.kind === 'waste' ? 1 : 2
      ctx.setLineDash(sh.kind === 'waste' ? [3, 3] : []); ctx.stroke(); ctx.setLineDash([])
    }

    // movement trails
    if (sim.show.trails) {
      for (const d of sim.drones) {
        if (d.trail.length < 2) continue
        ctx.beginPath(); ctx.moveTo(X(d.trail[0].x), Y(d.trail[0].y))
        for (const p of d.trail) ctx.lineTo(X(p.x), Y(p.y))
        ctx.strokeStyle = (d.benign ? '#56c596' : DRONE_TYPES[d.type].color) + '40'
        ctx.lineWidth = 1; ctx.stroke()
      }
    }

    // raw plots
    if (sim.show.rawPlots) for (const p of sim.plots) {
      ctx.beginPath(); ctx.arc(X(p.x), Y(p.y), 1.5, 0, Math.PI * 2)
      ctx.fillStyle = p.fake ? '#ff5d6c55' : '#ffffff33'; ctx.fill()
    }

    // tracks — square marker + "T### CLASS" label
    for (const tr of sim.visibleTracks()) {
      if (!tr.confirmed) continue
      const col = classColor(tr.classification)
      const phantom = tr.classification === 'phantom'
      ctx.strokeStyle = col; ctx.lineWidth = 1.4; ctx.setLineDash(phantom ? [2, 3] : [])
      ctx.strokeRect(X(tr.x) - 6, Y(tr.y) - 6, 12, 12); ctx.setLineDash([])
      ctx.fillStyle = col; ctx.font = '9px ui-monospace'
      ctx.fillText(`T${pad(tr.id)} ${tr.classification.toUpperCase()}`, X(tr.x) + 9, Y(tr.y) - 7)
      // GNSS divert arrow: from true position to spoofed position
      if (tr.gnss) {
        ctx.strokeStyle = '#ff5d6c'; ctx.lineWidth = 1; ctx.setLineDash([2, 2])
        ctx.beginPath(); ctx.moveTo(X(tr.gnss.ox), Y(tr.gnss.oy)); ctx.lineTo(X(tr.x), Y(tr.y)); ctx.stroke(); ctx.setLineDash([])
        ctx.fillStyle = '#ff5d6c'; ctx.font = '8px ui-monospace'; ctx.fillText('↯ diverted', X(tr.x) + 9, Y(tr.y) + 6)
      }
    }

    // SUPPRESSED tracks — show as faint red "HIDDEN" ghosts so you SEE what the operator can't
    for (const tr of sim.tracks) {
      if (!tr.suppressed || !tr.confirmed) continue
      ctx.beginPath(); ctx.arc(X(tr.x), Y(tr.y), 11, 0, Math.PI * 2)
      ctx.strokeStyle = '#ff5d6c55'; ctx.lineWidth = 1; ctx.setLineDash([2, 4]); ctx.stroke(); ctx.setLineDash([])
      ctx.fillStyle = '#ff5d6c88'; ctx.font = '8px ui-monospace'
      ctx.fillText(`T${pad(tr.id)} HIDDEN`, X(tr.x) + 9, Y(tr.y) - 7)
    }

    // ground-truth drones (optional overlay)
    if (sim.show.truth) for (const d of sim.drones) {
      const spec = DRONE_TYPES[d.type]
      ctx.beginPath(); ctx.arc(X(d.x), Y(d.y), spec.size, 0, Math.PI * 2)
      if (d.benign) { ctx.strokeStyle = '#56c596'; ctx.lineWidth = 1.5; ctx.stroke() }
      else { ctx.fillStyle = spec.color; ctx.fill() }
    }
  }, [sim, tick])

  function handleClick(e) {
    const rect = ref.current.getBoundingClientRect()
    const sx = sim.w / rect.width, sy = sim.h / rect.height
    const mx = (e.clientX - rect.left) * sx, my = (e.clientY - rect.top) * sy
    let best = null, bd = 30
    for (const d of sim.drones) { const dd = Math.hypot(d.x - mx, d.y - my); if (dd < bd) { bd = dd; best = d } }
    onPick && onPick(best)
  }

  return <canvas ref={ref} onClick={handleClick} />
}
