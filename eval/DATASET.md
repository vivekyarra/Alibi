# GRIDPRINT real dataset (human task H5)

This document is the shot list and procedure for the real-world dataset in `SPEC.md` Part 11.2. The team records the clips. `eval/validate_dataset.py` checks the result (`make validate-dataset`).

Store video files outside git, under `data/dataset/` (the `data/` folder is ignored). Store consent forms outside the repository.

## 1. Factors and levels

| Factor | Levels | Manifest value |
|---|---|---|
| Phone | At least 3 models. At least 1 model is not used for calibration (H3). | `phone_model` (exact model string, for example from Android `Build.MODEL`) |
| App | GRIDPRINT Capture; stock camera app | `app`: `capture` or `stock` |
| Lighting | Fluorescent tube; low-cost AC LED; quality LED bulb; incandescent or halogen (if available); daylight only; DC or battery lamp | `lighting`: `fluorescent`, `led_lowcost`, `led_quality`, `incandescent`, `daylight`, `dc_lamp` |
| Motion | Tripod; handheld still; handheld walking; people moving in the scene | `motion`: `tripod`, `handheld_still`, `handheld_walking`, `people_moving` |
| Duration | 10 s, 30 s, 60 s, 120 s | `duration_s` (measured from the file) |
| Compression | Original; WhatsApp round trip; YouTube upload and download; Instagram round trip; FFmpeg presets | `compression`: `original`, `whatsapp`, `youtube`, `instagram`, `ffmpeg_<preset>` |

## 2. Counts

- **Core matrix:** phone × app × lighting × motion, all at 30 s. Record at least 5 clips per cell.
- **Duration subset:** for each phone, app `capture`, lighting `fluorescent` and `led_lowcost`, motion `tripod`: at least 5 clips each at 10 s, 60 s, and 120 s.
- **Compression subset:** choose originals from the core matrix and make round trips per section 6. Each round-trip file is a new manifest entry with the same `session_id` as its original.
- **Total originals:** at least 300 (files with `compression = original`).
- **Days:** record on at least 5 different days, at different times of day (morning, afternoon, evening, night).

## 3. Recording procedure (each session)

1. Pick one room and one lighting level. Write down the light type.
2. Make sure the phone clock is synced to network time (Settings → Date and time → automatic).
3. Start a session: give it an ID `S<YYYYMMDD>-<NN>` (for example `S20261102-01`).
4. **Stock app only:** open an NTP clock on a second screen (for example a laptop showing time.is or a terminal running `date -u +%H:%M:%S.%N` after an NTP sync). At the start of each clip, film the clock for about 2 seconds, then turn to the scene. This filmed clock is the ground truth.
5. **Capture app:** the sidecar file records the wall-clock time and its clock source. Also film the NTP clock at the start, as a cross-check.
6. Record the clip with the planned motion and duration.
7. Note any person who appears. Every person must sign the consent form (`eval/templates/consent_form.md`) before recording.
8. Copy the files to `data/dataset/<session_id>/` with the clip ID as the file name.
9. Fill one manifest entry per file (section 5).

## 4. Ground truth

| App | Ground-truth start time | Uncertainty |
|---|---|---|
| `capture` | Sidecar `wall_clock_start_utc` with its clock source. Cross-check with the filmed NTP clock. | Record the difference between sidecar time and filmed clock, plus the clock source uncertainty. |
| `stock` | File creation time from the NTP-synced phone, corrected by the filmed NTP clock at the start of the clip. | Read the filmed clock frame by frame. Record the uncertainty in seconds (`gt_uncertainty_s`). |

Write the start time as ISO 8601 UTC with a `Z` suffix (`gt_start_utc`).

Class labels (`class`):
- `authentic-with-mains-light`: unedited clip with mains-powered light in the scene.
- `authentic-without-mains-light`: unedited clip with only daylight or DC light.
- `edited`: derived by `eval/generate_edits.py` (cuts, insertions, reorders) or by hand.
- `synthetic`: AI-generated video or face composite (H7). Record the tool, prompt, license, and date.

