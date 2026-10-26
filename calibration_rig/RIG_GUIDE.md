# GRIDPRINT calibration rig — Guide

Human task H3. The rig measures the rolling-shutter **readout time** of each phone camera mode
(SPEC 10.5). The engine uses it when a video has no sidecar (`READOUT_FROM_PROFILE`, SPEC 8.4).

## 1. How it works

1. An ESP32 blinks a group of white LEDs at an exact frequency `f_led` (default 200 Hz, from
   `calibration.led_frequency_hz` in `config/default.yaml`). The ESP32 timer runs from its crystal.
2. The LEDs light a matte white card. Room lights on mains power are **off**.
3. The phone films the card. The rolling shutter reads one row after another, so the card shows
   horizontal bands. One band cycle covers `P` rows.
4. `fit_readout.py` measures `P` in every frame. Row time = 1 / (`f_led` × `P`). Readout time
   `T_ro` = row time × (`N` − 1), where `N` is the number of rows in the coded video frame.
5. The script writes `T_ro` and its uncertainty to `config/camera_profiles.yaml`.

Bands per frame ≈ `f_led` × `T_ro`. With 200 Hz and a readout of 10–30 ms you get 2–6 bands.

## 2. Parts

| Qty | Part | Specification |
|---|---|---|
| 1 | ESP32 development board | Espressif ESP32-DevKitC V4 (same type as the Node) |
| 1 | NPN transistor | PN2222A (TO-92) |
| 4 | White LEDs | 5 mm, high brightness, about 3.0 V forward voltage at 20 mA |
| 4 | Resistors | 100 Ω, 0.25 W (one per LED) |
| 1 | Resistor | 1 kΩ, 0.25 W (transistor base) |
| 1 | Matte white card | A4 or larger, no gloss |
| 1 | Certified USB power supply | 5 V, 1 A or more |
| 1 | Phone tripod or clamp | — |
| 1 | Breadboard and wires | — |
| Optional | Frequency counter or oscilloscope | To check the LED frequency (step 5) |

The rig uses only the 5 V USB supply. It has no mains connection.

## 3. Circuit

```
   ESP32 GPIO 18 ---- 1k ---- B  PN2222A
                              E ---- GND
                              C ----+------+------+------+
                                    |      |      |      |
                                   LED    LED    LED    LED   (cathode to C)
                                    |      |      |      |
                                  100R   100R   100R   100R
                                    |      |      |      |
   ESP32 5V ------------------------+------+------+------+
```

Current per LED ≈ (5 V − 3.0 V − 0.2 V) / 100 Ω ≈ 18 mA. Total ≈ 72 mA.

## 4. Flash the firmware

```bash
cd calibration_rig/firmware
idf.py set-target esp32
idf.py menuconfig      # "GRIDPRINT calibration rig": LED frequency (default 200), GPIO (default 18)
idf.py build
idf.py -p <PORT> flash monitor
```

The LED frequency in menuconfig must equal `calibration.led_frequency_hz` in `config/default.yaml`.
If you change one, change the other, or pass `--f-led` to `fit_readout.py`.

The log prints the frequency that the LEDC driver reports, every 5 s.

## 5. Check the LED frequency (recommended)

Measure the transistor collector with a frequency counter or an oscilloscope. Write the value in
`docs/HUMAN_TASKS.md` (H3). It should read the configured frequency within the instrument's accuracy.
If it does not, stop and report it.

## 6. Set up

1. Dark room, or daylight only. Switch off all mains-powered lights in the room (they make their own
   100 Hz or 120 Hz bands).
2. Put the card 20–40 cm from the LEDs. Light it evenly.
3. Put the phone on the tripod. The card must fill the whole frame. Keep the phone still.
4. Film per `FILMING_CHECKLIST.md`.

## 7. Process

```bash
make calibrate
```

This runs `python calibration_rig/fit_readout.py --all data/calibration`. Clips must be at
`data/calibration/<device>/<W>x<H>_<fps>.mp4`. `<device>` must be the exact device model string that the
Capture sidecar reports (`device_model`), because the engine looks up profiles with it.

Single clip:

```bash
python calibration_rig/fit_readout.py data/calibration/Pixel_7/1920x1080_30.mp4 --device "Pixel 7"
```

Optional: put the Capture sidecar JSON next to the clip with the same name (`1920x1080_30.json`). The
script then records `sidecar_rolling_shutter_skew_s` and `sidecar_diff_s` (fitted readout minus the
Android `SENSOR_ROLLING_SHUTTER_SKEW` value).

Outputs:
- `config/camera_profiles.yaml`: key `"<device>|<W>x<H>|<fps>"` with `readout_s`, `uncertainty_s`,
  `n_frames`, `f_led_hz`, `source_clip_sha256`, `date`, and diagnostic fields.
- `results/calibration/<device>/<W>x<H>_<fps>.json`: the full fit result (source for any reported number).

`W` and `H` are the coded frame size. Phones often store portrait video as landscape frames with a
rotation tag; the engine and this script both use the coded size and coded row order.

## 8. Limits

- The bands must be clear. Frames with weak bands are skipped; a clip needs at least 10 good frames.
- A fitted readout longer than the frame period is rejected (it means the band count is wrong).
- The fit assumes rows are read at a constant rate. This is the same model the engine uses (SPEC 8.4).
