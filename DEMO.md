# Demo script (3-minute video)

Record the lens at http://127.0.0.1:8000 with `run_clip.py` running in a
terminal beside it. All runs below replay committed cache: $0, no key.

## 0:00–0:20 — Intent

Say: "Mr. Jeff Glasses watches what a technician looks at. Hold your gaze for
2.5 seconds and it classifies the context, identifies the object, and routes
to a specialist — one card at a time on the lens."

```bash
.venv/bin/python scripts/run_clip.py data/clips/synth_dwell_test.mp4
```

Show two dwell cards appearing as the clip plays.

## 0:20–2:20 — Manufacturing centerpiece (CNC-07)

```bash
.venv/bin/python scripts/run_clip.py data/clips/cnc07_e204.mp4
```

1. Dwell on the HMI → `E-204 Spindle overtemp · CNC-07`.
2. Three hypotheses, each citing work-order history (filter, coolant, bearing).
3. Dwell on the filter sight glass → ruled out. Dwell on the reservoir →
   ruled out. Dwell on the bearing → confirmed with visible scoring.
4. Fix steps from the manual (isolation first) + `Bearing 6205-2RS: 3 in
   stock, Bin A-14`.
5. Press Space (pinch) → `Work order WO-0001 created`.
6. Re-run the same command → symptom card now reads "4 WOs in history":
   the system learned. (Needs no key; the post-WO state is pre-recorded.)

## 2:20–2:45 — Retail and wandering (quick hits)

```bash
.venv/bin/python scripts/run_clip.py data/clips/retail_demo.mp4
.venv/bin/python scripts/run_clip.py data/clips/wandering_demo.mp4
```

Retail: product + two cheaper catalog alternatives. Wandering: place name
(set `MOCK_DESTINATION` + key for a live directed variant).

## 2:45–3:00 — Feasibility on target hardware

Say: "Dwell runs locally per frame — no API. The camera is one interface,
`FrameSource`, downsampled to the 504×896 @ 5 fps glasses-stream shape, so a
real Device Access Toolkit stream swaps in. Every model response is cached by
input hash: this whole video cost $0 to re-run." Show:

```bash
.venv/bin/python scripts/cost_report.py traces/*.jsonl | tail -3
```
