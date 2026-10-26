package dev.gridprint.capture

import android.Manifest
import android.app.Activity
import android.content.ContentValues
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.SurfaceTexture
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import android.text.InputType
import android.view.Gravity
import android.view.OrientationEventListener
import android.view.TextureView
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * GRIDPRINT Capture: one Activity with three views built in code (no XML layouts, no AndroidX):
 * consent notice (first run), capture screen, and Device check panel (over the capture screen, so
 * the camera keeps running for the probe).
 */
class MainActivity : Activity(), CameraController.Listener {

    private val prefs by lazy { getSharedPreferences("gridprint", MODE_PRIVATE) }
    private var camera: CameraController? = null

    private lateinit var texture: TextureView
    private lateinit var meterBar: ProgressBar
    private lateinit var meterText: TextView
    private lateinit var status: TextView
    private lateinit var zoneSpinner: Spinner
    private lateinit var apiField: EditText
    private lateinit var recordButton: Button
    private lateinit var uploadButton: Button
    private lateinit var saveButton: Button
    private lateinit var checkPanel: ScrollView
    private lateinit var checkText: TextView

    private var recording = false
    private var ready = false
    private var deviceOrientation = 0
    private var orientationListener: OrientationEventListener? = null

    /** Last finished recording. */
    private var lastVideo: File? = null
    private var lastSidecar: File? = null
    private var lastLog: File? = null
    private var lastZone: String? = null
    private var lastCapability: File? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        if (prefs.getBoolean(KEY_CONSENT, false)) showCapture() else showConsent()
    }

    override fun onDestroy() {
        orientationListener?.disable()
        camera?.shutdown()
        camera = null
        super.onDestroy()
    }

    override fun onPause() {
        super.onPause()
        if (recording) stopRecording()
    }

    // ------------------------------------------------------------------ consent

    private fun showConsent() {
        val col = column()
        col.addView(title("Before you start"))
        col.addView(body(CONSENT_TEXT))
        val agree = button("I agree") {
            prefs.edit().putBoolean(KEY_CONSENT, true).apply()
            showCapture()
        }
        col.addView(agree)
        col.addView(button("Exit") { finish() })
        setContentView(ScrollView(this).apply { addView(col) })
    }

    // ------------------------------------------------------------------ capture screen

    private fun showCapture() {
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.CAMERA), REQ_CAMERA)
            val col = column()
            col.addView(body("GRIDPRINT Capture needs the camera permission to record video."))
            col.addView(button("Ask again") { showCapture() })
            setContentView(col)
            return
        }
        val root = FrameLayout(this)
        root.setBackgroundColor(Color.BLACK)

        texture = TextureView(this)
        root.addView(texture, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP))

        val controls = column().apply { setBackgroundColor(0xCC000000.toInt()) }
        meterText = body("Band strength: waiting for frames")
        meterBar = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100
            contentDescription = "Band strength meter"
        }
        controls.addView(meterText)
        controls.addView(meterBar)

        zoneSpinner = Spinner(this)
        val zoneItems = listOf("Choose grid zone") + CaptureConfig.ZONES
        zoneSpinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, zoneItems)
        zoneSpinner.contentDescription = "Grid zone"
        val savedZone = prefs.getString(KEY_ZONE, null)
        if (savedZone != null && savedZone in CaptureConfig.ZONES) zoneSpinner.setSelection(zoneItems.indexOf(savedZone))
        zoneSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                val z = selectedZone()
                if (z != null) prefs.edit().putString(KEY_ZONE, z).apply()
                if (z != null && CaptureConfig.ZONE_NOMINAL_HZ[z] == 60) {
                    setStatus("In 60 Hz zones the bands can stand still at 30 fps. The meter can read low even when bands exist.")
                }
                updateButtons()
            }

            override fun onNothingSelected(parent: AdapterView<*>?) = updateButtons()
        }
        controls.addView(zoneSpinner)

        apiField = EditText(this).apply {
            hint = "API address, for example https://api.example.org"
            inputType = InputType.TYPE_TEXT_VARIATION_URI
            setText(prefs.getString(KEY_API, ""))
            setTextColor(Color.WHITE)
            setHintTextColor(Color.LTGRAY)
            contentDescription = "API address"
        }
        controls.addView(apiField)

        val row1 = row()
        recordButton = button("Record") { if (recording) stopRecording() else startRecording() }
        row1.addView(recordButton, weight())
        row1.addView(button("Measure light") { camera?.meterLight() }, weight())
        row1.addView(button("Device check") { runDeviceCheck() }, weight())
        controls.addView(row1)

        val row2 = row()
        uploadButton = button("Upload") { upload() }
        saveButton = button("Save to phone") { saveRecording() }
        row2.addView(uploadButton, weight())
        row2.addView(saveButton, weight())
        controls.addView(row2)

        status = body("Starting the camera.")
        controls.addView(status)
        root.addView(controls, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM))

        checkText = body("")
        val checkCol = column().apply {
            setBackgroundColor(0xF0101010.toInt())
            addView(title("Device check"))
            addView(checkText)
            addView(button("Save report to phone") { saveCapability() })
            addView(button("Close") { checkPanel.visibility = View.GONE })
        }
        checkPanel = ScrollView(this).apply {
            addView(checkCol)
            visibility = View.GONE
        }
        root.addView(checkPanel, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))

        setContentView(root)
        updateButtons()

        orientationListener = object : OrientationEventListener(this) {
            override fun onOrientationChanged(orientation: Int) {
                if (orientation == ORIENTATION_UNKNOWN) return
                deviceOrientation = ((orientation + 45) / 90 * 90) % 360
            }
        }.also { it.enable() }

        val cam = CameraController(this, this)
        if (!cam.selectCamera()) {
            setStatus("No usable back camera was found.")
            return
        }
        camera = cam
        // Preview aspect: buffers are landscape (sensor); the portrait view shows them rotated.
        val w = resources.displayMetrics.widthPixels
        texture.layoutParams = FrameLayout.LayoutParams(w, w * cam.videoSize.width / cam.videoSize.height, Gravity.TOP)
        texture.surfaceTextureListener = object : TextureView.SurfaceTextureListener {
            override fun onSurfaceTextureAvailable(st: SurfaceTexture, width: Int, height: Int) = cam.open(st)
            override fun onSurfaceTextureSizeChanged(st: SurfaceTexture, width: Int, height: Int) {}
            override fun onSurfaceTextureDestroyed(st: SurfaceTexture): Boolean = true
            override fun onSurfaceTextureUpdated(st: SurfaceTexture) {}
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_CAMERA && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) showCapture()
    }

    private fun selectedZone(): String? = CaptureConfig.ZONES.getOrNull(zoneSpinner.selectedItemPosition - 1)

    private fun updateButtons() {
        if (!::recordButton.isInitialized) return
        recordButton.isEnabled = ready && (recording || selectedZone() != null)
        recordButton.text = if (recording) "Stop" else "Record"
        uploadButton.isEnabled = !recording && lastVideo != null
        saveButton.isEnabled = !recording && lastVideo != null
    }

    // ------------------------------------------------------------------ recording

    private fun startRecording() {
        val cam = camera ?: return
        val zone = selectedZone() ?: run { setStatus("Choose the grid zone first."); return }
        val dir = getExternalFilesDir(Environment.DIRECTORY_MOVIES) ?: filesDir
        val stamp = SimpleDateFormat("yyyyMMdd'T'HHmmss'Z'", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }.format(Date())
        val file = File(dir, "gridprint_$stamp.mp4")
        // Back camera: display rotation = (sensor orientation + device rotation) mod 360. Pixels are not rotated.
        val hint = (cam.sensorOrientation + deviceOrientation) % 360
        lastZone = zone
        recording = true
        updateButtons()
        cam.startRecording(file, hint)
    }

    private fun stopRecording() {
        val cam = camera ?: return
        recording = false
        updateButtons()
        setStatus("Stopping. Writing the files.")
        val zone = lastZone ?: return
        cam.stopRecording { out -> Thread { finishRecording(cam, out, zone) }.start() }
    }

    private fun finishRecording(cam: CameraController, out: CameraController.RecordingOutput, zone: String) {
        val video = out.videoFile
        if (!video.exists() || video.length() == 0L) {
            runOnUiThread { setStatus("The video was not written. ${out.encoderError ?: ""}") }
            return
        }
        val sha = Sha256.ofFile(video)
        val alignment = FrameAligner.align(out.encodedPtsUs, out.results)
        val outcome = SidecarBuilder.build(
            alignment = alignment,
            appVersion = appVersion(),
            deviceModel = DeviceCheck.deviceModel(),
            sensorOrientation = cam.sensorOrientation,
            timestampSourceRealtime = cam.timestampSourceRealtime,
            wallClock = out.wallClock,
            zone = zone,
            videoSha256 = sha,
        )
        val base = video.name.removeSuffix(".mp4")
        val sidecarFile = File(video.parentFile, "$base.sidecar.json")
        val logFile = File(video.parentFile, "$base.capture_log.json")
        if (outcome is SidecarOutcome.Written) sidecarFile.writeText(outcome.sidecar.toJson()) else sidecarFile.delete()
        logFile.writeText(
            CaptureLog.toJson(
                videoFileName = video.name,
                alignment = alignment,
                capturedResults = out.results.size,
                bufferLostFrameNumbers = out.bufferLostFrameNumbers,
                captureFailedFrameNumbers = out.captureFailedFrameNumbers,
                sessionWithoutMeter = out.sessionWithoutMeter,
                outcome = outcome,
                requestedExposureNs = out.requestedExposureNs,
                requestedIso = out.requestedIso,
                requestedFrameDurationNs = CaptureConfig.FRAME_DURATION_NS,
                orientationHintDeg = out.orientationHintDeg,
            ),
        )
        val msg = StringBuilder("Saved ${video.name}: ${alignment.encodedFrames} frames.")
        if (alignment.droppedInside.isNotEmpty()) {
            msg.append(" The encoder dropped ${alignment.droppedInside.size} frames. They are listed in the capture log.")
        }
        when (outcome) {
            is SidecarOutcome.Written -> msg.append(" Sidecar written.")
            is SidecarOutcome.NotWritten -> msg.append(" No sidecar: ${outcome.reasons.joinToString("; ")}.")
        }
        out.encoderError?.let { msg.append(" Encoder note: $it") }
        runOnUiThread {
            lastVideo = video
            lastSidecar = if (outcome is SidecarOutcome.Written) sidecarFile else null
            lastLog = logFile
            setStatus(msg.toString())
            updateButtons()
        }
    }

    // ------------------------------------------------------------------ upload and save

    private fun upload() {
        val video = lastVideo ?: return
        val zone = lastZone ?: return
        val api = apiField.text.toString().trim()
        if (api.isEmpty()) {
            setStatus("Enter the API address first.")
            return
        }
        prefs.edit().putString(KEY_API, api).apply()
        val sidecarJson = lastSidecar?.readText()
        uploadButton.isEnabled = false
        Thread {
            val text = try {
                val jobId = Uploader.upload(api, video, zone, sidecarJson) { p -> runOnUiThread { setStatus(p) } }
                "Uploaded. Job id: $jobId. Open GRIDPRINT Verify to see the result."
            } catch (e: Exception) {
                "Upload failed: ${e.message}"
            }
            runOnUiThread {
                setStatus(text)
                updateButtons()
            }
        }.start()
    }

    private fun saveRecording() {
        val video = lastVideo ?: return
        Thread {
            val text = try {
                copyToMediaStore(video, "video/mp4", MediaStore.Video.Media.EXTERNAL_CONTENT_URI, Environment.DIRECTORY_MOVIES + "/GRIDPRINT")
                lastSidecar?.let { copyToMediaStore(it, "application/json", MediaStore.Downloads.EXTERNAL_CONTENT_URI, Environment.DIRECTORY_DOWNLOADS + "/GRIDPRINT") }
                lastLog?.let { copyToMediaStore(it, "application/json", MediaStore.Downloads.EXTERNAL_CONTENT_URI, Environment.DIRECTORY_DOWNLOADS + "/GRIDPRINT") }
                "Saved. Video in Movies/GRIDPRINT, sidecar and capture log in Download/GRIDPRINT."
            } catch (e: Exception) {
                "Save failed: ${e.message}"
            }
            runOnUiThread { setStatus(text) }
        }.start()
    }

    private fun saveCapability() {
        val f = lastCapability ?: return
        Thread {
            val text = try {
                copyToMediaStore(f, "application/json", MediaStore.Downloads.EXTERNAL_CONTENT_URI, Environment.DIRECTORY_DOWNLOADS + "/GRIDPRINT")
                "Report saved in Download/GRIDPRINT."
            } catch (e: Exception) {
                "Save failed: ${e.message}"
            }
            runOnUiThread { checkText.append("\n\n$text") }
        }.start()
    }

    /** Byte-exact copy, so the SHA-256 in the sidecar still matches the saved video. */
    private fun copyToMediaStore(src: File, mime: String, collection: Uri, relativePath: String) {
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, src.name)
            put(MediaStore.MediaColumns.MIME_TYPE, mime)
            put(MediaStore.MediaColumns.RELATIVE_PATH, relativePath)
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val uri = contentResolver.insert(collection, values) ?: throw IllegalStateException("MediaStore insert failed")
        contentResolver.openOutputStream(uri)?.use { out -> src.inputStream().use { it.copyTo(out) } }
            ?: throw IllegalStateException("Cannot open the output file")
        values.clear()
        values.put(MediaStore.MediaColumns.IS_PENDING, 0)
        contentResolver.update(uri, values, null, null)
    }

    // ------------------------------------------------------------------ device check

    private fun runDeviceCheck() {
        val cam = camera ?: return
        checkPanel.visibility = View.VISIBLE
        checkText.text = "Checking the camera. Point it at a lit room and hold still."
        cam.probe(30) { results ->
            val error = if (results.isEmpty()) "no capture results within 5 s" else null
            val report = DeviceCheck.build(cam.characteristics, cam.cameraId, appVersion(), results, error)
            val file = File(getExternalFilesDir(null) ?: filesDir, CaptureConfig.CAPABILITY_FILE)
            file.writeText(report.toJson())
            runOnUiThread {
                lastCapability = file
                checkText.text = DeviceCheck.summary(report) + "\n\nWritten to ${file.absolutePath}"
            }
        }
    }

    // ------------------------------------------------------------------ CameraController.Listener

    override fun onMeter(score: Double?) {
        runOnUiThread {
            if (!::meterBar.isInitialized) return@runOnUiThread
            meterBar.progress = BandMeter.barPercent(score)
            meterText.text = if (score == null) "Band strength: measuring" else
                String.format(Locale.US, "Band strength: %.2f %% (hold the phone still)", score * 100.0)
        }
    }

    override fun onStatus(text: String) = runOnUiThread { setStatus(text) }

    override fun onError(text: String) = runOnUiThread {
        recording = false
        setStatus(text)
        updateButtons()
    }

    override fun onReady(manualSupported: Boolean) = runOnUiThread {
        ready = manualSupported
        updateButtons()
    }

    // ------------------------------------------------------------------ helpers

    private fun setStatus(text: String) {
        if (::status.isInitialized) status.text = text
    }

    private fun appVersion(): String = try {
        packageManager.getPackageInfo(packageName, 0).versionName ?: "unknown"
    } catch (_: Exception) {
        "unknown"
    }

    private fun column() = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(16), dp(16), dp(16), dp(16))
    }

    private fun row() = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }

    private fun weight() = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)

    private fun title(text: String) = TextView(this).apply {
        this.text = text
        textSize = 22f
        setTextColor(Color.WHITE)
        setPadding(0, 0, 0, dp(12))
    }

    private fun body(text: String) = TextView(this).apply {
        this.text = text
        textSize = 16f
        setTextColor(Color.WHITE)
        setPadding(0, dp(4), 0, dp(4))
    }

    private fun button(text: String, onClick: () -> Unit) = Button(this).apply {
        this.text = text
        setOnClickListener { onClick() }
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    companion object {
        private const val REQ_CAMERA = 1
        private const val KEY_CONSENT = "consent_v1"
        private const val KEY_ZONE = "zone"
        private const val KEY_API = "api"

        const val CONSENT_TEXT = """GRIDPRINT Capture records video with camera settings that keep the faint light bands from mains-powered lights. GRIDPRINT can later compare these bands with a log of the power grid frequency.

What the app stores with each video:
- The video, without sound.
- A sidecar file: camera timing for each frame, exposure time, ISO, phone model, app version, the start time from the phone clock, and the grid zone that you choose.
- A capture log: how video frames match the camera timing, and any frames the phone dropped.

What the app does not collect:
- No GPS or other location. The only place information is the grid zone that you choose, for example India or Continental Europe.
- No account, no contacts, no sound.

The files stay on this phone until you press Upload or Save to phone. Upload sends the video and the sidecar to the GRIDPRINT API address that you enter.

Limits: a GRIDPRINT result is evidence, not certainty. If the lights in the room do not flicker, the result is INCONCLUSIVE. A missing signal does not mean that a video is fake.

Record only people who agree to be recorded."""
    }
}
