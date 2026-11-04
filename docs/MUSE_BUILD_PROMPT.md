# Build prompt: Mr. Jeff Glasses (Meta hackathon)

Paste everything below the line into Muse Spark (or any OpenAI-compatible coding agent pointed at `https://api.meta.ai/v1` with model `muse-spark-1.3`). It is written so the agent builds in phases and stops for review between them.

---

You are the lead engineer on a 3-person hackathon team. Build **Mr. Jeff Glasses**, a context-aware assistant for Meta Ray-Ban Display glasses, in a public GitHub repo named `mr-jeff-glasses`. Judges will run the repo from its README on a laptop with no glasses, and score a 3-minute demo video on intent, execution, and feasibility on the target hardware.

## What the product does

When the wearer holds their gaze on something (the head stays still and the view stays the same for about 2.5 seconds), the app:

1. **Detects the dwell** locally, with no API call.
2. **Classifies the context**: `manufacturing`, `retail`, `wandering`, or `unknown`.
3. **Identifies the object** in focus, using the context to narrow the candidates.
4. **Routes to a specialist** for that context:
   - `manufacturing` (the deep one): safety hazards in view, plus the root cause analysis (RCA) loop for a machine fault, plus logging a work order to Mr. Jeff.
   - `retail` (light): what the product is, and up to 2 cheaper alternatives.
   - `wandering` (light): what the place or object is, and directions to something the wearer asked for earlier.
5. **Shows one card at a time** on a simulated 600×600 lens; a "pinch" (keyboard key in the simulator) advances or confirms.

Mr. Jeff is the founder's AI work-order and inventory platform. The manufacturing specialist is the proof point: its diagnosis is better than a generic vision model **because** it reads the machine's work-order history.

## Hard constraints

- **Hardware reality.** Ray-Ban Display Web Apps cannot read the camera. In production, a phone app (Meta Wearables Device Access Toolkit) streams the glasses camera at about 504×896 and 2–7 fps and pushes cards back to the lens. For this build, the "camera" is a video file or a laptop/phone webcam, downsampled to 504×896 at 5 fps. Keep that interface (`FrameSource`) clean so a real glasses stream can be swapped in later.
- **There is no eye tracking.** Dwell means: (a) frame-to-frame similarity above a threshold for N consecutive frames, using a cheap local measure (downscaled grayscale + SSIM, or perceptual hash distance), and (b) optional phone gyro stillness when available. Make thresholds configurable and log them.
- **Budget: $150 of Meta Model API credit for the whole hackathon, including development.** Never call an API per frame. Only call when a dwell fires. Cache every API response by input hash (record/replay) so the demo and judges' runs cost $0.
- **Models (Meta Model API, OpenAI-compatible, base URL `https://api.meta.ai/v1`, key in `MODEL_API_KEY`):**
  - `muse-spark-1.3` for context classification, object ID, and specialists. Send frames as `image_url` content parts (base64 JPEG, max 504×896, quality 80). Ask for JSON output and validate it against a schema; on invalid JSON, retry once with the validation error, then fall back to a safe "Not sure what this is" card.
  - `muse-spark-1.3-contributor` is about 12× cheaper but its data may be used for training. Use it ONLY for synthetic/sample inputs during development, behind a `USE_CONTRIBUTOR=1` flag. Never send real workplace footage to it.
  - `sam-3.1` to segment the dwell target (the region around the frame center), so the specialist gets a crop plus the full frame. Make SAM optional (`USE_SAM=0` skips it) in case of errors.
  - Do not invent other endpoints, parameters, or model names. If an API call shape is unclear, write a tiny probe script, run it, and show me the result before building on it.
- **Safety framing.** Hazard alerts are advisory ("second pair of eyes"), never a replacement for lockout/tagout or machine guarding. Every repair procedure starts with the isolation step. Hazard cards take priority over any other card.
- **Grounding.** Fix steps come only from the files in `data/manuals/`, never from the model's general knowledge. If no manual matches, the card says "No procedure on file. Call maintenance lead."
- **No secrets in the repo.** Ship `.env.example`, and put `.env` in `.gitignore`.

## Architecture (Python 3.11 backend, plain HTML/JS lens simulator)

```
mr-jeff-glasses/
  README.md               # 3-command setup; runs fully on cached responses with no key
  .env.example
  app/
    frame_source.py       # VideoFileSource, WebcamSource -> 504x896 @ 5 fps
    dwell.py              # local dwell detector (similarity + optional gyro), emits DwellEvent
    router.py             # one Muse call -> {context, object, confidence, bbox_hint}
    segment.py            # SAM 3.1 crop of the dwell target (optional)
    specialists/
      manufacturing.py    # hazards + RCA state machine + work-order write-back
      retail.py           # product ID + cheaper alternatives
      wandering.py        # place ID + directions (mock location)
    rca.py                # RCA state machine: SYMPTOM -> HYPOTHESES -> CHECKS -> ROOT_CAUSE_FIX -> CLOSE
    mrjeff_client.py      # POST work order to MRJEFF_API_URL, else append to data/work_orders.jsonl
    cache.py              # record/replay keyed by sha256(model + prompt + image bytes)
    server.py             # FastAPI + WebSocket that pushes cards to the lens simulator
    prompts/              # every prompt as its own .txt file, versioned
  lens/                   # 600x600 simulator: card UI, Space = pinch/advance, H = history
  data/
    assets.json           # seeded machines with work-order history (see below)
    manuals/              # short procedures per error code, each starting with isolation
    products.json         # small retail catalog with prices, for alternatives
    clips/                # sample input videos (licensed; see README credits)
    cache/                # committed recorded API responses for the sample clips
  scripts/
    run_clip.py           # python scripts/run_clip.py data/clips/x.mp4 -> lens + trace log
    overlay_hmi.py        # burns a synthetic HMI error panel into a licensed clip, labeled SIMULATED
    cost_report.py        # sums tokens and $ from traces
  traces/                 # JSONL per run: frame idx, dwell, model, latency, tokens, $, card shown
```

