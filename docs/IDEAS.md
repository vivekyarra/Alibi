# Ideas (not in SPEC — not built)

Ideas that are outside SPEC.md go here and are not implemented (SPEC 0.3).

- Capture band meter for 60 Hz zones at 30 fps: the 120 Hz bands barely move between frames, so a running-mean meter reads low. A spatial band estimator that uses the readout time could fix this (from the Capture build notes).
- The same 60 Hz / 30 fps case limits the engine: the temporal mean keeps the static bands. A capture mode at a frame rate whose alias is not near 0 Hz would help (not in SPEC; not built).
- COOL Docker Marketplace product as the worker base image instead of mounting host libraries (infra notes; not checked).
