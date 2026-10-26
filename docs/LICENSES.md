# Licenses of models, tools, and libraries

This list implements the "Licenses" control in `SPEC.md` Part 13. "Confirmed" means the license was read from the file named in the "Evidence" column. "To confirm" means the license is the expected one but was not checked against a primary source in this repository.

## Models

| Item | Use | License | Source | Evidence | Status |
|---|---|---|---|---|---|
| YuNet `face_detection_yunet_2023mar.onnx` | S12 face-region check (EXPERIMENTAL) | MIT, copyright 2020 Shiqi Yu | `opencv/opencv_zoo`, `models/face_detection_yunet/` | `models/face_detection_yunet.LICENSE` (MIT text, "Copyright (c) 2020 Shiqi Yu") | Confirmed |
| PP-HumanSeg `human_segmentation_pphumanseg_2023mar.onnx` | S5 foreground masking | Apache-2.0, copyright 2021 PaddlePaddle Authors | `opencv/opencv_zoo`, `models/human_segmentation_pphumanseg/` | `models/human_segmentation_pphumanseg.LICENSE` (Apache License 2.0 text, "Copyright (c) 2021 PaddlePaddle Authors") | Confirmed |

Model file hashes are in `models/*.sha256`.

## Libraries and tools

| Item | Version on the dev host | Use | License | Evidence | Status |
|---|---|---|---|---|---|
| OpenCV 5.0.0 (`opencv-python-headless`) | 5.0.0.93 | Engine vision stages | Apache-2.0 | Package metadata `License: Apache 2.0` | Confirmed (package metadata) |
| PyAV (`av`) | 18.0.0 | Video decode, per-frame PTS | BSD-3-Clause | Package metadata `License-Expression: BSD-3-Clause` | Confirmed (package metadata) |
| FFmpeg libraries bundled in the PyAV wheel; `ffprobe` fallback | libavcodec 62.28.102 | Decoding | LGPL or GPL, depending on the build. The win_amd64 wheel on the dev host reports `LGPL version 3 or later` (`av._core.library_meta`), but its configure line enables `libx264` and `libx265`, which are GPL libraries. | `av._core.library_meta[...]['license']` and `['configuration']` | To confirm for the exact linux/arm64 and linux/amd64 wheels used in the container images |
| NumPy | 2.4.3 | Signal path arithmetic | BSD-3-Clause (the wheel also bundles components under 0BSD, MIT, Zlib, CC0-1.0) | Package metadata `License-Expression` | Confirmed (package metadata) |
| FastAPI | 0.133.1 | API service | MIT | Package metadata | Confirmed (package metadata) |
| Pydantic | 2.13.4 | Schemas | MIT | Package metadata | Confirmed (package metadata) |
| MCP Python SDK (`mcp`) | 1.28.1 | MCP server and client | MIT | Package metadata | Confirmed (package metadata) |
| boto3 | 1.42.89 | AWS access (adapters, agent) | Apache-2.0 | Package metadata | Confirmed (package metadata) |
| Jinja2 | 3.1.6 | Report HTML templates | BSD-3-Clause | Package classifier `BSD License` (variant not stated in metadata) | To confirm (BSD variant) |
| matplotlib | 3.10.0 | Evidence plots; PDF fallback (DECISIONS D-008) | Matplotlib License (PSF-based) | Package metadata: "License agreement for matplotlib versions 1.3.0 and later"; classifier `Python Software Foundation License` | Confirmed (package metadata) |
| WeasyPrint | not installed on the dev host | Report PDF | BSD-3-Clause | — | To confirm |

Versions in this table are the versions installed in the development `.venv` (command below). `uv.lock` is the source of truth for CI and containers.

Before the final check, confirm each "To confirm" row by reading the license metadata of the installed package, for example:

```bash
.venv/Scripts/python -c "import importlib.metadata as m; d=m.metadata('numpy'); print(d.get('License'), d.get('License-Expression'))"
```

Record the result here and change the status to "Confirmed". Package metadata is a secondary source; for redistribution, also read the license file inside each wheel.

## Datasets and generated media

| Item | License | Status |
|---|---|---|
| NESO System Frequency data (zone GB) | NESO Open Data Licence | To confirm on download (see `docs/VERIFICATION.md` V8) |
| Face-swap tool for H7 composites | Record at selection time | Not chosen yet (see `eval/FACE_COMPOSITES.md`) |
| Public video generator for synthetic room videos (SPEC 11.3) | Record tool, prompt, license, date | Not chosen yet |
