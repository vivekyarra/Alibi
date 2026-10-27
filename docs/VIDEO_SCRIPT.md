# Video script (maximum five minutes)

This is the plan for human task H8 (`SPEC.md` Part 14.4). The final video must not be longer than five minutes.

Number rule: this script contains no measured number. Each place that needs a measured value says "[value from results]" and has a source tag. Before recording, replace each "[value from results]" marker with the value from the named file and keep the tag in this file. The `<date>` in each tag is the frozen results folder.

Recording rules:
- Every result on screen comes from the live pipeline: the AWS endpoint, or `make local` when the endpoint is not public. No mock screens.
- Synthetic results on screen carry the label SYNTHETIC.
- Show the verdict card text and icon, not only color.
- Show the overlay label "Visualization of measured flicker. Not itself evidence." whenever the overlay is on screen.
- Do not use the words in the forbidden-claims list (SPEC R5).

## Timed script

### 0:00–0:20 Hook

| Item | Content |
|---|---|
| Voice | "AI can fake a video. Now people call real videos fake. We check whether a video is real with the light in the room." |
| Shot 1 | Close shot of a white wall under a mains-powered lamp, recorded with GRIDPRINT Capture. The band overlay shows bands moving across the wall. |
| Shot 2 | Title card: "GRIDPRINT". |

### 0:20–1:20 Capture → upload → `VERIFIED`

| Item | Content |
|---|---|
| Voice | "Lights on the power grid flicker at twice the grid frequency. The grid frequency changes a little every second, and the whole grid shares the same pattern. A phone camera reads its sensor one row at a time, so the flicker shows as bands. GRIDPRINT reads the pattern from the bands and matches it with a log of the real grid." |
| Shot 3 | Phone screen: GRIDPRINT Capture with the live band-strength meter. Record a short clip in a room. |
| Shot 4 | Upload from Capture. Job page: progress and the live agent trace. |
| Shot 5 | Verdict card `VERIFIED` with the recording time and its uncertainty: [value from results] <!-- src: results/demo/<date>/case1.json#time_uncertainty_s --> |
| Shot 6 | Evidence plot: video frequency track over the reference track. Grid zone shown. No finer location. |

### 1:20–2:10 Cut clip → `CONTRADICTED` → reviewer approves

| Item | Content |
|---|---|
| Voice | "Now we remove one second from the same clip and re-time it so it looks continuous. The flicker phase jumps at the cut. GRIDPRINT marks it. A person must approve this result before the report is final." |
| Shot 7 | Demo case 2 runs. Timeline strip with the red edit marker at the cut. |
| Shot 8 | Verdict card `CONTRADICTED`, state `PENDING_REVIEW`. Edit significance: [value from results] <!-- src: results/demo/<date>/case2.json#edit_significance --> |
| Shot 9 | Reviewer logs in, reads the evidence, approves with a note. Report becomes `FINAL`. |

### 2:10–2:40 Synthetic video → `INCONCLUSIVE`

| Item | Content |
|---|---|
| Voice | "This room video comes from an AI video generator. It has no grid signal, so the result is INCONCLUSIVE. That alone does not mean fake. Many real videos have no signal too, for example in daylight." |
| Shot 10 | Demo case 5 runs. Verdict card `INCONCLUSIVE` with reason `SIGNAL_ABSENT` and the plain explanation text. |
| Shot 11 | Demo case 6 (daylight) result card, short. |

### 2:40–3:30 Agent trace: weak signal → new patches → lock

| Item | Content |
|---|---|
| Voice | "The agent reads the OpenCV results and changes its plan. Here the first pass gives a weak signal. The agent picks other light patches and extracts again. Now the signal locks. The agent never writes the verdict. Fixed rules do that." |
| Shot 12 | Demo case 7. Live trace: `extract_flicker` → `SIGNAL_WEAK` → `propose_patches` → `extract_flicker` → signal locks. |
| Shot 13 | Band SNR before and after: [value from results] <!-- src: results/demo/<date>/case7_trace.json#band_snr_first --> and [value from results] <!-- src: results/demo/<date>/case7_trace.json#band_snr_final --> |
| Shot 14 | Agent workflow diagram (`docs/diagrams/agent_workflow.svg`), highlight B1 and B6. |

### 3:30–4:20 Architecture + measured COOL benchmark

| Item | Content |
|---|---|
| Voice | "The engine runs OpenCV 5 on AWS Graviton. The agent plans each job and calls engine tools through MCP. Its planner is Claude on Amazon Bedrock, with a deterministic planner as fallback. The reference grid log comes from our GPS-timed Node." |
| Voice check | Before recording, match each sentence to the facts on that day: say "with COOL" only if the COOL benchmark ran (`results/bench/`); say "Claude on Amazon Bedrock" planned this job only if the shown trace has planner type `bedrock`; say "GPS-timed Node" only if the shown reference came from Node data (H2), otherwise name the source shown in the report. |
| Shot 15 | Architecture diagram (`docs/diagrams/architecture.svg`). Highlight engine stages, Graviton workers, Node path. |
| Shot 16 | Benchmark chart from `results/bench/<date>/`. Throughput for configurations A, B, C: [value from results] <!-- src: results/bench/<date>/summary.json#throughput_A --> , [value from results] <!-- src: results/bench/<date>/summary.json#throughput_B --> , [value from results] <!-- src: results/bench/<date>/summary.json#throughput_C --> |
| Shot 17 | Cost per hour of video for each configuration: [value from results] <!-- src: results/bench/<date>/summary.json#cost_per_video_hour --> |
| Note | Show only stages where the profile shows COOL symbols. If V5 failed, say "COOL was not available; this runs stock OpenCV 5 on Graviton" and show B vs A only. |

### 4:20–5:00 Failure cases, limitations, team

| Item | Content |
|---|---|
| Voice | "GRIDPRINT has limits. Phone anti-banding hides the flicker in many ordinary videos. Short clips, strong compression, HDR, and fast motion also stop the check. We measured how often this happens." |
| Shot 18 | Results table: false-`CONTRADICTED` rate on authentic clips: [value from results] <!-- src: results/eval/<date>/summary.json#false_contradicted_rate --> |
| Shot 19 | `VERIFIED` coverage for Capture clips: [value from results] <!-- src: results/eval/<date>/summary.json#verified_coverage_capture --> ; `INCONCLUSIVE` rate for stock-app clips: [value from results] <!-- src: results/eval/<date>/summary.json#inconclusive_rate_stock --> |
| Shot 20 | Two or three items from the failure gallery (`results/eval/<date>/failures/`) with their plain explanations. |
| Shot 21 | Team on camera. Closing line: "GRIDPRINT: a check you can see in the light." |

## Shot list summary

| Shot | Source | Who |
|---|---|---|
| 1, 3 | Phone with GRIDPRINT Capture in a room with mains-powered lights | Team |
| 2 | Title card | Editor |
| 4–11 | Screen recording of the deployed Verify endpoint | Team |
| 12–14 | Screen recording of demo case 7 trace + agent diagram SVG | Team |
| 15–17 | Architecture SVG + benchmark chart from `results/bench/` | Editor |
| 18–20 | Tables and gallery from `results/eval/` | Editor |
| 21 | Camera on the team | Team |

## Before upload

1. Replace every "[value from results]" with the value from the tagged file.
2. Run `python scripts/check_numbers_sourced.py` and `python scripts/claims_lint.py`.
3. Check the duration: `python scripts/check_video_duration.py <file>`.
4. Upload as public or unlisted. Put the link in `README.md` (line "Video:").
