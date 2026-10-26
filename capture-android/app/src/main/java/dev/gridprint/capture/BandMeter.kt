package dev.gridprint.capture

import kotlin.math.log10
import kotlin.math.pow
import kotlin.math.sqrt

/**
 * Live band-strength meter (SPEC 10.3 item 4). UI guidance only; it never produces a verdict.
 *
 * Per preview frame:
 *  1. Convert 8-bit luma to approximate linear light (sRGB transfer inverse, lookup table).
 *  2. Row means over the frame (rows are sensor rows: camera output buffers are not rotated).
 *  3. d[r] = rowMean[r] - runningMean[r], where runningMean is an exponential running mean of
 *     earlier row profiles. Static scene content cancels; flicker bands that move between frames
 *     at the flicker alias rate (100 Hz at 30 fps aliases to 10 Hz: one third of a band cycle per
 *     frame) remain.
 *  4. Score = sqrt(variance of d over rows) / mean(rowMean): RMS fractional modulation.
 *
 * Known limit: at exactly 30 fps, 120 Hz flicker (60 Hz grids) aliases to about 0 Hz, so the
 * bands stand almost still and this meter reads low there even when bands exist.
 */
class BandMeter(
    private val alpha: Double = 0.1,
    private val warmupFrames: Int = 10,
) {
    init {
        require(alpha > 0.0 && alpha <= 1.0) { "alpha must be in (0, 1]" }
        require(warmupFrames >= 1) { "warmupFrames must be >= 1" }
    }

    private var running: DoubleArray? = null
    private var frames = 0

    fun reset() {
        running = null
        frames = 0
    }

    /**
     * Feed one row-mean profile (linear light). Returns the score, or null during warm-up or when
     * the frame is black.
     */
    fun update(rowMeans: DoubleArray): Double? {
        val prev = running
        if (prev == null || prev.size != rowMeans.size) {
            running = rowMeans.copyOf()
            frames = 1
            return null
        }
        val score = modulationScore(rowMeans, prev)
        for (i in prev.indices) prev[i] = (1.0 - alpha) * prev[i] + alpha * rowMeans[i]
        frames++
        return if (frames <= warmupFrames) null else score
    }

    companion object {
        /** sRGB transfer inverse for 8-bit codes, as a lookup table. */
        val LINEAR_LUT: DoubleArray = DoubleArray(256) { code ->
            val v = code / 255.0
            if (v <= 0.04045) v / 12.92 else ((v + 0.055) / 1.055).pow(2.4)
        }

        /**
         * Row means of an 8-bit luma plane in linear light.
         * [plane] holds rows with stride [rowStride]; pixel stride is 1 (YUV_420_888 Y plane).
         * Every [columnStep]-th column is sampled to save time.
         */
        fun rowMeansLinear(plane: ByteArray, width: Int, height: Int, rowStride: Int, columnStep: Int = 4): DoubleArray {
            require(width > 0 && height > 0) { "empty plane" }
            require(rowStride >= width) { "rowStride < width" }
            require(columnStep >= 1) { "columnStep must be >= 1" }
            require(plane.size >= (height - 1) * rowStride + width) { "plane too small" }
            val out = DoubleArray(height)
            for (r in 0 until height) {
                var sum = 0.0
                var n = 0
                var idx = r * rowStride
                val end = idx + width
                while (idx < end) {
                    sum += LINEAR_LUT[plane[idx].toInt() and 0xFF]
                    n++
                    idx += columnStep
                }
                out[r] = sum / n
            }
            return out
        }

        /** sqrt(var(current - reference)) / mean(current). Null if the frame is black. */
        fun modulationScore(current: DoubleArray, reference: DoubleArray): Double? {
            require(current.size == reference.size && current.isNotEmpty()) { "size mismatch" }
            val n = current.size
            var mean = 0.0
            for (v in current) mean += v
            mean /= n
            if (mean <= 1e-9) return null
            var dMean = 0.0
            for (i in 0 until n) dMean += current[i] - reference[i]
            dMean /= n
            var acc = 0.0
            for (i in 0 until n) {
                val d = current[i] - reference[i] - dMean
                acc += d * d
            }
            return sqrt(acc / n) / mean
        }

        /** Map a score to 0..100 on a log scale from 1e-4 (0) to 1e-1 (100). */
        fun barPercent(score: Double?): Int {
            if (score == null || score <= 1e-4) return 0
            val p = (log10(score) + 4.0) / 3.0 * 100.0
            return p.coerceIn(0.0, 100.0).toInt()
        }
    }
}
