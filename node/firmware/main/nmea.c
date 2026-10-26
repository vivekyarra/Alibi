#include "nmea.h"

#include <ctype.h>
#include <stdlib.h>
#include <string.h>

int64_t nmea_days_from_civil(int y, unsigned m, unsigned d)
{
    y -= m <= 2;
    const int64_t era = (y >= 0 ? y : y - 399) / 400;
    const unsigned yoe = (unsigned)(y - era * 400);
    const unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + (int64_t)doe - 719468;
}

static int hexval(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    c = (char)toupper((unsigned char)c);
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int two(const char *s)
{
    if (!isdigit((unsigned char)s[0]) || !isdigit((unsigned char)s[1])) return -1;
    return (s[0] - '0') * 10 + (s[1] - '0');
}

int nmea_parse_rmc(const char *line, int64_t *utc_s, int *valid)
{
    if (line[0] != '$' || strncmp(line + 3, "RMC,", 4) != 0) {
        return 0;
    }
    const char *star = strchr(line, '*');
    if (star == NULL || hexval(star[1]) < 0 || hexval(star[2]) < 0) {
        return 0;
    }
    unsigned char sum = 0;
    for (const char *p = line + 1; p < star; p++) {
        sum ^= (unsigned char)*p;
    }
    if (sum != (unsigned char)(hexval(star[1]) * 16 + hexval(star[2]))) {
        return 0;
    }
    // fields: 0 talker+RMC, 1 time hhmmss.ss, 2 status, 3-6 position (ignored), 7 speed, 8 course, 9 date ddmmyy
    const char *f[12] = {0};
    int nf = 0;
    f[nf++] = line;
    for (const char *p = line; p < star && nf < 12; p++) {
        if (*p == ',') f[nf++] = p + 1;
    }
    if (nf < 10) return 0;
    int hh = two(f[1]), mm = two(f[1] + 2), ss = two(f[1] + 4);
    int dd = two(f[9]), mo = two(f[9] + 2), yy = two(f[9] + 4);
    if (hh < 0 || mm < 0 || ss < 0 || dd < 1 || mo < 1 || mo > 12 || yy < 0 || hh > 23 || mm > 59 || ss > 60) {
        return 0;
    }
    int64_t days = nmea_days_from_civil(2000 + yy, (unsigned)mo, (unsigned)dd);
    *utc_s = days * 86400 + hh * 3600 + mm * 60 + ss;
    *valid = (f[2][0] == 'A');
    return 1;
}
