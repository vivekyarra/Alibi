---
title: GRIDPRINT
---

# GRIDPRINT

GRIDPRINT checks whether a video is real by reading the power-grid frequency from the flicker of the lights in
the room.

Mains-powered lights flicker at twice the grid frequency. A phone camera's rolling shutter reads the sensor one row
at a time, so the flicker becomes faint horizontal bands. GRIDPRINT measures the bands with OpenCV 5, rebuilds the
grid-frequency track (electric network frequency, ENF) and matches it against reference logs of the real grid.

It returns one of three verdicts:

- **VERIFIED** — a grid signal is present, matches the reference log at one time, and shows no unexplained break.
- **CONTRADICTED** — a grid signal is present and conflicts with the claim or shows an internal break. A human
  reviewer must approve this verdict before the report is final.
- **INCONCLUSIVE** — no usable signal, no reference coverage, or no unique match. A missing signal is never
  evidence that a video is fake.

## Read more

- [Technical report](TECHNICAL_REPORT.md)
- [Architecture](ARCHITECTURE.md)
- [Judge guide](JUDGE_GUIDE.md)
- [Responsible use](RESPONSIBLE_USE.md)
- [Progress and evidence](PROGRESS.md)
- [Source code on GitHub](https://github.com/vivekyarra/Alibi)
