# GRIDPRINT Node — Schematic

Read `SAFETY.md` first. Everything on this page is on the **low-voltage side** of a certified plug-in
AC-to-AC adapter. Nothing here connects to mains.

## 1. Zero-crossing input

```
   Certified plug-in AC-to-AC adapter (T1), 9 V AC output
   ======================================================
        lead A                      lead B
          |                           |
         J1 (barrel jack, tip)       J1 (sleeve)
          |                           |
         F1  PTC 0.1 A                |
          |                           |
         R1  220k                     |
          |                           |
          +------ node S -------------+---------------- VBIAS
          |       |    |              |                   ^
          |      C1   R2 10k ---------+                   |
          |     10nF   (S to VBIAS)                        |
          |       |                                       |
          |     VBIAS                                     |
          |                                               |
          +-- D1 BAT85 (anode S, cathode 3V3)             |
          +-- D2 BAT85 (anode GND, cathode S)             |
          |                                               |
         R5 10k                                           |
          |                                               |
          +------------------ IN+ (U3A pin 3)             |
          |                                               |
         R6 1M (IN+ to OUT, positive feedback)            |
          |                                               |
   VBIAS ------------------- IN- (U3A pin 2)              |
                                                          |
   U3A OUT (pin 1) --+-- R7 10k -- 3V3                    |
                     |                                    |
                     +------------------ ESP32 GPIO 27 (ZC input)
   U3 pin 8 (V+) = 5V (from ESP32 board 5V pin), C4 100nF to GND
   U3 pin 4 (GND) = GND.  Unused half U3B: pins 5 and 6 to GND, pin 7 open.

   Bias divider:
   3V3 --- R3 10k ---+--- R4 10k --- GND
                     |
                   VBIAS (1.65 V)  --- C2 10uF to GND, C3 100nF to GND
```

Notes:
- Lead B of the adapter connects to VBIAS. Lead A goes through F1 and R1 to node S. R2 connects node S
  to VBIAS. So node S = VBIAS + v_ac × 10 k / 230 k.
- With 9 V AC nominal (12.7 V peak) node S swings about ±0.55 V around 1.65 V. With 18 V peak (light
  load, worst case in the design) it swings about ±0.78 V: 0.87 V to 2.43 V. These values come from
  the divider ratio 10/230.
- The LM393 runs from 5 V. Its common-mode input range is 0 V to (V+ − 1.5 V) = 3.5 V, so both inputs
  stay in range.
- The LM393 output is open-collector. R7 pulls it up to **3.3 V**, so the ESP32 never sees 5 V.
- R5 and R6 give hysteresis of about 3.3 V × 10 k / 1 M ≈ 33 mV at node S. This stops multiple edges
  from noise near the crossing. The hysteresis delays the edge by the same amount every cycle, so the
  period (and the frequency) does not change.
- C1 with R1 ∥ R2 (about 9.6 kΩ) is a low-pass filter at about 1.7 kHz. It reduces harmonics and
  noise. Its delay is the same every cycle.
- The firmware uses one edge per cycle (rising edge on GPIO 27).

## 2. GPS

```
   GPS module (U2)                ESP32 DevKitC (U1)
   VIN  ------------------------- 5V
   GND  ------------------------- GND
   TX   ------------------------- GPIO 16 (UART2 RX)
   RX   ------------------------- GPIO 17 (UART2 TX)
   PPS  ---- R8 330R ------------ GPIO 26 (PPS input)
   C5 100nF from VIN to GND, close to the GPS module
```

- The GPS logic level must be 3.3 V. The Adafruit Ultimate GPS uses 3.3 V logic. Check this for any
  other module.
- The firmware never reads, stores or sends the GPS position. It reads only UTC date and time from the
  RMC sentence (rule R4).

## 3. Power

```
   Certified USB supply 5 V --- USB cable --- ESP32 DevKitC USB connector
   ESP32 DevKitC 5V pin --> LM393 V+ (pin 8), GPS VIN
   ESP32 DevKitC 3V3 pin --> R3 (bias divider), R7 (pull-up), D1 cathode
   All GND pins connected together.
```

## 4. Pin summary (firmware defaults, change in `idf.py menuconfig`)

| Signal | ESP32 GPIO | Kconfig option |
|---|---|---|
| Zero crossing | 27 | `GRIDPRINT_ZC_GPIO` |
| GPS PPS | 26 | `GRIDPRINT_PPS_GPIO` |
| GPS TX → ESP32 RX | 16 | `GRIDPRINT_GPS_RX_GPIO` |
| ESP32 TX → GPS RX | 17 | `GRIDPRINT_GPS_TX_GPIO` |

GPIO 16 and 17 are free on ESP32-WROOM modules. On ESP32-WROVER modules they connect to PSRAM; choose
other pins there.
