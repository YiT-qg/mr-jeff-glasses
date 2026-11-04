# Mr. Jeff Glasses

Context-aware assistant for Meta Ray-Ban Display glasses. When the wearer holds
their gaze (~2.5 s of still head + static view), the app classifies the context
(manufacturing / retail / wandering), identifies the object in focus, and shows
one card at a time on the lens. The manufacturing specialist is the proof point:
its diagnosis beats a generic vision model because it reads the machine's
work-order history.

Status: **complete through Phase 7** — all specialists live, cached, with cost
report and demo script.

## Setup (3 commands, no API key)

```bash
git clone <this-repo> && cd mr-jeff-glasses
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/run_clip.py data/clips/cnc07_e204.mp4
```

Then open http://127.0.0.1:8000 for the 600×600 lens simulator
(Space = pinch / advance, H = history). Runs fully on committed cache files.

Requirements: Python 3.11 recommended (3.9 tested on the dev machine), pip.
Video read/write comes from pip (`imageio-ffmpeg` bundles the codec) — no
system ffmpeg needed. If `pip install` hangs on a years-old pip, upgrade it
first: `python3 -m pip install --upgrade pip`.

With a key (`cp .env.example .env`, fill in `MODEL_API_KEY`), new dwells call
`muse-spark-1.3` live and record to `data/cache/`:

```bash
.venv/bin/python scripts/probe.py   # one image each to muse-spark-1.3 and sam-3.1
```

## Demo clips

| Clip | Dwells | Story |
|---|---|---|
| `data/clips/synth_dwell_test.mp4` | 2 | Dwell detector smoke test |
| `data/clips/cnc07_e204.mp4` | 4 | Full RCA: E-204 → bearing wear → fix → WO-0001 |
| `data/clips/retail_demo.mp4` | 1 | Product + 2 cheaper alternatives |
| `data/clips/wandering_demo.mp4` | 1 | Place ID (+ directions with `MOCK_DESTINATION`) |

See [DEMO.md](DEMO.md) for the 3-minute video shot list. `traces/` holds a
JSONL per run (frame, dwell, model, latency, tokens, card); every card links
to the frame and model response that produced it.

Environment knobs: `MODEL_API_KEY`, `MRJEFF_API_URL` (else JSONL ledger),
`MOCK_LOCATION`, `MOCK_DESTINATION`, `MRJEFF_OFFLINE=1` (cache-only, simulates
the judges' no-key run), `MRJEFF_NO_CACHE=1` (force live).

## How it works

1. **Dwell** (`app/dwell.py`): downscaled-grayscale frame diff under threshold
   for 12 frames @ 5 fps (≈2.5 s), optional gyro AND-gate. Local, no API.
2. **Router** (`app/router.py`): one `muse-spark-1.3` call per dwell →
   `{context, object, visible_text, confidence}`.
3. **Specialists**: manufacturing runs hazards first (pre-empting cards), then
   the RCA loop (`app/rca.py`: hypotheses from history → guided checks →
   manual fix steps → parts). Retail and wandering are one call each.
4. **Lens** (`lens/`, served by `app/server.py`): FastAPI + WebSocket pushes
   cards to a 600×600 page; pinch posts back and drives confirm/close.
5. **Cache** (`app/cache.py`): every response keyed by
   sha256(model + prompt + image); committed under `data/cache/`.

## What is live vs simulated

- Camera: video file or webcam downsampled to 504×896 @ 5 fps — the
  glasses-stream shape a phone app would push. The swap point is the
  `FrameSource` interface; no real glasses stream is connected.
- Lens: browser simulator matching the 600×600 display (dark additive-style
  UI). For Meta's own preview, load the lens URL through the
  [Meta Ray-Ban Display Simulator](https://chromewebstore.google.com/detail/meta-ray-ban-display-simu/jpjlmmodokemlepklkdbimceggpbjcll)
  Chrome extension.
- Models: live `muse-spark-1.3` with recorded cache. SAM segmentation is **not
  wired in**: the probe showed `sam-3.1` answers on `/v1/responses` but returns
  no segmentation payload for plain prompts (see `scripts/PROBE_NOTES.md`).
- Mr. Jeff: POSTs to `MRJEFF_API_URL` when set, else `data/work_orders.jsonl`.
- Footage: all synthetic — generated stills (labeled SIMULATED) and drawn
  scenes. No licensed clips, no real workplace footage.

## Layout

- `app/` — frame_source, dwell, cache, llm, router, rca, server,
  mrjeff_client, specialists/{manufacturing,retail,wandering}, prompts/*.txt
- `lens/` — 600×600 simulator (plain HTML/JS)
- `scripts/` — probe, run_clip, make_synthetic_clip, overlay_hmi, cost_report
- `data/` — assets.json, manuals/, products.json, prices.json, stills/,
  clips/, cache/ (committed recordings)
- `traces/` — JSONL per run (gitignored)

## Budget

No API calls between dwells; at most 1 router call per dwell. Demo set:
8 dwells, 8 router calls, 32,453 tokens ≈ **$0.10** at $1.25/$4.25 per M
(`scripts/cost_report.py`; replay cost is $0). Whole-hackathon spend is a few
dollars against the $150 credit. See `scripts/PROBE_NOTES.md`.

## Build notes

- `rca_check.txt` deviates from the original spec wording (documented here, not
  hidden): "does this frame confirm the check" made the model confirm the check
  *target* was shown even with "no debris visible" as evidence. The shipped
  prompt asks cause-centric verdicts (support/refute/inconclusive), which rules
  out clean states correctly.
- Check-spot footage is generated stills (`data/stills/`, labeled SIMULATED),
  not cartoons: the model rightly refuses text-labeled drawings ("SIGHT GLASS:
  CLEAR") as physical evidence, but judges photorealistic states honestly
  (clear glass → ruled out; scored bearing → confirmed).
- During an open RCA session, `unknown`-context dwells also feed the current
  check; retail/wandering dwells do not.
- `unclear` check verdicts don't advance the hypothesis pointer: the frame
  didn't answer the check (often the wrong spot), so it stays open. Only
  `ruled_out` advances; all-ruled-out closes as unresolved.
- New history entries are stamped `"today"` (literal), and router prompts
  carry no wall-clock time — both keep cache keys identical on any run date
  so judges' offline replay always hits.
- Offline learning covers one WO cycle (pre-recorded); further WO cycles need
  `MODEL_API_KEY` since each new history state is a new prompt.

## Credits

All footage and stills are generated for this repo (no licenses needed):
`make_synthetic_clip.py` scenes, `overlay_hmi.py` SIMULATED HMI panel, and
`data/stills/` AI stills. No real people, workplaces, or products depicted;
brand-like names (Auralux, CNC-07) are fictional.
