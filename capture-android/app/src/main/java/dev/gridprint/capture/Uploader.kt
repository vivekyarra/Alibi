package dev.gridprint.capture

import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * Upload through the GRIDPRINT API (SPEC 10.1):
 *  1. POST {api}/v1/jobs                -> {job_id, upload_url, upload_method: "PUT"}
 *  2. PUT the video bytes to upload_url (presigned URL)
 *  3. POST {api}/v1/jobs/{job_id}/start with {"claim": {"claimed_zone": zone}, "sidecar": {...}}
 *     ("sidecar" is left out when no sidecar was written).
 */
object Uploader {
    fun upload(apiBase: String, video: File, zone: String, sidecarJson: String?, progress: (String) -> Unit): String {
        val base = apiBase.trim().trimEnd('/')
        require(base.startsWith("https://") || base.startsWith("http://")) { "The API address must start with https://" }

        progress("Creating the job.")
        val created = JSONObject(request("POST", "$base/v1/jobs", "{}".toByteArray(), "application/json"))
        val jobId = created.getString("job_id")
        val uploadUrl = created.getString("upload_url")
        val method = created.optString("upload_method", "PUT")
        if (method != "PUT") throw IOException("The API asked for upload method $method. Only PUT is supported.")

        progress("Uploading the video.")
        put(uploadUrl, video)

        progress("Starting the analysis.")
        val body = StringBuilder()
        body.append("{\"claim\":{\"claimed_zone\":").append(Json.quote(zone)).append('}')
        if (sidecarJson != null) body.append(",\"sidecar\":").append(sidecarJson)
        body.append('}')
        request("POST", "$base/v1/jobs/${jobId}/start", body.toString().toByteArray(Charsets.UTF_8), "application/json")
        return jobId
    }

    private fun request(method: String, url: String, body: ByteArray, contentType: String): String {
        val c = URL(url).openConnection() as HttpURLConnection
        try {
            c.requestMethod = method
            c.connectTimeout = 15_000
            c.readTimeout = 60_000
            c.doOutput = true
            c.setRequestProperty("Content-Type", contentType)
            c.setFixedLengthStreamingMode(body.size)
            c.outputStream.use { it.write(body) }
            val code = c.responseCode
            val text = (if (code in 200..299) c.inputStream else c.errorStream)?.bufferedReader()?.use { it.readText() } ?: ""
            if (code !in 200..299) throw IOException("$method $url returned HTTP $code: ${text.take(300)}")
            return text
        } finally {
            c.disconnect()
        }
    }

    private fun put(url: String, file: File) {
        val c = URL(url).openConnection() as HttpURLConnection
        try {
            c.requestMethod = "PUT"
            c.connectTimeout = 15_000
            c.readTimeout = 300_000
            c.doOutput = true
            c.setRequestProperty("Content-Type", "video/mp4")
            c.setFixedLengthStreamingMode(file.length())
            c.outputStream.use { out -> file.inputStream().use { it.copyTo(out, 1 shl 16) } }
            val code = c.responseCode
            if (code !in 200..299) {
                val text = c.errorStream?.bufferedReader()?.use { it.readText() } ?: ""
                throw IOException("Upload returned HTTP $code: ${text.take(300)}")
            }
        } finally {
            c.disconnect()
        }
    }
}
