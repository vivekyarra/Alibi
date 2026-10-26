package dev.gridprint.capture

/**
 * Content of `gridprint_capability.json`, written by the Device check screen (SPEC Part 4 V7).
 * `capture-android/validate_capability.py` reads this format. Keep both in step.
 *
 * Integer constant values used below are the documented values of the Android constants:
 * CONTROL_AE_MODE_OFF = 0, CONTROL_AE_ANTIBANDING_MODE_OFF = 0,
 * SENSOR_INFO_TIMESTAMP_SOURCE_UNKNOWN = 0, SENSOR_INFO_TIMESTAMP_SOURCE_REALTIME = 1,
 * REQUEST_AVAILABLE_CAPABILITIES_MANUAL_SENSOR = 1. The Android code reads them from the
 * android.hardware.camera2 constants; the values are repeated here only for the JVM tests.
 */
data class CapabilityReport(
    val appVersion: String,
    val deviceModel: String,
    val androidSdkInt: Int,
    val cameraId: String,
    val hardwareLevel: String,
    val sensorOrientation: Int,
    val checkedAtUtc: String,
    val availableAeModes: List<Int>,
    val availableAntibandingModes: List<Int>,
    val manualSensorCapability: Boolean,
    val exposureRangeNs: List<Long>?,
    val sensitivityRange: List<Int>?,
    val requestedExposureNs: Long,
    val availableFpsRanges: List<List<Int>>,
    val skewListedInResultKeys: Boolean,
    val timestampSource: Int?,
    val probe: ProbeResult?,
) {
    data class ProbeResult(
        val framesReceived: Int,
        val skewObservedNs: Long?,
        val exposureMedianNs: Long?,
        val frameDurationMedianNs: Long?,
        val isoMedian: Int?,
        val error: String?,
    )

    val aeModeOff: Boolean get() = AE_MODE_OFF in availableAeModes
    val antibandingOff: Boolean get() = ANTIBANDING_OFF in availableAntibandingModes
    val manualExposure: Boolean
        get() = manualSensorCapability && exposureRangeNs != null &&
            requestedExposureNs >= exposureRangeNs[0] && requestedExposureNs <= exposureRangeNs[1]
    val fixed30Fps: Boolean get() = availableFpsRanges.any { it.size == 2 && it[0] <= CaptureConfig.FPS && it[1] >= CaptureConfig.FPS }
    val rollingShutterSkew: Boolean get() = skewListedInResultKeys && (probe?.skewObservedNs ?: 0L) > 0L
    val timestampRealtime: Boolean get() = timestampSource == TIMESTAMP_SOURCE_REALTIME

    fun toJson(): String = Json.encode(toMap())

    fun toMap(): Map<String, Any?> = linkedMapOf(
        "schema" to SCHEMA,
        "app_version" to appVersion,
        "device_model" to deviceModel,
        "android_sdk_int" to androidSdkInt,
        "camera_id" to cameraId,
        "hardware_level" to hardwareLevel,
        "sensor_orientation" to sensorOrientation,
        "checked_at_utc" to checkedAtUtc,
        "capabilities" to linkedMapOf(
            "ae_mode_off" to linkedMapOf(
                "supported" to aeModeOff,
                "available_ae_modes" to availableAeModes,
            ),
            "antibanding_off" to linkedMapOf(
                "supported" to antibandingOff,
                "available_antibanding_modes" to availableAntibandingModes,
            ),
            "manual_exposure" to linkedMapOf(
                "supported" to manualExposure,
                "manual_sensor_capability" to manualSensorCapability,
                "exposure_range_ns" to exposureRangeNs,
                "sensitivity_range" to sensitivityRange,
                "requested_exposure_ns" to requestedExposureNs,
            ),
            "fixed_30fps" to linkedMapOf(
                "supported" to fixed30Fps,
                "available_fps_ranges" to availableFpsRanges,
            ),
            "rolling_shutter_skew" to linkedMapOf(
                "supported" to rollingShutterSkew,
                "listed_in_result_keys" to skewListedInResultKeys,
                "observed_ns" to probe?.skewObservedNs,
            ),
            "timestamp_source_realtime" to linkedMapOf(
                "supported" to timestampRealtime,
                "value" to timestampSource,
                "name" to timestampSourceName(timestampSource),
            ),
        ),
        "probe" to probe?.let {
            linkedMapOf(
                "frames_received" to it.framesReceived,
                "exposure_median_ns" to it.exposureMedianNs,
                "frame_duration_median_ns" to it.frameDurationMedianNs,
                "iso_median" to it.isoMedian,
                "error" to it.error,
            )
        },
    )

    companion object {
        const val SCHEMA = "gridprint_capability/1"
        const val AE_MODE_OFF = 0
        const val ANTIBANDING_OFF = 0
        const val TIMESTAMP_SOURCE_REALTIME = 1

        fun timestampSourceName(v: Int?): String? = when (v) {
            null -> null
            0 -> "UNKNOWN"
            1 -> "REALTIME"
            else -> "OTHER_$v"
        }
    }
}
