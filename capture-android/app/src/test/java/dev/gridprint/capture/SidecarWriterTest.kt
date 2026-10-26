package dev.gridprint.capture

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SidecarWriterTest {

    private val sha = "a".repeat(64)

    private fun metas(n: Int, startNs: Long = 5_000_000_123L, stepNs: Long = 33_333_333L, skew: Long? = 20_000_000L) =
        (0 until n).map { i ->
            FrameMeta(
                frameNumber = i.toLong(),
                sensorTimestampNs = startNs + i * stepNs,
                exposureNs = 1_000_000L,
                frameDurationNs = 33_333_333L,
                rollingShutterSkewNs = skew,
                iso = 800 + i,
            )
        }

    private val clock = WallClockSample(wallNs = 1_793_000_000_000_000_000L, elapsedRealtimeNs = 4_000_000_000L, clockName = "android_network_time_clock")

    private fun build(alignment: AlignmentResult, realtime: Boolean = true, zone: String = "IN") =
        SidecarBuilder.build(alignment, "0.1.0", "Test Phone", 90, realtime, clock, zone, sha)

    @Test
    fun alignmentMatchesEncoderPtsToSensorTimestamps() {
        val m = metas(5)
        val pts = m.map { it.sensorTimestampNs / 1000 }
        val a = FrameAligner.align(pts.reversed(), m.shuffled())
        assertTrue(a.oneToOne)
        assertEquals(m.map { it.sensorTimestampNs }, a.matched.map { it.sensorTimestampNs })
        assertTrue(a.droppedInside.isEmpty() && a.notEncodedBeforeStart.isEmpty() && a.notEncodedAfterEnd.isEmpty())
    }

    @Test
    fun alignmentRecordsDroppedFramesAndEdges() {
        val m = metas(8)
        // Encoder got frames 1..6 but dropped frame 3. Frame 0 came before the first encoded frame, 7 after the last.
        val pts = listOf(1, 2, 4, 5, 6).map { m[it].sensorTimestampNs / 1000 }
        val a = FrameAligner.align(pts, m)
        assertTrue(a.oneToOne)
        assertEquals(5, a.matched.size)
        assertEquals(listOf(m[3].sensorTimestampNs), a.droppedInside)
        assertEquals(listOf(m[0].sensorTimestampNs), a.notEncodedBeforeStart)
        assertEquals(listOf(m[7].sensorTimestampNs), a.notEncodedAfterEnd)
    }

    @Test
    fun alignmentToleratesOneMicrosecondRounding() {
        val m = metas(3, startNs = 1_000_999_999L)
        val pts = m.map { (it.sensorTimestampNs + 500) / 1000 } // rounded instead of truncated
        val a = FrameAligner.align(pts, m)
        assertTrue(a.oneToOne)
    }

    @Test
    fun encodedFrameWithoutResultBlocksSidecar() {
        val m = metas(4)
        val pts = m.map { it.sensorTimestampNs / 1000 } + (m.last().sensorTimestampNs / 1000 + 33_333)
        val a = FrameAligner.align(pts, m)
        assertFalse(a.oneToOne)
        assertEquals(listOf(4), a.encodedWithoutResult)
        val out = build(a)
        assertTrue(out is SidecarOutcome.NotWritten)
    }

    @Test
    fun sidecarHasExactSchemaKeysInOrderAndNoLocation() {
        val m = metas(4)
        val out = build(FrameAligner.align(m.map { it.sensorTimestampNs / 1000 }, m))
        out as SidecarOutcome.Written
        val keys = out.sidecar.toMap().keys.toList()
        assertEquals(CaptureSidecar.SCHEMA_KEYS, keys)
        val json = out.sidecar.toJson()
        for (k in CaptureSidecar.SCHEMA_KEYS) assertTrue("missing $k", json.contains("\"$k\":"))
        for (bad in listOf("lat", "lon", "gps", "location", "altitude")) assertFalse(json.lowercase().contains("\"$bad"))
    }

    @Test
    fun sidecarValuesAndRealtimeWallClock() {
        val m = metas(3)
        val out = build(FrameAligner.align(m.map { it.sensorTimestampNs / 1000 }, m)) as SidecarOutcome.Written
        val s = out.sidecar
        assertEquals(m.map { it.sensorTimestampNs }, s.frameSensorTimestampsNs)
        assertEquals(listOf(800, 801, 802), s.iso)
        assertEquals(20_000_000L, s.rollingShutterSkewNs)
        val offset = clock.wallNs - clock.elapsedRealtimeNs
        assertEquals(offset, s.sensorTimestampWallOffsetNs)
        assertEquals(SidecarBuilder.isoUtc(m[0].sensorTimestampNs + offset), s.wallClockStartUtc)
        assertEquals("android_network_time_clock:first_frame", s.wallClockSource)
        assertTrue(s.wallClockStartUtc.endsWith("Z"))
        assertTrue(s.validate().isEmpty())
    }

    @Test
    fun nonRealtimeSourceGivesNullOffset() {
        val m = metas(3)
        val out = build(FrameAligner.align(m.map { it.sensorTimestampNs / 1000 }, m), realtime = false) as SidecarOutcome.Written
        assertNull(out.sidecar.sensorTimestampWallOffsetNs)
        assertEquals("android_network_time_clock:record_start", out.sidecar.wallClockSource)
        assertEquals(SidecarBuilder.isoUtc(clock.wallNs), out.sidecar.wallClockStartUtc)
        assertTrue(out.sidecar.toJson().contains("\"sensor_timestamp_wall_offset_ns\":null"))
    }

    @Test
    fun missingSkewMeansNoSidecarNeverAGuess() {
        val m = metas(3, skew = null)
        val out = build(FrameAligner.align(m.map { it.sensorTimestampNs / 1000 }, m))
        out as SidecarOutcome.NotWritten
        assertTrue(out.reasons.any { it.contains("SENSOR_ROLLING_SHUTTER_SKEW") })
    }

    @Test
    fun unknownZoneIsRejected() {
        val m = metas(2)
        val out = build(FrameAligner.align(m.map { it.sensorTimestampNs / 1000 }, m), zone = "Mumbai")
        assertTrue(out is SidecarOutcome.NotWritten)
    }

    @Test
    fun skewIsMedian() {
        assertEquals(20L, SidecarBuilder.median(listOf(30L, 10L, 20L)))
        assertEquals(20L, SidecarBuilder.median(listOf(30L, 10L, 20L, 40L)))
    }

    @Test
    fun jsonEscapesStrings() {
        assertEquals("\"a\\\"b\\\\c\\n\\u0001\"", Json.quote("a\"b\\c\n\u0001"))
        assertEquals("{\"x\":[1,2],\"y\":null,\"z\":true}", Json.encode(linkedMapOf("x" to listOf(1L, 2L), "y" to null, "z" to true)))
    }

    @Test
    fun captureLogListsDroppedFrames() {
        val m = metas(5)
        val pts = listOf(0, 1, 3, 4).map { m[it].sensorTimestampNs / 1000 }
        val a = FrameAligner.align(pts, m)
        val out = build(a)
        val log = CaptureLog.toJson("v.mp4", a, 5, emptyList(), emptyList(), false, out, 1_000_000L, 800, 33_333_333L, 90)
        assertTrue(log.contains("\"dropped_inside_recording_ns\":[${m[2].sensorTimestampNs}]"))
        assertTrue(log.contains("\"sidecar_written\":true"))
    }
}
