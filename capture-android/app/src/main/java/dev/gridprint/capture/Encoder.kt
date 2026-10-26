package dev.gridprint.capture

import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.media.MediaMuxer
import android.util.Log
import android.util.Size
import android.view.Surface
import java.io.File
import java.util.concurrent.ConcurrentLinkedQueue

/**
 * H.264 encoder (MediaCodec, Surface input) plus MP4 muxer (MediaMuxer).
 *
 * - Bit rate CaptureConfig.BITRATE_BPS (40 Mbps), 30 fps, key frame every second, no B-frames
 *   (MediaFormat.KEY_MAX_B_FRAMES = 0) so decode order equals presentation order.
 * - The encoder input Surface receives camera buffers in sensor orientation. Pixels are never
 *   rotated: MediaMuxer.setOrientationHint only writes the display rotation into the MP4, so coded
 *   rows are sensor rows.
 * - [ptsUs] lists presentationTimeUs of every frame written to the MP4, in output order. The
 *   camera sets the Surface buffer timestamp to SENSOR_TIMESTAMP, so pts * 1000 ~ SENSOR_TIMESTAMP.
 */
class Encoder(private val file: File, size: Size, orientationHintDeg: Int) {
    private val codec: MediaCodec = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
    private val muxer: MediaMuxer = MediaMuxer(file.absolutePath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
    val inputSurface: Surface
    val ptsUs = ConcurrentLinkedQueue<Long>()
    @Volatile private var error: String? = null
    private val drainThread: Thread

    init {
        val format = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, size.width, size.height)
        format.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
        format.setInteger(MediaFormat.KEY_BIT_RATE, CaptureConfig.BITRATE_BPS)
        format.setInteger(MediaFormat.KEY_FRAME_RATE, CaptureConfig.FPS)
        format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, CaptureConfig.I_FRAME_INTERVAL_S)
        format.setInteger(MediaFormat.KEY_MAX_B_FRAMES, 0)
        codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        inputSurface = codec.createInputSurface()
        muxer.setOrientationHint(orientationHintDeg)
        codec.start()
        drainThread = Thread({ drain() }, "gridprint-encoder")
        drainThread.start()
    }

    private fun drain() {
        val info = MediaCodec.BufferInfo()
        var track = -1
        var started = false
        try {
            while (true) {
                val idx = codec.dequeueOutputBuffer(info, 10_000L)
                when {
                    idx == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                        track = muxer.addTrack(codec.outputFormat)
                        muxer.start()
                        started = true
                    }
                    idx >= 0 -> {
                        val buf = codec.getOutputBuffer(idx)
                        val isConfig = info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0
                        if (buf != null && !isConfig && info.size > 0 && started) {
                            buf.position(info.offset)
                            buf.limit(info.offset + info.size)
                            muxer.writeSampleData(track, buf, info)
                            ptsUs.add(info.presentationTimeUs)
                        }
                        codec.releaseOutputBuffer(idx, false)
                        if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) break
                    }
                }
            }
        } catch (e: Exception) {
            Log.e("GridprintEncoder", "drain failed", e)
            error = "encoder: ${e.message}"
        }
        try {
            if (started) muxer.stop()
        } catch (e: Exception) {
            error = (error ?: "") + " muxer stop: ${e.message}"
        }
    }

    /** End the stream, wait for the drain thread, release. Returns an error text or null. */
    fun finish(): String? {
        try {
            codec.signalEndOfInputStream()
        } catch (e: Exception) {
            error = "signalEndOfInputStream: ${e.message}"
        }
        drainThread.join(5000)
        if (drainThread.isAlive) error = (error ?: "") + " encoder did not reach end of stream in 5 s"
        release()
        return error
    }

    fun abort() {
        try {
            codec.signalEndOfInputStream()
        } catch (_: Exception) {
        }
        drainThread.join(2000)
        release()
        file.delete()
    }

    private fun release() {
        try { codec.stop() } catch (_: Exception) {}
        codec.release()
        try { muxer.release() } catch (_: Exception) {}
        inputSurface.release()
    }
}