## 5. Manifest fields

The manifest is a JSON file `data/dataset/manifest.json` with a list `clips`. The validator checks every field below. A template with two example entries is in `eval/templates/manifest_template.json`. The schema file is `eval/manifest_schema.json`.

| Field | Type | Rule |
|---|---|---|
| `clip_id` | string | Unique. Pattern `<session_id>-C<NNN>`. |
| `file` | string | Path relative to `data/dataset/`. The file must exist. |
| `sha256` | string | Lowercase hex SHA-256 of the file. Must match. |
| `phone_model` | string | Not empty. |
| `app` | string | `capture` or `stock`. |
| `lighting` | string | One of the values in section 1. |
| `motion` | string | One of the values in section 1. |
| `duration_s` | number | Greater than 0. Must agree with the file duration. |
| `compression` | string | `original`, `whatsapp`, `youtube`, `instagram`, or `ffmpeg_<preset>`. |
| `recorded_day` | string | `YYYY-MM-DD` (UTC date). |
| `session_id` | string | `S<YYYYMMDD>-<NN>`. |
| `zone` | string | A zone ID from `config/zones.yaml`. |
| `gt_start_utc` | string | ISO 8601 UTC with `Z`. |
| `gt_uncertainty_s` | number | Greater than or equal to 0. |
| `has_sidecar` | boolean | `true` only for `app = capture`; the sidecar file `<file>.sidecar.json` must exist. |
| `people_present` | boolean | `true` if any person is visible. |
| `consent_ids` | list of strings | Not empty when `people_present` is `true`. IDs refer to forms stored outside the repository. |
| `split` | string | `calibration` or `test`. The validator checks that no `session_id` appears in both splits. |
| `class` | string | `authentic-with-mains-light`, `authentic-without-mains-light`, `edited`, or `synthetic`. |

The validator also checks:
- counts per core-matrix cell (at least 5);
- total originals (at least 300);
- distinct `recorded_day` values (at least 5);
- that splits are separated by recording day and phone (SPEC Part 11.4).

## 6. Platform round trips (human task H6)

Use originals that are already in the manifest. Do each step on a phone or account used only for this project.

**File naming:** `<clip_id>__<platform>.mp4`, where `<platform>` is `whatsapp`, `youtube`, or `instagram`. Example: `S20261102-01-C004__whatsapp.mp4`. Put the file in the same session folder as its original.

### WhatsApp
1. Send the original video to a second team phone in a one-to-one chat. Send it as a normal video (not as a document).
2. On the second phone, save the received video.
3. Copy it to `data/dataset/<session_id>/<clip_id>__whatsapp.mp4`.

### YouTube
1. Upload the original as an unlisted video on the project account.
2. Wait until processing is complete.
3. Download the processed video with YouTube Studio (Content → video → Download).
4. Save as `<clip_id>__youtube.mp4`. Delete the unlisted upload after the download.

### Instagram
1. Post the original as a Reel or story on a private project account.
2. Download it with the app's own save function. If you must use another method (for example a screen recording), write the method in the session log.
3. Save as `<clip_id>__instagram.mp4`. Delete the post after the download.

### FFmpeg presets
Run `eval/generate_edits.py` compression presets, or use FFmpeg directly. Name the output `<clip_id>__ffmpeg_<preset>.mp4` and set `compression` to `ffmpeg_<preset>`.

For each round-trip file, add a manifest entry: same `session_id`, `gt_start_utc`, `phone_model`, `app`, `lighting`, `motion`, `class`, and `split` as the original; new `clip_id` (`<clip_id>__<platform>`), `file`, `sha256`, `duration_s`, `compression`; `has_sidecar` = `false`.

## 7. Templates and related files

- Manifest template: `eval/templates/manifest_template.json`
- Consent form template: `eval/templates/consent_form.md`
- Face-composite procedure (H7): `eval/FACE_COMPOSITES.md`
- Validator: `eval/validate_dataset.py` (`make validate-dataset`)
- Edit generator: `eval/generate_edits.py`
