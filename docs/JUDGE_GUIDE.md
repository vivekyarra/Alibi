# Judge guide

GRIDPRINT checks if a video is real by reading the power-grid frequency from the flicker of indoor lights. The camera's rolling shutter records the flicker as faint horizontal bands. GRIDPRINT compares the measured frequency track with a reference log of the real grid.

Endpoint: 

The public HTTPS URL is added on this line at deployment.

**Live demonstration.** The team runs the full system with `make local` in a live screen-share on request. This runs the same engine, agent and web app as the AWS deployment, with local storage and the deterministic planner.

## 1. What you can do on the endpoint

1. Open the endpoint. The home page has three parts: upload, demo cases, and the live grid tile.
2. Run a demo case, or upload your own MP4 or MOV file.
3. Watch the job page. It shows progress, the live agent trace, the verdict card, the band overlay player with timeline markers, plots, and downloads (report PDF, report JSON, overlay MP4).
4. Log in as a reviewer to see the approval screen for `CONTRADICTED` results.

## 2. Verdicts

GRIDPRINT gives exactly three verdicts:

| Verdict | Meaning |
|---|---|
| `VERIFIED` | A grid signal is present. It matches the reference log at one time only. No significant edit evidence exists. If you gave a claimed time, the matched time agrees with it. |
| `CONTRADICTED` | A grid signal is present, and it conflicts with the claimed time, or it shows a break that frame timestamps do not explain, or different parts match different times. A human reviewer must approve this result before the report is final. |
| `INCONCLUSIVE` | The check could not be completed. For example: no usable grid signal, no reference data for the zone and time, or no unique match. |

`INCONCLUSIVE` is not evidence that a video is fake.

## 3. Demo cases

All demo cases run through the live pipeline (`POST /v1/demo-cases/{id}/run`). No result is stored in advance. The latest measured verdicts are in `results/`. The "Target verdict" column is the result that `SPEC.md` defines for each case; the verdict you see is the one the pipeline measures on the run.

| # | Case | Target verdict |
|---|---|---|
| 1 | Capture clip | `VERIFIED` with recording time |
| 2 | Same clip with a one-second cut | `CONTRADICTED`, then reviewer approval |
| 3 | Insertion of a segment recorded at another time | `CONTRADICTED` (`SEGMENT_OFFSET_INCONSISTENT`) |
| 4 | Dropped frames with their original timestamps | `VERIFIED` with `DROPPED_FRAMES_EXPLAINED` |
| 5 | Synthetic room video from a public video generator | `INCONCLUSIVE` (`SIGNAL_ABSENT`). This alone does not mean the video is fake. |
| 6 | Daylight-only clip | `INCONCLUSIVE` |
| 7 | Agent recovery: first pass `SIGNAL_WEAK`, the agent selects new patches, the signal locks | Final verdict from the second pass; the trace shows the change of plan |
| 8 | Face-composite clip (consenting team members) | Face-region result labeled `EXPERIMENTAL`. This result is never the only basis for `CONTRADICTED`. |

## 4. Reviewer login

Reviewer credentials for the endpoint are provided to judges on request. They are not in this repository. With `make local`, the reviewer token is in `work/local_reviewer_token.txt`.

Use the reviewer screen to approve or reject a `CONTRADICTED` result. A rejection makes the report final with verdict `INCONCLUSIVE` and reason `REVIEWER_REJECTED`. The note you write is stored.

## 5. What to expect from ordinary phone videos

Most phone camera apps turn on "anti-banding". Anti-banding sets the exposure time to a whole number of flicker periods. This removes the flicker bands from the video. Without the bands, GRIDPRINT cannot read the grid signal.

So, if you upload a video from a normal phone camera app, the result is often `INCONCLUSIVE`. This does not mean that the video is fake. It means that the video has no usable signal.

Other common reasons for `INCONCLUSIVE`:
- the scene has only daylight or battery-powered lights;
- the clip is short;
- the video was recompressed strongly (for example by a messaging app);
- the video is HDR (not supported);
- there is no reference data for the zone and time of recording.

GRIDPRINT Capture (the Android app) turns off anti-banding and uses a short exposure. It also records sensor timing in a sidecar file. Videos from Capture are the main use case. The check of other videos is best effort.

## 6. What GRIDPRINT does not do

- It does not decide whether pixels look AI-made.
- It does not recognize faces or identify people.
- It does not report any location finer than the grid zone.
- It is not cryptographic proof.

## 7. More information

- Architecture: `docs/ARCHITECTURE.md`
- Technical report: `docs/TECHNICAL_REPORT.md`
- Responsible use: `docs/RESPONSIBLE_USE.md`
