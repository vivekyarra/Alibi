"""Build the GRIDPRINT CDK app (all stacks in the region from config/default.yaml)."""

from __future__ import annotations

from pathlib import Path

import aws_cdk as cdk

from . import config as config_mod
from .ai import AiStack
from .api import ApiStack
from .auth import AuthStack
from .bench_images import BenchImagesStack
from .compute import ComputeStack
from .data import DataStack
from .iot import IotStack
from .network import NetworkStack
from .observability import ObservabilityStack
from .storage import StorageStack
from .web import WebStack


def build_app(account: str | None = None, config_dir: Path | None = None,
              outdir: str | None = None, context: dict | None = None) -> cdk.App:
    cfg = config_mod.load(config_dir or config_mod.CONFIG_DIR)
    app = cdk.App(outdir=outdir, context=context) if outdir or context else cdk.App()
    env = cdk.Environment(account=account, region=cfg.region)
    p = "Gridprint"

    network = NetworkStack(app, f"{p}Network", env=env)
    storage = StorageStack(app, f"{p}Storage", cfg=cfg, env=env)
    data = DataStack(app, f"{p}Data", env=env)
    ai = AiStack(app, f"{p}Ai", cfg=cfg, env=env)
    auth = AuthStack(app, f"{p}Auth", env=env)
    compute = ComputeStack(app, f"{p}Compute", cfg=cfg, vpc=network.vpc, storage=storage, data=data, ai=ai,
                           auth=auth, env=env)
    api = ApiStack(app, f"{p}Api", cfg=cfg, vpc=network.vpc, storage=storage, data=data, compute=compute,
                   auth=auth, env=env)
    iot = IotStack(app, f"{p}Iot", data=data, env=env)
    WebStack(app, f"{p}Web", cfg=cfg, api=api, storage=storage, env=env)
    ObservabilityStack(app, f"{p}Observability", cfg=cfg, compute=compute, api=api, iot=iot, env=env)

    if str(app.node.try_get_context("bench")).lower() == "true":
        BenchImagesStack(app, f"{p}BenchImages", env=env)

    for key, value in {"project": "gridprint", "managed-by": "cdk"}.items():
        cdk.Tags.of(app).add(key, value)
    return app
