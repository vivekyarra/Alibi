package dev.gridprint.capture

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt

class BandMeterTest {

    /** Synthetic 8-bit luma plane: scene gradient x (1 + m sin(2 pi (r / period + phase))), in code values. */
    private fun plane(w: Int, h: Int, stride: Int, m: Double, periodRows: Double, phase: Double): ByteArray {
        val p = ByteArray(stride * h)
        for (r in 0 until h) {
            val base = 100.0 + 60.0 * r / h
            val v = base * (1.0 + m * sin(2 * PI * (r / periodRows + phase)))
            for (c in 0 until w) p[r * stride + c] = v.roundToInt().coerceIn(0, 255).toByte()
        }
        return p
    }

    @Test
    fun lutIsSrgbInverse() {
        assertEquals(0.0, BandMeter.LINEAR_LUT[0], 0.0)
        assertEquals(1.0, BandMeter.LINEAR_LUT[255], 1e-12)
        assertEquals(0.21586, BandMeter.LINEAR_LUT[128], 1e-5) // ((128/255 + 0.055) / 1.055)^2.4
    }

    @Test
    fun rowMeansRespectStrideAndColumnStep() {
        val w = 8
        val h = 3
        val stride = 12
        val p = ByteArray(stride * h)
        for (r in 0 until h) for (c in 0 until stride) p[r * stride + c] = if (c < w) (r * 100).toByte() else 255.toByte()
        val rows = BandMeter.rowMeansLinear(p, w, h, stride, columnStep = 3)
        for (r in 0 until h) assertEquals(BandMeter.LINEAR_LUT[(r * 100) and 0xFF], rows[r], 1e-12)
    }

    @Test
    fun staticSceneGivesNearZero() {
        val meter = BandMeter(alpha = 0.1, warmupFrames = 3)
        val p = plane(64, 120, 64, 0.0, 20.0, 0.0)
        var last: Double? = null
        repeat(10) { last = meter.update(BandMeter.rowMeansLinear(p, 64, 120, 64)) }
        assertNotNull(last)
        assertTrue("static score $last", last!! < 1e-12)
    }

    @Test
    fun movingBandsGiveScoreNearModulation() {
        // 100 Hz flicker at 30 fps: bands advance by 1/3 cycle per frame (alias 10 Hz).
        val meter = BandMeter(alpha = 0.1, warmupFrames = 30)
        val m = 0.05
        var score: Double? = null
        for (k in 0 until 60) {
            val p = plane(64, 240, 64, m, 40.0, k / 3.0)
            score = meter.update(BandMeter.rowMeansLinear(p, 64, 240, 64, columnStep = 1))
        }
        assertNotNull(score)
        // The running mean nearly cancels a band moving 1/3 cycle per frame, so d is about the band itself.
        // Linear-light modulation of a sine in code values is about 2.2 x m (sRGB slope); RMS of a sine is amplitude / sqrt(2).
        val expectedOrder = 2.2 * m / sqrt(2.0)
        assertTrue("score $score vs $expectedOrder", abs(score!! - expectedOrder) / expectedOrder < 0.35)
    }

    @Test
    fun strongerBandsScoreHigher() {
        fun run(m: Double): Double {
            val meter = BandMeter(alpha = 0.1, warmupFrames = 20)
            var s: Double? = null
            for (k in 0 until 40) s = meter.update(BandMeter.rowMeansLinear(plane(32, 200, 32, m, 50.0, k / 3.0), 32, 200, 32))
            return s!!
        }
        assertTrue(run(0.01) < run(0.03))
        assertTrue(run(0.03) < run(0.08))
    }

    @Test
    fun warmupAndBlackFramesReturnNull() {
        val meter = BandMeter(alpha = 0.1, warmupFrames = 5)
        val black = ByteArray(16 * 10)
        repeat(8) { assertNull(meter.update(BandMeter.rowMeansLinear(black, 16, 10, 16))) }
    }

    @Test
    fun barPercentScale() {
        assertEquals(0, BandMeter.barPercent(null))
        assertEquals(0, BandMeter.barPercent(1e-5))
        assertEquals(33, BandMeter.barPercent(1e-3))
        assertEquals(100, BandMeter.barPercent(0.5))
    }

    @Test
    fun isoCompensation() {
        // Auto: 10 ms at ISO 100 -> 1 ms needs ISO 1000.
        assertEquals(1000, Exposure.compensatedIso(10_000_000L, 100, 1_000_000L, 50, 3200))
        assertEquals(3200, Exposure.compensatedIso(40_000_000L, 400, 1_000_000L, 50, 3200))
        assertEquals(50, Exposure.compensatedIso(500_000L, 50, 1_000_000L, 50, 3200))
        assertEquals(1_000_000L, Exposure.clampExposure(1_000_000L, 13_000L, 680_000_000L))
    }

    @Test
    fun capabilityReportFlags() {
        val r = CapabilityReport(
            appVersion = "0.1.0", deviceModel = "X", androidSdkInt = 34, cameraId = "0", hardwareLevel = "FULL",
            sensorOrientation = 90, checkedAtUtc = "2026-10-26T00:00:00Z",
            availableAeModes = listOf(0, 1, 2), availableAntibandingModes = listOf(0, 1, 2, 3),
            manualSensorCapability = true, exposureRangeNs = listOf(10_000L, 500_000_000L), sensitivityRange = listOf(50, 6400),
            requestedExposureNs = 1_000_000L, availableFpsRanges = listOf(listOf(15, 30), listOf(30, 30)),
            skewListedInResultKeys = true, timestampSource = 1,
            probe = CapabilityReport.ProbeResult(30, 21_000_000L, 1_000_000L, 33_333_333L, 1000, null),
        )
        assertTrue(r.aeModeOff && r.antibandingOff && r.manualExposure && r.fixed30Fps && r.rollingShutterSkew && r.timestampRealtime)
        val noSkew = r.copy(probe = r.probe!!.copy(skewObservedNs = null), timestampSource = 0, availableAeModes = listOf(1))
        assertTrue(!noSkew.rollingShutterSkew && !noSkew.timestampRealtime && !noSkew.aeModeOff)
        assertTrue(r.toJson().startsWith("{\"schema\":\"gridprint_capability/1\""))
    }
}
