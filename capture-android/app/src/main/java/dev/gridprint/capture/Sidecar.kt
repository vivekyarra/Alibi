package dev.gridprint.capture

/**
 * Capture sidecar. Field names and types match `engine/gridprint_engine/schemas.py::CaptureSidecar`
 * (pydantic, extra fields forbidden). There is no location field (R4); `zone` is the grid zone
 * the user selected.
 */
data class CaptureSidecar(
    val appVersion: String,
    val deviceModel: String,
    val sensorOrientation: Int,
    val frameSensorTimestampsNs: List<Long>,
    val frameExposureNs: List<Long>,
    val frameDurationNs: List<Long>,
    val rollingShutterSkewNs: Long,
    val iso: List<Int>,
    val wallClockStartUtc: String,
    val wallClockSource: String,
    val sensorTimestampWallOffsetNs: Long?,
    val zone: String,
    val videoSha256: String,
) {
    /** Problems that make this sidecar invalid. Empty list means valid. */
    fun validate(): List<String> {
        val errors = ArrayList<String>()
        val n = frameSensorTimestampsNs.size
        if (n == 0) errors.add("no frames")
        if (frameExposureNs.size != n) errors.add("frame_exposure_ns length ${frameExposureNs.size} != $n")
        if (frameDurationNs.size != n) errors.add("frame_duration_ns length ${frameDurationNs.size} != $n")
        if (iso.size != n) errors.add("iso length ${iso.size} != $n")
        for (i in 1 until n) {
            if (frameSensorTimestampsNs[i] <= frameSensorTimestampsNs[i - 1]) {
                errors.add("frame_sensor_timestamps_ns not strictly increasing at index $i")
                break
            }
        }
        if (frameExposureNs.any { it <= 0 }) errors.add("frame_exposure_ns has a value <= 0")
        if (frameDurationNs.any { it <= 0 }) errors.add("frame_duration_ns has a value <= 0")
        if (iso.any { it <= 0 }) errors.add("iso has a value <= 0")
        if (rollingShutterSkewNs <= 0) errors.add("rolling_shutter_skew_ns must be > 0")
        if (sensorOrientation !in setOf(0, 90, 180, 270)) errors.add("sensor_orientation must be 0/90/180/270")
        if (zone !in CaptureConfig.ZONES) errors.add("zone '$zone' is not one of ${CaptureConfig.ZONES}")
        if (!SHA256_HEX.matches(videoSha256)) errors.add("video_sha256 must be 64 lower-case hex characters")
        if (!wallClockStartUtc.endsWith("Z")) errors.add("wall_clock_start_utc must be ISO 8601 UTC ending in Z")
        if (wallClockSource.isBlank()) errors.add("wall_clock_source is empty")
        if (appVersion.isBlank()) errors.add("app_version is empty")
        if (deviceModel.isBlank()) errors.add("device_model is empty")
        return errors
    }

    /** JSON in schema field order. */
    fun toJson(): String = Json.encode(toMap())

    fun toMap(): Map<String, Any?> = linkedMapOf(
        "app_version" to appVersion,
        "device_model" to deviceModel,
        "sensor_orientation" to sensorOrientation,
        "frame_sensor_timestamps_ns" to frameSensorTimestampsNs,
        "frame_exposure_ns" to frameExposureNs,
        "frame_duration_ns" to frameDurationNs,
        "rolling_shutter_skew_ns" to rollingShutterSkewNs,
        "iso" to iso,
        "wall_clock_start_utc" to wallClockStartUtc,
        "wall_clock_source" to wallClockSource,
        "sensor_timestamp_wall_offset_ns" to sensorTimestampWallOffsetNs,
        "zone" to zone,
        "video_sha256" to videoSha256,
    )

    companion object {
        /** Exact key set of the engine schema. Used by tests. */
        val SCHEMA_KEYS: List<String> = listOf(
            "app_version", "device_model", "sensor_orientation", "frame_sensor_timestamps_ns",
            "frame_exposure_ns", "frame_duration_ns", "rolling_shutter_skew_ns", "iso",
            "wall_clock_start_utc", "wall_clock_source", "sensor_timestamp_wall_offset_ns", "zone",
            "video_sha256",
        )
        private val SHA256_HEX = Regex("^[0-9a-f]{64}$")
    }
}