## Seeded data (write these yourself, clearly fictional)

`data/assets.json` holds 3 machines. Make one of them tell a clear RCA story:

- `CNC-07` (a 3-axis mill): error `E-204 Spindle overtemp` appeared twice in the last 60 days; last preventive maintenance 140 days ago (interval 90); coolant pump replaced 200 days ago; bearing never replaced. The correct root cause for the demo is **spindle bearing wear**, with **clogged coolant filter** as a plausible second hypothesis that a guided check rules out.
- Two other machines with unremarkable histories, to show the history actually drives the hypotheses.

`data/manuals/` holds procedures for E-204 and 2 other codes. Every procedure's first step is: "Isolate power at the machine disconnect and apply your lock (LOTO)."

## Prompts (store in app/prompts/, return strict JSON)

**router.txt** (input: full frame + optional SAM crop + coarse hints {time_of_day, mock_location_type})
"You see one first-person frame from smart glasses. The wearer has been looking at the center of the frame for several seconds. Return JSON: {context: manufacturing|retail|wandering|unknown, object: short noun phrase for what is at the center, object_type, visible_text: any codes or labels you can read verbatim, confidence: 0-1}. Use unknown if confidence < 0.5. Do not guess error codes you cannot read."

**manufacturing_hazards.txt** (always run first in manufacturing)
"List only hazards you can see in this frame from this set: missing eye protection, missing hard hat, person inside a marked keep-out zone, spill or blocked walkway, removed machine guard. Return JSON {hazards: [{type, where, confidence}]}. Return an empty list if none are clearly visible. These alerts are advisory."

**rca_hypotheses.txt** (input: frame, visible_text, asset record from assets.json)
"Given the symptom and this machine's work-order history, propose at most 3 root-cause hypotheses ranked by likelihood. Each must cite the specific history fact that supports it. For each, give one visual or physical check a technician can do in under 2 minutes. Return JSON {hypotheses: [{cause, reason_from_history, check}]}."

**rca_check.txt** (input: new frame after the worker looks at the check location)
"Does this frame confirm, rule out, or fail to show the check '{check}'? Return JSON {result: confirmed|ruled_out|unclear, evidence}."

**retail.txt**: identify the product and return up to 2 cheaper alternatives, only from `products.json` passed in context.

**wandering.txt**: name the landmark or object in 1 line, and give a direction from the mock location if the wearer set a destination.

Lens cards are at most 3 short lines plus a step counter, e.g. "Step 2/6 · Isolate power at panel B".

## RCA flow on the lens (the 2-minute centerpiece of the video)

1. Dwell on CNC-07's HMI → card "E-204 Spindle overtemp · CNC-07".
2. Card with 3 hypotheses, each with its history reason ("Bearing wear: E-204 twice in 60 days, PM 50 days overdue").
3. Guided checks, one per card; the worker dwells on the check spot, or pinches to confirm or rule out.
4. Confirmed cause → fix steps from the manual, starting with LOTO, plus a part check against inventory ("Bearing 6205-2RS: 3 in stock, Bin A-14").
5. Pinch → work order written to Mr. Jeff with the frame, the checks performed, the root cause, and the parts used → "Work order WO-#### created" card. Re-running the same clip now shows 3 events in the history, demonstrating that the system learns.

## Build phases (stop after each one, show me the output, wait for "go")

1. **Probe**: a 20-line script that sends one image to `muse-spark-1.3` and one to `sam-3.1`, then prints the response shape, token usage, and latency. Write down the real per-image token count; we budget from it.
2. **Offline skeleton**: frame source, dwell detector, lens simulator, and cache, with a fake router. Run on a sample clip and show dwell events in the trace log.
3. **Router + manufacturing hazards** live, cached.
4. **RCA state machine** with seeded data, end to end on the CNC-07 clip.
5. **Work-order write-back** (`MRJEFF_API_URL` if set, else JSONL).
6. **Retail and wandering specialists**, light.
7. **README, cost report, and demo script**: the README says plainly what is live and what is simulated (camera = phone/video file at glasses resolution; lens = browser simulator matching the 600×600 display; Mr. Jeff = live API or JSONL).

## Acceptance checks

- `git clone && pip install -r requirements.txt && python scripts/run_clip.py data/clips/cnc07_e204.mp4` works with **no API key**, using committed cache files.
- At most 1 router call per dwell, no calls between dwells. `cost_report.py` shows the total for the full demo clip set under $1.
- Every card is traceable in `traces/` to the frame and model response that produced it.
- Hazard cards always pre-empt RCA cards.
- No card ever shows a fix step that isn't in `data/manuals/`.

Before writing code, restate the plan in 10 lines or fewer and ask me up to 3 questions you need answered. Then start Phase 1.
