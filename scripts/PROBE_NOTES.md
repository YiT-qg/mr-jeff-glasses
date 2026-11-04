# Probe notes (Phase 1, live, 2026-11-03)

Test image: synthetic 504×896 JPEG q80 (~9.6 KB, 12884 b64 chars).

## muse-spark-1.3 — POST /v1/chat/completions

- First run with `max_tokens: 200` → 200 but `content: null`,
  `finish_reason: "length"`: 198 reasoning tokens ate the whole budget.
- **Lesson: always set `max_tokens >= 1000` for this model.**
- Phase 3 update: even 1000 starved once (reasoning hit 1430 tokens on the
  router prompt). Router/hazards now use `max_tokens=4000, temperature=0`.
  Typical: ~700 prompt + ~1500 completion (mostly reasoning) per call.
- Rerun: 200, latency **~11.3 s**, vision correct
  (`{"seen": "A red rectangle with the text PROBE E-204…"}`).
- Usage per image + short prompt: **prompt 602, completion 299
  (of which reasoning 268), total 901.**
- Budget rule of thumb: **~600 prompt + ~300 completion ≈ 900 tokens
  per single-image call.** Longer prompts/crops scale from there.

## sam-3.1 — POST /v1/responses (NOT /chat/completions)

- `/chat/completions` → 404: "The model `sam-3.1` is not available on
  this endpoint. Use /v1/responses."
- `/v1/responses` with Responses-style `{role, content: [input_text,
  input_image]}` → 200, latency 3.3–5.7 s, `status: completed`.
- Usage is all zeros plus **`images_processed: 1`** (per-image billing? tokens $0).
- Output message `text` is **empty** with a plain text prompt — the real
  segmentation output shape (mask/bbox/tool call?) is still unknown.
- **Phase 3 must probe SAM again** (point/box prompts or tools) before
  building `segment.py` on it. `USE_SAM=0` skip stays mandatory.

## Spend so far

5 probe calls total (spark ×2, sam ×3). Token usage above; **$ price per
token is unknown** — `cost_report.py` must report tokens exactly and mark
$ TBD until pricing is published. Demo/judges' runs replay cache: $0.
