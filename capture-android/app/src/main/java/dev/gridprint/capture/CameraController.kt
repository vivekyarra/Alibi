package dev.gridprint.capture

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.ImageFormat
import android.graphics.SurfaceTexture
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CameraMetadata
import android.hardware.camera2.CaptureFailure
import android.hardware.camera2.CaptureRequest
import android.hardware.camera2.CaptureResult
import android.hardware.camera2.TotalCaptureResult
import android.media.ImageReader
import android.media.MediaCodec
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import android.util.Log
import android.util.Range
import android.util.Size
import android.view.Surface
import java.io.File
import java.util.concurrent.ConcurrentLinkedQueue

/**
 * Camera2 control for GRIDPRINT Capture (SPEC 10.3).
 *
 * Preview session: [preview Surface, meter ImageReader]. Recording session: [preview Surface,
 * encoder input Surface, meter ImageReader]; if the device refuses three streams, the recording
 * session uses [preview, encoder] and the meter pauses (recorded in the capture log).
 *
 * Every request after light metering uses: CONTROL_AE_MODE_OFF, CONTROL_AE_ANTIBANDING_MODE_OFF,
 * SENSOR_EXPOSURE_TIME = CaptureConfig.EXPOSURE_NS, SENSOR_SENSITIVITY raised to keep brightness,
 * SENSOR_FRAME_DURATION = 1/30 s, CONTROL_AE_TARGET_FPS_RANGE = [30, 30], and
 * CONTROL_VIDEO_STABILIZATION_MODE_OFF (electronic stabilization warps rows).
 */
class CameraController(private val context: Context, private val listener: Listener) {

    interface Listener {
        /** Called on the camera thread. */
        fun onMeter(score: Double?)
        fun onStatus(text: String)
        fun onError(text: String)
        fun onReady(manualSupported: Boolean)
    }

    /** Everything collected while recording. */
    class RecordingOutput(
        val videoFile: File,
        val encodedPtsUs: List<Long>,
        val results: List<FrameMeta>,
        val bufferLostFrameNumbers: List<Long>,
        val captureFailedFrameNumbers: List<Long>,
        val sessionWithoutMeter: Boolean,
        val wallClock: WallClockSample,
        val orientationHintDeg: Int,
        val requestedExposureNs: Long,
        val requestedIso: Int,
        val encoderError: String?,
    )

    private val manager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
    private val thread = HandlerThread("gridprint-camera").also { it.start() }
    val handler = Handler(thread.looper)

    lateinit var cameraId: String
        private set
    lateinit var characteristics: CameraCharacteristics
        private set
    lateinit var videoSize: Size
        private set
    private lateinit var meterSize: Size

    private var device: CameraDevice? = null
    private var session: CameraCaptureSession? = null
    private var previewSurface: Surface? = null
    private var meterReader: ImageReader? = null
    private val meter = BandMeter()
    private var meterBytes = ByteArray(0)

    var manualSupported = false
        private set
    var exposureNs: Long = CaptureConfig.EXPOSURE_NS
        private set
    var manualIso: Int = 0
        private set

    // Recording state (camera thread only, except the queues).
    private var encoder: Encoder? = null
    private val results = ConcurrentLinkedQueue<FrameMeta>()
    private val lostFrames = ConcurrentLinkedQueue<Long>()
    private val failedFrames = ConcurrentLinkedQueue<Long>()
    private var recordingWithoutMeter = false
    private var recordingWallClock: WallClockSample? = null
    private var recordingHint = 0
    private var recordingFile: File? = null

    /** Optional collector used by the Device check (camera thread). */
    private var probeSink: ((TotalCaptureResult) -> Unit)? = null

