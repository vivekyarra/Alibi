package dev.gridprint.capture

/**
 * Capture settings. These values mirror `config/default.yaml` -> `capture:` in the repository
 * (exposure_ns, fps, bitrate_bps). `capture-android/tests/test_validate_capability.py` checks that
 * they stay equal. Exposure choice: docs/DECISIONS.md D-012.
 */
object CaptureConfig {
    /** Manual exposure: 1 ms. One flicker period is 10 ms (100 Hz) or 8.33 ms (120 Hz). */
    const val EXPOSURE_NS: Long = 1_000_000L

    /** Fixed frame rate. */
    const val FPS: Int = 30

    /** Frame duration for FPS, in ns (1e9 / 30, truncated). */
    const val FRAME_DURATION_NS: Long = 1_000_000_000L / FPS

    /** Video bit rate, bits per second. */
    const val BITRATE_BPS: Int = 40_000_000

    /** Key frame interval, seconds. */
    const val I_FRAME_INTERVAL_S: Int = 1

    /** Grid zones the user can select (config/zones.yaml, without the simulator zones). */
    val ZONES: List<String> = listOf("IN", "CE", "GB", "US-EI")

    /** Nominal grid frequency per zone, Hz (config/zones.yaml). Used only for UI hints. */
    val ZONE_NOMINAL_HZ: Map<String, Int> = mapOf("IN" to 50, "CE" to 50, "GB" to 50, "US-EI" to 60)

    /** File name written by the Device check screen. */
    const val CAPABILITY_FILE = "gridprint_capability.json"
}
