// Host unit tests for the pure C parts of the Node firmware (no ESP-IDF needed).
// Build and run from node/firmware/test_host:
//   gcc -O2 -Wall -Wextra -I../main test_host.c ../main/freq_calc.c ../main/nmea.c ../main/sample_buffer.c -lm -o test_host
//   ./test_host
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "freq_calc.h"
#include "nmea.h"
#include "sample_buffer.h"

static int failures;
#define CHECK(c)                                                         \
    do {                                                                 \
        if (!(c)) {                                                      \
            printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c);           \
            failures++;                                                  \
        }                                                                \
    } while (0)

static double urand(unsigned *s)
{
    *s = *s * 1103515245u + 12345u;
    return ((*s >> 8) & 0xFFFF) / 65535.0;
}

// Edges of a mains signal at f_hz on a local timer that runs us_per_s per true second.
static int make_edges(int64_t *t, int max, double f_hz, double us_per_s, double t0_us, double dur_s,
                      double jitter_us, unsigned seed)
{
    int n = 0;
    double period = us_per_s / f_hz;
    for (double x = t0_us; x < t0_us + dur_s * us_per_s && n < max; x += period) {
        t[n++] = (int64_t)llround(x + (urand(&seed) - 0.5) * 2.0 * jitter_us);
    }
    return n;
}

static void test_clean(void)
{
    int64_t t[400];
    int n = make_edges(t, 400, 50.0123, 1000000.0, 0.0, 3.0, 0.0, 1);
    freq_result_t r;
    freq_from_edges(t, n, 1000000, 2000000, 1000000.0, 50.0, &r);
    CHECK(r.ok);
    CHECK(fabs(r.freq_hz - 50.0123) < 1e-4);
    CHECK(r.n_periods >= 49 && r.n_periods <= 51);
}

static void test_jitter_and_drift(void)
{
    // local timer 30 ppm fast, +-3 us interrupt jitter, 59.98 Hz on a 60 Hz grid
    int64_t t[400];
    double us = 1000030.0;
    int n = make_edges(t, 400, 59.98, us, 0.0, 3.0, 3.0, 7);
    freq_result_t r;
    freq_from_edges(t, n, (int64_t)us, (int64_t)(2 * us), us, 60.0, &r);
    CHECK(r.ok);
    CHECK(fabs(r.freq_hz - 59.98) < 2e-3);
}

static void test_glitches_and_missed_edges(void)
{
    int64_t a[400], b[500];
    int n = make_edges(a, 400, 49.97, 1000000.0, 0.0, 3.0, 1.0, 3);
    int m = 0;
    for (int i = 0; i < n; i++) {
        if (i == 70 || i == 71) continue;           // two missed edges
        b[m++] = a[i];
        if (i % 9 == 0) b[m++] = a[i] + 3000;     // noise edge 3 ms after a real edge (harmonic/ringing)
    }
    freq_result_t r;
    freq_from_edges(b, m, 1000000, 2000000, 1000000.0, 50.0, &r);
    CHECK(r.ok);
    CHECK(r.n_glitches > 0);
    CHECK(r.n_rejected >= 1);
    CHECK(fabs(r.freq_hz - 49.97) < 1e-3);
}

static void test_too_few_edges(void)
{
    int64_t t[400];
    int n = make_edges(t, 400, 50.0, 1000000.0, 0.0, 1.3, 0.0, 1);  // window [1 s, 2 s) has 15 edges
    freq_result_t r;
    freq_from_edges(t, n, 1000000, 2000000, 1000000.0, 50.0, &r);
    CHECK(!r.ok);
}

static void test_nmea(void)
{
    int64_t utc;
    int valid;
    // checksum computed for this test sentence; position fields are dummies
    const char *base = "GPRMC,000000.00,A,0000.0000,N,00000.0000,E,0.0,0.0,210926,,,A";
    unsigned char sum = 0;
    for (const char *p = base; *p; p++) sum ^= (unsigned char)*p;
    char line[128];
    snprintf(line, sizeof(line), "$%s*%02X\r\n", base, sum);
    CHECK(nmea_parse_rmc(line, &utc, &valid) == 1);
    CHECK(utc == 1789948800LL);  // 2026-09-21T00:00:00Z
    CHECK(valid == 1);
    line[10] = '1';  // corrupt -> checksum fails
    CHECK(nmea_parse_rmc(line, &utc, &valid) == 0);
    CHECK(nmea_parse_rmc("$GPGGA,000000.00*00", &utc, &valid) == 0);
    CHECK(nmea_days_from_civil(1970, 1, 1) == 0);
    CHECK(nmea_days_from_civil(2000, 3, 1) == 11017);
}

static void test_buffer(void)
{
    sample_t store[3];
    sample_buffer_t b;
    sb_init(&b, store, 3);
    for (int i = 0; i < 5; i++) {
        sample_t s = {.t_utc_s = i, .freq_hz = 50.0};
        sb_push(&b, &s);
    }
    sample_t o;
    CHECK(b.count == 3 && b.dropped == 2);
    CHECK(sb_peek(&b, &o) && o.t_utc_s == 2);
    sb_pop(&b);
    CHECK(sb_peek(&b, &o) && o.t_utc_s == 3);
    sb_pop(&b);
    sb_pop(&b);
    CHECK(!sb_peek(&b, &o));
}

int main(void)
{
    test_clean();
    test_jitter_and_drift();
    test_glitches_and_missed_edges();
    test_too_few_edges();
    test_nmea();
    test_buffer();
    if (failures) {
        printf("%d FAILED\n", failures);
        return 1;
    }
    printf("ALL HOST TESTS PASSED\n");
    return 0;
}
