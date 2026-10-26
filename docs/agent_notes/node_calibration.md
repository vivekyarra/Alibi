# Agent notes — Node and calibration rig (M4, M5 groundwork)

Date: 2026-10-26. Scope: `node/`, `calibration_rig/`. These are decisions under SPEC 0.5 (ambiguity
rule). The main `docs/DECISIONS.md` can copy them.

## Decisions

### N-1 — GridLog item layout with several nodes per second
- Decision: one DynamoDB item per (zone, second): `pk` = `"<zone>#<YYYYMMDD>"` (string, UTC day), `t` =
  epoch second (number). Each node's reading lives in a `readings` map (`node_id -> {freq, quality,
  source}`). Top-level `freq` (median), `node` (comma-joined ids), `quality`, `source` are a convenience
  copy. Writes use get + conditional put with a `version` counter (optimistic locking, 8 retries).
- Reason: SPEC 10.4 fixes PK/SK and asks for the median over nodes. One item per second cannot hold
  several nodes without a map. Readers (`aws_gridlog.py`) take the median from `readings`.
- Alternatives: SK = second plus node suffix (breaks "SK epoch second (number)"); UpdateItem with nested
  map paths (needs the map to exist first; two-step anyway).

### N-2 — Top-level `quality` and `source`
- `quality` = `gps` only if every reading is `gps`, else the first non-gps value. `source` = the common
  source, or `mixed`.

### N-3 — Message validation in the Lambda
- Required fields as SPEC 10.4. `quality` ∈ {gps, ntp}; `gps` needs `gps_lock=true`. `freq_hz` in
  [40, 70] Hz (covers 50 and 60 Hz grids; a plausibility band, not a measurement claim). `t_utc_s` a whole
  second, ≥ 2020-01-01 and ≤ now + 300 s. Zone and node id match the MQTT topic when the IoT rule passes
  `topic(2)`/`topic(3)`. Optional `ALLOWED_ZONES` env var.
- Optional field `source` ∈ {node, sim}, default `node`. The simulated publisher sets `sim`, so simulated
  data is always labelled.
- Invalid messages are logged and dropped (not retried).

### N-4 — Firmware timing method
- GPIO interrupt + `esp_timer_get_time()` (1 µs resolution) for zero crossings and PPS, as recorded in
  VERIFICATION V11. The PPS interval gives the local timer's microseconds per true second each second.
- Filter: drop edges < 0.5 nominal periods after the last kept edge; keep periods within ±10 % of nominal;
  keep periods within ±0.5 % of the median; frequency = us_per_s / mean(kept periods); need ≥ 80 % of the
  nominal cycle count. Mean after median filtering, not the median itself, because the median of 1 µs
  quantized periods is coarse (1 µs in 20 ms is 50 ppm, 2.5 mHz at 50 Hz).
- Alternative: MCPWM capture (hardware capture at the APB clock). Not chosen: the simplest option that
  matches V11; can be revisited after measuring interrupt jitter on hardware.

### N-5 — UTC labelling of PPS edges
- The RMC sentence received within 1 s after a PPS edge labels that edge. A Kconfig offset
  (`GRIDPRINT_NMEA_PPS_OFFSET_S`, default 0) corrects modules that behave differently; `node/SELFTEST.md`
  step 6 checks it against an NTP-synced PC.

### N-6 — NTP fallback (V11)
- Without GPS lock, seconds are framed by SNTP time, scale = 1e6 µs/s (crystal not corrected), and
  messages carry `quality="ntp"`, `gps_lock=false`. The data-quality script counts them as "no GPS lock".

### N-7 — Offline buffer and back-fill
- RAM FIFO, default 1800 s (Kconfig, 60–7200), heap-allocated. Full buffer drops the oldest sample and
  counts it. Drained oldest first at ≤ 20 msg/s (Kconfig) with QoS 1. A sample is removed when
  `esp_mqtt_client_publish` accepts it; a disconnect between that and PUBACK can lose it (gap shows in the
  data-quality report). Power loss loses the buffer.

### N-8 — Node circuit values
- Adapter lead B tied to VBIAS (1.65 V), 220 k / 10 k divider, 10 nF low-pass (~1.7 kHz), LM393 at 5 V
  (input common-mode range then reaches 3.5 V), open-collector output pulled up to 3.3 V, 10 k / 1 M
  hysteresis (~33 mV). Designed for up to 18 V peak input. Values are computed, not measured.

### N-9 — Data-quality rules
- Coverage = seconds with at least one row / seconds in the window (window ends at `--end`, default
  now − 1 s, so a dead Node fails). GPS lock % = rows with `quality=gps` / all rows. Outliers: |f − nominal|
  > 1.0 Hz, or |f − 61 s running median| > 0.05 Hz (engineering constants). Pass: coverage ≥ 99 % and GPS
  lock ≥ 99 % (H2).

### N-10 — NESO import
- Writes `source="neso"`, `node="neso"`, `quality="external"` for zone GB. Time column: first header
  containing dtm/date/time; frequency column: f/freq/frequency or containing "freq"; header-less files read
  as (time, freq). Naive timestamps read as UTC (V8 says GMT; not re-checked against a real file in this
  session). Rows outside 45–55 Hz are counted and skipped. Accepts `.zip`. Does not download.
- DynamoDB mode uses the per-item upsert, which is slow for monthly files (about 2.6 M rows); local mode
  is the practical path for evaluation.

### N-11 — Readout fit
- Luma from plane 0 of the decoded frame (coded orientation, same as the engine's `probe_video`).
  Quadratic detrend, Hann window, zero-padded `cv2.dft` (8×), Gaussian (log-parabolic) peak
  interpolation, search band periods 3 rows to rows/2, frame accepted when peak/median spectrum ≥ 8, clip
  needs ≥ 10 accepted frames. Uncertainty = 1.2533 × 1.4826 × MAD / √n (standard error of the median).
  Readout longer than the frame period is rejected.
- Profile key = `gridprint_engine.readout.profile_key(device, W, H, fps)` with coded W×H and stream fps
  (mode folder name is only checked; mismatch → warning).
- Also writes `results/calibration/<device>/<W>x<H>_<fps>.json` so reported readout numbers have a source
  file (R12).

### N-12 — Rig firmware
- ESP32 LEDC with `LEDC_USE_APB_CLK` (crystal-derived via PLL, not the RC oscillator), 10-bit, 50 % duty,
  default 1000 Hz on GPIO 18 (Kconfig). Not measured yet; RIG_GUIDE step 5 asks for a frequency check.

### N-13 — Alignment with the infra stack (read from `infra/gridprint_infra/iot.py`, `data.py`)
- Lambda entry point `handler.handler` → `handler.py` exports `handler = lambda_handler`.
- Table name env: `GRIDLOG_TABLE` (task brief) or `GRIDPRINT_GRIDLOG_TABLE` (infra). Key attributes `pk`
  (S) and `t` (N) match the data stack. CLI default table name `gridprint-GridLog`.
- `provision.py` attaches the stack policy `gridprint-node` and thing type `gridprint-node` when they
  exist (thing attribute `zone` set); without the stack it creates a policy scoped to one node.

## Issue for the orchestrator (not changed: outside scope)

- **Exposure vs LED frequency.** Capture uses a 1 ms exposure (D-012). The rig default is 1000 Hz (1 ms
  period). A 1 ms exposure integrates one full LED cycle, so the band contrast is near zero (sinc(1) = 0).
  The readout time does not depend on exposure, so `FILMING_CHECKLIST.md` asks for ≤ 0.25 ms exposure, or a
  lower rig frequency with `--f-led`. Consider a calibration exposure option in Capture, or a different
  `calibration.led_frequency_hz` (for example 400 Hz: sinc(0.4) ≈ 0.76 at 1 ms). Logged here, not
  changed.

## Verification status

- Python: ruff and pytest pass (see final report of this task).
- Firmware host tests (`node/firmware/test_host`): compiled with MinGW gcc and passed on 2026-10-26
  (`ALL HOST TESTS PASSED`).
- ESP-IDF firmware (`node/firmware/main/main.c`, `calibration_rig/firmware`): **not compiled** in this
  session (no ESP-IDF toolchain on this machine). API names follow ESP-IDF v5.x documentation from memory:
  `gpio_config`, `gpio_install_isr_service`, `gpio_isr_handler_add`, `esp_timer_get_time`,
  `uart_driver_install`, `uart_param_config`, `uart_set_pin`, `uart_read_bytes`, `esp_mqtt_client_init`,
  `esp_mqtt_client_register_event`, `esp_mqtt_client_start`, `esp_mqtt_client_publish`,
  `esp_netif_sntp_init`, `esp_netif_sntp_sync_wait`, `ESP_NETIF_SNTP_DEFAULT_CONFIG`, `ledc_timer_config`,
  `ledc_channel_config`, `ledc_get_freq`, `LEDC_USE_APB_CLK`. First `idf.py build` on the human's machine
  (H2/H3) confirms them; record the result in `docs/VERIFICATION.md` V11.
- Not verified: the GPS module's PPS/RMC alignment; ESP32 interrupt jitter; MQTT/TLS to IoT Core from the
  ESP32 (V11, BLOCKED-HUMAN); the NESO CSV column names on a real downloaded file; part availability.
