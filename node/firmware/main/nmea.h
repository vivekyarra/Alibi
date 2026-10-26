// Minimal NMEA RMC parser: UTC date and time only. The Node never stores or sends position (R4).
// Pure C, unit-tested on the host (test_host/).
#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Days since 1970-01-01 for a proleptic Gregorian date (H. Hinnant's days_from_civil).
int64_t nmea_days_from_civil(int y, unsigned m, unsigned d);

// Parse one sentence ("$GPRMC,..." or "$GNRMC,...", with or without CR/LF).
// Returns 1 and sets *utc_s (whole UTC seconds) and *valid (status 'A') on success; 0 otherwise
// (not RMC, bad checksum, missing date or time).
int nmea_parse_rmc(const char *line, int64_t *utc_s, int *valid);

#ifdef __cplusplus
}
#endif
