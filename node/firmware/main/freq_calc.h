// Frequency for one UTC second from zero-crossing timestamps (SPEC 10.4 firmware steps 1-2).
// Pure C, no ESP-IDF dependency, so it is unit-tested on the host (test_host/).
#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FREQ_MAX_PERIODS 256

typedef struct {
    double freq_hz;    // valid only when ok != 0
    int n_edges;       // edges offered in the window (after the start edge)
    int n_glitches;    // edges dropped because they came too soon after the previous edge
    int n_periods;     // periods used for the estimate
    int n_rejected;    // periods rejected by the band and median filters
    int ok;
} freq_result_t;

// t_us: ascending local timer timestamps (microseconds) of one edge per mains cycle.
//   Pass the last edge before the window too; only periods that END at or after t_start_us count.
// t_start_us, t_end_us: window on the local timer, [t_start_us, t_end_us).
// us_per_s: local timer microseconds in one true second (from the GPS PPS interval; 1e6 if unknown).
// nominal_hz: 50 or 60.
// Steps: (1) drop edges closer than 0.5 nominal periods to the last kept edge (noise, harmonics);
//        (2) keep periods within +-10 % of the nominal period (rejects missed edges);
//        (3) keep periods within +-0.5 % of the median period;
//        (4) frequency = us_per_s / mean(kept periods). Needs >= 80 % of the nominal cycle count.
void freq_from_edges(const int64_t *t_us, int n, int64_t t_start_us, int64_t t_end_us, double us_per_s,
                     double nominal_hz, freq_result_t *out);

#ifdef __cplusplus
}
#endif
