# AEGIS — C-UAS Detection, Tracking, Defeat & Adversarial Simulator

A SENTINEL-class counter-UAS simulator — **and more.** It models the full C-UAS pipeline
(sensors → raw plots → tracker → confirmed tracks → fusion/decision → effectors) **and** lets
you attack the system's software the way a cyber adversary would. That attack layer is the
part a pure visualiser does not have — and is the live demonstration of our C-UAS
security-testing proposal.

## Run it

```bash
cd cuas-sim
npm install
npm run dev        # opens on http://localhost:5173
```

Build for deployment (e.g. Vercel, like SENTINEL):

```bash
npm run build      # outputs to dist/
npm run preview    # preview the production build
```

## What it does

- **Detection → tracking pipeline** — sensors emit noisy *raw plots*; a tracker associates them
  into *tentative* then *confirmed* tracks (M-of-N), so tracks form slowly and legibly.
- **Layered defence by type** — radar misses nano (small RCS); RF misses autonomous no-RF
  drones; EO is short-range/cued; jammers fail on no-RF drones; nets fail on fast FPV. You see
  *why* mixed sensors/effectors are needed.
- **Sensor toggles** — turn any sensor off and watch coverage and tracking degrade.

## The adversary / security layer (the differentiator)

Toggle these to attack the C2 and watch the operator picture diverge from reality:

- **Inject false tracks** — phantom drones appear and get confirmed.
- **Suppress a real track** — a genuine hostile vanishes from the operator's screen.
- **Poison fusion** — one real track splits into ghost tracks (desync/correlation attack).
- **Saturate / overload** — flood the tracker; effectors waste shots on phantoms.
- **Replay stale tracks** — dead tracks linger as if still live.
- **Blind EO (night / jam)** — remove a sensor modality; watch fusion cope or fail.

Each maps to a test in the proposal's catalogue (false-track injection, fusion
poisoning, saturation, replay, sensor dropout).

## Honest note

This is a **modelled simulation** for demonstration and security-education — it shows how the
system works and how it fails under attack. It is not a claim of real-world detection
performance (that needs real hardware + trained ML). The physics are simplified for clarity.

## Files
- `src/data/catalog.js` — drone / sensor / effector types and specs
- `src/engine/sim.js` — the simulation engine: plot→track pipeline, defeat logic, **attack injection**
- `src/ui/` — React UI: `App.jsx` (loop + panels), `Stage.jsx` (canvas renderer), `styles.css`
