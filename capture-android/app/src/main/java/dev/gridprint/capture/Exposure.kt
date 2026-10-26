package dev.gridprint.capture

import kotlin.math.roundToLong

/** Exposure math for switching from metered auto exposure to the fixed short exposure. */
object Exposure {
    /**
     * ISO that keeps the image brightness of the metered auto-exposure state when exposure time
     * changes to [targetExposureNs]: iso = autoIso * autoExposureNs / targetExposureNs,
     * clamped to the sensor range [isoMin, isoMax].
     */
    fun compensatedIso(autoExposureNs: Long, autoIso: Int, targetExposureNs: Long, isoMin: Int, isoMax: Int): Int {
        require(autoExposureNs > 0 && autoIso > 0 && targetExposureNs > 0) { "values must be positive" }
        require(isoMin in 1..isoMax) { "bad ISO range" }
        val raw = (autoIso.toDouble() * autoExposureNs.toDouble() / targetExposureNs.toDouble()).roundToLong()
        return raw.coerceIn(isoMin.toLong(), isoMax.toLong()).toInt()
    }

    /** Clamp the configured exposure to the sensor exposure range. */
    fun clampExposure(targetNs: Long, minNs: Long, maxNs: Long): Long = targetNs.coerceIn(minNs, maxNs)
}
