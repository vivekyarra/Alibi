> **WARNING:** Do not connect the Node electronics directly to mains voltage. Use only a certified plug-in AC-to-AC adapter. Mains voltage can kill.

# GRIDPRINT Node — Assembly guide

Human task H2. Read `SAFETY.md` completely before you start. Use the parts in `BOM.md` and the circuit
in `schematic.md`.

Keep the AC-to-AC adapter **unplugged from the wall** until step 9.

## 1. Check the parts

1. Check the adapter label. It must say "AC" output (symbol `~`), about 9 V, and show a safety mark.
2. Check that the adapter plug fits the barrel jack J1.
3. Check the resistor values with the multimeter.

## 2. Build the bias divider

1. Solder R3 (10 kΩ) from the 3V3 rail to node VBIAS.
2. Solder R4 (10 kΩ) from node VBIAS to GND.
3. Solder C2 (10 µF) and C3 (100 nF) from VBIAS to GND. Check the polarity of C2 if it is electrolytic.

## 3. Build the input divider

1. Solder F1 from the J1 tip terminal to one end of R1 (220 kΩ).
2. Solder the other end of R1 to node S.
3. Solder R2 (10 kΩ) from node S to VBIAS.
4. Connect the J1 sleeve terminal to VBIAS.
5. Solder C1 (10 nF) from node S to VBIAS.
6. Solder D1 (BAT85): anode to node S, cathode to 3V3.
7. Solder D2 (BAT85): anode to GND, cathode to node S.

## 4. Build the comparator

1. Solder the DIP-8 socket. Do not insert U3 yet.
2. Socket pin 8 to 5V. Socket pin 4 to GND. Solder C4 (100 nF) from pin 8 to pin 4, close to the socket.
3. R5 (10 kΩ) from node S to pin 3 (IN+ A).
4. R6 (1 MΩ) from pin 3 to pin 1 (OUT A).
5. Pin 2 (IN− A) to VBIAS.
6. R7 (10 kΩ) from pin 1 to **3V3** (not 5V).
7. Pins 5 and 6 to GND. Leave pin 7 open.
8. Pin 1 to the header pin for ESP32 GPIO 27.

## 5. Wire the GPS module

1. GPS VIN to 5V, GPS GND to GND. C5 (100 nF) from VIN to GND near the module.
2. GPS TX to ESP32 GPIO 16. GPS RX to ESP32 GPIO 17.
3. GPS PPS through R8 (330 Ω) to ESP32 GPIO 26.

## 6. Power checks (USB only, adapter not connected)

1. Do not insert U3 yet. Plug the ESP32 board into the computer by USB.
2. Measure 3V3 to GND: about 3.3 V.
3. Measure 5V to GND: about 5 V (a little lower is normal through USB).
4. Measure VBIAS to GND: 1.60 V to 1.70 V.
5. Measure node S to GND: about 1.6 V (no AC input yet).
6. Unplug USB. Insert U3 (notch to pin 1). Plug USB again.
7. Measure GPIO 27 to GND: either about 0 V or about 3.3 V. It must never be above 3.4 V.

## 7. Flash the firmware

Follow `../firmware/FLASHING.md`.

## 8. Fit the enclosure

1. Mount the boards on nylon standoffs.
2. Mount J1 in the enclosure wall.
3. Put the GPS module (or its antenna) where it can see the sky through a window.
4. Close the enclosure. The USB cable goes through a grommet.

## 9. First power-up with the adapter

1. Check again that the enclosure is closed and nothing metal touches the board.
2. Plug the adapter into J1 first. Then plug the adapter into the wall socket.
3. Measure AC voltage between node S test point and VBIAS (if you left a test point outside the
   enclosure): about 0.4 V AC on a 9 V adapter (9 V × 10 / 230). Do not open the enclosure for this.
4. Run the self-test in `../SELFTEST.md`.

## 10. Install

1. Place the Node indoors, in a dry place, near a window for GPS.
2. Use a wall socket on the grid zone you set in the firmware (`GRIDPRINT_ZONE`).
3. Keep it running at least 24 h, then run `make node-quality ZONE=<zone> HOURS=24` (see
   `docs/HUMAN_TASKS.md` H2).
