package dev.gridprint.capture

/**
 * Capture log written next to every video as `<name>.capture_log.json`. It records how encoded
 * frames were matched to capture results, every frame the encoder dropped, and why a sidecar was
 * not written. The sidecar schema forbids extra fields, so this information lives here.
 */
object CaptureLog {
    fun toJson(
        videoFileName: String,
        alignment: AlignmentResult,
        capturedResults: Int,
        bufferLostFrameNumbers: List<Long>,
        captureFailedFrameNumbers: List<Long>,
        sessionWithoutMeter: Boolean,
        outcome: SidecarOutcome,
        requestedExposureNs: Long,
        requestedIso: Int,
        requestedFrameDurationNs: Long,
        orientationHintDeg: Int,
    ): String {
        val skews = alignment.matched.mapNotNull { it.rollingShutterSkewNs }
        val map = linkedMapOf<String, Any?>(
            "schema" to "gridprint_capture_log/1",
            "video_file" to videoFileName,
            "encoded_frames" to alignment.encodedFrames,
            "capture_results" to capturedResults,
            "matched_frames" to alignment.matched.size,
            "one_to_one" to alignment.oneToOne,
            "alignment_method" to "encoder presentationTimeUs == SENSOR_TIMESTAMP / 1000 (+-1 us)",
            "encoded_frames_without_capture_result" to alignment.encodedWithoutResult,
            "captures_not_encoded" to linkedMapOf(
                "before_first_encoded_frame_ns" to alignment.notEncodedBeforeStart,
                "dropped_inside_recording_ns" to alignment.droppedInside,
                "after_last_encoded_frame_ns" to alignment.notEncodedAfterEnd,
            ),
            "buffer_lost_frame_numbers" to bufferLostFrameNumbers,
            "capture_failed_frame_numbers" to captureFailedFrameNumbers,
            "rolling_shutter_skew_ns" to linkedMapOf(
                "min" to skews.minOrNull(),
                "max" to skews.maxOrNull(),
                "frames_missing" to (alignment.matched.size - skews.size),
            ),
            "requested" to linkedMapOf(
                "exposure_ns" to requestedExposureNs,
                "iso" to requestedIso,
                "frame_duration_ns" to requestedFrameDurationNs,
            ),
            "orientation_hint_deg" to orientationHintDeg,
            "meter_stream_disabled_during_recording" to sessionWithoutMeter,
            "sidecar_written" to (outcome is SidecarOutcome.Written),
            "sidecar_not_written_reasons" to ((outcome as? SidecarOutcome.NotWritten)?.reasons ?: emptyList<String>()),
        )
        return Json.encode(map)
    }
}
