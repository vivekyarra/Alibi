# GRIDPRINT Node — Self-test

Human task H2, step 7. Run every step after assembly (`hardware/ASSEMBLY.md`) and flashing
(`firmware/FLASHING.md`). Write the results (pass/fail, date, Node id) in `docs/HUMAN_TASKS.md` under
H2. Read `hardware/SAFETY.md` first. Do not open the enclosure while the adapter is in the wall.

| Step | Check | Pass when |
|---|---|---|
| 1 | Host unit tests: `firmware/FLASHING.md` section 5 | `ALL HOST TESTS PASSED` |
| 2 | Bias and supply voltages: `hardware/ASSEMBLY.md` section 6 | All values in range |
| 3 | Zero crossings. Serial monitor, adapter plugged in, GPS unplugged, SNTP fallback on | Log lines with `q=ntp` and `periods=` 48–51 (50 Hz) or 58–61 (60 Hz), `rejected=` 0–2 |
| 4 | GPS lock. Put the Node near a window. Wait up to 15 min | Log lines with `q=gps` |
| 5 | Plausible frequency | `f=` within 0.5 Hz of nominal, and it changes slowly from second to second |
| 6 | UTC label check (see below) | `P − T` is 1 or 2 in 10 of 10 readings |
| 7 | MQTT. AWS IoT console → MQTT test client → subscribe to `gridprint/#` | One message per second with your zone and node id |
| 8 | Ingest. After 10 min: `make node-quality ZONE=<zone> HOURS=0.15` | Coverage close to 100 %, GPS lock close to 100 % |
| 9 | Offline back-fill. Switch off the Wi-Fi router for 5 min, then switch it on | Log shows `queued=` rising, then falling to 0. Step 8 for the last 0.5 h shows no gap |
| 10 | GPS loss. Disconnect the GPS antenna (or cover it with a metal box) for 2 min | Log shows `q=ntp`; data-quality report shows GPS lock below 100 % for that window |
| 11 | 24 h run: `make node-quality ZONE=<zone> HOURS=24` | `PASS` (coverage ≥ 99 %, GPS lock ≥ 99 %) |

## Step 6 — UTC label check

The firmware labels each PPS edge with the time from the RMC sentence that follows it. Most GPS modules
send the RMC for second S just after the PPS edge that starts second S. This step checks that.

1. Sync the PC clock to internet time (Windows: Settings → Time → Sync now; Linux: `timedatectl`
   shows "System clock synchronized: yes").
2. In the serial monitor, note a log line `t=<T> ... q=gps`. At the same moment run
   `python -c "import time; print(int(time.time()))"` on the PC and note the value `P`.
3. The firmware prints second T about 0.05 s after second T ends, so expect `P − T = 1`.
   Serial and terminal delays can add a little, so `P − T = 2` sometimes is normal.
4. Repeat 10 times.
5. If `P − T` is always 0 (or less), set `GRIDPRINT_NMEA_PPS_OFFSET_S` to −1. If it is always 3 or more,
   set it to +1. Rebuild, flash, and repeat this step.

## Timing quality: gps and ntp

- `gps`: each second is framed by the GPS PPS edges. The local timer rate is corrected every second
  from the PPS interval.
- `ntp` (fallback, SPEC V11): each second is framed by SNTP time and the local timer rate is not
  corrected. Two effects make it less exact:
  - SNTP time over the internet can be off by many milliseconds, so second boundaries move.
  - The ESP32 crystal error becomes a frequency bias. For example, a crystal that is 20 ppm fast makes
    a 50 Hz reading 0.001 Hz low (50 Hz × 20 × 10⁻⁶).
- The reference matching uses all readings. The data-quality report counts `ntp` seconds as "no GPS
  lock", so a Node that is often in `ntp` mode fails step 11.

## Known limits (not yet measured)

- The interrupt latency jitter of the ESP32 GPIO interrupt has not been measured on this hardware. The
  host test with simulated ±3 µs jitter passes with a tolerance of 0.002 Hz; that is a test bound, not a
  measurement. Measure it when hardware is available (two Nodes on one socket should agree closely).
- The offline buffer is in RAM. A power cut loses the buffered seconds.
