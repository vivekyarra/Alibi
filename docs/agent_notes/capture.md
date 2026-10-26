# Agent notes: GRIDPRINT Capture (capture-android/)

Scope: `capture-android/` only. Proposals for shared files (DECISIONS.md, IDEAS.md, VERIFICATION.md)
are listed at the end for the lead agent to merge.

## Decisions

| Date | Decision | Reason | Alternatives considered |
|---|---|---|---|
| 2026-10-26 | Platform SDK only, no AndroidX; UI built in Kotlin code (no XML layouts). | Fewest dependencies; all sources type-check with `kotlinc` against `android.jar` without a Gradle build (no network here). | AndroidX CameraX (hides Camera2 manual controls); Jetpack Compose (large dependency set). |
| 2026-10-26 | Record with MediaCodec (H.264, Surface input) + MediaMuxer, not MediaRecorder. | MediaCodec gives `BufferInfo.presentationTimeUs` for every encoded frame, which is needed to match frames to capture results 1:1. MediaRecorder gives no per-frame output. | MediaRecorder (no per-frame data); HEVC (less universal decode support; H.264 is enough at 40 Mbps). |
| 2026-10-26 | Frame alignment: encoded frame ↔ capture result where `presentationTimeUs == SENSOR_TIMESTAMP / 1000` (±1 µs). | Android reference for `CaptureResult.SENSOR_TIMESTAMP` states the timestamp is also included in all image buffers of the same capture; MediaCodec Surface input converts the buffer timestamp (ns) to `presentationTimeUs` (µs). | Frame-number counting (breaks silently when the encoder drops a frame). |
| 2026-10-26 | Dropped frames are never silent: sidecar entries = encoded frames only (1:1 with the MP4); every capture result without an encoded frame is listed in `<name>.capture_log.json` (before start / dropped inside / after end), with `onCaptureBufferLost` and `onCaptureFailed` frame numbers. The status line shows the drop count. | Sidecar schema forbids extra fields, so the drop record lives in a separate file. Gaps stay visible in the sensor timestamps, so the engine sees them (S1 gap detection). | Adding fields to the sidecar (schema forbids); padding with fake entries (fabrication). |
| 2026-10-26 | No sidecar is written when any encoded frame lacks a capture result, or when exposure / frame duration / ISO is missing for a frame, or when `SENSOR_ROLLING_SHUTTER_SKEW` is never reported. The reason is shown and stored in the capture log. | The schema needs integers; filling a missing value would be a guess. The engine still works without a sidecar (readout from profile / estimate). | Write 0 or a typical value (fabrication). |
| 2026-10-26 | `rolling_shutter_skew_ns` = lower median of per-frame skew values; min/max/missing count in the capture log. | Schema has one value; skew is constant in fixed-exposure mode on normal devices. | First frame value (sensitive to one bad frame). |
| 2026-10-26 | Wall clock: `SystemClock.currentNetworkTimeClock()` (API 33+) when it has network time, else `System.currentTimeMillis()`; sampled between two `elapsedRealtimeNanos()` reads. If `SENSOR_INFO_TIMESTAMP_SOURCE` = REALTIME: `sensor_timestamp_wall_offset_ns = wall_ns − elapsedRealtime_ns`, `wall_clock_start_utc` = first frame time, source `"<clock>:first_frame"`. Else offset `null`, start = Record press, source `"<clock>:record_start"`. | REALTIME means sensor timestamps share the `elapsedRealtimeNanos` time base (Android reference). | GPS time (forbidden: no location access); NTP client in the app (more code, network). |
| 2026-10-26 | ISO compensation: meter with AE on (until `CONTROL_AE_STATE_CONVERGED` and ≥10 frames, max 45 frames), then ISO = autoISO × autoExposure / 1 ms, clamped to `SENSOR_INFO_SENSITIVITY_RANGE`. "Measure light" button repeats it. | Keeps the image brightness of the AE state with the 1 ms exposure (CaptureConfig.EXPOSURE_NS = config/default.yaml `capture.exposure_ns`, D-012). | Fixed ISO (too dark or too bright in many rooms). |
| 2026-10-26 | `CONTROL_VIDEO_STABILIZATION_MODE_OFF` when available. | Electronic stabilization warps and shifts rows, so coded rows would no longer be sensor rows. | Leave default (some phones enable EIS in TEMPLATE_RECORD). |
| 2026-10-26 | Orientation: `MediaMuxer.setOrientationHint((sensorOrientation + deviceRotation) mod 360)`; pixels never rotated; video size chosen from `getOutputSizes(MediaCodec::class.java)` (1920x1080 preferred, min frame duration ≤ 1/30 s). | SPEC 8.2 step 6 needs coded rows = sensor rows. | Rotating in a GL pass (would mix rows). |
| 2026-10-26 | No B-frames (`KEY_MAX_B_FRAMES = 0`, API 29 → minSdk 29); key frame every 1 s; no audio track. | Decode order = presentation order; simpler alignment. No audio collected (privacy). | Allow B-frames and sort by PTS (the aligner still sorts by PTS as a guard). |
| 2026-10-26 | Band meter: 8-bit Y of a small YUV_420_888 ImageReader stream → sRGB-inverse LUT (approximate linear light) → row means (every 4th column) → d = rowMean − exponential running mean (α = 0.1) → score = std(d) / mean(rowMean); bar is log scale 1e-4…1e-1; 10 warm-up frames. | Implements the specified "variance of the row-mean difference vs a running mean". UI guidance only, never a verdict. | Spatial Goertzel at the expected band frequency (needs readout time; scene content leaks in). |
| 2026-10-26 | Streams: preview TextureView + meter ImageReader (+ encoder Surface while recording). If the 3-stream session fails, record with preview + encoder and pause the meter (logged as `meter_stream_disabled_during_recording`). | Three-stream combinations are not supported on every hardware level. | Meter from `TextureView.getBitmap()` (display-rotated, slow). |
| 2026-10-26 | Recording is blocked unless AE OFF, anti-banding OFF and MANUAL_SENSOR are all available. | These are the core of the method (V7); without them the bands are hidden. | Record anyway with AE (bands suppressed). |
| 2026-10-26 | Device check reads `CameraCharacteristics` and 30 results from the running manual preview; writes `gridprint_capability.json` (schema `gridprint_capability/1`) to the app external files dir; "Save report to phone" copies it to `Download/GRIDPRINT`. Required: ae_mode_off, antibanding_off, manual_exposure (1 ms in range + MANUAL_SENSOR), fixed_30fps. Optional (fallback exists): rolling_shutter_skew, timestamp_source_realtime. | V7 lists the five capabilities; SPEC V7 fallback (calibration rig readout) covers skew; REALTIME only affects the start-time offset. | All five required (would reject phones that the calibration-rig path can serve). |
| 2026-10-26 | `validate_capability.py` recomputes every `supported` flag from the raw values and fails on a mismatch. | Do not trust a flag without its evidence. | Check flags only. |
| 2026-10-26 | Upload: `POST {api}/v1/jobs` with body `{}`; `PUT upload_url` with `Content-Type: video/mp4`; `POST {api}/v1/jobs/{id}/start` with `{"claim":{"claimed_zone":zone},"sidecar":{...}}` (sidecar omitted if not written). HTTPS only, except cleartext for localhost, 127.0.0.1, 10.0.2.2 (network security config) for `make local`. | Matches the contract given for this component. | — |
| 2026-10-26 | Local save: byte-exact copy through MediaStore (video → `Movies/GRIDPRINT`, sidecar + capture log → `Download/GRIDPRINT`). No storage permission needed on API 29+. | Copy keeps the SHA-256 valid. | Legacy external storage (needs permission). |
| 2026-10-26 | Gradle wrapper files generated offline with the locally cached Gradle 9.8.0 (`gradle wrapper --gradle-version 8.14.3`); versions: AGP 8.9.1, Kotlin 2.1.0, JUnit 4.13.2, compileSdk/targetSdk 35. | AGP 8.9.1 is in the local Gradle cache; Gradle 8.14.3 is within AGP 8.9's supported range. | — |

