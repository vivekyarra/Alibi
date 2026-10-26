> **WARNING:** Do not connect the Node electronics directly to mains voltage. Use only a certified plug-in AC-to-AC adapter. Mains voltage can kill.

# GRIDPRINT Node — Safety

This page applies to everyone who builds, installs or moves a GRIDPRINT Node (rule R11, human task H2).
Read all of it before you start.

## 1. The safety design

- The Node measures the grid through a **certified plug-in AC-to-AC adapter**. The adapter is a small
  transformer in a wall-plug case. Its output is low-voltage AC (about 9 V AC).
- The transformer isolates the Node from the mains. The Node electronics only see the low-voltage side.
- No part of the Node circuit board connects to a mains socket, a mains cable or a mains terminal.
- The ESP32 board gets power from a separate certified USB power supply.

## 2. Rules

1. Use only a certified, factory-sealed AC-to-AC adapter with a **low-voltage AC output** (not DC).
   Look for the safety mark for your country on the label (for example UL or ETL in the USA, CE or UKCA
   in Europe and the UK, BIS in India).
2. Do not open the adapter case. Do not repair it.
3. Do not cut the adapter cable to connect it to anything other than the Node input jack.
4. Do not build your own transformer, and do not use a "transformerless" circuit, a capacitor dropper,
   or a resistor divider from mains. These have no isolation.
5. Do not connect any Node wire to a wall socket, a light fitting, a fuse box, an extension lead or a
   mains cable.
6. Unplug the adapter from the wall before you touch the circuit board.
7. Use the Node indoors only, in a dry place. Keep it away from water and from children.
8. If the adapter case is cracked, hot, wet, smells of burning, or makes a buzzing noise that is new,
   unplug it at once and replace it.
9. Use a plastic enclosure. Keep the board inside the enclosure when the adapter is plugged in.
10. Do not leave the Node near flammable materials.

## 3. Voltage limits on the Node side

- Adapter output: about 9 V AC nominal. With a light load, the output can be higher than the label
  value. The circuit is designed for up to 18 V peak on the input jack.
- Do not use an adapter with an output above 12 V AC.
- The comparator and the ESP32 see less than 3.3 V (see `schematic.md`).

## 4. If something goes wrong

- Smoke, heat or a burning smell: unplug the adapter from the wall, then unplug the USB supply. Do
  not touch the board until it is cool.
- The ESP32 resets in a loop or the board gets warm: unplug both supplies and check the wiring
  against `schematic.md`.
- Never "test" mains with the Node or with the multimeter leads used for the Node.

## 5. Who should build it

- A person who can solder and use a multimeter.
- If you are not sure about any step, stop and ask a qualified person.