    /** Select the first back camera and the stream sizes. Returns false if there is none. */
    fun selectCamera(): Boolean {
        val id = manager.cameraIdList.firstOrNull { id ->
            manager.getCameraCharacteristics(id).get(CameraCharacteristics.LENS_FACING) == CameraMetadata.LENS_FACING_BACK
        } ?: return false
        cameraId = id
        characteristics = manager.getCameraCharacteristics(id)
        val map = characteristics.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP) ?: return false
        val videoSizes = map.getOutputSizes(MediaCodec::class.java)?.toList().orEmpty()
            .filter { map.getOutputMinFrameDuration(MediaCodec::class.java, it) <= CaptureConfig.FRAME_DURATION_NS }
        videoSize = videoSizes.firstOrNull { it.width == 1920 && it.height == 1080 }
            ?: videoSizes.filter { it.width <= 1920 && it.height <= 1080 }.maxByOrNull { it.width * it.height }
            ?: return false
        val yuv = map.getOutputSizes(ImageFormat.YUV_420_888)?.toList().orEmpty()
        val aspect = videoSize.width.toDouble() / videoSize.height
        meterSize = yuv.filter { it.width >= 320 && Math.abs(it.width.toDouble() / it.height - aspect) < 0.02 }
            .minByOrNull { it.width * it.height }
            ?: yuv.filter { it.width >= 320 }.minByOrNull { it.width * it.height }
            ?: return false
        val aeModes = characteristics.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_MODES) ?: IntArray(0)
        val abModes = characteristics.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_ANTIBANDING_MODES) ?: IntArray(0)
        val caps = characteristics.get(CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES) ?: IntArray(0)
        manualSupported = CameraMetadata.CONTROL_AE_MODE_OFF in aeModes &&
            CameraMetadata.CONTROL_AE_ANTIBANDING_MODE_OFF in abModes &&
            CameraMetadata.REQUEST_AVAILABLE_CAPABILITIES_MANUAL_SENSOR in caps
        val range = characteristics.get(CameraCharacteristics.SENSOR_INFO_EXPOSURE_TIME_RANGE)
        exposureNs = if (range != null) Exposure.clampExposure(CaptureConfig.EXPOSURE_NS, range.lower, range.upper) else CaptureConfig.EXPOSURE_NS
        return true
    }

    val sensorOrientation: Int get() = characteristics.get(CameraCharacteristics.SENSOR_ORIENTATION) ?: 0

    val timestampSourceRealtime: Boolean
        get() = characteristics.get(CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE) ==
            CameraMetadata.SENSOR_INFO_TIMESTAMP_SOURCE_REALTIME

    @SuppressLint("MissingPermission") // The Activity requests CAMERA before calling open().
    fun open(texture: SurfaceTexture) {
        texture.setDefaultBufferSize(videoSize.width, videoSize.height)
        previewSurface = Surface(texture)
        val reader = ImageReader.newInstance(meterSize.width, meterSize.height, ImageFormat.YUV_420_888, 3)
        reader.setOnImageAvailableListener({ r -> onMeterImage(r) }, handler)
        meterReader = reader
        manager.openCamera(cameraId, object : CameraDevice.StateCallback() {
            override fun onOpened(camera: CameraDevice) {
                device = camera
                startPreviewSession()
            }

            override fun onDisconnected(camera: CameraDevice) {
                camera.close()
                device = null
                listener.onError("The camera was disconnected.")
            }

            override fun onError(camera: CameraDevice, error: Int) {
                camera.close()
                device = null
                listener.onError("The camera reported error $error.")
            }
        }, handler)
    }

    fun close() {
        handler.post {
            try {
                session?.close()
            } catch (_: Exception) {
            }
            session = null
            device?.close()
            device = null
            meterReader?.close()
            meterReader = null
            previewSurface?.release()
            previewSurface = null
        }
    }

    fun shutdown() {
        close()
        thread.quitSafely()
    }

    @Suppress("DEPRECATION") // createCaptureSession(List, StateCallback, Handler) is simple and still supported.
    private fun startPreviewSession() {
        val dev = device ?: return
        val targets = listOf(previewSurface!!, meterReader!!.surface)
        dev.createCaptureSession(targets, object : CameraCaptureSession.StateCallback() {
            override fun onConfigured(s: CameraCaptureSession) {
                session = s
                meterLight()
            }

            override fun onConfigureFailed(s: CameraCaptureSession) {
                listener.onError("The camera could not start the preview.")
            }
        }, handler)
    }

    /**
     * Measure the light with auto exposure for up to 45 frames, then switch to the fixed short
     * exposure with ISO raised to keep the same brightness.
     */
    fun meterLight() {
        handler.post {
            val s = session ?: return@post
            val dev = device ?: return@post
            listener.onStatus("Measuring the light. Hold the phone still.")
            val b = dev.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW)
            b.addTarget(previewSurface!!)
            b.addTarget(meterReader!!.surface)
            b.set(CaptureRequest.CONTROL_MODE, CameraMetadata.CONTROL_MODE_AUTO)
            b.set(CaptureRequest.CONTROL_AE_MODE, CameraMetadata.CONTROL_AE_MODE_ON)
            var count = 0
            var done = false
            s.setRepeatingRequest(b.build(), object : CameraCaptureSession.CaptureCallback() {
                override fun onCaptureCompleted(session: CameraCaptureSession, request: CaptureRequest, result: TotalCaptureResult) {
                    if (done) return
                    count++
                    val state = result.get(CaptureResult.CONTROL_AE_STATE)
                    val converged = state == CameraMetadata.CONTROL_AE_STATE_CONVERGED ||
                        state == CameraMetadata.CONTROL_AE_STATE_FLASH_REQUIRED
                    if ((converged && count >= 10) || count >= 45) {
                        done = true
                        val autoExp = result.get(CaptureResult.SENSOR_EXPOSURE_TIME)
                        val autoIso = result.get(CaptureResult.SENSOR_SENSITIVITY)
                        handler.post { startManualPreview(autoExp, autoIso) }
                    }
                }
            }, handler)
        }
    }

    private fun startManualPreview(autoExposureNs: Long?, autoIso: Int?) {
        val s = session ?: return
        val dev = device ?: return
        val isoRange = characteristics.get(CameraCharacteristics.SENSOR_INFO_SENSITIVITY_RANGE)
        manualIso = if (autoExposureNs != null && autoIso != null && isoRange != null) {
            Exposure.compensatedIso(autoExposureNs, autoIso, exposureNs, isoRange.lower, isoRange.upper)
        } else {
            isoRange?.upper ?: 800
        }
        val b = dev.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW)
        b.addTarget(previewSurface!!)
        b.addTarget(meterReader!!.surface)
        if (manualSupported) applyManual(b)
        s.setRepeatingRequest(b.build(), probeCallback, handler)
        meter.reset()
        listener.onReady(manualSupported)
        if (manualSupported) {
            listener.onStatus("Ready. Exposure ${exposureNs / 1000} us, ISO $manualIso.")
        } else {
            listener.onStatus("This camera cannot turn off auto exposure or anti-banding. Recording is not available.")
        }
    }

    private val probeCallback = object : CameraCaptureSession.CaptureCallback() {
        override fun onCaptureCompleted(session: CameraCaptureSession, request: CaptureRequest, result: TotalCaptureResult) {
            probeSink?.invoke(result)
        }
    }

    /** Collect [n] capture results from the running preview, then call [done] on the camera thread. */
    fun probe(n: Int, done: (List<TotalCaptureResult>) -> Unit) {
        handler.post {
            val list = ArrayList<TotalCaptureResult>()
            probeSink = { r ->
                list.add(r)
                if (list.size >= n) {
                    probeSink = null
                    done(list)
                }
            }
            handler.postDelayed({
                if (probeSink != null) {
                    probeSink = null
                    done(list)
                }
            }, 5000)
        }
    }

    private fun applyManual(b: CaptureRequest.Builder) {
        b.set(CaptureRequest.CONTROL_MODE, CameraMetadata.CONTROL_MODE_AUTO)
        b.set(CaptureRequest.CONTROL_AE_MODE, CameraMetadata.CONTROL_AE_MODE_OFF)
        b.set(CaptureRequest.CONTROL_AE_ANTIBANDING_MODE, CameraMetadata.CONTROL_AE_ANTIBANDING_MODE_OFF)
        b.set(CaptureRequest.SENSOR_EXPOSURE_TIME, exposureNs)
        b.set(CaptureRequest.SENSOR_SENSITIVITY, manualIso)
        b.set(CaptureRequest.SENSOR_FRAME_DURATION, CaptureConfig.FRAME_DURATION_NS)
        b.set(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, Range(CaptureConfig.FPS, CaptureConfig.FPS))
        val stab = characteristics.get(CameraCharacteristics.CONTROL_AVAILABLE_VIDEO_STABILIZATION_MODES) ?: IntArray(0)
        if (CameraMetadata.CONTROL_VIDEO_STABILIZATION_MODE_OFF in stab) {
            b.set(CaptureRequest.CONTROL_VIDEO_STABILIZATION_MODE, CameraMetadata.CONTROL_VIDEO_STABILIZATION_MODE_OFF)
        }
        val af = characteristics.get(CameraCharacteristics.CONTROL_AF_AVAILABLE_MODES) ?: IntArray(0)
        if (CameraMetadata.CONTROL_AF_MODE_CONTINUOUS_VIDEO in af) {
            b.set(CaptureRequest.CONTROL_AF_MODE, CameraMetadata.CONTROL_AF_MODE_CONTINUOUS_VIDEO)
        }
    }

    private fun onMeterImage(reader: ImageReader) {
        val image = reader.acquireLatestImage() ?: return
        try {
            val plane = image.planes[0]
            val buf = plane.buffer
            val n = buf.remaining()
            if (meterBytes.size != n) meterBytes = ByteArray(n)
            buf.get(meterBytes)
            val rows = BandMeter.rowMeansLinear(meterBytes, image.width, image.height, plane.rowStride)
            listener.onMeter(meter.update(rows))
        } catch (e: Exception) {
            Log.w(TAG, "meter frame skipped", e)
        } finally {
            image.close()
        }
    }

    // ---------------------------------------------------------------- recording

    /** Start recording to [file]. [hintDeg] goes to MediaMuxer.setOrientationHint; pixels are not rotated. */
    fun startRecording(file: File, hintDeg: Int) {
        handler.post {
            val dev = device ?: return@post
            if (!manualSupported) {
                listener.onError("Recording is not available on this camera.")
                return@post
            }
            results.clear(); lostFrames.clear(); failedFrames.clear()
            val enc = try {
                Encoder(file, videoSize, hintDeg)
            } catch (e: Exception) {
                listener.onError("The video encoder could not start: ${e.message}")
                return@post
            }
            encoder = enc
            recordingFile = file
            recordingHint = hintDeg
            recordingWallClock = WallClock.sample()
            recordingWithoutMeter = false
            createRecordingSession(dev, enc, withMeter = true)
        }
    }

    @Suppress("DEPRECATION")
    private fun createRecordingSession(dev: CameraDevice, enc: Encoder, withMeter: Boolean) {
        val targets = if (withMeter) listOf(previewSurface!!, enc.inputSurface, meterReader!!.surface)
        else listOf(previewSurface!!, enc.inputSurface)
        dev.createCaptureSession(targets, object : CameraCaptureSession.StateCallback() {
            override fun onConfigured(s: CameraCaptureSession) {
                session = s
                val b = dev.createCaptureRequest(CameraDevice.TEMPLATE_RECORD)
                for (t in targets) b.addTarget(t)
                applyManual(b)
                meter.reset()
                s.setRepeatingRequest(b.build(), recordCallback, handler)
                listener.onStatus(if (withMeter) "Recording." else "Recording. The meter is paused on this phone while recording.")
            }

            override fun onConfigureFailed(s: CameraCaptureSession) {
                if (withMeter) {
                    recordingWithoutMeter = true
                    createRecordingSession(dev, enc, withMeter = false)
                } else {
                    enc.abort()
                    encoder = null
                    listener.onError("The camera could not start recording.")
                    startPreviewSession()
                }
            }
        }, handler)
    }

    private var stopRequested: (() -> Unit)? = null

    private val recordCallback = object : CameraCaptureSession.CaptureCallback() {
        override fun onCaptureCompleted(session: CameraCaptureSession, request: CaptureRequest, result: TotalCaptureResult) {
            val ts = result.get(CaptureResult.SENSOR_TIMESTAMP) ?: return
            results.add(
                FrameMeta(
                    frameNumber = result.frameNumber,
                    sensorTimestampNs = ts,
                    exposureNs = result.get(CaptureResult.SENSOR_EXPOSURE_TIME),
                    frameDurationNs = result.get(CaptureResult.SENSOR_FRAME_DURATION),
                    rollingShutterSkewNs = result.get(CaptureResult.SENSOR_ROLLING_SHUTTER_SKEW),
                    iso = result.get(CaptureResult.SENSOR_SENSITIVITY),
                ),
            )
        }

        override fun onCaptureFailed(session: CameraCaptureSession, request: CaptureRequest, failure: CaptureFailure) {
            failedFrames.add(failure.frameNumber)
        }

        override fun onCaptureBufferLost(session: CameraCaptureSession, request: CaptureRequest, target: Surface, frameNumber: Long) {
            if (target == encoder?.inputSurface) lostFrames.add(frameNumber)
        }

        override fun onCaptureSequenceCompleted(session: CameraCaptureSession, sequenceId: Int, frameNumber: Long) {
            stopRequested?.invoke()
        }

        override fun onCaptureSequenceAborted(session: CameraCaptureSession, sequenceId: Int) {
            stopRequested?.invoke()
        }
    }

    /**
     * Stop the repeating request, wait for the last capture (max 1 s), end the encoder stream,
     * then return everything collected. [done] runs on the camera thread.
     */
    fun stopRecording(done: (RecordingOutput) -> Unit) {
        handler.post {
            val enc = encoder ?: return@post
            var finished = false
            val finish = {
                if (!finished) {
                    finished = true
                    stopRequested = null
                    val err = enc.finish()
                    encoder = null
                    val out = RecordingOutput(
                        videoFile = recordingFile!!,
                        encodedPtsUs = enc.ptsUs.toList(),
                        results = results.toList(),
                        bufferLostFrameNumbers = lostFrames.toList(),
                        captureFailedFrameNumbers = failedFrames.toList(),
                        sessionWithoutMeter = recordingWithoutMeter,
                        wallClock = recordingWallClock!!,
                        orientationHintDeg = recordingHint,
                        requestedExposureNs = exposureNs,
                        requestedIso = manualIso,
                        encoderError = err,
                    )
                    startPreviewSessionManual()
                    done(out)
                }
            }
            stopRequested = { handler.post(finish) }
            try {
                session?.stopRepeating()
            } catch (e: Exception) {
                Log.w(TAG, "stopRepeating failed", e)
                handler.post(finish)
            }
            handler.postDelayed(finish, 1000)
        }
    }

    @Suppress("DEPRECATION")
    private fun startPreviewSessionManual() {
        val dev = device ?: return
        val targets = listOf(previewSurface!!, meterReader!!.surface)
        dev.createCaptureSession(targets, object : CameraCaptureSession.StateCallback() {
            override fun onConfigured(s: CameraCaptureSession) {
                session = s
                val b = dev.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW)
                for (t in targets) b.addTarget(t)
                applyManual(b)
                s.setRepeatingRequest(b.build(), probeCallback, handler)
                meter.reset()
            }

            override fun onConfigureFailed(s: CameraCaptureSession) {
                listener.onError("The camera could not restart the preview.")
            }
        }, handler)
    }

    companion object {
        private const val TAG = "GridprintCamera"
    }
}

/** Wall-clock sampling paired with SystemClock.elapsedRealtimeNanos(). */
object WallClock {
    fun sample(): WallClockSample {
        val before = SystemClock.elapsedRealtimeNanos()
        var name = "android_system_wall_clock"
        var wallMs = System.currentTimeMillis()
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            try {
                wallMs = SystemClock.currentNetworkTimeClock().millis()
                name = "android_network_time_clock"
            } catch (_: java.time.DateTimeException) {
                // No network time yet: keep the system wall clock.
            }
        }
        val after = SystemClock.elapsedRealtimeNanos()
        return WallClockSample(wallMs * 1_000_000L, before + (after - before) / 2, name)
    }
}
