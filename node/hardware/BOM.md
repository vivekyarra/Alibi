# GRIDPRINT Node — Bill of materials

Read `SAFETY.md` first. Prices are not listed (no sourced prices). Example parts are real products. Check
the current datasheet and product page before you buy; specifications can change.

## Core parts

| Ref | Qty | Part type | Required specification | Example part |
|---|---|---|---|---|
| U1 | 1 | ESP32 development board | ESP32 with Wi-Fi, USB-UART, 3.3 V regulator, 5 V pin, GPIO 16, 17, 26, 27 free | Espressif ESP32-DevKitC V4 with ESP32-WROOM-32E module |
| U2 | 1 | GPS module with PPS output | NMEA output at 3.3 V logic, RMC sentence, 1 PPS output pin, 3.3–5 V supply | Adafruit Ultimate GPS Breakout v3 (product 746, MediaTek MT3339). Alternative: a u-blox NEO-M8N board with the TIMEPULSE pin brought out |
| T1 | 1 | Certified plug-in AC-to-AC adapter | Wall-plug transformer, **AC output** 9 V AC nominal (max 12 V AC), 300 mA or more, safety mark for your country, plug type for your country | Any certified 9 V AC-AC wall adapter. OpenEnergyMonitor sells 9 V AC-AC adapters for voltage sensing in several plug types (check model and marks) |
| U3 | 1 | Dual comparator | LM393, open-collector output, 2–36 V supply, DIP-8 | Texas Instruments LM393P or onsemi LM393N |
| PSU | 1 | Certified USB power supply | 5 V DC, 1 A or more, safety mark for your country | Any certified USB phone charger |
| — | 1 | USB cable | Matches the ESP32 board connector (micro-USB on DevKitC V4) | — |

## Signal conditioning

| Ref | Qty | Part type | Value / specification | Purpose |
|---|---|---|---|---|
| R1 | 1 | Metal film resistor, 1 %, 0.25 W | 220 kΩ | Input divider, top |
| R2 | 1 | Metal film resistor, 1 %, 0.25 W | 10 kΩ | Input divider, bottom (to VBIAS) |
| R3, R4 | 2 | Metal film resistor, 1 %, 0.25 W | 10 kΩ | Bias divider 3.3 V → 1.65 V |
| R5 | 1 | Metal film resistor, 1 %, 0.25 W | 10 kΩ | Comparator input resistor (hysteresis) |
| R6 | 1 | Metal film resistor, 1 %, 0.25 W | 1 MΩ | Comparator positive feedback (hysteresis) |
| R7 | 1 | Metal film resistor, 1 %, 0.25 W | 10 kΩ | Comparator output pull-up to 3.3 V |
| R8 | 1 | Metal film resistor, 1 %, 0.25 W | 330 Ω | Series resistor on the PPS line |
| C1 | 1 | Film or C0G ceramic capacitor | 10 nF, 50 V | Low-pass filter (about 1.7 kHz) |
| C2 | 1 | Electrolytic or ceramic capacitor | 10 µF, 16 V | VBIAS decoupling |
| C3, C4, C5 | 3 | Ceramic capacitor | 100 nF, 50 V | Decoupling (VBIAS, LM393 supply, GPS supply) |
| D1, D2 | 2 | Small-signal Schottky diode | BAT85 (DO-35) | Clamp the divider node to GND and 3.3 V |
| F1 | 1 | PTC resettable fuse | 0.1 A hold, 30 V or more | Limits current if the adapter side is short-circuited |
| J1 | 1 | Panel-mount DC barrel jack | Matches the adapter plug (often 2.1 mm or 2.5 mm), 1 A or more | Adapter input |

## Mechanical

| Qty | Part type | Specification |
|---|---|---|
| 1 | Plastic (ABS) enclosure | Fits the ESP32 board, GPS board and a 50 × 70 mm perfboard. Example: Hammond 1591 series ABS box (check inside size) |
| 1 | Perfboard or stripboard | About 50 × 70 mm |
| 1 set | Pin headers and female headers | 2.54 mm pitch, to plug in the ESP32 and GPS boards |
| 1 | DIP-8 socket | For U3 |
| 4 | Nylon standoffs and screws | M3 |
| — | Hook-up wire | 24 AWG solid core, two or more colours |
| 1 | Cable gland or grommet | For the USB cable |
| 1 | Optional external active GPS antenna | 3–5 V active patch antenna with a cable and the adapter for the GPS board's antenna connector, if the Node cannot see the sky through a window |

## Tools

- Soldering iron and solder, side cutters, wire strippers.
- Digital multimeter with DC and AC voltage ranges.
- Optional: oscilloscope (for `SELFTEST.md` steps 3 and 4).
- A computer with USB, for flashing (see `../firmware/FLASHING.md`).
