# GRIDPRINT Node — Build and flash the firmware

Human task H2, step 5. The firmware is ESP-IDF C for the ESP32 (written for ESP-IDF v5.x; it has not
been compiled on hardware yet — see `docs/agent_notes/node_calibration.md`).

## 1. Install ESP-IDF

1. Follow the official guide: <https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/index.html>.
   Install a v5.x release.
2. Open an "ESP-IDF" terminal (Windows) or run `. $IDF_PATH/export.sh` (Linux, macOS).
3. Check: `idf.py --version` prints a v5.x version.

## 2. Create the device certificate (once per Node)

Needs AWS access (human task H1).

```bash
python node/provision.py --profile gridprint --node-id node-01 --zone IN
```

This writes `node/firmware/certs/device.pem.crt`, `private.pem.key`, `endpoint.txt` and
`certificate_arn.txt`. The folder is git-ignored. Never commit these files.

Then download the Amazon Root CA 1 certificate yourself and save it as
`node/firmware/certs/AmazonRootCA1.pem`:
<https://www.amazontrust.com/repository/AmazonRootCA1.pem>.

The build fails if any of the three files `AmazonRootCA1.pem`, `device.pem.crt`, `private.pem.key` is
missing (they are embedded with `EMBED_TXTFILES`).

## 3. Configure

```bash
cd node/firmware
idf.py set-target esp32
idf.py menuconfig
```

Open **GRIDPRINT Node** and set:

| Option | Value |
|---|---|
| Wi-Fi SSID / password | your network |
| AWS IoT Core data endpoint | the host name in `certs/endpoint.txt` |
| Grid zone id | the zone id from `config/zones.yaml` (for example `IN`) |
| Node id | the same `--node-id` you gave to `provision.py` |
| Nominal grid frequency | 50 or 60 |
| GPIO and UART options | keep the defaults if you wired per `../hardware/schematic.md` |
| NMEA/PPS offset | keep 0 until `../SELFTEST.md` step 6 says otherwise |
| Offline buffer size | default 1800 s (about 43 KB of RAM) |
| SNTP fallback | on (quality `ntp` when there is no GPS lock) |

Save and exit. The values go to `sdkconfig` (do not commit it: it holds the Wi-Fi password).

## 4. Build, flash, monitor

```bash
idf.py build
idf.py -p <PORT> flash monitor
```

`<PORT>` is for example `COM5` on Windows or `/dev/ttyUSB0` on Linux. Exit the monitor with `Ctrl+]`.

Expected log lines (after GPS lock and MQTT connection):

```
I (...) gridprint: GRIDPRINT Node node-01 zone IN nominal 50 Hz
I (...) gridprint: Wi-Fi connected
I (...) gridprint: MQTT connected
I (...) gridprint: t=<epoch s> f=<freq> q=gps periods=<about 50> rejected=<small> queued=0 dropped=0
```

## 5. Host unit tests (no hardware)

The frequency filter, the NMEA time parser and the offline buffer are plain C. Test them on a PC:

```bash
cd node/firmware/test_host
gcc -O2 -Wall -Wextra -I../main test_host.c ../main/freq_calc.c ../main/nmea.c ../main/sample_buffer.c -lm -o test_host
./test_host
```

Expected last line: `ALL HOST TESTS PASSED`.

## 6. Message format

Topic `gridprint/<zone>/<node_id>`, QoS 1, one message per UTC second:

```json
{"zone":"IN","node_id":"node-01","t_utc_s":1790000000,"freq_hz":50.012345,"quality":"gps","gps_lock":true}
```

`quality` is `gps` (PPS-disciplined timing) or `ntp` (SNTP fallback, larger timing uncertainty;
`gps_lock` is then false). The ingest Lambda (`node/ingest/handler.py`) rejects any other value.

## MQTT topic prefix

The Node publishes to `<prefix>/<zone>/<node_id>`. Set "MQTT topic prefix" in `idf.py menuconfig` to the value
of `aws.resource_prefix` in `config/default.yaml` (default `orchard`). `node/provision.py` prints the exact topic.
