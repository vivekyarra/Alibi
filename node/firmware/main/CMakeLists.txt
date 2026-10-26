idf_component_register(
    SRCS "main.c" "freq_calc.c" "nmea.c" "sample_buffer.c"
    INCLUDE_DIRS "."
    EMBED_TXTFILES "../certs/AmazonRootCA1.pem" "../certs/device.pem.crt" "../certs/private.pem.key"
)
