package dev.gridprint.capture

import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraMetadata
import android.hardware.camera2.CaptureResult
import android.hardware.camera2.TotalCaptureResult
import android.os.Build

/**
 * Device check (SPEC Part 4 V7). Reads CameraCharacteristics and the capture results of the
 * running preview (which already uses the manual settings when they are supported), then builds
 * the report written to gridprint_capability.json.
 */
object DeviceCheck {
    fun build(
        chars: CameraCharacteristics,
        cameraId: String,
        appVersion: String,
        probeResults: List<TotalCaptureResult>,
        probeError: String?,
    ): CapabilityReport {
        val exposureRange = chars.get(CameraCharacteristics.SENSOR_INFO_EXPOSURE_TIME_RANGE)
        val isoRange = chars.get(CameraCharacteristics.SENSOR_INFO_SENSITIVITY_RANGE)
        val caps = chars.get(CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES) ?: IntArray(0)
        val fps = chars.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES).orEmpty()
        val skewKeyListed = chars.availableCaptureResultKeys.contains(CaptureResult.SENSOR_ROLLING_SHUTTER_SKEW)
        val skews = probeResults.mapNotNull { it.get(CaptureResult.SENSOR_ROLLING_SHUTTER_SKEW) }.filter { it > 0 }
        val exps = probeResults.mapNotNull { it.get(CaptureResult.SENSOR_EXPOSURE_TIME) }
        val durs = probeResults.mapNotNull { it.get(CaptureResult.SENSOR_FRAME_DURATION) }
        val isos = probeResults.mapNotNull { it.get(CaptureResult.SENSOR_SENSITIVITY) }
        return CapabilityReport(
            appVersion = appVersion,
            deviceModel = deviceModel(),
            androidSdkInt = Build.VERSION.SDK_INT,
            cameraId = cameraId,
            hardwareLevel = hardwareLevelName(chars.get(CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL)),
            sensorOrientation = chars.get(CameraCharacteristics.SENSOR_ORIENTATION) ?: -1,
            checkedAtUtc = java.time.Instant.now().toString(),
            availableAeModes = (chars.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_MODES) ?: IntArray(0)).toList(),
            availableAntibandingModes = (chars.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_ANTIBANDING_MODES) ?: IntArray(0)).toList(),
            manualSensorCapability = CameraMetadata.REQUEST_AVAILABLE_CAPABILITIES_MANUAL_SENSOR in caps,
            exposureRangeNs = exposureRange?.let { listOf(it.lower, it.upper) },
            sensitivityRange = isoRange?.let { listOf(it.lower, it.upper) },
            requestedExposureNs = CaptureConfig.EXPOSURE_NS,
            availableFpsRanges = fps.map { listOf(it.lower, it.upper) },
            skewListedInResultKeys = skewKeyListed,
            timestampSource = chars.get(CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE),
            probe = CapabilityReport.ProbeResult(
                framesReceived = probeResults.size,
                skewObservedNs = if (skews.isEmpty()) null else SidecarBuilder.median(skews),
                exposureMedianNs = if (exps.isEmpty()) null else SidecarBuilder.median(exps),
                frameDurationMedianNs = if (durs.isEmpty()) null else SidecarBuilder.median(durs),
                isoMedian = if (isos.isEmpty()) null else SidecarBuilder.median(isos.map { it.toLong() }).toInt(),
                error = probeError,
            ),
        )
    }

    /** Plain-text summary for the screen. */
    fun summary(r: CapabilityReport): String {
        fun line(ok: Boolean, name: String, detail: String) = (if (ok) "PASS  " else "FAIL  ") + name + "\n      " + detail
        return listOf(
            "Device: ${r.deviceModel} (Android SDK ${r.androidSdkInt}), camera ${r.cameraId}, level ${r.hardwareLevel}",
            "Sensor orientation: ${r.sensorOrientation} deg",
            "",
            line(r.aeModeOff, "Auto exposure OFF (required)", "AE modes: ${r.availableAeModes}"),
            line(r.antibandingOff, "Anti-banding OFF (required)", "Anti-banding modes: ${r.availableAntibandingModes}"),
            line(r.manualExposure, "Manual exposure of ${r.requestedExposureNs} ns (required)",
                "MANUAL_SENSOR: ${r.manualSensorCapability}, range ns: ${r.exposureRangeNs}"),
            line(r.fixed30Fps, "Fixed ${CaptureConfig.FPS} fps (required)", "FPS ranges: ${r.availableFpsRanges}"),
            line(r.rollingShutterSkew, "Rolling-shutter skew reported (optional)",
                "Listed: ${r.skewListedInResultKeys}, observed ns: ${r.probe?.skewObservedNs}. If FAIL: no sidecar; the calibration rig profile is used."),
            line(r.timestampRealtime, "Timestamp source REALTIME (optional)",
                "Value: ${CapabilityReport.timestampSourceName(r.timestampSource)}. If FAIL: the start time comes from the record button time."),
            "",
            "Probe: ${r.probe?.framesReceived} frames, exposure ${r.probe?.exposureMedianNs} ns, " +
                "frame duration ${r.probe?.frameDurationMedianNs} ns, ISO ${r.probe?.isoMedian}" +
                (r.probe?.error?.let { ", error: $it" } ?: ""),
        ).joinToString("\n")
    }

    fun deviceModel(): String = "${Build.MANUFACTURER} ${Build.MODEL}".trim()

    private fun hardwareLevelName(v: Int?): String = when (v) {
        CameraMetadata.INFO_SUPPORTED_HARDWARE_LEVEL_LEGACY -> "LEGACY"
        CameraMetadata.INFO_SUPPORTED_HARDWARE_LEVEL_LIMITED -> "LIMITED"
        CameraMetadata.INFO_SUPPORTED_HARDWARE_LEVEL_FULL -> "FULL"
        CameraMetadata.INFO_SUPPORTED_HARDWARE_LEVEL_3 -> "LEVEL_3"
        CameraMetadata.INFO_SUPPORTED_HARDWARE_LEVEL_EXTERNAL -> "EXTERNAL"
        null -> "UNKNOWN"
        else -> "OTHER_$v"
    }
}
