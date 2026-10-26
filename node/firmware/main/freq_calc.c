#include "freq_calc.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

#define BAND_FRAC 0.10        // step 2: +-10 % of the nominal period
#define MEDIAN_FRAC 0.005     // step 3: +-0.5 % of the median period
#define MIN_CYCLE_FRAC 0.80   // need at least 80 % of the nominal cycles in the second

static int cmp_double(const void *a, const void *b)
{
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

void freq_from_edges(const int64_t *t_us, int n, int64_t t_start_us, int64_t t_end_us, double us_per_s,
                     double nominal_hz, freq_result_t *out)
{
    memset(out, 0, sizeof(*out));
    if (n < 2 || nominal_hz <= 0.0 || us_per_s <= 0.0) {
        return;
    }
    const double t_nom = us_per_s / nominal_hz;  // nominal period in local microseconds
    double periods[FREQ_MAX_PERIODS];
    int np = 0;
    int64_t last = 0;
    int have_last = 0;
    for (int i = 0; i < n; i++) {
        int64_t t = t_us[i];
        if (t >= t_end_us) {
            break;
        }
        if (t >= t_start_us) {
            out->n_edges++;
        }
        if (have_last && (double)(t - last) < 0.5 * t_nom) {
            if (t >= t_start_us) {
                out->n_glitches++;
            }
            continue;
        }
        if (have_last && t >= t_start_us && np < FREQ_MAX_PERIODS) {
            periods[np++] = (double)(t - last);
        }
        last = t;
        have_last = 1;
    }
    // step 2: band filter
    double band[FREQ_MAX_PERIODS];
    int nb = 0;
    for (int i = 0; i < np; i++) {
        if (fabs(periods[i] - t_nom) <= BAND_FRAC * t_nom) {
            band[nb++] = periods[i];
        }
    }
    if (nb == 0) {
        out->n_rejected = np;
        return;
    }
    // step 3: median filter
    double sorted[FREQ_MAX_PERIODS];
    memcpy(sorted, band, sizeof(double) * (size_t)nb);
    qsort(sorted, (size_t)nb, sizeof(double), cmp_double);
    double med = (nb % 2) ? sorted[nb / 2] : 0.5 * (sorted[nb / 2 - 1] + sorted[nb / 2]);
    double sum = 0.0;
    int nk = 0;
    for (int i = 0; i < nb; i++) {
        if (fabs(band[i] - med) <= MEDIAN_FRAC * med) {
            sum += band[i];
            nk++;
        }
    }
    out->n_periods = nk;
    out->n_rejected = np - nk;
    if (nk < (int)ceil(MIN_CYCLE_FRAC * nominal_hz) || sum <= 0.0) {
        return;
    }
    // step 4
    out->freq_hz = us_per_s / (sum / nk);
    out->ok = 1;
}
