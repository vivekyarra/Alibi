package dev.gridprint.capture

/**
 * Per-frame values from one Camera2 CaptureResult. Null means the device did not report the key.
 */
data class FrameMeta(
    val frameNumber: Long,
    /** CaptureResult.SENSOR_TIMESTAMP: start of exposure of the first row, ns. */
    val sensorTimestampNs: Long,
    val exposureNs: Long?,
    val frameDurationNs: Long?,
    val rollingShutterSkewNs: Long?,
    val iso: Int?,
)

/**
 * Result of matching encoded video frames to capture results.
 *
 * How alignment works: the camera writes each buffer to the encoder input Surface with buffer
 * timestamp = SENSOR_TIMESTAMP (Android reference, CaptureResult.SENSOR_TIMESTAMP: the timestamp
 * is also included in all image buffers produced for the same capture). MediaCodec turns the
 * Surface timestamp (ns) into MediaCodec.BufferInfo.presentationTimeUs (us). So each encoded frame
 * is matched to the capture result whose SENSOR_TIMESTAMP / 1000 equals its presentationTimeUs
 * (tolerance +-1 us for rounding).
 */
data class AlignmentResult(
    /** Matched capture results, one per encoded frame, in presentation order. */
    val matched: List<FrameMeta>,
    /** Number of encoded frames. */
    val encodedFrames: Int,
    /** Presentation-order indices of encoded frames with no capture result. */
    val encodedWithoutResult: List<Int>,
    /** Capture results with no encoded frame, before the first encoded frame. */
    val notEncodedBeforeStart: List<Long>,
    /** Capture results with no encoded frame, between the first and last encoded frame (dropped). */
    val droppedInside: List<Long>,
    /** Capture results with no encoded frame, after the last encoded frame. */
    val notEncodedAfterEnd: List<Long>,
) {
    /** True when every encoded frame has exactly one capture result. */
    val oneToOne: Boolean get() = encodedWithoutResult.isEmpty() && matched.size == encodedFrames
}

object FrameAligner {
    const val TOLERANCE_US = 1L

    fun align(encodedPtsUs: List<Long>, results: Collection<FrameMeta>): AlignmentResult {
        val pts = encodedPtsUs.sorted()
        val byUs = HashMap<Long, MutableList<FrameMeta>>()
        for (m in results) byUs.getOrPut(Math.floorDiv(m.sensorTimestampNs, 1000L)) { mutableListOf() }.add(m)
        val used = HashSet<Long>() // frame numbers already matched
        val matched = ArrayList<FrameMeta>(pts.size)
        val missing = ArrayList<Int>()
        for ((i, p) in pts.withIndex()) {
            var hit: FrameMeta? = null
            for (delta in longArrayOf(0L, -TOLERANCE_US, TOLERANCE_US)) {
                val cands = byUs[p + delta] ?: continue
                hit = cands.firstOrNull { it.frameNumber !in used }
                if (hit != null) break
            }
            if (hit == null) {
                missing.add(i)
            } else {
                used.add(hit.frameNumber)
                matched.add(hit)
            }
        }
        val firstNs = pts.firstOrNull()?.let { it * 1000L }
        val lastNs = pts.lastOrNull()?.let { it * 1000L }
        val unused = results.filter { it.frameNumber !in used }.map { it.sensorTimestampNs }.sorted()
        val before = ArrayList<Long>()
        val inside = ArrayList<Long>()
        val after = ArrayList<Long>()
        for (ts in unused) {
            when {
                firstNs == null || ts < firstNs -> before.add(ts)
                ts > lastNs!! + 1000L -> after.add(ts)
                else -> inside.add(ts)
            }
        }
        return AlignmentResult(matched, pts.size, missing, before, inside, after)
    }
}
