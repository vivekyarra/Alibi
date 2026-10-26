// FIFO of per-second samples kept while the Node is offline (SPEC 10.4 step 4: buffer, back-fill).
// When full, the oldest sample is dropped and counted. Not thread-safe: the caller holds a mutex.
// Pure C, unit-tested on the host (test_host/).
#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int64_t t_utc_s;
    double freq_hz;
    uint8_t quality;   // 0 = gps, 1 = ntp
    uint8_t gps_lock;
} sample_t;

typedef struct {
    sample_t *items;
    int capacity;
    int head;      // index of the oldest sample
    int count;
    uint32_t dropped;
} sample_buffer_t;

void sb_init(sample_buffer_t *b, sample_t *storage, int capacity);
void sb_push(sample_buffer_t *b, const sample_t *s);
int sb_peek(const sample_buffer_t *b, sample_t *out);  // 1 if a sample was copied
void sb_pop(sample_buffer_t *b);

#ifdef __cplusplus
}
#endif
