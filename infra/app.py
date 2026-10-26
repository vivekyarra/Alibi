#!/usr/bin/env python3
"""GRIDPRINT CDK v2 app. Run from infra/: `npx aws-cdk@2 synth`, or `make deploy` (SPEC 10.6)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gridprint_infra.app import build_app  # noqa: E402

if __name__ == "__main__":
    build_app(account=os.environ.get("CDK_DEFAULT_ACCOUNT")).synth()
