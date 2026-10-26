package dev.gridprint.capture

/**
 * Minimal JSON writer with no Android dependency, so it runs in JVM unit tests.
 * Supported values: null, String, Boolean, Int, Long, Short, Byte, Double, Float, List, Map<String, *>.
 * Map key order is kept (use LinkedHashMap / linkedMapOf for a stable field order).
 */
object Json {
    fun encode(value: Any?): String = StringBuilder().also { write(it, value) }.toString()

    fun quote(s: String): String = StringBuilder().also { writeString(it, s) }.toString()

    private fun write(sb: StringBuilder, value: Any?) {
        when (value) {
            null -> sb.append("null")
            is String -> writeString(sb, value)
            is Boolean -> sb.append(if (value) "true" else "false")
            is Int, is Long, is Short, is Byte -> sb.append(value.toString())
            is Double -> {
                require(value.isFinite()) { "JSON cannot hold a non-finite number: $value" }
                sb.append(value.toString())
            }
            is Float -> write(sb, value.toDouble())
            is Map<*, *> -> {
                sb.append('{')
                var first = true
                for ((k, v) in value) {
                    require(k is String) { "JSON object keys must be strings" }
                    if (!first) sb.append(',')
                    first = false
                    writeString(sb, k)
                    sb.append(':')
                    write(sb, v)
                }
                sb.append('}')
            }
            is Iterable<*> -> {
                sb.append('[')
                var first = true
                for (v in value) {
                    if (!first) sb.append(',')
                    first = false
                    write(sb, v)
                }
                sb.append(']')
            }
            is LongArray -> write(sb, value.toList())
            is IntArray -> write(sb, value.toList())
            else -> throw IllegalArgumentException("Unsupported JSON type: ${value::class.java.name}")
        }
    }

    private fun writeString(sb: StringBuilder, s: String) {
        sb.append('"')
        for (c in s) {
            when (c) {
                '"' -> sb.append("\\\"")
                '\\' -> sb.append("\\\\")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                '\t' -> sb.append("\\t")
                '\b' -> sb.append("\\b")
                '\u000C' -> sb.append("\\f")
                else -> if (c < ' ') sb.append(String.format("\\u%04x", c.code)) else sb.append(c)
            }
        }
        sb.append('"')
    }
}
