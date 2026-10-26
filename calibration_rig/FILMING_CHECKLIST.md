# GRIDPRINT calibration rig — Filming checklist

Human task H3. Use one checklist per phone. Set up the rig first (`RIG_GUIDE.md`).

## Before you film

- [ ] Mains-powered room lights are off.
- [ ] The rig log shows the configured LED frequency.
- [ ] The phone is on a tripod. The white card fills the whole frame.
- [ ] Note the exact device model string (Android: `Build.MODEL`, as shown in a Capture sidecar).

## Exposure (important)

The LED blinks at 200 Hz (DECISIONS D-017), so one cycle is 5 ms. The Capture exposure of 1 ms keeps
about 94 % of the band contrast (sinc(0.2) ≈ 0.94). A shorter exposure is also fine.

- If the phone cannot set the exposure, use bright LEDs so the phone picks a short exposure itself.
- An exposure of 5 ms or longer averages a whole LED cycle and the bands disappear.
- If you change the rig frequency in menuconfig, run `fit_readout.py --f-led <Hz>` with the same value and
  record it in `docs/HUMAN_TASKS.md`.

Exposure does not change the readout time. Resolution, frame rate and sensor mode can change it, so
film every mode that you use in the dataset.

## For each mode (resolution × frame rate)

- [ ] Set the mode, for example 1920×1080 at 30 fps. Use the same app and settings as for the dataset
      (GRIDPRINT Capture if possible).
- [ ] Turn off video stabilisation if the app allows it.
- [ ] Lock focus and exposure on the card.
- [ ] Film 10 s. Do not touch the phone during the clip.
- [ ] Check on the phone screen: horizontal bands are visible (in landscape frames).
- [ ] Copy the file to `data/calibration/<device>/<W>x<H>_<fps>.mp4` (for example
      `data/calibration/Pixel 7/1920x1080_30.mp4`). Keep the original file; do not re-encode it.
- [ ] If GRIDPRINT Capture wrote a sidecar, copy it to `data/calibration/<device>/<W>x<H>_<fps>.json`.

## After filming

- [ ] Run `make calibrate`.
- [ ] Check the printed JSON line for each clip: `n_frames` is 10 or more and `warnings` is empty.
- [ ] Check that `uncertainty_s` is small compared to `readout_s`. If not, film the mode again with a
      shorter exposure or brighter LEDs.
- [ ] Write the device, modes and date in `docs/HUMAN_TASKS.md` (H3).
