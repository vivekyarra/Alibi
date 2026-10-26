# GRIDPRINT COOL benchmark

This folder holds the benchmark of SPEC Part 12. It compares the same engine code on three
configurations of equal vCPU and memory (see `configs.yaml`):

- **A** — x86 `c7i.2xlarge`, stock OpenCV 5, amd64 image.
- **B** — Graviton4 `c8g.2xlarge`, stock OpenCV 5, arm64 image.
- **C** — Graviton4 `c8g.2xlarge`, OpenCV 5 with COOL (Marketplace AMI).

No result in this folder is written by hand. Every number comes from a script and goes to
`results/bench/<date>/`.

## Files

| File | Purpose |
|---|---|
| `configs.yaml` | Configurations A, B, C: instance type, vCPU, memory, AMI, image platform. |
| `prices.py` | Gets on-demand EC2 prices from the AWS Price List API. Saves raw JSON and USD/hour with the date. |
| `cool_evidence.py` | Saves OpenCV build information, `cv2.__file__`, loaded libraries and an optional `perf` profile. |
| `run_bench.py` | Runs the engine on the pinned inputs and records metrics (owned by the lead; not in this change). |
| `run_remote.md` | Exact steps for a person to run A, B and C on EC2. |
| `inputs.txt` | Pinned input files with SHA-256 hashes (created with the inputs). |

## Protocol (SPEC Part 12)

1. Use the same engine code (same git commit) and the same inputs. `inputs.txt` lists each input
   file with its SHA-256 hash. Check the hashes on each instance before a run.
2. Run A, B and C on instances with equal vCPU and memory (8 vCPU, 16 GiB). A has 4 physical cores
   with 2 threads each; B and C have 8 physical cores. State this in the report.
3. Record for each run: throughput (video-seconds processed per wall-second), per-stage latency
   p50 and p95, CPU utilization, peak memory.
4. Do at least 5 runs per configuration. Report the mean and the standard deviation.
5. Parity check: the ENF tracks and verdicts from A, B and C must agree within the configured
   tolerance. Report every difference.
6. Evidence that COOL executes (configuration C, and B as the control): run `cool_evidence.py`
   with `--cmd` set to the benchmark command. It saves build information, library paths, version
   strings and a `perf` capture under `results/bench/<date>/evidence/<label>/`.
7. Report which stages COOL accelerates and which it does not. Claim a speedup for a stage only if
   the `perf` report shows COOL or KleidiCV symbols in that stage. If the evidence is missing, the
   COOL award is not claimed.

## Cost formula

```
cost_per_video_hour = hourly_price / throughput
```

- `hourly_price` is in USD per instance-hour.
  - A and B: the on-demand EC2 price from `results/bench/<date>/prices.json` (`prices.py`, V12).
  - C: the on-demand EC2 price for `c8g.2xlarge` **plus** the COOL software fee per instance-hour
    shown on the Marketplace listing for that instance type. `prices.py` does not read Marketplace
    fees. A person records the fee, the listing URL and the date in
    `results/bench/<date>/cool_software_fee.json`. If the fee is not recorded, the cost for C is
    not reported.
- `throughput` is video-seconds processed per wall-second (dimensionless).
- Why this works: one instance-hour processes `throughput` hours of video, so one hour of video
  costs `hourly_price / throughput`.

Example of units only (no real numbers): with a price of P USD/h and a throughput of T, one hour of
video costs P / T USD.

## Commands

```
python -m bench.prices c7i.2xlarge c8g.2xlarge            # needs the gridprint AWS profile (H1)
python -m bench.cool_evidence --label C --cmd "<benchmark command>"
```

## Limits

- This is not a general OpenCV benchmark. It measures the GRIDPRINT engine on its pinned inputs.
- The results hold for the listed instance types, region and date only.