/** Wall clock sampled together with the sensor clock at recording start. */
data class WallClockSample(
    /** Wall-clock time, ns since the Unix epoch (UTC). */
    val wallNs: Long,
    /** SystemClock.elapsedRealtimeNanos() at the same instant. */
    val elapsedRealtimeNs: Long,
    /** Clock name, for example "android_network_time_clock" or "android_system_wall_clock". */
    val clockName: String,
)

sealed class SidecarOutcome {
    data class Written(val sidecar: CaptureSidecar) : SidecarOutcome()
    data class NotWritten(val reasons: List<String>) : SidecarOutcome()
}

object SidecarBuilder {
    /**
     * Build the sidecar from aligned frames. The sidecar is written only when every encoded frame
     * has a capture result with all per-frame values. It never fills a missing value with a guess.
     *
     * Wall clock: when SENSOR_INFO_TIMESTAMP_SOURCE is REALTIME, sensor timestamps share the
     * SystemClock.elapsedRealtimeNanos() time base, so
     *   offset = wallNs - elapsedRealtimeNs   (sensor_timestamp_wall_offset_ns)
     *   wall_clock_start_utc = time of the first frame = firstSensorTs + offset
     * and wall_clock_source = "<clock>:first_frame". Otherwise the offset is null,
     * wall_clock_start_utc is the wall clock when recording started, and the source is
     * "<clock>:record_start".
     */
    fun build(
        alignment: AlignmentResult,
        appVersion: String,
        deviceModel: String,
        sensorOrientation: Int,
        timestampSourceRealtime: Boolean,
        wallClock: WallClockSample,
        zone: String,
        videoSha256: String,
    ): SidecarOutcome {
        val reasons = ArrayList<String>()
        if (alignment.encodedFrames == 0) reasons.add("the video has no encoded frames")
        if (alignment.encodedWithoutResult.isNotEmpty()) {
            reasons.add("${alignment.encodedWithoutResult.size} encoded frames have no capture result")
        }
        val frames = alignment.matched
        if (frames.any { it.exposureNs == null }) reasons.add("SENSOR_EXPOSURE_TIME missing for some frames")
        if (frames.any { it.frameDurationNs == null }) reasons.add("SENSOR_FRAME_DURATION missing for some frames")
        if (frames.any { it.iso == null }) reasons.add("SENSOR_SENSITIVITY missing for some frames")
        val skews = frames.mapNotNull { it.rollingShutterSkewNs }.filter { it > 0 }
        if (skews.isEmpty()) reasons.add("SENSOR_ROLLING_SHUTTER_SKEW not reported")
        if (reasons.isNotEmpty()) return SidecarOutcome.NotWritten(reasons)

        val offset: Long? = if (timestampSourceRealtime) wallClock.wallNs - wallClock.elapsedRealtimeNs else null
        val startWallNs = if (offset != null) frames.first().sensorTimestampNs + offset else wallClock.wallNs
        val source = wallClock.clockName + if (offset != null) ":first_frame" else ":record_start"
        val sidecar = CaptureSidecar(
            appVersion = appVersion,
            deviceModel = deviceModel,
            sensorOrientation = sensorOrientation,
            frameSensorTimestampsNs = frames.map { it.sensorTimestampNs },
            frameExposureNs = frames.map { it.exposureNs!! },
            frameDurationNs = frames.map { it.frameDurationNs!! },
            rollingShutterSkewNs = median(skews),
            iso = frames.map { it.iso!! },
            wallClockStartUtc = isoUtc(startWallNs),
            wallClockSource = source,
            sensorTimestampWallOffsetNs = offset,
            zone = zone,
            videoSha256 = videoSha256,
        )
        val errors = sidecar.validate()
        return if (errors.isEmpty()) SidecarOutcome.Written(sidecar) else SidecarOutcome.NotWritten(errors)
    }

    /** Lower median of a non-empty list. */
    fun median(values: List<Long>): Long {
        require(values.isNotEmpty())
        val s = values.sorted()
        return s[(s.size - 1) / 2]
    }

    /** ISO 8601 UTC with nanoseconds, for example 2026-10-26T10:15:30.123456789Z. */
    fun isoUtc(epochNs: Long): String =
        java.time.Instant.ofEpochSecond(Math.floorDiv(epochNs, 1_000_000_000L), Math.floorMod(epochNs, 1_000_000_000L)).toString()
}
