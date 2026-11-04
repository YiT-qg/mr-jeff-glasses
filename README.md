# Mr. Jeff Glasses

A context-aware assistant for Meta Ray-Ban Display glasses, built for the Meta hackathon.

Hold your gaze on something for a couple of seconds and the app works out where you are (a factory floor, a store, out walking), identifies what you're looking at, and hands off to a specialist for that setting. The deep specialist is the **shop floor**: it flags safety hazards, then walks a technician through a root cause analysis of a machine fault on the lens. It uses the machine's work-order history from [Mr. Jeff](https://github.com/YiT-qg/mr-jeff), and logs the confirmed cause back as a new work order.

> **Status:** planning. The build spec is in [`docs/MUSE_BUILD_PROMPT.md`](docs/MUSE_BUILD_PROMPT.md). Setup instructions will land here as phases ship.

## How it works

1. **Dwell detection (on device).** No eye tracking on Ray-Ban Display, so a "look" means the head is still and the frames stop changing for about 2.5 s. No API call until this fires.
2. **Context router.** One Muse Spark call classifies the scene (`manufacturing` / `retail` / `wandering`) and names the object in focus.
3. **Segmentation.** SAM 3.1 crops the target so the specialist gets a clean view.
4. **Specialists.**
   - **Manufacturing:** hazards first, then RCA (symptom → hypotheses from asset history → guided checks → root cause and fix from the manual → work order).
   - **Retail:** cheaper alternatives.
   - **Wandering:** directions.
5. **Lens.** One short card at a time on the 600×600 display; a pinch advances.

## What's live vs. simulated in the demo

| Piece | Demo | On real hardware |
|---|---|---|
| Camera | Video file or phone camera at 504×896, 5 fps | Glasses camera via the Wearables Device Access Toolkit phone app |
| Lens | Browser simulator at 600×600 | Ray-Ban Display cards |
| Models | Meta Model API (Muse Spark 1.3, SAM 3.1), with cached responses so it runs without a key | Same |
| Mr. Jeff | Live API if `MRJEFF_API_URL` is set, otherwise a local JSONL file | Mr. Jeff platform |
| Machine data | Seeded, fictional asset history | Customer's work-order system |

## Safety

Hazard alerts are advisory, a second pair of eyes. They never replace lockout/tagout or machine guarding. Every repair procedure starts with isolation.

## Footage credits

See [`docs/FOOTAGE.md`](docs/FOOTAGE.md).
