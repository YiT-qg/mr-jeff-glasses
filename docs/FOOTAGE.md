# Sample footage

Only clips with licenses that allow redistribution go in `data/clips/`. Check each clip's license page before committing it.

## Shop-floor context (free to use)
- Pexels: [Aging industrial machinery in factory workshop](https://www.pexels.com/video/aging-industrial-machinery-in-factory-workshop-30456098/)
- Pexels: [Machines and two workers in factory](https://www.pexels.com/video/machines-and-two-workers-in-factory-11017956/)
- Pexels: [Aluminium automatic machinery drill CNC](https://www.pexels.com/video/aluminium-automatic-machinery-drill-cnc-18883365/)
- Pexels: [Cooling system in an industrial machine](https://www.pexels.com/video/cooling-system-in-an-industrial-machine-14132388/)
- Pixabay: [Conveyor, factory, industry](https://pixabay.com/videos/conveyor-factory-industry-metal-332263/)
- Pixabay: [Welder, industry, factory](https://pixabay.com/videos/welder-industry-factory-source-135848/)

## First-person industrial footage (CC BY 4.0, attribution required)
- [IndEgo](https://huggingface.co/datasets/FraunhoferIPK/IndEgo) (Fraunhofer IPK, NeurIPS 2025): about 197 hours of egocentric industrial recordings, including inspection and repair, with mistake annotations. Recorded through Meta's Project Aria program. The full set is 19 TB; download only a few clips.

## Staged clips
Machine faults and hazards (HMI error codes, missing eye protection, keep-out zones) are staged or overlaid with `scripts/overlay_hmi.py`, and labeled **SIMULATED** in the video.

## Demo video only (never committed)
Third-party footage used only as local pipeline input or in the recorded demo
video — never redistributed in this repo. Keep such files under
`data/clips/local/` (gitignored) and credit on screen:
- YouTube: [FANUC 16T: Troubleshooting alarm EX0490 Spindle Speed Abnormal](https://www.youtube.com/watch?v=S_0LHUV1L7Y) (Fabian Achaval) — real HMI alarm reference for the demo video.