## Verification done here (2026-10-26)

- All 14 Kotlin sources type-check with the Kotlin compiler bundled in Android Studio
  (`kotlinc` 2.3.10, via `K2JVMCompiler`) against `platforms/android-35/android.jar`: no errors.
  This checks every Android API name used (camera2, media, MediaStore, SystemClock).
- Kotlin JVM unit tests (`SidecarWriterTest`, `BandMeterTest`) compiled with the same compiler and
  run with JUnit 4.13.2: `OK (21 tests)`.
- A sidecar produced by the Kotlin `SidecarBuilder` (synthetic inputs) validates against the real
  pydantic `CaptureSidecar` (`model_validate_json` OK). Stored as
  `capture-android/tests/fixtures/sidecar_from_kotlin.json`.
- `pytest capture-android/tests -q`: `11 passed`.

## Not verified

- No Gradle build was run (the Kotlin Gradle plugin and the Gradle 8.14.3 distribution are not in
  the local cache; network is too slow). APK not produced. → H4.
- Nothing ran on a phone: three-stream session support, real SENSOR_ROLLING_SHUTTER_SKEW values,
  the encoder-timestamp = sensor-timestamp behavior on each device, ISO compensation, the meter on
  real bands. → H4 checklist in `capture-android/BUILD.md`.
- The API request body for `POST /v1/jobs` (`{}`) and the PUT content type depend on `api/`, which
  did not exist when this was written.

## Open issues for the lead agent

1. Band meter at 60 Hz grids: at exactly 30 fps, 120 Hz flicker aliases to ~0 Hz, so the bands
   stand still and the running-mean difference reads low. The UI states this. Candidate for
   `docs/IDEAS.md` (not built): a spatial band estimator that uses the readout time.
2. Suggested `docs/DECISIONS.md` entries: the alignment rule, "no sidecar instead of a guessed
   value", and the capture log file `<name>.capture_log.json`.
3. Suggested `docs/VERIFICATION.md` V7 note: method = Device check + `validate_capability.py`;
   status stays BLOCKED-HUMAN until H4 files arrive.
