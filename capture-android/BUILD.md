# GRIDPRINT Capture: build, install, device check (human task H4)

GRIDPRINT Capture is the Android app that records video with settings that keep the light bands
from mains-powered lights (SPEC 10.3). This file tells you how to build it, install it on each
test phone, and check each phone.

## 1. What you need

| Item | Version |
|---|---|
| JDK | 17 or 21 (tested path: `C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot`) |
| Android SDK | Platform `android-35`, Build-Tools 35.x, Platform-Tools (`adb`) |
| Gradle | Wrapper included (`gradlew`, `gradlew.bat`) → downloads Gradle 8.14.3 on first run |
| Android Gradle Plugin | 8.9.1 (`gradle/libs.versions.toml`) |
| Kotlin | 2.1.0 (`gradle/libs.versions.toml`) |
| Phone | Android 10 (API 29) or newer, with a back camera |
| Network | First build downloads Gradle, AGP, Kotlin and JUnit (several hundred MB) |

The app has no AndroidX or other runtime dependencies. It uses only the platform SDK.

## 2. Build

1. Open a terminal in `capture-android/`.
2. Tell Gradle where the SDK is. Create `capture-android/local.properties` (not committed):
   ```
   sdk.dir=C\:\\Users\\<you>\\AppData\\Local\\Android\\Sdk
   ```
   (Or set the environment variable `ANDROID_HOME` to the SDK folder.)
3. Set `JAVA_HOME` to the JDK folder.
4. Run the unit tests and build the debug APK:
   - Windows: `gradlew.bat testDebugUnitTest assembleDebug`
   - macOS/Linux: `./gradlew testDebugUnitTest assembleDebug`
5. Expected result: `BUILD SUCCESSFUL`, and the file
   `capture-android/app/build/outputs/apk/debug/app-debug.apk`.
6. Unit test report: `capture-android/app/build/reports/tests/testDebugUnitTest/index.html`
   (tests: `SidecarWriterTest`, `BandMeterTest`).

Android Studio also works: File → Open → select `capture-android/`, wait for sync, then Run.

## 3. Install on a phone

1. On the phone: Settings → About phone → tap "Build number" 7 times → Developer options →
   turn on "USB debugging".
2. Connect the phone with USB. Accept the "Allow USB debugging" prompt on the phone.
3. `adb devices` → the phone is listed as `device`.
4. `adb install -r capture-android/app/build/outputs/apk/debug/app-debug.apk`
5. Open "GRIDPRINT Capture" on the phone. Read the notice. Press "I agree". Allow the camera.

## 4. Device check (one time per phone)

1. Go to a room lit by mains-powered lights (LED or fluorescent ceiling lights are best).
2. Point the camera at a plain, lit wall. Wait until the status line says "Ready".
3. Press "Device check". Wait about 2 seconds. The screen lists PASS / FAIL for each item.
4. Press "Save report to phone". The file goes to `Download/GRIDPRINT/gridprint_capability.json`.
   It is also in the app folder.
5. Copy the file to the computer. Rename it with the phone model, for example
   `pixel8_gridprint_capability.json`:
   ```
   adb pull /sdcard/Android/data/dev.gridprint.capture/files/gridprint_capability.json pixel8_gridprint_capability.json
   ```
   (If that path is blocked on your phone, use `adb pull /sdcard/Download/GRIDPRINT/gridprint_capability.json`.)
6. Validate it:
   ```
   .venv/Scripts/python capture-android/validate_capability.py pixel8_gridprint_capability.json
   ```
   Exit code 0 means every required item is present. Exit code 1 means a required item is missing.
7. Keep one file per phone (send them to the team) and record the result in
   `docs/VERIFICATION.md` under V7 (date, phone, PASS/FAIL per item).

| Item | Required | If it fails |
|---|---|---|
| `ae_mode_off` (CONTROL_AE_MODE_OFF) | yes | The phone cannot record for GRIDPRINT. The Record button stays off. |
| `antibanding_off` (CONTROL_AE_ANTIBANDING_MODE_OFF) | yes | Same as above. |
| `manual_exposure` (MANUAL_SENSOR, 1 ms in SENSOR_INFO_EXPOSURE_TIME_RANGE) | yes | Same as above. |
| `fixed_30fps` (30 in CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES) | yes | Same as above. |
| `rolling_shutter_skew` (SENSOR_ROLLING_SHUTTER_SKEW reported) | no | The app writes no sidecar. Film calibration clips (H3) for the readout profile. |
| `timestamp_source_realtime` (SENSOR_INFO_TIMESTAMP_SOURCE = REALTIME) | no | The sidecar start time is the time of the Record press; `sensor_timestamp_wall_offset_ns` is null. |

## 5. Test recording checklist (per phone)

Do each step. Write the result in `docs/VERIFICATION.md` (V7) or the H4 section of `docs/HUMAN_TASKS.md`.

- [ ] Device check done, file validated (section 4).
- [ ] In settings of the phone, the date and time are set automatically from the network.
- [ ] Choose the grid zone (IN, CE, GB or US-EI). The Record button stays off until you choose one.
- [ ] In a room with mains lights, the band-strength bar moves above zero when you hold still.
      (50 Hz zones. In 60 Hz zones the bands can stand still at 30 fps and the bar can stay low.)
- [ ] Record 20 seconds while you hold the phone still. Press Stop.
- [ ] The status line says "Sidecar written". If it says "No sidecar", copy the reason here.
- [ ] If the status line says the encoder dropped frames, note the number.
- [ ] Press "Save to phone". Pull the three files:
      `adb pull /sdcard/Movies/GRIDPRINT/` and `adb pull /sdcard/Download/GRIDPRINT/`
- [ ] Check the hash: `certutil -hashfile <video>.mp4 SHA256` (Windows) or `sha256sum <video>.mp4`.
      It must equal `video_sha256` in `<video>.sidecar.json`.
- [ ] Check the sidecar against the engine schema:
      ```
      .venv/Scripts/python -c "import sys; sys.path.insert(0,'engine'); from gridprint_engine.schemas import CaptureSidecar; s=CaptureSidecar.model_validate_json(open(sys.argv[1]).read()); print(len(s.frame_sensor_timestamps_ns), 'frames OK')" <video>.sidecar.json
      ```
- [ ] Check frame count: `ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 <video>.mp4`
      must equal the number of entries in `frame_sensor_timestamps_ns`.
- [ ] Check that pixels are not rotated: `ffprobe -v error -show_streams <video>.mp4` shows a
      landscape `width` > `height` (sensor rows) and a rotation side-data / `rotate` tag.
- [ ] Optional: upload. Enter the API address (for `make local` on a USB phone:
      `adb reverse tcp:8000 tcp:8000`, then `http://localhost:8000`). Press Upload. Note the job id.

## 6. Notes for the person building

- Camera2 settings in use: `CONTROL_AE_MODE_OFF`, `CONTROL_AE_ANTIBANDING_MODE_OFF`,
  `SENSOR_EXPOSURE_TIME` = 1 000 000 ns, `SENSOR_SENSITIVITY` raised from the metered auto value,
  `SENSOR_FRAME_DURATION` = 33 333 333 ns, `CONTROL_AE_TARGET_FPS_RANGE` = [30, 30],
  `CONTROL_VIDEO_STABILIZATION_MODE_OFF`.
- Video: H.264, 40 Mbps, 1920x1080 when the camera offers it at 30 fps, no B-frames, no audio.
- The app never asks for location permission.
- Release signing is not set up. A debug APK is enough for H4.
